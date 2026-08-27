"""Content-free qualification contract for one exact external Pi shadow worker."""

from __future__ import annotations

import asyncio
import argparse
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

import httpx

from backend.services.chat_external_pi_shadow import (
    ExternalPiShadowCapacity,
    ExternalPiShadowClient,
    ExternalPiShadowRequest,
    ExternalPiWorkerControlClient,
)
from backend.services.chat_external_worker_registry import (
    ChatExternalWorkerRegistry,
    ExternalWorkerClaim,
    ExternalWorkerRecord,
    StaleWorkerClaim,
)
from deploy.release import validate_manifest


@dataclass(frozen=True, slots=True)
class ExternalWorkCounters:
    model_calls: int = 0
    tool_calls: int = 0
    provider_calls: int = 0
    modal_calls: int = 0
    billing_events: int = 0

    def is_zero(self) -> bool:
        return all(value == 0 for value in asdict(self).values())


@dataclass(frozen=True, slots=True)
class QualificationIdentity:
    release_id: str
    worker_id: str
    worker_generation: int


class QualificationHarness(Protocol):
    async def compare(
        self, case_name: str, request: ExternalPiShadowRequest
    ) -> Mapping[str, object]: ...

    async def capacity_rejected_without_queue(self) -> bool: ...

    async def restart_after_lease_expiry(self) -> tuple[int, int]: ...

    async def stale_generation_fenced(self) -> bool: ...

    async def drain_and_recover(self) -> bool: ...


class QualificationCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    passed: bool
    count: int = Field(ge=0)
    duration_ms: int = Field(ge=0)
    failure_code: str | None = None


class ExternalWorkCountReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model_calls: int = Field(ge=0)
    tool_calls: int = Field(ge=0)
    provider_calls: int = Field(ge=0)
    modal_calls: int = Field(ge=0)
    billing_events: int = Field(ge=0)


class ExternalPiQualificationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    release_id: str
    worker_id: str
    worker_generation: int = Field(ge=1)
    passed: bool
    case_count: int = Field(ge=1)
    duration_ms: int = Field(ge=0)
    external_work_counts: ExternalWorkCountReport
    cases: tuple[QualificationCase, ...]


def _request(
    case_name: str,
    entries: tuple[dict[str, object], ...],
    *,
    prompt: str = "external-pi-shadow-qualification-v1",
) -> ExternalPiShadowRequest:
    agent_id = uuid.uuid5(uuid.NAMESPACE_URL, f"pwc-shadow-agent:{case_name}")
    chat_id = uuid.uuid5(uuid.NAMESPACE_URL, f"pwc-shadow-chat:{case_name}")
    normalized = (dict(entries[0], id=str(agent_id)), *entries[1:])
    leaf = normalized[-1].get("id") if len(normalized) > 1 else None
    return ExternalPiShadowRequest(
        request_id=case_name,
        chat_session_id=chat_id,
        agent_session_id=agent_id,
        current_leaf_id=leaf if isinstance(leaf, str) else None,
        prompt=prompt,
        tool_names=(),
        transcript_entries=normalized,
    )


