"""Lazy, fenced executor workspace ownership for external Pi turns."""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from backend.chat_sandbox_worker.executor_protocol import ProtocolError
from backend.config import Settings
from backend.services.chat_sandbox_acquisition_coordinator import (
    ChatSandboxAcquisitionCoordinator,
)
from backend.services.chat_sandbox_executor import (
    ExecutorTransportError,
    SandboxExecutorClient,
)
from backend.services.chat_sandbox_lease_lifecycle_coordinator import (
    ChatSandboxLeaseLifecycleCoordinator,
)
from backend.services.chat_sandbox_lease_maintenance_coordinator import (
    ChatSandboxLeaseMaintenanceCoordinator,
)
from backend.services.chat_sandbox_provider import (
    SandboxError,
    SandboxLaunchMode,
    SandboxProvider,
)
from backend.services.chat_sandbox_state_repository import (
    ChatSandboxStateRepository,
    LeaseUnavailable,
    WorkerClaim,
    WorkerGenerationUnavailable,
)
from backend.services.chat_turn_job_repository import (
    ChatTurnJobRepository,
    StaleTurnClaim,
    TurnLeaseClaim,
)

SessionFactory = Callable[[], Session]


@dataclass(frozen=True)
class ExternalExecutorWorkspace:
    """One exact busy claim on a durable session workspace."""

    session_id: uuid.UUID
    sandbox: object
    sandbox_id: str
    worker_generation: str
    workspace_generation: int
    claim: WorkerClaim


def _workspace_generation(worker_generation: str) -> int:
    """Map the durable opaque generation into the executor's positive int fence."""

    value = int.from_bytes(
        hashlib.sha256(worker_generation.encode()).digest()[:8], "big"
    ) & (2**63 - 1)
    return value or 1


class ChatExternalExecutorWorkspaceManager:
    """Acquire executor-only sandboxes lazily and retain them while idle."""

    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: SessionFactory,
        state_repository: ChatSandboxStateRepository,
        acquisition: ChatSandboxAcquisitionCoordinator,
        lifecycle: ChatSandboxLeaseLifecycleCoordinator,
        maintenance: ChatSandboxLeaseMaintenanceCoordinator,
        executor: SandboxExecutorClient,
        turn_repository: ChatTurnJobRepository | None = None,
        utcnow: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
        assignment_token_factory: Callable[[], str] | None = None,
    ) -> None:
        if settings.chat_workspace_snapshots_enabled:
            raise ValueError("External executor workspaces require snapshots disabled")
        if acquisition.settings is not settings:
            raise ValueError("Workspace acquisition settings must be shared")
        if acquisition.session_factory is not session_factory:
            raise ValueError("Workspace acquisition sessions must be shared")
        if acquisition.state_repository is not state_repository:
            raise ValueError("Workspace state repository must be shared")
        if lifecycle.repository is not state_repository:
            raise ValueError("Workspace lifecycle repository must be shared")
        if maintenance.repository is not state_repository:
            raise ValueError("Workspace maintenance repository must be shared")
        self.settings = settings
        self.session_factory = session_factory
        self.state_repository = state_repository
        self.acquisition = acquisition
        self.lifecycle = lifecycle
        self.maintenance = maintenance
        self.executor = executor
        self.turn_repository = turn_repository or ChatTurnJobRepository()
        self.utcnow = utcnow or (lambda: datetime.now(UTC))
        self.monotonic = monotonic
        self.sleeper = sleeper
        self.assignment_token_factory = assignment_token_factory or (
            lambda: secrets.token_urlsafe(24)
        )

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        provider: SandboxProvider,
        executor: SandboxExecutorClient,
    ) -> ChatExternalExecutorWorkspaceManager:
        # Local import keeps the compatibility façade out of the domain module's
        # import graph while reusing its single, validated dependency assembly.
        from backend.services.chat_sandbox_service import SandboxSessionManager

        owner = SandboxSessionManager(settings, sandbox_provider=provider)
        manager = cls(
            settings=settings,
            session_factory=owner.session_factory,
            state_repository=owner._state_repository(),
            acquisition=owner._acquisition_coordinator(),
            lifecycle=owner._lease_lifecycle_coordinator(),
            maintenance=owner._lease_maintenance_coordinator(),
            executor=executor,
        )
        manager._dependency_owner = owner
        return manager

    async def acquire(
        self,
        *,
        session_id: uuid.UUID,
        turn_claim: TurnLeaseClaim,
    ) -> ExternalExecutorWorkspace:
        deadline = self.monotonic() + self.acquisition.ready_timeout_seconds
        replacement_attempts = 0
        while True:
            self._require_live_turn(turn_claim)
            outcome = await self.acquisition.acquire(
                session_id,
                launch_mode=SandboxLaunchMode.EXECUTOR,
                allow_pool=False,
            )
            try:
                claim = self._claim(session_id, str(outcome.sandbox.object_id))
            except (LeaseUnavailable, WorkerGenerationUnavailable):
                if self.monotonic() >= deadline:
                    raise SandboxError(
                        "sandbox_timeout", "Secure workspace startup timed out"
                    ) from None
                await self.sleeper(0.05)
                continue

            workspace = ExternalExecutorWorkspace(
                session_id=session_id,
                sandbox=outcome.sandbox,
                sandbox_id=claim.sandbox_id,
                worker_generation=claim.worker_generation,
                workspace_generation=_workspace_generation(claim.worker_generation),
                claim=claim,
            )
            try:
                healthy = await self.executor.health(workspace.sandbox) == "ok"
            except (ExecutorTransportError, ProtocolError, SandboxError):
                healthy = False
            if healthy:
                try:
                    self._require_live_turn(turn_claim)
                except StaleTurnClaim:
                    await self.release(workspace)
                    raise
                return workspace

            await self.lifecycle.terminate_worker(
                session_id,
                claim,
                failure_code="sandbox_worker_failed",
            )
            replacement_attempts += 1
            if replacement_attempts >= 2 or self.monotonic() >= deadline:
                raise SandboxError(
                    "sandbox_worker_failed", "Secure workspace executor is unavailable"
                )

    async def release(self, workspace: ExternalExecutorWorkspace) -> bool:
        with self.session_factory() as db, db.begin():
            lease = self.state_repository.load_lease(
                db, workspace.session_id, lock=True
            )
            released = self.state_repository.release_worker(
                lease,
                claim=workspace.claim,
                now=self.utcnow(),
            )
        if released:
            await self.maintenance.enforce_warm_cap()
        return released

    async def invalidate(
        self,
        workspace: ExternalExecutorWorkspace,
        *,
        failure_code: str = "sandbox_worker_failed",
    ) -> None:
        """Fence and terminate only the exact busy workspace claim."""

        await self.lifecycle.terminate_worker(
            workspace.session_id,
            workspace.claim,
            failure_code=failure_code,
        )

    def _claim(self, session_id: uuid.UUID, sandbox_id: str) -> WorkerClaim:
        with self.session_factory() as db, db.begin():
            lease = self.state_repository.load_lease(db, session_id, lock=True)
            return self.state_repository.claim_worker(
                lease,
                sandbox_id=sandbox_id,
                assignment_token=self.assignment_token_factory(),
                now=self.utcnow(),
            )

    def _require_live_turn(self, claim: TurnLeaseClaim) -> None:
        with self.session_factory() as db, db.begin():
            self.turn_repository.require_live_claim(
                db,
                claim=claim,
                now=self.utcnow(),
            )
