"""Transaction-scoped state transitions for durable chat sandbox leases."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import ChatSandboxLease


@dataclass(frozen=True)
class StartClaim:
    token_hash: str
    stale_sandbox_id: str | None
    snapshot_id: str | None
    worker_generation: str = ""


@dataclass(frozen=True)
class WorkerClaim:
    sandbox_id: str
    token_hash: str
    assignment_token: str = ""
    worker_generation: str = ""


@dataclass(frozen=True)
class TerminationClaim:
    sandbox_id: str | None
    token_hash: str
    worker_generation: str | None = None


class LeaseUnavailable(RuntimeError):
    """The requested lease transition is not currently allowed."""


class WorkerGenerationUnavailable(RuntimeError):
    """A worker cannot be claimed without a durable generation."""


class ChatSandboxStateRepository:
    """Mutate locked lease rows without owning or committing transactions."""

    def __init__(self, settings: Settings):
        self.settings = settings

    @staticmethod
    def load_lease(
        db: Session, chat_session_id: uuid.UUID, *, lock: bool
    ) -> ChatSandboxLease | None:
        query = select(ChatSandboxLease).where(
            ChatSandboxLease.chat_session_id == chat_session_id
        )
        if lock:
            query = query.with_for_update()
        return db.execute(query).scalar_one_or_none()

    @staticmethod
    def lock_start_claim(db: Session, chat_session_id: uuid.UUID) -> None:
        """Serialize start claims even before the lease row exists."""

        db.execute(
            select(
                func.pg_advisory_xact_lock(
                    func.hashtextextended(f"chat-sandbox:{chat_session_id}", 0)
                )
            )
        )

    @staticmethod
    def token_hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    @staticmethod
    def unexpired(lease: ChatSandboxLease, now: datetime) -> bool:
        expires_at = lease.lease_expires_at
        if expires_at is None:
            return False
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return expires_at > now

    def claim_start(
        self,
        lease: ChatSandboxLease,
        *,
        creation_token: str,
        now: datetime,
        ready_timeout_seconds: float,
        worker_generation: str | None = None,
    ) -> StartClaim:
        snapshot_id = None
        if (
            self.settings.chat_workspace_snapshots_enabled
            and lease.workspace_snapshot_id
            and lease.snapshot_image_version == self.settings.chat_modal_image_version
        ):
            snapshot_id = lease.workspace_snapshot_id
        elif lease.workspace_snapshot_id:
            lease.workspace_snapshot_id = None
            lease.snapshot_image_version = None
            lease.snapshot_updated_at = None

        token_hash = self.token_hash(creation_token)
        worker_generation = worker_generation or secrets.token_hex(16)
        claim = StartClaim(
            token_hash=token_hash,
            stale_sandbox_id=lease.modal_sandbox_id,
            snapshot_id=snapshot_id,
            worker_generation=worker_generation,
        )
        lease.state = "starting"
        lease.modal_sandbox_id = None
        lease.app_release_id = self.settings.release_id
        lease.image_version = self.settings.chat_modal_image_version
        lease.worker_contract_version = self.settings.chat_worker_contract_version
        lease.worker_generation = worker_generation
        lease.lease_token_hash = token_hash
        lease.lease_expires_at = now + timedelta(seconds=ready_timeout_seconds + 15)
        lease.failure_code = None
        lease.updated_at = now
        return claim

    @staticmethod
    def clear_start_snapshot(
        lease: ChatSandboxLease | None, *, claim: StartClaim
    ) -> bool:
        if not ChatSandboxStateRepository._owns_start(lease, claim):
            return False
        lease.workspace_snapshot_id = None
        lease.snapshot_image_version = None
        lease.snapshot_updated_at = None
        return True

    @staticmethod
    def land_start(
        lease: ChatSandboxLease | None,
        *,
        claim: StartClaim,
        sandbox_id: str,
        now: datetime,
    ) -> bool:
        if not ChatSandboxStateRepository._owns_start(lease, claim):
            return False
        lease.modal_sandbox_id = sandbox_id
        lease.state = "ready"
        lease.lease_token_hash = None
        lease.lease_expires_at = None
        lease.last_activity_at = now
        lease.workspace_dirty = False
        lease.updated_at = now
        return True

    @staticmethod
    def fail_start(
        lease: ChatSandboxLease | None,
        *,
        claim: StartClaim,
        code: str,
        now: datetime,
    ) -> bool:
        if not ChatSandboxStateRepository._owns_start(lease, claim):
            return False
        lease.state = "failed"
        lease.failure_code = code
        lease.lease_token_hash = None
        lease.lease_expires_at = None
        lease.updated_at = now
        return True

    @staticmethod
    def finish_termination(
        lease: ChatSandboxLease | None,
        *,
        claim: TerminationClaim,
        state: str,
        failure_code: str | None,
        clear_sandbox: bool,
        now: datetime,
    ) -> bool:
        if not ChatSandboxStateRepository._owns_termination(lease, claim):
            return False
        if clear_sandbox:
            lease.modal_sandbox_id = None
        lease.state = state
        lease.failure_code = failure_code
        lease.lease_token_hash = None
        lease.lease_expires_at = None
        lease.updated_at = now
        return True

    @staticmethod
    def finish_owned_operation(
        lease: ChatSandboxLease | None,
        *,
        token_hash: str,
        expected_state: str,
        expected_sandbox_id: str | None,
        state: str,
        failure_code: str | None,
        clear_sandbox: bool,
        now: datetime,
    ) -> bool:
        """Compatibility transition for legacy, pre-typed manager callers."""

        if not (
            lease
            and lease.state == expected_state
            and lease.lease_token_hash == token_hash
            and lease.modal_sandbox_id == expected_sandbox_id
        ):
            return False
        if clear_sandbox:
            lease.modal_sandbox_id = None
        lease.state = state
        lease.failure_code = failure_code
        lease.lease_token_hash = None
        lease.lease_expires_at = None
        lease.updated_at = now
        return True

    def claim_worker(
        self,
        lease: ChatSandboxLease | None,
        *,
        sandbox_id: str,
        assignment_token: str,
        now: datetime,
    ) -> WorkerClaim:
        if not (
            lease
            and lease.state in {"ready", "idle"}
            and lease.modal_sandbox_id == sandbox_id
            and lease.lease_token_hash is None
        ):
            raise LeaseUnavailable
        if not lease.worker_generation:
            raise WorkerGenerationUnavailable
        claim = WorkerClaim(
            sandbox_id=sandbox_id,
            token_hash=self.token_hash(assignment_token),
            assignment_token=assignment_token,
            worker_generation=lease.worker_generation,
        )
        lease.state = "busy"
        lease.lease_token_hash = claim.token_hash
        lease.lease_expires_at = None
        lease.last_activity_at = now
        lease.updated_at = now
        return claim

    @staticmethod
    def release_worker(
        lease: ChatSandboxLease | None,
        *,
        claim: WorkerClaim,
        now: datetime,
    ) -> bool:
        if not ChatSandboxStateRepository._owns_worker(lease, claim):
            return False
        lease.state = "idle"
        lease.lease_token_hash = None
        lease.lease_expires_at = None
        lease.last_activity_at = now
        lease.workspace_dirty = True
        lease.updated_at = now
        return True

    def claim_worker_termination(
        self,
        lease: ChatSandboxLease | None,
        *,
        claim: WorkerClaim,
        termination_token: str,
        failure_code: str,
        expires_at: datetime,
        now: datetime,
    ) -> TerminationClaim | None:
        if not self._owns_worker(lease, claim):
            return None
        termination = TerminationClaim(
            sandbox_id=claim.sandbox_id,
            token_hash=self.token_hash(termination_token),
            worker_generation=claim.worker_generation,
        )
        lease.state = "terminating"
        lease.failure_code = failure_code
        lease.lease_token_hash = termination.token_hash
        lease.lease_expires_at = expires_at
        lease.updated_at = now
        return termination

    @staticmethod
    def _owns_start(lease: ChatSandboxLease | None, claim: StartClaim) -> bool:
        return bool(
            lease
            and lease.state == "starting"
            and lease.modal_sandbox_id is None
            and lease.lease_token_hash == claim.token_hash
            and lease.worker_generation == claim.worker_generation
        )

    @staticmethod
    def _owns_worker(lease: ChatSandboxLease | None, claim: WorkerClaim) -> bool:
        return bool(
            lease
            and lease.state == "busy"
            and lease.modal_sandbox_id == claim.sandbox_id
            and lease.lease_token_hash == claim.token_hash
            and lease.worker_generation == claim.worker_generation
        )

    @staticmethod
    def _owns_termination(
        lease: ChatSandboxLease | None, claim: TerminationClaim
    ) -> bool:
        return bool(
            lease
            and lease.state == "terminating"
            and lease.modal_sandbox_id == claim.sandbox_id
            and lease.lease_token_hash == claim.token_hash
            and lease.worker_generation == claim.worker_generation
        )
