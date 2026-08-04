#!/usr/bin/env python3
"""Run sanitized, authenticated blank-pool qualification on staging."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics
import time
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import NoResultFound

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.models.database import (
    ChatSandboxComputeInterval,
    ChatSandboxLease,
    ChatSandboxPool,
    ChatSession,
    ChatTurnLatency,
)
from backend.routers.auth import _encode_legacy_session
from backend.scripts.qualify_chat_sandbox import settings_for_release
from backend.scripts.staging_qualification_http import client as staging_client
from backend.services.chat_latency_service import ChatLatencyService
from backend.services.hf_inference_billing_service import COOKIE_NAME, encrypt_token
from backend.services.chat_sandbox_service import SandboxSessionManager

CONFIRMATION = "QUALIFY_STAGING_CHAT_POOL"


@dataclass(frozen=True)
class PoolSample:
    request_id: str | None
    acquisition_outcome: str | None
    pool_lookup_ms: int | None
    sdk_dispatch_ms: int | None
    first_delta_ms: int | None
    total_ms: int | None
    estimated_active_cost_usd: float | None
    continuous_pool_interval: bool
    cleanup_confirmed: bool
    terminal_status: str
    error_code: str | None


def percentile(values: list[int], quantile: float) -> int:
    if not values:
        raise ValueError("At least one value is required")
    ordered = sorted(values)
    return ordered[max(0, math.ceil(quantile * len(ordered)) - 1)]


def summarize(samples: list[PoolSample]) -> dict[str, Any]:
    def metric(name: str) -> dict[str, int] | None:
        values = [
            value for sample in samples if (value := getattr(sample, name)) is not None
        ]
        if not values:
            return None
        return {
            "count": len(values),
            "p50": round(statistics.median(values)),
            "p95": percentile(values, 0.95),
            "max": max(values),
        }

    return {
        "samples": len(samples),
        "complete": sum(sample.terminal_status == "complete" for sample in samples),
        "pool_hits": sum(
            sample.acquisition_outcome == "pool_hit" for sample in samples
        ),
        "pool_misses": sum(
            sample.acquisition_outcome == "pool_miss" for sample in samples
        ),
        "continuous_pool_intervals": sum(
            sample.continuous_pool_interval for sample in samples
        ),
        "cleanup_confirmed": sum(sample.cleanup_confirmed for sample in samples),
        "pool_lookup_ms": metric("pool_lookup_ms"),
        "sdk_dispatch_ms": metric("sdk_dispatch_ms"),
        "first_delta_ms": metric("first_delta_ms"),
        "total_ms": metric("total_ms"),
        "estimated_active_cost_usd": {
            "total": round(
                sum(sample.estimated_active_cost_usd or 0 for sample in samples),
                8,
            ),
            "per_completed_turn": round(
                sum(sample.estimated_active_cost_usd or 0 for sample in samples)
                / max(
                    1,
                    sum(sample.terminal_status == "complete" for sample in samples),
                ),
                8,
            ),
        },
    }


class PoolQualification:
    def __init__(
        self,
        *,
        settings,
        billing_settings,
        samples: int,
        blank_timeout: float,
    ):
        self.settings = settings
        self.billing_settings = billing_settings
        self.samples = samples
        self.blank_timeout = blank_timeout
        self.started_at = datetime.now(UTC)
        self.run_id = uuid.uuid4().hex[:12]

    def validate(self, *, cpu: float, memory_mib: int) -> None:
        if self.settings.environment != "staging":
            raise ValueError("Pool qualification requires staging")
        if not self.settings.chat_persistent_worker_enabled:
            raise ValueError("Persistent workers must be enabled")
        if not self.settings.chat_blank_pool_enabled:
            raise ValueError("The blank pool must be enabled")
        if self.settings.chat_sandbox_cpu != cpu:
            raise ValueError("Configured CPU request does not match the candidate")
        if self.settings.chat_sandbox_memory_mib != memory_mib:
            raise ValueError("Configured memory request does not match the candidate")

    def _compatible_blank_count(self) -> int:
        cpu_limit = (
            self.settings.chat_sandbox_cpu_limit or self.settings.chat_sandbox_cpu
        )
        memory_limit = (
            self.settings.chat_sandbox_memory_limit_mib
            or self.settings.chat_sandbox_memory_mib
        )
        with db_manager.session_local() as db:
            return (
                db.scalar(
                    select(func.count())
                    .select_from(ChatSandboxPool)
                    .where(
                        ChatSandboxPool.state == "blank_ready",
                        ChatSandboxPool.image_version
                        == self.settings.chat_modal_image_version,
                        ChatSandboxPool.worker_contract_version
                        == self.settings.chat_worker_contract_version,
                        ChatSandboxPool.app_release_id == self.settings.release_id,
                        ChatSandboxPool.cpu_request == self.settings.chat_sandbox_cpu,
                        ChatSandboxPool.cpu_limit == cpu_limit,
                        ChatSandboxPool.memory_request_mib
                        == self.settings.chat_sandbox_memory_mib,
                        ChatSandboxPool.memory_limit_mib == memory_limit,
                    )
                )
                or 0
            )

    async def _wait_for_blank(self) -> None:
        deadline = time.monotonic() + self.blank_timeout
        while time.monotonic() < deadline:
            if self._compatible_blank_count() > 0:
                return
            await asyncio.sleep(0.25)
        raise TimeoutError("Compatible blank worker was not replenished")

    def _latency(
        self, request_id: str, error_code: str | None
    ) -> tuple[PoolSample, uuid.UUID, uuid.UUID | None]:
        with db_manager.session_local() as db:
            row = db.execute(
                select(ChatTurnLatency).where(
                    ChatTurnLatency.request_id == uuid.UUID(request_id)
                )
            ).scalar_one()
            intervals = list(
                db.scalars(
                    select(ChatSandboxComputeInterval).where(
                        ChatSandboxComputeInterval.chat_session_id
                        == row.chat_session_id
                    )
                )
            )
            lease = db.get(ChatSandboxLease, row.chat_session_id)
            interval = intervals[0] if len(intervals) == 1 else None
            continuous = bool(
                interval is not None
                and lease is not None
                and interval.origin == "blank_pool"
                and interval.modal_sandbox_id is not None
                and interval.modal_sandbox_id == lease.modal_sandbox_id
                and interval.provider_created_at is not None
                and interval.claimed_at is not None
                and interval.reserved_at <= interval.provider_created_at
                and interval.provider_created_at <= interval.claimed_at
                and interval.terminal_at is None
            )
            return (
                PoolSample(
                    request_id=request_id,
                    acquisition_outcome=row.acquisition_outcome,
                    pool_lookup_ms=row.pool_lookup_completed_ms,
                    sdk_dispatch_ms=row.sdk_query_dispatched_ms,
                    first_delta_ms=row.first_application_sse_delta_ms,
                    total_ms=row.total_ms,
                    estimated_active_cost_usd=(
                        float(row.estimated_active_cost_usd)
                        if row.estimated_active_cost_usd is not None
                        else None
                    ),
                    continuous_pool_interval=continuous,
                    cleanup_confirmed=False,
                    terminal_status=row.terminal_status,
                    error_code=error_code,
                ),
                row.chat_session_id,
                interval.id if interval is not None else None,
            )

    def _session_id(self, subject: str) -> uuid.UUID | None:
        with db_manager.session_local() as db:
            return db.scalar(
                select(ChatSession.id).where(ChatSession.hf_user_id == subject)
            )

    def _cleanup_confirmed(
        self, session_id: uuid.UUID, interval_id: uuid.UUID | None
    ) -> bool:
        if interval_id is None:
            return False
        with db_manager.session_local() as db:
            lease = db.get(ChatSandboxLease, session_id)
            interval = db.get(ChatSandboxComputeInterval, interval_id)
            return bool(
                lease is not None
                and lease.state == "terminated"
                and lease.modal_sandbox_id is None
                and interval is not None
                and interval.terminal_at is not None
            )

    async def _turn(self, index: int) -> PoolSample:
        subject = f"pool-qualification-{self.run_id}-{index}"
        token = _encode_legacy_session({"sub": subject, "username": subject})
        billing = encrypt_token(
            self.billing_settings.hf_token,
            subject,
            self.billing_settings,
        )
        payload = {
            "message": "Reply with a concise acknowledgement.",
            "client_message_id": str(uuid.uuid4()),
        }
        request_id: str | None = None
        terminal = "error"
        error_code: str | None = None
        async with (
            staging_client(
                timeout=240,
                cookies={
                    self.settings.session_cookie_name: token,
                    COOKIE_NAME: billing,
                },
            ) as client,
            client.stream(
                "POST",
                "/api/v1/chat/stream",
                json=payload,
            ) as response,
        ):
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                event = json.loads(line[6:])
                if event.get("type") == "stream_start":
                    request_id = str(event["request_id"])
                if event.get("type") in {"done", "cancelled", "error"}:
                    terminal = str(event["type"])
                    error_code = str(event.get("code")) if event.get("code") else None
        sample = PoolSample(
            request_id,
            None,
            None,
            None,
            None,
            None,
            None,
            False,
            False,
            terminal,
            error_code,
        )
        session_id: uuid.UUID | None = None
        interval_id: uuid.UUID | None = None
        if request_id is not None:
            for _ in range(40):
                try:
                    sample, session_id, interval_id = self._latency(
                        request_id, error_code
                    )
                    break
                except NoResultFound:
                    await asyncio.sleep(0.05)
        session_id = session_id or self._session_id(subject)
        if session_id is not None:
            await SandboxSessionManager(self.settings).terminate(session_id)
            sample = replace(
                sample,
                cleanup_confirmed=self._cleanup_confirmed(session_id, interval_id),
            )
        return sample

    def _blank_starts(self) -> int:
        with db_manager.session_local() as db:
            return (
                db.scalar(
                    select(func.count())
                    .select_from(ChatSandboxPool)
                    .where(
                        ChatSandboxPool.created_at >= self.started_at,
                        ChatSandboxPool.app_release_id == self.settings.release_id,
                        ChatSandboxPool.cpu_request == self.settings.chat_sandbox_cpu,
                        ChatSandboxPool.memory_request_mib
                        == self.settings.chat_sandbox_memory_mib,
                    )
                )
                or 0
            )

    async def run(self) -> tuple[list[PoolSample], int]:
        landed: list[PoolSample] = []
        for index in range(self.samples):
            await self._wait_for_blank()
            landed.append(await self._turn(index))
        await self._wait_for_blank()
        return landed, self._blank_starts()

    def mark_samples(self, samples: list[PoolSample]) -> int:
        request_ids = [sample.request_id for sample in samples if sample.request_id]
        with db_manager.session_local() as db:
            service = ChatLatencyService(db)
            marked = sum(
                service.mark_qualification(
                    request_id,
                    run_id=self.run_id,
                    scenario="focused_latency",
                )
                for request_id in request_ids
            )
            db.commit()
        return marked


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Qualify authenticated staging blank-pool claims and turns"
    )
    result.add_argument("--samples", type=int, default=100)
    result.add_argument("--candidate-cpu", type=float, required=True)
    result.add_argument("--candidate-memory-mib", type=int, required=True)
    result.add_argument("--blank-timeout", type=float, default=90)
    result.add_argument("--release-dir", type=Path, required=True)
    result.add_argument("--confirm", required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.confirm != CONFIRMATION:
        raise SystemExit(f"--confirm must be {CONFIRMATION}")
    if not 1 <= args.samples <= 200:
        raise SystemExit("--samples must be 1-200")
    environment_settings = get_settings()
    release = settings_for_release(args.release_dir)
    release_settings = environment_settings.model_copy(
        update={
            "release_id": release.release_id,
            "chat_enabled": release.chat_enabled,
            "chat_default_backend": release.chat_default_backend,
            "chat_new_chat_modal_percentage": (release.chat_new_chat_modal_percentage),
            "chat_modal_image_version": release.chat_modal_image_version,
            "chat_pwc_cli_version": release.chat_pwc_cli_version,
            "chat_worker_contract_version": release.chat_worker_contract_version,
            "chat_system_prompt_sha256": release.chat_system_prompt_sha256,
        }
    )
    qualification = PoolQualification(
        settings=release_settings,
        billing_settings=environment_settings,
        samples=args.samples,
        blank_timeout=args.blank_timeout,
    )
    qualification.validate(cpu=args.candidate_cpu, memory_mib=args.candidate_memory_mib)
    samples, blank_starts = asyncio.run(qualification.run())
    marked = qualification.mark_samples(samples)
    summary = summarize(samples)
    passed = (
        summary["complete"] == args.samples
        and summary["pool_hits"] == args.samples
        and summary["continuous_pool_intervals"] == args.samples
        and summary["cleanup_confirmed"] == args.samples
        and blank_starts >= args.samples
        and marked == args.samples
    )
    print(
        json.dumps(
            {
                "status": "passed" if passed else "failed",
                "release_id": qualification.settings.release_id,
                "image_id": qualification.settings.chat_modal_image_version,
                "worker_contract_version": (
                    qualification.settings.chat_worker_contract_version
                ),
                "configuration": {
                    "samples": args.samples,
                    "sandbox_cpu": args.candidate_cpu,
                    "sandbox_cpu_limit": (
                        qualification.settings.chat_sandbox_cpu_limit
                    ),
                    "sandbox_memory_mib": args.candidate_memory_mib,
                    "sandbox_memory_limit_mib": (
                        qualification.settings.chat_sandbox_memory_limit_mib
                    ),
                },
                "blank_starts": blank_starts,
                "marked": marked,
                "summary": summary,
                "raw_samples": [asdict(sample) for sample in samples],
            },
            indent=2,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
