"""Assigned sandbox lease termination and deleted-session cleanup."""

from __future__ import annotations

import asyncio
import secrets
import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol

from sqlalchemy.orm import Session

from backend.config import Settings
from backend.services.chat_sandbox_capacity_repository import lock_capacity
from backend.services.chat_sandbox_lease_eviction_coordinator import (
    ChatSandboxLeaseEvictionCoordinator,
)
from backend.services.chat_sandbox_provider import SandboxProvider
from backend.services.chat_sandbox_spend_service import ChatSandboxSpendService
from backend.services.chat_sandbox_state_repository import (
    ChatSandboxStateRepository,
    TerminationClaim,
    WorkerClaim,
)
from backend.services.chat_sandbox_worker_transport import (
    ChatSandboxWorkerTransport,
    SessionControl,
)

MAX_LEASE_TERMINATION_CONCURRENCY = 8

SessionFactory = Callable[[], Session]
SpendFactory = Callable[[Session], ChatSandboxSpendService]
CapacityLocker = Callable[[Session], bool]
UtcClock = Callable[[], datetime]
TokenFactory = Callable[[], str]


class SnapshotDeleter(Protocol):
    async def delete(self, snapshot_id: str) -> None: ...


class LeaseTerminationOutcome(StrEnum):
    FINISHED = "finished"
    NOT_CLAIMED = "not_claimed"
    OWNERSHIP_CHANGED = "ownership_changed"

    @property
    def acquired(self) -> bool:
        return self is not LeaseTerminationOutcome.NOT_CLAIMED


class SandboxCleanupUnverified(RuntimeError):
    """The application could not confirm deletion of all provider state."""


