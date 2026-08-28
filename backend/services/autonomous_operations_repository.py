"""Durable, content-free state and fencing for autonomous operators."""

from __future__ import annotations

import re
import uuid
from hashlib import sha256
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models.database import (
    AutonomousAction,
    AutonomousControlEvent,
    AutonomousIncidentAttempt,
    AutonomousOperatorState,
    AutonomousRepairLease,
    AutonomousRun,
    ChatProviderRuntimeState,
    ChatReliabilityBaseline,
)

_CONTROL_ROWS = ("global", "submissions", "cron_health", "chat_reliability")
_CODE = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,199}$")
_RESOURCE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,254}$")
_ACTOR = re.compile(r"^(?:admin|system):[A-Za-z0-9][A-Za-z0-9._@-]{0,199}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_SHA = re.compile(r"^[0-9a-f]{40}$")
_SECRET_PREFIXES = ("sk-", "hf_", "bearer", "eyj")


class Operator(StrEnum):
    SUBMISSIONS = "submissions"
    CRON_HEALTH = "cron_health"
    CHAT_RELIABILITY = "chat_reliability"


@dataclass(frozen=True, slots=True)
class RunContext:
    run_id: uuid.UUID
    operator: Operator
    dry_run: bool
    manifest_revision: str


@dataclass(frozen=True, slots=True)
class ControlState:
    manual_mode: bool
    enabled: dict[Operator, bool]
    revision: int


@dataclass(frozen=True, slots=True)
class RepairLease:
    lease_id: uuid.UUID
    owner_run_id: uuid.UUID
    expires_at: datetime


class AutonomousStateConflict(RuntimeError):
    """The control state changed after the caller read it."""


class ManualModeEnabled(RuntimeError):
    """Global manual mode blocked an autonomous mutation."""


class OperatorDisabled(RuntimeError):
    """The selected operator is not mutation-enabled."""


class DryRunMutation(RuntimeError):
    """A dry-run context attempted a mutating capability."""


class RepairLeaseUnavailable(RuntimeError):
    """Another live run owns the singleton source-repair lease."""


class StaleRepairLease(RuntimeError):
    """A release request did not match the current lease fencing tuple."""


class IncidentAttemptLimit(RuntimeError):
    """The fixed chat source-repair attempt budget is exhausted."""


Clock = Callable[[Session], datetime]


class AutonomousOperationsRepository:
    """Persistence boundary for operator controls and append-only audit data."""

    def __init__(self, *, clock: Clock | None = None):
        self._clock = clock or self._database_now

    @staticmethod
    def _database_now(db: Session) -> datetime:
        clock = (
            func.clock_timestamp()
            if db.bind is not None and db.bind.dialect.name == "postgresql"
            else func.current_timestamp()
        )
        value = db.scalar(select(clock))
        if not isinstance(value, datetime):
            raise RuntimeError("Database did not return a timestamp")
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value

    @staticmethod
    def _validate_code(value: str, *, label: str, max_length: int) -> None:
        if (
            len(value) > max_length
            or _CODE.fullmatch(value) is None
            or value.lower().startswith(_SECRET_PREFIXES)
        ):
            raise ValueError(f"{label} is invalid")

    @staticmethod
    def _validate_actor(actor: str) -> None:
        if _ACTOR.fullmatch(actor) is None:
            raise ValueError("Autonomous actor is invalid")

    @staticmethod
    def _state_digest(*parts: object) -> str:
        canonical = "\x1f".join(str(part) for part in parts)
        return sha256(canonical.encode()).hexdigest()

    def _append_control_event(
        self,
        db: Session,
        *,
        actor: str,
        event_kind: str,
        target: str,
        before_digest: str,
        after_digest: str,
        now: datetime,
    ) -> None:
        db.add(
            AutonomousControlEvent(
                id=uuid.uuid4(),
                actor=actor,
                event_kind=event_kind,
                target=target,
                before_digest=before_digest,
                after_digest=after_digest,
                created_at=now,
            )
        )

    def _ensure_control_rows(self, db: Session) -> None:
        for key in _CONTROL_ROWS:
            if db.get(AutonomousOperatorState, key) is None:
                db.add(
                    AutonomousOperatorState(
                        operator=key,
                        enabled=False,
                        manual_mode=key == "global",
                        revision=1,
                        updated_by="system:bootstrap",
                    )
                )
        db.flush()

    def get_control_state(self, db: Session) -> ControlState:
        self._ensure_control_rows(db)
        rows = {
            row.operator: row
            for row in db.scalars(select(AutonomousOperatorState)).all()
        }
        return ControlState(
            manual_mode=rows["global"].manual_mode,
            enabled={operator: rows[operator.value].enabled for operator in Operator},
            revision=rows["global"].revision,
        )

    def _locked_global_state(self, db: Session) -> AutonomousOperatorState:
        self._ensure_control_rows(db)
        return db.execute(
            select(AutonomousOperatorState)
            .where(AutonomousOperatorState.operator == "global")
            .with_for_update()
        ).scalar_one()

    @staticmethod
    def _require_revision(row: AutonomousOperatorState, expected_revision: int) -> None:
        if row.revision != expected_revision:
            raise AutonomousStateConflict("Autonomous control state is stale")

    def set_manual_mode(
        self,
        db: Session,
        *,
        enabled: bool,
        expected_revision: int,
        actor: str,
        now: datetime,
    ) -> ControlState:
        self._validate_actor(actor)
        if now.tzinfo is None:
            raise ValueError("Autonomous control timestamp is invalid")
        global_state = self._locked_global_state(db)
        self._require_revision(global_state, expected_revision)
        before_digest = self._state_digest("manual_mode", global_state.manual_mode)
        global_state.manual_mode = enabled
        global_state.revision += 1
        global_state.updated_by = actor
        global_state.updated_at = now
        self._append_control_event(
            db,
            actor=actor,
            event_kind="manual_mode",
            target="global",
            before_digest=before_digest,
            after_digest=self._state_digest("manual_mode", enabled),
            now=now,
        )
        db.flush()
        return self.get_control_state(db)

    def set_operator_enabled(
        self,
        db: Session,
        *,
        operator: Operator,
        enabled: bool,
        expected_revision: int,
        actor: str,
        now: datetime,
    ) -> ControlState:
        self._validate_actor(actor)
        if now.tzinfo is None:
            raise ValueError("Autonomous control timestamp is invalid")
        global_state = self._locked_global_state(db)
        self._require_revision(global_state, expected_revision)
        operator_state = db.execute(
            select(AutonomousOperatorState)
            .where(AutonomousOperatorState.operator == operator.value)
            .with_for_update()
        ).scalar_one()
        before_digest = self._state_digest(
            "operator_enabled", operator.value, operator_state.enabled
        )
        operator_state.enabled = enabled
        operator_state.updated_by = actor
        operator_state.updated_at = now
        global_state.revision += 1
        global_state.updated_by = actor
        global_state.updated_at = now
        self._append_control_event(
            db,
            actor=actor,
            event_kind="operator_enabled",
            target=operator.value,
            before_digest=before_digest,
            after_digest=self._state_digest(
                "operator_enabled", operator.value, enabled
            ),
            now=now,
        )
        db.flush()
        return self.get_control_state(db)

    def assert_mutation_allowed(self, db: Session, context: RunContext) -> None:
        if context.dry_run:
            raise DryRunMutation("Dry-run contexts cannot mutate")
        global_state = self._locked_global_state(db)
        operator_state = db.execute(
            select(AutonomousOperatorState)
            .where(AutonomousOperatorState.operator == context.operator.value)
            .with_for_update()
        ).scalar_one()
        if global_state.manual_mode:
            raise ManualModeEnabled("Global manual mode blocks autonomous mutations")
        if not operator_state.enabled:
            raise OperatorDisabled(f"{context.operator.value} operator is disabled")

    @staticmethod
    def _require_run_context(db: Session, context: RunContext) -> AutonomousRun:
        run = db.get(AutonomousRun, context.run_id)
        if (
            run is None
            or run.operator != context.operator.value
            or run.dry_run != context.dry_run
            or run.manifest_revision != context.manifest_revision
        ):
            raise ValueError("Autonomous run context mismatches durable identity")
        return run

    @staticmethod
    def _advisory_lock(db: Session, key: str) -> None:
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            db.execute(
                select(func.pg_advisory_xact_lock(func.hashtextextended(key, 0)))
            )

    def append_run(
        self,
        db: Session,
        *,
        context: RunContext,
        status: str,
        now: datetime,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: Decimal = Decimal("0"),
        result_digest: str | None = None,
    ) -> uuid.UUID:
        try:
            self._validate_code(
                context.manifest_revision,
                label="Manifest revision",
                max_length=128,
            )
        except ValueError:
            raise ValueError("Autonomous run is invalid") from None
        if (
            status
            not in {"completed", "rejected", "failed", "budget_exhausted", "cancelled"}
            or now.tzinfo is None
            or input_tokens < 0
            or output_tokens < 0
            or cost_usd < 0
            or (result_digest is not None and _DIGEST.fullmatch(result_digest) is None)
        ):
            raise ValueError("Autonomous run is invalid")
        db.add(
            AutonomousRun(
                id=context.run_id,
                operator=context.operator.value,
                dry_run=context.dry_run,
                manifest_revision=context.manifest_revision,
                status=status,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                result_digest=result_digest,
                created_at=now,
            )
        )
        db.flush()
        return context.run_id

    def append_action(
        self,
        db: Session,
        *,
        context: RunContext,
        capability: str,
        reason_code: str,
        resource_kind: str,
        resource_identifier: str,
        before_digest: str | None,
        after_digest: str | None,
        now: datetime,
    ) -> uuid.UUID:
        self.assert_mutation_allowed(db, context)
        for value, label, max_length in (
            (capability, "Capability", 64),
            (reason_code, "Reason code", 64),
            (resource_kind, "Resource kind", 64),
        ):
            self._validate_code(value, label=label, max_length=max_length)
        if (
            _RESOURCE_IDENTIFIER.fullmatch(resource_identifier) is None
            or resource_identifier.lower().startswith(_SECRET_PREFIXES)
            or now.tzinfo is None
            or (before_digest is not None and _DIGEST.fullmatch(before_digest) is None)
            or (after_digest is not None and _DIGEST.fullmatch(after_digest) is None)
        ):
            raise ValueError("Autonomous action is invalid")
        self._require_run_context(db, context)
        action_id = uuid.uuid4()
        db.add(
            AutonomousAction(
                id=action_id,
                run_id=context.run_id,
                operator=context.operator.value,
                capability=capability,
                reason_code=reason_code,
                resource_kind=resource_kind,
                resource_identifier=resource_identifier,
                before_digest=before_digest,
                after_digest=after_digest,
                created_at=now,
            )
        )
        db.flush()
        return action_id

    def acquire_repair_lease(
        self, db: Session, *, context: RunContext, ttl: timedelta
    ) -> RepairLease:
        if context.operator not in {Operator.CRON_HEALTH, Operator.CHAT_RELIABILITY}:
            raise ValueError("Operator is not eligible for source repair")
        self.assert_mutation_allowed(db, context)
        self._require_run_context(db, context)
        if not timedelta(seconds=30) <= ttl <= timedelta(hours=2):
            raise ValueError("Repair lease TTL is invalid")
        now = self._clock(db)
        self._advisory_lock(db, "autonomous:source-repair")
        row = db.execute(
            select(AutonomousRepairLease)
            .where(AutonomousRepairLease.singleton_key == "source_repair")
            .with_for_update()
        ).scalar_one_or_none()
        if row is not None and self._aware(row.expires_at) > now:
            if row.owner_run_id != context.run_id:
                raise RepairLeaseUnavailable("Source-repair lease is already owned")
            return RepairLease(
                row.lease_id, row.owner_run_id, self._aware(row.expires_at)
            )
        if row is not None:
            db.delete(row)
            db.flush()
        lease_id = uuid.uuid4()
        expires_at = now + ttl
        db.add(
            AutonomousRepairLease(
                singleton_key="source_repair",
                lease_id=lease_id,
                owner_run_id=context.run_id,
                owner_operator=context.operator.value,
                expires_at=expires_at,
                created_at=now,
            )
        )
        db.flush()
        return RepairLease(lease_id, context.run_id, expires_at)

    def release_repair_lease(
        self,
        db: Session,
        *,
        lease_id: uuid.UUID,
        owner_run_id: uuid.UUID,
    ) -> bool:
        row = db.execute(
            select(AutonomousRepairLease)
            .where(AutonomousRepairLease.singleton_key == "source_repair")
            .with_for_update()
        ).scalar_one_or_none()
        if row is None or row.lease_id != lease_id or row.owner_run_id != owner_run_id:
            raise StaleRepairLease("Repair lease fencing tuple is stale")
        db.delete(row)
        db.flush()
        return True

    def reserve_chat_repair_attempt(
        self, db: Session, *, context: RunContext, signature: str
    ) -> uuid.UUID:
        if context.operator != Operator.CHAT_RELIABILITY:
            raise ValueError("Only chat-reliability can reserve chat repair attempts")
        if _DIGEST.fullmatch(signature) is None:
            raise ValueError("Incident signature must be a server-generated digest")
        self.assert_mutation_allowed(db, context)
        self._require_run_context(db, context)
        self._advisory_lock(db, f"autonomous:chat-attempt:{signature}")
        now = self._clock(db)
        if self._count_chat_repair_attempts(db, signature=signature, now=now) >= 2:
            raise IncidentAttemptLimit("Chat repair attempt budget is exhausted")
        attempt_id = uuid.uuid4()
        db.add(
            AutonomousIncidentAttempt(
                id=attempt_id,
                run_id=context.run_id,
                operator=Operator.CHAT_RELIABILITY.value,
                signature=signature,
                attempted_at=now,
            )
        )
        db.flush()
        return attempt_id

    @staticmethod
    def _count_chat_repair_attempts(
        db: Session, *, signature: str, now: datetime
    ) -> int:
        return int(
            db.scalar(
                select(func.count())
                .select_from(AutonomousIncidentAttempt)
                .where(
                    AutonomousIncidentAttempt.operator
                    == Operator.CHAT_RELIABILITY.value,
                    AutonomousIncidentAttempt.signature == signature,
                    AutonomousIncidentAttempt.attempted_at > now - timedelta(hours=6),
                    AutonomousIncidentAttempt.attempted_at <= now,
                )
            )
            or 0
        )

    def count_chat_repair_attempts(self, db: Session, *, signature: str) -> int:
        if _DIGEST.fullmatch(signature) is None:
            raise ValueError("Incident signature must be a server-generated digest")
        return self._count_chat_repair_attempts(
            db, signature=signature, now=self._clock(db)
        )

    def qualify_chat_baseline(
        self,
        db: Session,
        *,
        sha: str,
        actor: str,
        expected_revision: int,
        now: datetime,
    ) -> ChatReliabilityBaseline:
        if _SHA.fullmatch(sha) is None or now.tzinfo is None:
            raise ValueError("Chat baseline qualification is invalid")
        self._validate_actor(actor)
        self._advisory_lock(db, "autonomous:chat-baseline")
        row = db.execute(
            select(ChatReliabilityBaseline)
            .where(ChatReliabilityBaseline.singleton.is_(True))
            .with_for_update()
        ).scalar_one_or_none()
        if row is None:
            if expected_revision != 0:
                raise AutonomousStateConflict("Chat baseline state is stale")
            before_digest = self._state_digest("chat_baseline", "absent")
            row = ChatReliabilityBaseline(singleton=True, revision=1)
            db.add(row)
        else:
            if row.revision != expected_revision:
                raise AutonomousStateConflict("Chat baseline state is stale")
            before_digest = self._state_digest("chat_baseline", row.sha, row.revision)
            row.revision += 1
        row.sha = sha
        row.qualified_by = actor
        row.qualified_at = now
        self._append_control_event(
            db,
            actor=actor,
            event_kind="chat_baseline",
            target="scalable-chat",
            before_digest=before_digest,
            after_digest=self._state_digest("chat_baseline", sha, row.revision),
            now=now,
        )
        db.flush()
        return row

    def set_chat_provider_state(
        self,
        db: Session,
        *,
        context: RunContext,
        environment: str,
        manifest_revision: str,
        expected_state_revision: int,
        active_provider: str,
        reason_code: str,
        now: datetime,
    ) -> ChatProviderRuntimeState:
        if context.operator != Operator.CHAT_RELIABILITY:
            raise ValueError("Only chat-reliability can change chat provider state")
        self.assert_mutation_allowed(db, context)
        self._require_run_context(db, context)
        if environment not in {"staging", "production"} or now.tzinfo is None:
            raise ValueError("Chat provider environment is invalid")
        for value, label, max_length in (
            (manifest_revision, "Provider revision", 128),
            (active_provider, "Active provider", 64),
            (reason_code, "Provider reason code", 64),
        ):
            self._validate_code(value, label=label, max_length=max_length)
        row = db.execute(
            select(ChatProviderRuntimeState)
            .where(ChatProviderRuntimeState.environment == environment)
            .with_for_update()
        ).scalar_one_or_none()
        if row is None:
            if expected_state_revision != 0:
                raise AutonomousStateConflict("Chat provider state is stale")
            before_digest = self._state_digest("provider", environment, "absent")
            row = ChatProviderRuntimeState(environment=environment, state_revision=1)
            db.add(row)
        else:
            if row.state_revision != expected_state_revision:
                raise AutonomousStateConflict("Chat provider state is stale")
            before_digest = self._state_digest(
                "provider",
                environment,
                row.manifest_revision,
                row.active_provider,
                row.state_revision,
            )
            row.state_revision += 1
        row.manifest_revision = manifest_revision
        row.active_provider = active_provider
        row.reason_code = reason_code
        row.updated_at = now
        db.flush()
        self.append_action(
            db,
            context=context,
            capability="switch_chat_provider",
            reason_code=reason_code,
            resource_kind="chat_provider",
            resource_identifier=environment,
            before_digest=before_digest,
            after_digest=self._state_digest(
                "provider",
                environment,
                manifest_revision,
                active_provider,
                row.state_revision,
            ),
            now=now,
        )
        return row