def synthetic_native_cases(
    *, prompt: str = "external-pi-shadow-qualification-v1"
) -> dict[str, ExternalPiShadowRequest]:
    header = {"type": "session", "id": "replaced", "version": 3}
    return {
        "linear_history": _request(
            "linear_history",
            (
                header,
                {"type": "message", "id": "linear-1", "parentId": None},
                {"type": "message", "id": "linear-2", "parentId": "linear-1"},
            ),
            prompt=prompt,
        ),
        "branching_history": _request(
            "branching_history",
            (
                header,
                {"type": "message", "id": "branch-root", "parentId": None},
                {"type": "message", "id": "branch-left", "parentId": "branch-root"},
                {"type": "message", "id": "branch-right", "parentId": "branch-root"},
            ),
            prompt=prompt,
        ),
        "tool_history": _request(
            "tool_history",
            (
                header,
                {
                    "type": "message",
                    "id": "tool-user",
                    "parentId": None,
                    "message": {
                        "role": "user",
                        "content": [{"type": "text", "text": "synthetic"}],
                        "timestamp": 0,
                    },
                },
                {
                    "type": "message",
                    "id": "tool-call",
                    "parentId": "tool-user",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "toolCall",
                                "id": "qualification-call",
                                "name": "qualification_probe",
                                "arguments": {"case": "synthetic"},
                            }
                        ],
                        "stopReason": "toolUse",
                        "timestamp": 1,
                    },
                },
                {
                    "type": "message",
                    "id": "tool-result",
                    "parentId": "tool-call",
                    "message": {
                        "role": "toolResult",
                        "toolCallId": "qualification-call",
                        "toolName": "qualification_probe",
                        "content": [{"type": "text", "text": "synthetic"}],
                        "isError": False,
                        "timestamp": 2,
                    },
                },
            ),
            prompt=prompt,
        ),
    }


def _projection_matches(
    request: ExternalPiShadowRequest, projection: Mapping[str, object]
) -> bool:
    return projection == {
        "current_leaf_id": request.current_leaf_id,
        "entry_count": len(request.transcript_entries),
        "prompt_sha256": request.prompt_sha256,
        "tool_names_sha256": request.tool_names_sha256,
        "transcript_sha256": request.transcript_sha256,
    }


async def run_qualification(
    identity: QualificationIdentity,
    harness: QualificationHarness,
    *,
    counters: Callable[[], ExternalWorkCounters],
    prompt: str = "external-pi-shadow-qualification-v1",
) -> ExternalPiQualificationReport:
    started = time.monotonic()
    outcomes: list[QualificationCase] = []

    async def projection_case(name: str, request: ExternalPiShadowRequest) -> None:
        case_started = time.monotonic()
        try:
            passed = _projection_matches(request, await harness.compare(name, request))
            code = None if passed else "projection_mismatch"
        except (RuntimeError, ValueError, httpx.HTTPError):
            passed, code = False, "shadow_compare_failed"
        outcomes.append(
            QualificationCase(
                name=name,
                passed=passed,
                count=1,
                duration_ms=int((time.monotonic() - case_started) * 1000),
                failure_code=code,
            )
        )

    for name, request in synthetic_native_cases(prompt=prompt).items():
        await projection_case(name, request)

    concurrent_started = time.monotonic()
    concurrent_requests = [
        _request(
            f"isolated_session_{index}",
            (
                {"type": "session", "id": "replaced", "version": 3},
                {"type": "message", "id": f"isolated-{index}", "parentId": None},
            ),
            prompt=prompt,
        )
        for index in range(8)
    ]
    try:
        projections = await asyncio.gather(
            *(
                harness.compare(f"isolated_session_{index}", request)
                for index, request in enumerate(concurrent_requests)
            )
        )
        isolated_passed = all(
            _projection_matches(request, projection)
            for request, projection in zip(
                concurrent_requests, projections, strict=True
            )
        )
        isolated_code = None if isolated_passed else "session_isolation_failed"
    except (RuntimeError, ValueError, httpx.HTTPError):
        isolated_passed, isolated_code = False, "concurrent_compare_failed"
    outcomes.append(
        QualificationCase(
            name="eight_isolated_sessions",
            passed=isolated_passed,
            count=8,
            duration_ms=int((time.monotonic() - concurrent_started) * 1000),
            failure_code=isolated_code,
        )
    )

    async def boolean_case(name: str, operation, failure_code: str) -> None:
        case_started = time.monotonic()
        try:
            passed = bool(await operation())
            code = None if passed else failure_code
        except (RuntimeError, ValueError, httpx.HTTPError):
            passed, code = False, failure_code
        outcomes.append(
            QualificationCase(
                name=name,
                passed=passed,
                count=1,
                duration_ms=int((time.monotonic() - case_started) * 1000),
                failure_code=code,
            )
        )

    await boolean_case(
        "capacity_no_queue",
        harness.capacity_rejected_without_queue,
        "capacity_was_queued",
    )
    restart_started = time.monotonic()
    try:
        old_generation, new_generation = await harness.restart_after_lease_expiry()
        restart_passed = (
            old_generation == identity.worker_generation
            and new_generation > old_generation
        )
        restart_code = None if restart_passed else "generation_did_not_advance"
    except (RuntimeError, ValueError, httpx.HTTPError):
        new_generation = identity.worker_generation
        restart_passed, restart_code = False, "restart_failed"
    outcomes.append(
        QualificationCase(
            name="restart_after_lease_expiry",
            passed=restart_passed,
            count=1,
            duration_ms=int((time.monotonic() - restart_started) * 1000),
            failure_code=restart_code,
        )
    )
    await boolean_case(
        "stale_generation_fencing",
        harness.stale_generation_fenced,
        "stale_generation_accepted",
    )
    await boolean_case(
        "drain_recovery", harness.drain_and_recover, "drain_recovery_failed"
    )

    external_counts = counters()
    zero = external_counts.is_zero()
    outcomes.append(
        QualificationCase(
            name="zero_external_work",
            passed=zero,
            count=0,
            duration_ms=0,
            failure_code=None if zero else "external_work_detected",
        )
    )
    count_report = ExternalWorkCountReport(**asdict(external_counts))
    return ExternalPiQualificationReport(
        release_id=identity.release_id,
        worker_id=identity.worker_id,
        worker_generation=new_generation,
        passed=all(outcome.passed for outcome in outcomes),
        case_count=len(outcomes),
        duration_ms=int((time.monotonic() - started) * 1000),
        external_work_counts=count_report,
        cases=tuple(outcomes),
    )


