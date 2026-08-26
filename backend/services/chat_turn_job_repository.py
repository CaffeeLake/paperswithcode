"""PostgreSQL-backed durable ownership and fencing for research chat turns."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Callable

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.models.database import ChatTurnJob

NONTERMINAL_STATES = frozenset(
    {"admitted", "leased", "running", "waiting_model", "waiting_tool", "cancelling"}
)
TERMINAL_STATES = frozenset({"completed", "failed", "interrupted"})
_CLAIMED_STATES = NONTERMINAL_STATES - {"admitted"}
_TRANSITIONS = {
    "leased": frozenset({"running", "cancelling"}),
    "running": frozenset({"waiting_model", "waiting_tool", "cancelling"}),
    "waiting_model": frozenset({"running", "cancelling"}),
    "waiting_tool": frozenset({"running", "cancelling"}),
    "cancelling": frozenset(),
}
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_FAILURE_CODE = re.compile(r"^[a-z0-9][a-z0-9_]{0,63}$")


class TurnJobError(RuntimeError):
    """Base class for typed durable turn-job outcomes."""


class AdmissionRejected(TurnJobError):
    code: str


class AccountBusy(AdmissionRejected):
    code = "account_busy"


class ChatOverload(AdmissionRejected):
    code = "chat_overload"


class IdempotencyMismatch(TurnJobError):
    """A turn or request identifier was reused with different identity."""


class TurnNotClaimable(TurnJobError):
    """The exact durable turn cannot be claimed from its current state."""


class StaleTurnClaim(TurnJobError):
    """A post-claim mutation did not carry the exact current fencing tuple."""


class InvalidTurnTransition(TurnJobError):
    """A claimed turn requested an invalid state transition."""


@dataclass(frozen=True, slots=True)
class TurnLeaseClaim:
    turn_id: uuid.UUID
    worker_id: str
    worker_generation: int
    lease_generation: int


@dataclass(frozen=True, slots=True)
class TurnAdmission:
    job: ChatTurnJob
    created: bool


AdvisoryLocker = Callable[[Session, str], None]


class ChatTurnJobRepository:
    """Persist one content-free job per turn with PostgreSQL fencing semantics."""

    def __init__(self, *, advisory_locker: AdvisoryLocker | None = None):
        self._advisory_locker = advisory_locker or self._lock_advisory_key

    @staticmethod
    def _lock_advisory_key(db: Session, key: str) -> None:
        db.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(key, 0))))

    def load_by_turn(
        self, db: Session, turn_id: uuid.UUID, *, lock: bool = False
    ) -> ChatTurnJob | None:
        query = select(ChatTurnJob).where(ChatTurnJob.turn_id == turn_id)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        return db.execute(query).scalar_one_or_none()

    def load_by_request(
        self, db: Session, request_id: str, *, lock: bool = False
    ) -> ChatTurnJob | None:
        query = select(ChatTurnJob).where(ChatTurnJob.request_id == request_id)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        return db.execute(query).scalar_one_or_none()

    def admit(
        self,
        db: Session,
        *,
        turn_id: uuid.UUID,
        chat_session_id: uuid.UUID,
        hf_user_id: str,
        request_id: str,
        revision: int,
        dispatch_class: str,
        dispatch_route: str,
        app_release_id: str,
        worker_contract_version: str,
        now: datetime,
        emergency_capacity: int,
    ) -> TurnAdmission:
        self._validate_admission(
            hf_user_id=hf_user_id,
            request_id=request_id,
            revision=revision,
            dispatch_class=dispatch_class,
            dispatch_route=dispatch_route,
            app_release_id=app_release_id,
            worker_contract_version=worker_contract_version,
            now=now,
            emergency_capacity=emergency_capacity,
        )
        # This order is shared with the existing chat admission path. Both are
        # transaction-scoped locks, so count-then-insert remains atomic in PG.
        self._advisory_locker(db, f"chat-user:{hf_user_id}")
        self._advisory_locker(db, "chat-global-active-turns")

        matches = list(
            db.execute(
                select(ChatTurnJob)
                .where(
                    or_(
                        ChatTurnJob.turn_id == turn_id,
                        ChatTurnJob.request_id == request_id,
                    )
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            ).scalars()
        )
        if matches:
            if len(matches) != 1 or not self._matches_admission(
                matches[0],
                turn_id=turn_id,
                chat_session_id=chat_session_id,
                hf_user_id=hf_user_id,
                request_id=request_id,
                revision=revision,
                dispatch_class=dispatch_class,
                dispatch_route=dispatch_route,
                app_release_id=app_release_id,
                worker_contract_version=worker_contract_version,
            ):
                raise IdempotencyMismatch(
                    "Turn/request idempotency identity mismatches"
                )
            return TurnAdmission(matches[0], created=False)

        owner_active = db.scalar(
            select(func.count())
            .select_from(ChatTurnJob)
            .where(
                ChatTurnJob.hf_user_id == hf_user_id,
                ChatTurnJob.state.in_(NONTERMINAL_STATES),
            )
        )
        if owner_active:
            raise AccountBusy("This account already has a nonterminal turn")
        active_total = db.scalar(
            select(func.count())
            .select_from(ChatTurnJob)
            .where(ChatTurnJob.state.in_(NONTERMINAL_STATES))
        )
        if (active_total or 0) >= emergency_capacity:
            raise ChatOverload("Emergency chat capacity is full")

        job = ChatTurnJob(
            turn_id=turn_id,
            chat_session_id=chat_session_id,
            hf_user_id=hf_user_id,
            request_id=request_id,
            revision=revision,
            dispatch_class=dispatch_class,
            dispatch_route=dispatch_route,
            state="admitted",
            app_release_id=app_release_id,
            worker_contract_version=worker_contract_version,
            admitted_at=now,
        )
        db.add(job)
        db.flush()
        return TurnAdmission(job, created=True)

    def claim(
        self,
        db: Session,
        *,
        turn_id: uuid.UUID,
        worker_id: str,
        worker_generation: int,
        now: datetime,
        lease_seconds: int,
    ) -> TurnLeaseClaim:
        if (
            _IDENTIFIER.fullmatch(worker_id) is None
            or worker_generation <= 0
            or lease_seconds <= 0
            or now.tzinfo is None
        ):
            raise ValueError("Turn claim is invalid")
        job = self.load_by_turn(db, turn_id, lock=True)
        if job is None or job.state != "admitted":
            raise TurnNotClaimable("Turn is not admitted")
        job.worker_id = worker_id
        job.worker_generation = worker_generation
        job.lease_generation = (job.lease_generation or 0) + 1
        job.state = "leased"
        job.dispatched_at = now
        job.heartbeat_at = now
        job.lease_expires_at = now + timedelta(seconds=lease_seconds)
        db.flush()
        return self._claim_for(job)

    def heartbeat(
        self,
        db: Session,
        *,
        claim: TurnLeaseClaim,
        now: datetime,
        lease_seconds: int,
    ) -> ChatTurnJob:
        if now.tzinfo is None or lease_seconds <= 0:
            raise ValueError("Turn heartbeat is invalid")
        job = self._load_claimed(db, claim)
        if job.state not in _CLAIMED_STATES or self._lease_expired(job, now):
            raise StaleTurnClaim("Turn lease is no longer live")
        job.heartbeat_at = now
        job.lease_expires_at = now + timedelta(seconds=lease_seconds)
        db.flush()
        return job

    def transition(
        self,
        db: Session,
        *,
        claim: TurnLeaseClaim,
        state: str,
        now: datetime,
        last_agent_session_id: uuid.UUID | None = None,
        last_resume_boundary_id: str | None = None,
    ) -> ChatTurnJob:
        if now.tzinfo is None:
            raise ValueError("Turn transition timestamp is invalid")
        job = self._load_claimed(db, claim)
        if self._lease_expired(job, now):
            raise StaleTurnClaim("Turn lease is no longer live")
        if state not in _TRANSITIONS.get(job.state, frozenset()):
            raise InvalidTurnTransition(f"Cannot transition {job.state} to {state}")
        job.state = state
        if state == "running" and job.started_at is None:
            job.started_at = now
        job.heartbeat_at = now
        if last_agent_session_id is not None:
            job.last_agent_session_id = last_agent_session_id
        if last_resume_boundary_id is not None:
            job.last_resume_boundary_id = last_resume_boundary_id
        db.flush()
        return job

    def write_terminal(
        self,
        db: Session,
        *,
        claim: TurnLeaseClaim,
        state: str,
        now: datetime,
        failure_code: str | None = None,
        last_agent_session_id: uuid.UUID | None = None,
        last_resume_boundary_id: str | None = None,
    ) -> ChatTurnJob:
        if state not in TERMINAL_STATES or now.tzinfo is None:
            raise ValueError("Terminal turn state is invalid")
        if failure_code is not None and _FAILURE_CODE.fullmatch(failure_code) is None:
            raise ValueError("Turn failure code is not sanitized")
        if state == "completed" and failure_code is not None:
            raise ValueError("Completed turn cannot have a failure code")
        job = self._load_claimed(db, claim)
        if job.state in TERMINAL_STATES:
            if job.state != state or job.failure_code != failure_code:
                raise InvalidTurnTransition("Terminal turn state is immutable")
            return job
        if job.state not in _CLAIMED_STATES:
            raise InvalidTurnTransition("Only a claimed turn can become terminal")
        if self._lease_expired(job, now):
            raise StaleTurnClaim("Turn lease is no longer live")
        job.state = state
        job.failure_code = failure_code
        job.terminal_at = now
        job.heartbeat_at = now
        job.lease_expires_at = None
        if last_agent_session_id is not None:
            job.last_agent_session_id = last_agent_session_id
        if last_resume_boundary_id is not None:
            job.last_resume_boundary_id = last_resume_boundary_id
        db.flush()
        return job

    def interrupt_expired(self, db: Session, *, now: datetime, limit: int = 100) -> int:
        if now.tzinfo is None or limit <= 0:
            raise ValueError("Expiry sweep is invalid")
        jobs = list(
            db.execute(
                select(ChatTurnJob)
                .where(
                    ChatTurnJob.state.in_(_CLAIMED_STATES),
                    ChatTurnJob.lease_expires_at <= now,
                )
                .order_by(ChatTurnJob.lease_expires_at, ChatTurnJob.turn_id)
                .limit(limit)
                .with_for_update(skip_locked=True)
                .execution_options(populate_existing=True)
            ).scalars()
        )
        for job in jobs:
            job.state = "interrupted"
            job.failure_code = "lease_expired"
            job.terminal_at = now
            job.heartbeat_at = now
            job.lease_expires_at = None
        db.flush()
        return len(jobs)

    def _load_claimed(self, db: Session, claim: TurnLeaseClaim) -> ChatTurnJob:
        job = self.load_by_turn(db, claim.turn_id, lock=True)
        if job is None or self._claim_for(job) != claim:
            raise StaleTurnClaim("Turn claim was fenced")
        return job

    @staticmethod
    def _lease_expired(job: ChatTurnJob, now: datetime) -> bool:
        expires_at = job.lease_expires_at
        if expires_at is None:
            return True
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return expires_at <= now

    @staticmethod
    def _claim_for(job: ChatTurnJob) -> TurnLeaseClaim:
        if (
            job.worker_id is None
            or job.worker_generation is None
            or job.lease_generation is None
        ):
            raise StaleTurnClaim("Turn has no durable claim")
        return TurnLeaseClaim(
            turn_id=job.turn_id,
            worker_id=job.worker_id,
            worker_generation=job.worker_generation,
            lease_generation=job.lease_generation,
        )

    @staticmethod
    def _matches_admission(job: ChatTurnJob, **expected: object) -> bool:
        return all(getattr(job, name) == value for name, value in expected.items())

    @staticmethod
    def _validate_admission(**values: object) -> None:
        now = values["now"]
        if (
            not values["hf_user_id"]
            or len(values["hf_user_id"]) > 255
            or not values["request_id"]
            or len(values["request_id"]) > 200
            or values["revision"] <= 0
            or _IDENTIFIER.fullmatch(values["dispatch_class"]) is None
            or not values["dispatch_route"]
            or len(values["dispatch_route"]) > 255
            or not values["app_release_id"]
            or len(values["app_release_id"]) > 255
            or _IDENTIFIER.fullmatch(values["worker_contract_version"]) is None
            or not isinstance(now, datetime)
            or now.tzinfo is None
            or values["emergency_capacity"] <= 0
        ):
            raise ValueError("Turn admission is invalid")
