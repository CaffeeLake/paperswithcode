"""Coordinate durable sandbox shutdown after the spend circuit trips."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import batched
from typing import TypedDict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import (
    ChatSandboxComputeInterval,
    ChatSandboxLease,
    ChatSandboxPool,
    ChatTurnCapability,
)
from backend.services.chat_sandbox_lease_lifecycle_coordinator import (
    ChatSandboxLeaseLifecycleCoordinator,
)
from backend.services.chat_sandbox_pool_coordinator import ChatSandboxPoolCoordinator
from backend.services.chat_sandbox_provider import SandboxProvider
from backend.services.chat_sandbox_spend_service import ChatSandboxSpendService
from backend.services.chat_sandbox_worker_transport import ChatSandboxWorkerTransport

MAX_SPEND_CAP_TERMINATION_CONCURRENCY = 8

SessionFactory = Callable[[], Session]
SpendFactory = Callable[[Session], ChatSandboxSpendService]
UtcClock = Callable[[], datetime]
Sleeper = Callable[[float], Awaitable[None]]


@dataclass(frozen=True)
class SpendCapEnforcementResult:
    state: str
    terminated: int = 0
    uncertain: int = 0


class SpendCapPublicResult(TypedDict):
    state: str
    terminated: int
    uncertain: int


@dataclass(frozen=True)
class PoolShutdownTarget:
    pool_id: uuid.UUID
    sandbox_id: str | None


@dataclass(frozen=True)
class TrackedShutdownPlan:
    lease_ids: tuple[uuid.UUID, ...]
    pool_targets: tuple[PoolShutdownTarget, ...]


@dataclass(frozen=True)
class ProviderSweepResult:
    terminated: int = 0
    uncertain: int = 0


class ChatSandboxSpendCapCoordinator:
    """Drain tracked sandboxes and reconcile tagged provider leftovers."""

    def __init__(
        self,
        settings: Settings,
        *,
        session_factory: SessionFactory,
        lifecycle: ChatSandboxLeaseLifecycleCoordinator,
        pool: ChatSandboxPoolCoordinator,
        transport: ChatSandboxWorkerTransport,
        provider: SandboxProvider,
        spend_factory: SpendFactory | None = None,
        utcnow: UtcClock | None = None,
        sleeper: Sleeper = asyncio.sleep,
        termination_concurrency: int = MAX_SPEND_CAP_TERMINATION_CONCURRENCY,
    ) -> None:
        if lifecycle.settings is not settings or pool.settings is not settings:
            raise ValueError("Spend cap coordinator settings must be shared")
        if (
            lifecycle.repository.settings is not settings
            or pool.repository.settings is not settings
        ):
            raise ValueError("Spend cap repository settings must be shared")
        if (
            lifecycle.session_factory is not session_factory
            or pool.session_factory is not session_factory
        ):
            raise ValueError("Spend cap coordinator sessions must be shared")
        if (
            transport.provider is not provider
            or lifecycle.provider is not provider
            or pool.provider is not provider
        ):
            raise ValueError("Spend cap coordinator provider must be shared")
        if lifecycle.transport is not transport or pool.transport is not transport:
            raise ValueError("Spend cap coordinator transport must be shared")
        if lifecycle.capacity_locker is not pool.repository.capacity_locker:
            raise ValueError("Spend cap capacity locker must be shared")
        self.settings = settings
        self.session_factory = session_factory
        self.lifecycle = lifecycle
        self.pool = pool
        self.transport = transport
        self.provider = provider
        self.capacity_locker = lifecycle.capacity_locker
        self.spend_factory = spend_factory or (
            lambda db: ChatSandboxSpendService(db, settings)
        )
        self.utcnow = utcnow or (lambda: datetime.now(UTC))
        self.sleeper = sleeper
        self.termination_concurrency = min(
            MAX_SPEND_CAP_TERMINATION_CONCURRENCY,
            max(1, termination_concurrency),
        )
        self._enforcement_lock = asyncio.Lock()

    async def enforce(self) -> SpendCapEnforcementResult:
        """Apply the durable trip time to workers and tagged provider orphans."""

        async with self._enforcement_lock:
            return await self._enforce_once()

    async def _enforce_once(self) -> SpendCapEnforcementResult:
        status = self._spend_status()
        state = str(status["circuit_state"])
        if state != "tripped":
            return SpendCapEnforcementResult(state=state)

        deadline = self._deadline(status["tripped_at"])
        terminated = await self._terminate_tracked(self._tracked_shutdown_plan())
        await self._wait_for_grace(deadline)
        forced = self.utcnow() >= deadline
        if forced:
            terminated += await self._force_busy_shutdown()
        protected_busy_ids = set() if forced else self._busy_sandbox_ids()
        provider_sweep = await self._sweep_provider(protected_busy_ids)
        terminated += provider_sweep.terminated
        self._record_kill_sweep(provider_uncertain=provider_sweep.uncertain)
        return SpendCapEnforcementResult(
            state="tripped",
            terminated=terminated,
            uncertain=provider_sweep.uncertain,
        )

    def _spend_status(self) -> dict:
        with self.session_factory() as db, db.begin():
            return self.spend_factory(db).status()

    def _deadline(self, tripped_at: datetime | None) -> datetime:
        now = self.utcnow()
        tripped_at = tripped_at or now
        if tripped_at.tzinfo is None:
            tripped_at = tripped_at.replace(tzinfo=UTC)
        return tripped_at + timedelta(
            seconds=self.settings.chat_sandbox_drain_grace_seconds
        )

    def _tracked_shutdown_plan(self) -> TrackedShutdownPlan:
        with self.session_factory() as db:
            lease_ids = tuple(
                db.execute(
                    select(ChatSandboxLease.chat_session_id).where(
                        ChatSandboxLease.state.in_(
                            ["starting", "ready", "idle", "terminating"]
                        )
                    )
                ).scalars()
            )
            pool_targets = tuple(
                PoolShutdownTarget(pool_id=pool_id, sandbox_id=sandbox_id)
                for pool_id, sandbox_id in db.execute(
                    select(
                        ChatSandboxPool.id,
                        ChatSandboxPool.modal_sandbox_id,
                    ).where(
                        ChatSandboxPool.state.in_(
                            ["starting", "blank_ready", "draining"]
                        )
                    )
                ).all()
            )
        return TrackedShutdownPlan(
            lease_ids=lease_ids,
            pool_targets=pool_targets,
        )

    async def _terminate_tracked(self, plan: TrackedShutdownPlan) -> int:
        terminated = await self._terminate_leases(plan.lease_ids)
        for target in plan.pool_targets:
            terminated += bool(
                await self.pool.terminate_pool_row(
                    target.pool_id,
                    target.sandbox_id,
                    failure_code="chat_disabled_interrupted",
                )
            )
        return terminated

    async def _wait_for_grace(self, deadline: datetime) -> None:
        remaining = (deadline - self.utcnow()).total_seconds()
        if remaining > 0:
            await self.sleeper(
                min(remaining, self.settings.chat_sandbox_watchdog_seconds)
            )

    async def _force_busy_shutdown(self) -> int:
        for running in self.transport.running_workers():
            try:
                await self.transport.signal_cancel(running)
            except Exception:
                pass
        with self.session_factory() as db, db.begin():
            db.query(ChatTurnCapability).filter(
                ChatTurnCapability.revoked_at.is_(None)
            ).update(
                {ChatTurnCapability.revoked_at: self.utcnow()},
                synchronize_session=False,
            )
            busy = tuple(
                db.execute(
                    select(ChatSandboxLease.chat_session_id).where(
                        ChatSandboxLease.state == "busy"
                    )
                ).scalars()
            )
        return await self._terminate_leases(busy)

    def _busy_sandbox_ids(self) -> set[str]:
        with self.session_factory() as db:
            return set(
                db.execute(
                    select(ChatSandboxLease.modal_sandbox_id).where(
                        ChatSandboxLease.state == "busy",
                        ChatSandboxLease.modal_sandbox_id.is_not(None),
                    )
                ).scalars()
            )

    async def _sweep_provider(
        self,
        protected_busy_ids: set[str],
    ) -> ProviderSweepResult:
        terminated = 0
        uncertain = 0
        async for sandbox in self.provider.iter_sandboxes(
            tags={"service": "pwc-chat", "environment": self.settings.environment},
        ):
            if sandbox.object_id in protected_busy_ids:
                continue
            try:
                confirmed = await self.provider.terminate(
                    sandbox.object_id,
                    sandbox,
                )
                if not confirmed:
                    raise RuntimeError("provider termination was not confirmed")
                with self.session_factory() as db, db.begin():
                    self.spend_factory(db).terminate(
                        sandbox.object_id,
                        "chat_disabled_interrupted",
                        confirmed=True,
                    )
                terminated += 1
            except Exception:
                uncertain += 1
                with self.session_factory() as db, db.begin():
                    self.spend_factory(db).terminate(
                        sandbox.object_id,
                        "termination_uncertain",
                        confirmed=False,
                    )
        return ProviderSweepResult(terminated=terminated, uncertain=uncertain)

    def _record_kill_sweep(self, *, provider_uncertain: int) -> None:
        with self.session_factory() as db, db.begin():
            spend = self.spend_factory(db)
            ChatSandboxSpendService(
                db, self.settings
            ).abort_abandoned_direct_reservations()
            self.capacity_locker(db)
            remaining_live = (
                db.scalar(
                    select(func.count())
                    .select_from(ChatSandboxLease)
                    .where(
                        ChatSandboxLease.state.in_(
                            ["starting", "ready", "busy", "idle", "terminating"]
                        )
                    )
                )
                or 0
            ) + (
                db.scalar(
                    select(func.count())
                    .select_from(ChatSandboxPool)
                    .where(
                        ChatSandboxPool.state.in_(
                            ["starting", "blank_ready", "draining"]
                        )
                    )
                )
                or 0
            )
            unresolved_intervals = (
                db.scalar(
                    select(func.count())
                    .select_from(ChatSandboxComputeInterval)
                    .where(
                        ChatSandboxComputeInterval.environment
                        == self.settings.environment,
                        ChatSandboxComputeInterval.terminal_at.is_(None),
                    )
                )
                or 0
            )
            spend.record_kill_sweep(
                complete=(
                    provider_uncertain == 0
                    and remaining_live == 0
                    and unresolved_intervals == 0
                )
            )

    async def _terminate_leases(self, session_ids: Sequence[uuid.UUID]) -> int:
        async def terminate_one(session_id: uuid.UUID) -> bool:
            await self.lifecycle.terminate(
                session_id,
                failure_code="chat_disabled_interrupted",
            )
            return True

        terminated = 0
        for batch in batched(session_ids, self.termination_concurrency):
            terminated += sum(
                await asyncio.gather(
                    *(terminate_one(session_id) for session_id in batch)
                )
            )
        return terminated
