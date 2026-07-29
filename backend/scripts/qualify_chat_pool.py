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
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.exc import NoResultFound

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.models.database import ChatSandboxPool, ChatTurnLatency
from backend.routers.auth import _encode_legacy_session

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
    def __init__(self, *, samples: int, blank_timeout: float):
        self.settings = get_settings()
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

    def _latency(self, request_id: str) -> PoolSample:
        with db_manager.session_local() as db:
            row = db.execute(
                select(ChatTurnLatency).where(
                    ChatTurnLatency.request_id == uuid.UUID(request_id)
                )
            ).scalar_one()
        return PoolSample(
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
            terminal_status=row.terminal_status,
            error_code=None,
        )

    async def _turn(self, index: int) -> PoolSample:
        subject = f"pool-qualification-{self.run_id}-{index}"
        token = _encode_legacy_session({"sub": subject, "username": subject})
        payload = {
            "message": "Reply with a concise acknowledgement.",
            "client_message_id": str(uuid.uuid4()),
        }
        request_id: str | None = None
        terminal = "error"
        error_code: str | None = None
        async with httpx.AsyncClient(
            timeout=240,
            cookies={self.settings.session_cookie_name: token},
        ) as client:
            async with client.stream(
                "POST",
                "http://127.0.0.1:8001/api/v1/chat/stream",
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    event = json.loads(line[6:])
                    if event.get("type") == "stream_start":
                        request_id = str(event["request_id"])
                    if event.get("type") in {"done", "cancelled", "error"}:
                        terminal = str(event["type"])
                        error_code = (
                            str(event.get("code")) if event.get("code") else None
                        )
        if request_id is None:
            return PoolSample(
                None, None, None, None, None, None, None, terminal, error_code
            )
        for _ in range(40):
            try:
                return self._latency(request_id)
            except NoResultFound:
                await asyncio.sleep(0.05)
        return PoolSample(
            request_id, None, None, None, None, None, None, terminal, error_code
        )

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


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Qualify authenticated staging blank-pool claims and turns"
    )
    result.add_argument("--samples", type=int, default=100)
    result.add_argument("--candidate-cpu", type=float, required=True)
    result.add_argument("--candidate-memory-mib", type=int, required=True)
    result.add_argument("--blank-timeout", type=float, default=90)
    result.add_argument("--confirm", required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.confirm != CONFIRMATION:
        raise SystemExit(f"--confirm must be {CONFIRMATION}")
    if not 1 <= args.samples <= 200:
        raise SystemExit("--samples must be 1-200")
    qualification = PoolQualification(
        samples=args.samples, blank_timeout=args.blank_timeout
    )
    qualification.validate(cpu=args.candidate_cpu, memory_mib=args.candidate_memory_mib)
    samples, blank_starts = asyncio.run(qualification.run())
    summary = summarize(samples)
    passed = (
        summary["complete"] == args.samples
        and summary["pool_hits"] == args.samples
        and blank_starts >= args.samples
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
                "summary": summary,
                "raw_samples": [asdict(sample) for sample in samples],
            },
            indent=2,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