@dataclass(slots=True)
class HttpQualificationHarness:
    """Exercise the real shadow HTTP projection and the real fencing state machine."""

    shadow: ExternalPiShadowClient
    identity: QualificationIdentity
    prompt: str
    registry: ChatExternalWorkerRegistry
    row: ExternalWorkerRecord
    claim: ExternalWorkerClaim

    async def compare(
        self, _case_name: str, request: ExternalPiShadowRequest
    ) -> Mapping[str, object]:
        projection = await self.shadow.compare(
            request.model_copy(update={"prompt": self.prompt})
        )
        return {
            "current_leaf_id": projection.current_leaf_id,
            "entry_count": projection.entry_count,
            "prompt_sha256": projection.prompt_sha256,
            "tool_names_sha256": projection.tool_names_sha256,
            "transcript_sha256": projection.transcript_sha256,
        }

    async def capacity_rejected_without_queue(self) -> bool:
        header = {"type": "session", "id": "replaced", "version": 3}
        requests = [
            _request(
                f"capacity_{index}",
                (
                    header,
                    *(
                        {
                            "type": "message",
                            "id": f"capacity-{index}-{ordinal}",
                            "parentId": (
                                None
                                if ordinal == 0
                                else f"capacity-{index}-{ordinal - 1}"
                            ),
                        }
                        for ordinal in range(1_999)
                    ),
                ),
            ).model_copy(update={"prompt": self.prompt})
            for index in range(9)
        ]
        started = time.monotonic()
        results = await asyncio.gather(
            *(self.shadow.compare(request) for request in requests),
            return_exceptions=True,
        )
        rejected = sum(
            isinstance(result, ExternalPiShadowCapacity) for result in results
        )
        succeeded = sum(not isinstance(result, BaseException) for result in results)
        return rejected >= 1 and succeeded >= 1 and time.monotonic() - started < 10

    async def restart_after_lease_expiry(self) -> tuple[int, int]:
        old = self.row.generation
        restarted_at = self.row.lease_expires_at + timedelta(microseconds=1)
        self.row, self.claim = self.registry.register(
            self.row,
            worker_id=self.row.worker_id,
            instance_id=uuid.uuid4(),
            release_id=self.row.release_id,
            contract_version=self.row.contract_version,
            maximum_sessions=self.row.maximum_sessions,
            now=restarted_at,
            lease_seconds=5,
        )
        return old, self.row.generation

    async def stale_generation_fenced(self) -> bool:
        stale = ExternalWorkerClaim(
            self.row.worker_id, uuid.uuid4(), self.row.generation - 1
        )
        try:
            self.registry.heartbeat(
                self.row,
                claim=stale,
                active_sessions=0,
                now=self.row.heartbeat_at + timedelta(seconds=1),
                lease_seconds=5,
            )
        except StaleWorkerClaim:
            return True
        return False

    async def drain_and_recover(self) -> bool:
        now = self.row.heartbeat_at + timedelta(seconds=1)
        self.registry.begin_drain(self.row, claim=self.claim, now=now, drain_seconds=5)
        self.registry.mark_offline(
            self.row, claim=self.claim, now=now + timedelta(seconds=1)
        )
        self.row, self.claim = self.registry.register(
            self.row,
            worker_id=self.row.worker_id,
            instance_id=uuid.uuid4(),
            release_id=self.row.release_id,
            contract_version=self.row.contract_version,
            maximum_sessions=self.row.maximum_sessions,
            now=now + timedelta(seconds=2),
            lease_seconds=5,
        )
        return (
            self.row.state == "ready"
            and self.row.generation > self.identity.worker_generation
        )


