import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.models.database import (
    ChatQualificationEvidenceEvent,
    ChatSandboxComputeInterval,
    ChatTurnLatency,
)
from backend.services.chat_durable_qualification_evidence import (
    ChatDurableQualificationEvidenceService,
    ChatQualificationEvidenceRepository,
    QualificationEvidenceUnavailable,
)

START = datetime(2026, 8, 30, 12, tzinfo=UTC)
END = START + timedelta(minutes=1)


@pytest.fixture
def engine():
    value = create_engine("sqlite+pysqlite:///:memory:")
    ChatTurnLatency.__table__.create(value)
    ChatSandboxComputeInterval.__table__.create(value)
    ChatQualificationEvidenceEvent.__table__.create(value)
    return value


def _latency(index: int, *, run_id: str = "qualified-f32"):
    return ChatTurnLatency(
        turn_id=uuid.UUID(f"a0000000-0000-4000-8000-{index:012x}"),
        request_id=uuid.UUID(f"b0000000-0000-4000-8000-{index:012x}"),
        chat_session_id=uuid.UUID(f"c0000000-0000-4000-8000-{index:012x}"),
        traffic_class="new_chat",
        execution_backend="modal_cli",
        agent_harness="pi",
        acquisition_outcome="created" if index == 0 else "reused_session",
        model_route="model:test",
        app_release_id="0123456789ab-staging",
        qualification_run_id=run_id,
        qualification_scenario="reliability",
        terminal_status="complete",
        admitted_at=START,
    )


def _interval(index: int, *, started_at: datetime, terminal_at: datetime | None):
    return ChatSandboxComputeInterval(
        id=uuid.uuid4(),
        modal_sandbox_id=f"sb-{index}",
        environment="staging",
        modal_app="paperswithcode",
        app_release_id="0123456789ab-staging",
        image_version="sha256:" + "a" * 64,
        worker_generation="generation-a",
        origin="direct",
        chat_session_id=uuid.UUID(f"c0000000-0000-4000-8000-{index:012x}"),
        cpu_request_millicores=1000,
        cpu_limit_millicores=1000,
        memory_request_mib=1024,
        memory_limit_mib=1024,
        reserved_at=started_at,
        provider_created_at=started_at,
        terminal_at=terminal_at,
        billing_cycle=date(2026, 8, 1),
    )


def test_exact_cohort_aggregates_cross_session_writes_and_clips_billed_lifetime(engine):
    with Session(engine) as first, first.begin():
        first.add_all(_latency(index) for index in range(32))
        first.add(
            _interval(
                0,
                started_at=START - timedelta(seconds=10),
                terminal_at=START + timedelta(seconds=50),
            )
        )
        first.add(
            _interval(1, started_at=START + timedelta(seconds=10), terminal_at=None)
        )
    with Session(engine) as second, second.begin():
        repository = ChatQualificationEvidenceRepository()
        for index in range(16):
            latency = _latency(index)
            assert repository.record(
                second,
                turn_id=latency.turn_id,
                chat_session_id=latency.chat_session_id,
                event_type="workspace_created" if index == 0 else "workspace_reused",
                occurred_at=START + timedelta(seconds=1),
            )

            assert repository.record(
                second,
                turn_id=latency.turn_id,
                chat_session_id=latency.chat_session_id,
                event_type="executor_started",
                operation_id=f"operation-{index}",
                occurred_at=START + timedelta(seconds=2),
            )
        unrelated = _latency(99, run_id="unrelated-f32")
        second.add(unrelated)
        second.flush()
        assert repository.record(
            second,
            turn_id=unrelated.turn_id,
            chat_session_id=unrelated.chat_session_id,
            event_type="stale_fence",
            occurred_at=START + timedelta(seconds=3),
        )

    with Session(engine) as reader:
        evidence = ChatDurableQualificationEvidenceService(reader).collect(
            run_id="qualified-f32",
            profile="32-functional-turns",
            window_started_at=START,
            window_ended_at=END,
        )

    assert evidence.admitted_turns == evidence.terminal_turns == 32
    assert evidence.executor_starts == 16
    assert evidence.duplicate_executor_starts == 0
    assert evidence.workspace_creates == 1
    assert evidence.workspace_reuses == 15
    assert evidence.workspace_evictions == evidence.stale_fences == 0
    assert evidence.billed_duration_ms == 100_000


def test_duplicate_executor_start_is_counted_and_missing_cohort_refuses(engine):
    with Session(engine) as db, db.begin():
        db.add_all(_latency(index) for index in range(32))
        repository = ChatQualificationEvidenceRepository()
        db.flush()
        latency = _latency(0)
        for _ in range(2):
            repository.record(
                db,
                turn_id=latency.turn_id,
                chat_session_id=latency.chat_session_id,
                event_type="executor_started",
                operation_id="same-operation",
                occurred_at=START + timedelta(seconds=1),
            )

    with Session(engine) as db:
        evidence = ChatDurableQualificationEvidenceService(db).collect(
            run_id="qualified-f32",
            profile="32-functional-turns",
            window_started_at=START,
            window_ended_at=END,
        )
        assert evidence.executor_starts == 2
        assert evidence.duplicate_executor_starts == 1
        with pytest.raises(QualificationEvidenceUnavailable, match="incomplete"):
            ChatDurableQualificationEvidenceService(db).collect(
                run_id="missing-a100",
                profile="100-immediate-admission",
                window_started_at=START,
                window_ended_at=END,
            )


def test_qualification_evidence_migration_matches_content_free_model_contract():
    sql = (
        Path(__file__).parents[1]
        / "database/migrations/add_chat_qualification_evidence_events.sql"
    ).read_text()

    assert "chat_qualification_evidence_event_type_check" in sql
    assert "chat_qualification_evidence_operation_shape_check" in sql
    assert "idx_chat_qualification_evidence_session_time" in sql
    assert "idx_chat_qualification_evidence_turn_event" in sql
    assert "REVOKE ALL ON chat_qualification_evidence_events" in sql
    assert "message" not in sql.lower()