class ChatSandboxLeaseLifecycleCoordinator:
    """Coordinate lease termination without holding transactions over I/O."""

    def __init__(
        self,
        settings: Settings,
        *,
        session_factory: SessionFactory,
        repository: ChatSandboxStateRepository,
        provider: SandboxProvider,
        transport: ChatSandboxWorkerTransport,
        snapshots: SnapshotDeleter,
        idle_eviction: ChatSandboxLeaseEvictionCoordinator,
        spend_factory: SpendFactory | None = None,
        capacity_locker: CapacityLocker = lock_capacity,
        utcnow: UtcClock | None = None,
        token_factory: TokenFactory | None = None,
        termination_concurrency: int = MAX_LEASE_TERMINATION_CONCURRENCY,
    ) -> None:
        if transport.provider is not provider:
            raise ValueError("Lease lifecycle provider and transport must be shared")
        if (
            idle_eviction.provider is not provider
            or idle_eviction.transport is not transport
        ):
            raise ValueError(
                "Lease lifecycle and idle eviction transports must be shared"
            )
        self.settings = settings
        self.session_factory = session_factory
        self.repository = repository
        self.provider = provider
        self.transport = transport
        self.snapshots = snapshots
        self.idle_eviction = idle_eviction
        self.spend_factory = spend_factory or (
            lambda db: ChatSandboxSpendService(db, settings)
        )
        self.capacity_locker = capacity_locker
        self.utcnow = utcnow or (lambda: datetime.now(UTC))
        self.token_factory = token_factory or (lambda: secrets.token_urlsafe(24))
        self.termination_concurrency = min(
            MAX_LEASE_TERMINATION_CONCURRENCY,
            max(1, termination_concurrency),
        )

    @property
    def ready_timeout_seconds(self) -> float:
        if getattr(self.settings, "chat_persistent_worker_enabled", False):
            return getattr(
                self.settings,
                "chat_worker_ready_timeout_seconds",
                self.settings.chat_sandbox_ready_timeout_seconds,
            )
        return self.settings.chat_sandbox_ready_timeout_seconds

    @property
    def blank_pool_enabled(self) -> bool:
        return bool(
            getattr(self.settings, "chat_blank_pool_enabled", False)
            and getattr(self.settings, "chat_sandbox_admission_enabled", True)
        )

    async def terminate(
        self,
        chat_session_id: uuid.UUID,
        *,
        failure_code: str | None = None,
    ) -> LeaseTerminationOutcome:
        now = self.utcnow()
        with self.session_factory() as db, db.begin():
            lease = self.repository.load_lease(db, chat_session_id, lock=True)
            claim = self.repository.claim_termination(
                lease,
                termination_token=self.token_factory(),
                failure_code=failure_code,
                expires_at=now + timedelta(seconds=self.ready_timeout_seconds + 15),
            )
        if claim is None:
            return LeaseTerminationOutcome.NOT_CLAIMED
        return await self.terminate_claimed(chat_session_id, claim)

    async def terminate_worker(
        self,
        chat_session_id: uuid.UUID,
        claim: WorkerClaim,
        *,
        failure_code: str,
    ) -> LeaseTerminationOutcome:
        now = self.utcnow()
        with self.session_factory() as db, db.begin():
            lease = self.repository.load_lease(db, chat_session_id, lock=True)
            termination = self.repository.claim_worker_termination(
                lease,
                claim=claim,
                termination_token=self.token_factory(),
                failure_code=failure_code,
                expires_at=now + timedelta(seconds=self.ready_timeout_seconds + 15),
                now=now,
            )
        if termination is None:
            return LeaseTerminationOutcome.NOT_CLAIMED
        return await self.terminate_claimed(chat_session_id, termination)

    async def terminate_claimed(
        self,
        chat_session_id: uuid.UUID,
        claim: TerminationClaim,
    ) -> LeaseTerminationOutcome:
        control = self._claimed_control(chat_session_id, claim.sandbox_id)
        if control is not None:
            self.transport.drop_session_control(
                chat_session_id,
                expected=control,
            )

        failure_code = claim.failure_code
        confirmed: bool | None = None
        if claim.sandbox_id:
            confirmed = await self.provider.terminate(claim.sandbox_id)
            if not confirmed:
                failure_code = "termination_uncertain"
        return self._finalize_termination(
            chat_session_id,
            claim,
            failure_code=failure_code,
            confirmed=confirmed,
        )

    async def cleanup_deleted(
        self,
        sandbox_id: str | None,
        snapshot_id: str | None,
    ) -> None:
        termination_confirmed = True
        if sandbox_id:
            self.transport.drop_session_controls_by_sandbox(sandbox_id)
            termination_confirmed = await self.provider.terminate(sandbox_id)
            if getattr(
                self.settings,
                "chat_sandbox_spend_enforcement_enabled",
                False,
            ):
                with self.session_factory() as db, db.begin():
                    self.capacity_locker(db)
                    self.spend_factory(db).terminate(
                        sandbox_id,
                        "session_deleted",
                        confirmed=termination_confirmed,
                        now=self.utcnow(),
                    )
        if snapshot_id:
            await self.snapshots.delete(snapshot_id)
        if not termination_confirmed:
            raise SandboxCleanupUnverified(
                "Sandbox termination could not be confirmed after chat deletion"
            )

    async def terminate_idle_many(
        self,
        chat_session_ids: Sequence[uuid.UUID],
    ) -> int:
        semaphore = asyncio.Semaphore(self.termination_concurrency)

        async def terminate_one(chat_session_id: uuid.UUID) -> bool:
            async with semaphore:
                outcome = await self.idle_eviction.evict_idle(chat_session_id)
                return outcome.acquired

        results = await asyncio.gather(
            *(terminate_one(session_id) for session_id in chat_session_ids)
        )
        return sum(results)

    def _claimed_control(
        self,
        chat_session_id: uuid.UUID,
        sandbox_id: str | None,
    ) -> SessionControl | None:
        control = self.transport.session_control(chat_session_id)
        if control is not None and sandbox_id and control.sandbox_id != sandbox_id:
            return None
        return control

    def _finalize_termination(
        self,
        chat_session_id: uuid.UUID,
        claim: TerminationClaim,
        *,
        failure_code: str | None,
        confirmed: bool | None,
    ) -> LeaseTerminationOutcome:
        now = self.utcnow()
        spend_policy_enabled = bool(
            getattr(
                self.settings,
                "chat_sandbox_spend_enforcement_enabled",
                False,
            )
        )
        spend_enforced = bool(claim.sandbox_id) and spend_policy_enabled
        with self.session_factory() as db, db.begin():
            if self.blank_pool_enabled or spend_policy_enabled:
                self.capacity_locker(db)
            lease = self.repository.load_lease(db, chat_session_id, lock=True)
            finished = self.repository.finish_termination(
                lease,
                claim=claim,
                state="failed" if failure_code else "terminated",
                failure_code=failure_code,
                clear_sandbox=True,
                now=now,
            )
            if spend_enforced:
                assert claim.sandbox_id is not None
                assert confirmed is not None
                self.spend_factory(db).terminate(
                    claim.sandbox_id,
                    claim.failure_code,
                    confirmed=confirmed,
                    now=now,
                )
        if finished:
            return LeaseTerminationOutcome.FINISHED
        return LeaseTerminationOutcome.OWNERSHIP_CHANGED
