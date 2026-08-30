"""Durable, cohort-scoped evidence for protected external-Pi qualification."""

from __future__ import annotations

import hashlib
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import (
    ChatQualificationEvidenceEvent,
    ChatSandboxComputeInterval,
    ChatTurnLatency,
)

QUALIFICATION_PROFILES = {
    "32-functional-turns": 32,
    "100-immediate-admission": 100,
}
QUALIFICATION_EVENT_TYPES = frozenset(
    {
        "executor_started",
        "stale_fence",
        "queued",
        "workspace_created",
        "workspace_reused",
        "workspace_evicted",
    }
)


def _as_utc(value: datetime) -> datetime:
    """Normalize SQLite's timezone-naive test values and PostgreSQL timestamps."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class QualificationEvidenceUnavailable(RuntimeError):
    """The requested exact cohort does not have complete durable evidence."""


@dataclass(frozen=True, slots=True)
class DurableQualificationEvidence:
    expected_users: int
    admitted_turns: int
    terminal_turns: int
    queued_states: int
    stale_fences: int
    executor_starts: int
    duplicate_executor_starts: int
    workspace_creates: int
    workspace_reuses: int
    workspace_evictions: int
    billed_duration_ms: int
    source: str = "durable_qualification_records"


class ChatQualificationEvidenceRepository:
    def record(
        self,
        db: Session,
        *,
        turn_id: uuid.UUID,
        chat_session_id: uuid.UUID,
        event_type: str,
        operation_id: str | None = None,
        occurred_at: datetime | None = None,
    ) -> bool:
        if event_type not in QUALIFICATION_EVENT_TYPES:
            raise ValueError("qualification evidence event is invalid")
        if (event_type == "executor_started") != bool(operation_id):
            raise ValueError("qualification executor evidence is invalid")
        qualified = db.execute(
            select(ChatTurnLatency.turn_id).where(
                ChatTurnLatency.turn_id == turn_id,
                ChatTurnLatency.chat_session_id == chat_session_id,
                ChatTurnLatency.qualification_run_id.is_not(None),
                ChatTurnLatency.qualification_scenario == "reliability",
            )
        ).scalar_one_or_none()
        if qualified is None:
            return False
        db.add(
            ChatQualificationEvidenceEvent(
                id=uuid.uuid4(),
                turn_id=turn_id,
                chat_session_id=chat_session_id,
                event_type=event_type,
                operation_digest=(
                    hashlib.sha256(operation_id.encode()).hexdigest()
                    if operation_id is not None
                    else None
                ),
                occurred_at=occurred_at or datetime.now(UTC),
            )
        )
        return True


def record_qualification_event(**kwargs) -> bool:
    with db_manager.session_local() as db, db.begin():
        return ChatQualificationEvidenceRepository().record(db, **kwargs)


class ChatDurableQualificationEvidenceService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def collect(
        self,
        *,
        run_id: str,
        profile: str,
        window_started_at: datetime,
        window_ended_at: datetime,
    ) -> DurableQualificationEvidence:
        expected_users = QUALIFICATION_PROFILES.get(profile)
        if (
            expected_users is None
            or not run_id
            or len(run_id) > 64
            or window_started_at.tzinfo is None
            or window_ended_at.tzinfo is None
            or window_ended_at <= window_started_at
        ):
            raise QualificationEvidenceUnavailable(
                "qualification evidence scope is invalid"
            )
        latency_rows = self.db.execute(
            select(
                ChatTurnLatency.turn_id,
                ChatTurnLatency.chat_session_id,
                ChatTurnLatency.terminal_status,
            ).where(
                ChatTurnLatency.qualification_run_id == run_id,
                ChatTurnLatency.qualification_scenario == "reliability",
            )
        ).all()
        session_ids = {row.chat_session_id for row in latency_rows}
        turn_ids = {row.turn_id for row in latency_rows}
        if len(latency_rows) != expected_users or len(session_ids) != expected_users:
            raise QualificationEvidenceUnavailable(
                "qualification cohort evidence is incomplete"
            )
        terminal_turns = sum(row.terminal_status == "complete" for row in latency_rows)
        if terminal_turns != expected_users:
            raise QualificationEvidenceUnavailable(
                "qualification terminal evidence is incomplete"
            )

        events = self.db.execute(
            select(
                ChatQualificationEvidenceEvent.turn_id,
                ChatQualificationEvidenceEvent.event_type,
                ChatQualificationEvidenceEvent.operation_digest,
            ).where(
                ChatQualificationEvidenceEvent.chat_session_id.in_(session_ids),
                ChatQualificationEvidenceEvent.turn_id.in_(turn_ids),
                ChatQualificationEvidenceEvent.occurred_at >= window_started_at,
                ChatQualificationEvidenceEvent.occurred_at <= window_ended_at,
            )
        ).all()
        event_counts = Counter(row.event_type for row in events)
        operations = Counter(
            (row.turn_id, row.operation_digest)
            for row in events
            if row.event_type == "executor_started"
        )
        duplicate_executor_starts = sum(count - 1 for count in operations.values())

        intervals = self.db.execute(
            select(
                ChatSandboxComputeInterval.reserved_at,
                ChatSandboxComputeInterval.provider_created_at,
                ChatSandboxComputeInterval.terminal_at,
            ).where(ChatSandboxComputeInterval.chat_session_id.in_(session_ids))
        ).all()
        billed_duration_ms = 0
        for interval in intervals:
            started_at = _as_utc(interval.provider_created_at or interval.reserved_at)
            ended_at = _as_utc(interval.terminal_at or window_ended_at)
            overlap_start = max(started_at, window_started_at)
            overlap_end = min(ended_at, window_ended_at)
            if overlap_end > overlap_start:
                billed_duration_ms += round(
                    (overlap_end - overlap_start).total_seconds() * 1_000
                )

        return DurableQualificationEvidence(
            expected_users=expected_users,
            admitted_turns=len(latency_rows),
            terminal_turns=terminal_turns,
            queued_states=event_counts["queued"],
            stale_fences=event_counts["stale_fence"],
            executor_starts=event_counts["executor_started"],
            duplicate_executor_starts=duplicate_executor_starts,
            workspace_creates=event_counts["workspace_created"],
            workspace_reuses=event_counts["workspace_reused"],
            workspace_evictions=event_counts["workspace_evicted"],
            billed_duration_ms=billed_duration_ms,
        )