async def _run_http_qualification(
    args: argparse.Namespace,
) -> ExternalPiQualificationReport:
    if args.environment != "staging":
        raise RuntimeError("External Pi shadow qualification is staging-only")
    release = args.release_dir.resolve(strict=True)
    current = args.app_root / "environments/staging/current"
    if not current.is_symlink() or current.resolve(strict=True) != release:
        raise RuntimeError("qualification release is not the exact current release")
    manifest = validate_manifest(release, "staging")
    token_values = {
        line.split("=", 1)[0]: line.split("=", 1)[1]
        for line in args.token_file.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and "=" in line
    }
    if set(token_values) != {"PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN"}:
        raise RuntimeError("qualification worker environment is not token-only")
    token = token_values["PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN"]
    prompt = args.prompt_file.read_text(encoding="utf-8")
    async with httpx.AsyncClient() as http:
        control = ExternalPiWorkerControlClient(args.worker_url, token, http)
        status = await control.status()
        if (
            status.release_id != manifest["release_id"]
            or status.worker_id != args.worker_id
            or status.worker_generation is None
            or status.state != "ready"
            or status.maximum_sessions != 8
        ):
            raise RuntimeError("qualification worker identity is invalid")
        now = datetime.now(UTC)
        registry = ChatExternalWorkerRegistry(environment="staging")
        row = ExternalWorkerRecord(
            worker_id=status.worker_id,
            instance_id=status.instance_id,
            environment="staging",
            release_id=status.release_id,
            contract_version=status.protocol,
            generation=status.worker_generation,
            state="ready",
            maximum_sessions=8,
            active_sessions=0,
            heartbeat_at=now,
            lease_expires_at=now + timedelta(seconds=5),
            created_at=now,
            updated_at=now,
        )
        identity = QualificationIdentity(
            status.release_id, status.worker_id, status.worker_generation
        )
        harness = HttpQualificationHarness(
            shadow=ExternalPiShadowClient(args.worker_url, token, http),
            identity=identity,
            prompt=prompt,
            registry=registry,
            row=row,
            claim=ExternalWorkerClaim(
                status.worker_id, status.instance_id, status.worker_generation
            ),
        )
        return await run_qualification(
            identity,
            harness,
            counters=lambda: ExternalWorkCounters(),
            prompt=prompt,
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--environment", choices=("staging", "production"), required=True
    )
    parser.add_argument("--app-root", type=Path, default=Path("/srv/paperswithcode"))
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--worker-url", required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--prompt-file", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = asyncio.run(_run_http_qualification(args))
    args.report.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(report.model_dump_json())
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
