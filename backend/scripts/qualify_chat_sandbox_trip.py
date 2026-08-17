#!/usr/bin/env python3
"""Qualify graceful and forced staging sandbox shutdown after a spend trip."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import modal
from sqlalchemy import func, select

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.models.database import (
    ChatSandboxBudgetState,
    ChatSandboxCircuitEvent,
    ChatSandboxComputeInterval,
    ChatSandboxLease,
    ChatSandboxPool,
    ChatSession,
    ChatTurnCapability,
)
from backend.scripts.qualify_chat_sandbox import (
    merge_release_settings,
    settings_for_release,
)
from backend.services.chat_capability_service import ChatCapabilityService
from backend.services.chat_sandbox_service import (
    SandboxSessionManager,
    create_isolated_sandbox,
)
from backend.services.chat_sandbox_spend_service import ChatSandboxSpendService

CONFIRMATION = "QUALIFY_STAGING_CHAT_TRIP"
ACTIVE_LEASE_STATES = ("starting", "ready", "busy", "idle", "terminating")
ACTIVE_POOL_STATES = ("starting", "blank_ready", "draining")


@dataclass(frozen=True)
class PreparedCase:
    name: str
    environment: str
    session_id: uuid.UUID
    capability_id: uuid.UUID
    interval_id: uuid.UUID
    sandbox: object
    process: object


class TripQualification:
    def __init__(self, release_dir: Path, max_total_microusd: int):
        environment = get_settings()
        release = settings_for_release(release_dir)
        self.settings = merge_release_settings(environment, release)
        self.run_id = uuid.uuid4().hex[:10]
        self.max_total_microusd = max_total_microusd

    def _case_settings(self, name: str):
        return self.settings.model_copy(
            update={"environment": f"staging-tq-{self.run_id}-{name}"}
        )

    async def _provider_sandboxes(self, environment: str) -> list[object]:
        return [
            sandbox
            async for sandbox in modal.Sandbox.list.aio(
                tags={"service": "pwc-chat", "environment": environment}
            )
        ]

    async def validate(self) -> int:
        if self.settings.environment != "staging":
            raise ValueError("Trip qualification requires staging")
        if self.settings.chat_blank_pool_enabled:
            raise ValueError("Trip qualification requires the blank pool to be off")
        if not self.settings.chat_persistent_worker_enabled:
            raise ValueError("Trip qualification requires persistent workers")
        if self.settings.chat_sandbox_drain_grace_seconds != 30:
            raise ValueError("Trip qualification requires the reviewed 30-second grace")
        if await self._provider_sandboxes("staging"):
            raise ValueError(
                "Tagged staging sandboxes must be zero before qualification"
            )
        now = datetime.now(UTC)
        with db_manager.session_local() as db:
            active_leases = (
                db.scalar(
                    select(func.count())
                    .select_from(ChatSandboxLease)
                    .where(ChatSandboxLease.state.in_(ACTIVE_LEASE_STATES))
                )
                or 0
            )
            active_pool = (
                db.scalar(
                    select(func.count())
                    .select_from(ChatSandboxPool)
                    .where(ChatSandboxPool.state.in_(ACTIVE_POOL_STATES))
                )
                or 0
            )
            live_capabilities = (
                db.scalar(
                    select(func.count())
                    .select_from(ChatTurnCapability)
                    .where(
                        ChatTurnCapability.revoked_at.is_(None),
                        ChatTurnCapability.expires_at > now,
                    )
                )
                or 0
            )
            unresolved = (
                db.scalar(
                    select(func.count())
                    .select_from(ChatSandboxComputeInterval)
                    .where(
                        ChatSandboxComputeInterval.environment == "staging",
                        ChatSandboxComputeInterval.terminal_at.is_(None),
                    )
                )
                or 0
            )
            reservation = ChatSandboxSpendService(
                db, self._case_settings("ceiling")
            ).reservation_amount()
        if active_leases or active_pool or live_capabilities or unresolved:
            raise ValueError("Staging lifecycle baseline is not empty")
        total_reservation = reservation * 2
        if total_reservation > self.max_total_microusd:
            raise ValueError("Qualification reservation exceeds the recorded ceiling")
        return total_reservation

    async def _prepare(self, name: str, sleep_seconds: int) -> PreparedCase:
        settings = self._case_settings(name)
        session_id = uuid.uuid4()
        turn_id = uuid.uuid4()
        worker_generation = secrets.token_hex(16)
        now = datetime.now(UTC)
        with db_manager.session_local() as db, db.begin():
            db.add(
                ChatSession(
                    id=session_id,
                    hf_user_id=f"trip-qualification-{self.run_id}-{name}",
                    hf_username=f"trip-qualification-{self.run_id}-{name}",
                    selected_model=self.settings.chat_model_choices[0]["id"],
                    execution_backend="modal_cli",
                    active_turn_id=turn_id,
                    active_turn_expires_at=now + timedelta(minutes=5),
                )
            )
            interval_id = ChatSandboxSpendService(db, settings).reserve_interval(
                origin="qualification",
                worker_generation=worker_generation,
                chat_session_id=session_id,
                now=now,
            )
            db.add(
                ChatSandboxLease(
                    chat_session_id=session_id,
                    app_release_id=settings.release_id,
                    image_version=settings.chat_modal_image_version,
                    worker_contract_version=settings.chat_worker_contract_version,
                    worker_generation=worker_generation,
                    state="starting",
                    last_activity_at=now,
                    updated_at=now,
                )
            )
            capability = ChatCapabilityService(db).issue(
                chat_session_id=session_id,
                turn_id=turn_id,
                owner_id=f"trip-qualification-{self.run_id}",
                model=self.settings.chat_model_choices[0]["id"],
                scopes={"catalog"},
                lifetime_seconds=240,
            )
        sandbox = None
        try:
            sandbox = await create_isolated_sandbox(
                settings,
                name=f"trip-qualification-{self.run_id}-{name}",
                tags={
                    "service": "pwc-chat",
                    "environment": settings.environment,
                    "purpose": "circuit-trip-qualification",
                    "run": self.run_id,
                    "case": name,
                    "release": settings.release_id,
                },
                worker_generation=worker_generation,
            )
            with db_manager.session_local() as db, db.begin():
                ChatSandboxSpendService(db, settings).provider_created(
                    interval_id, sandbox.object_id
                )
                lease = db.get(ChatSandboxLease, session_id)
                lease.modal_sandbox_id = sandbox.object_id
                lease.state = "busy"
                lease.updated_at = datetime.now(UTC)
            process = await sandbox.exec.aio(
                "sleep", str(sleep_seconds), timeout=sleep_seconds + 60
            )
        except (asyncio.CancelledError, Exception):
            if sandbox is None:
                with db_manager.session_local() as db, db.begin():
                    ChatSandboxSpendService(db, settings).abort_reservation(
                        interval_id, "qualification_setup_failed"
                    )
            else:
                await sandbox.terminate.aio(wait=True)
                with db_manager.session_local() as db, db.begin():
                    ChatSandboxSpendService(db, settings).terminate(
                        sandbox.object_id,
                        "qualification_setup_failed",
                        confirmed=True,
                    )
            with db_manager.session_local() as db, db.begin():
                lease = db.get(ChatSandboxLease, session_id)
                if lease is not None:
                    lease.modal_sandbox_id = None
                    lease.state = "failed"
                    lease.failure_code = "qualification_setup_failed"
                    lease.lease_token_hash = None
                    lease.lease_expires_at = None
                    lease.updated_at = datetime.now(UTC)
                ChatCapabilityService(db).revoke(capability.capability_id)
            raise
        return PreparedCase(
            name,
            settings.environment,
            session_id,
            capability.capability_id,
            interval_id,
            sandbox,
            process,
        )

    def _trip(self, prepared: PreparedCase) -> None:
        with db_manager.session_local() as db, db.begin():
            ChatSandboxSpendService(db, self._case_settings(prepared.name)).trip(
                "qualification_trip"
            )

    async def _evidence(self, prepared: PreparedCase) -> dict[str, object]:
        settings = self._case_settings(prepared.name)
        with db_manager.session_local() as db, db.begin():
            ChatSandboxSpendService(db, settings).refresh(datetime.now(UTC))
            lease = db.get(ChatSandboxLease, prepared.session_id)
            capability = db.get(ChatTurnCapability, prepared.capability_id)
            interval = db.get(ChatSandboxComputeInterval, prepared.interval_id)
            event_types = sorted(
                db.execute(
                    select(ChatSandboxCircuitEvent.event_type)
                    .join(
                        ChatSandboxBudgetState,
                        ChatSandboxBudgetState.id
                        == ChatSandboxCircuitEvent.budget_state_id,
                    )
                    .where(ChatSandboxBudgetState.environment == settings.environment)
                ).scalars()
            )
            evidence = {
                "lease_state": lease.state,
                "failure_code": lease.failure_code,
                "capability_revoked": capability.revoked_at is not None,
                "interval_terminal": interval.terminal_at is not None,
                "reservation_released": interval.reserved_microusd == 0,
                "reconciliation_state": interval.reconciliation_state,
                "event_types": event_types,
            }
        evidence["provider_sandboxes"] = len(
            await self._provider_sandboxes(prepared.environment)
        )
        return evidence

    async def _cleanup(self, prepared: PreparedCase) -> None:
        manager = SandboxSessionManager(self._case_settings(prepared.name))
        with db_manager.session_local() as db:
            lease = db.get(ChatSandboxLease, prepared.session_id)
            active = bool(lease and lease.state in ACTIVE_LEASE_STATES)
        if active:
            await manager.terminate(
                prepared.session_id, failure_code="qualification_cleanup"
            )
        for sandbox in await self._provider_sandboxes(prepared.environment):
            with contextlib.suppress(Exception):
                await sandbox.terminate.aio(wait=True)
            with db_manager.session_local() as db, db.begin():
                ChatSandboxSpendService(
                    db, self._case_settings(prepared.name)
                ).terminate(sandbox.object_id, "qualification_cleanup", confirmed=True)
        if not await self._provider_sandboxes(prepared.environment):
            with db_manager.session_local() as db, db.begin():
                ChatSandboxSpendService(
                    db, self._case_settings(prepared.name)
                ).terminate(
                    prepared.sandbox.object_id,
                    "qualification_cleanup",
                    confirmed=True,
                )
        with db_manager.session_local() as db, db.begin():
            ChatCapabilityService(db).revoke(prepared.capability_id)

    async def _natural_case(self) -> dict[str, object]:
        prepared = await self._prepare("natural", sleep_seconds=3)
        manager = SandboxSessionManager(self._case_settings(prepared.name))
        try:
            self._trip(prepared)

            async def finish_normally() -> int:
                await prepared.process.wait.aio()
                with db_manager.session_local() as db, db.begin():
                    ChatCapabilityService(db).revoke(prepared.capability_id)
                await manager.terminate(prepared.session_id)
                return int(prepared.process.returncode or 0)

            completion = asyncio.create_task(finish_normally())
            started = time.monotonic()
            enforcement = await manager.enforce_spend_cap()
            returncode = await completion
            elapsed_ms = round((time.monotonic() - started) * 1000)
            evidence = await self._evidence(prepared)
            passed = bool(
                returncode == 0
                and evidence["lease_state"] == "terminated"
                and evidence["failure_code"] is None
                and evidence["capability_revoked"]
                and evidence["interval_terminal"]
                and evidence["reservation_released"]
                and evidence["provider_sandboxes"] == 0
                and enforcement["terminated"] == 0
                and enforcement["uncertain"] == 0
                and "circuit_tripped" in evidence["event_types"]
                and "kill_sweep_complete" in evidence["event_types"]
            )
            return {
                "status": "passed" if passed else "failed",
                "elapsed_ms": elapsed_ms,
                "process_returncode": returncode,
                "enforcement": enforcement,
                "evidence": evidence,
            }
        finally:
            await self._cleanup(prepared)

    async def _forced_case(self) -> dict[str, object]:
        prepared = await self._prepare("forced", sleep_seconds=120)
        manager = SandboxSessionManager(self._case_settings(prepared.name))
        try:
            self._trip(prepared)
            started = time.monotonic()
            first = await manager.enforce_spend_cap()
            midway = await self._evidence(prepared)
            second = await manager.enforce_spend_cap()
            elapsed_ms = round((time.monotonic() - started) * 1000)
            with contextlib.suppress(Exception):
                await prepared.process.wait.aio()
            evidence = await self._evidence(prepared)
            passed = bool(
                midway["lease_state"] == "busy"
                and not midway["capability_revoked"]
                and midway["provider_sandboxes"] == 1
                and first["terminated"] == 0
                and first["uncertain"] == 0
                and "kill_sweep_incomplete" in midway["event_types"]
                and evidence["lease_state"] == "failed"
                and evidence["failure_code"] == "chat_disabled_interrupted"
                and evidence["capability_revoked"]
                and evidence["interval_terminal"]
                and evidence["reservation_released"]
                and evidence["provider_sandboxes"] == 0
                and second["terminated"] >= 1
                and second["uncertain"] == 0
                and "circuit_tripped" in evidence["event_types"]
                and "kill_sweep_complete" in evidence["event_types"]
                and elapsed_ms >= self.settings.chat_sandbox_drain_grace_seconds * 1000
            )
            return {
                "status": "passed" if passed else "failed",
                "elapsed_ms": elapsed_ms,
                "first_enforcement": first,
                "midway": midway,
                "second_enforcement": second,
                "evidence": evidence,
            }
        finally:
            await self._cleanup(prepared)

    async def run(self) -> dict[str, object]:
        total_reservation = await self.validate()
        natural = await self._natural_case()
        forced = await self._forced_case()
        passed = natural["status"] == "passed" and forced["status"] == "passed"
        return {
            "status": "passed" if passed else "failed",
            "run_id": self.run_id,
            "release_id": self.settings.release_id,
            "pool_enabled": self.settings.chat_blank_pool_enabled,
            "drain_grace_seconds": self.settings.chat_sandbox_drain_grace_seconds,
            "qualification_spend_ceiling_microusd": self.max_total_microusd,
            "reserved_upper_bound_microusd": total_reservation,
            "natural": natural,
            "forced": forced,
        }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--release-dir", type=Path, required=True)
    result.add_argument("--max-total-microusd", type=int, required=True)
    result.add_argument("--confirm", required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.confirm != CONFIRMATION:
        raise SystemExit(f"--confirm must be {CONFIRMATION}")
    if not 1 <= args.max_total_microusd <= 5_000_000:
        raise SystemExit("--max-total-microusd must be between 1 and 5000000")
    report = asyncio.run(
        TripQualification(args.release_dir, args.max_total_microusd).run()
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
