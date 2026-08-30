import uuid
import asyncio
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from backend.config import Settings

from backend.models.database import (
    ChatQualificationEvidenceEvent,
    ChatQualificationScope,
    ChatSandboxComputeInterval,
    ChatTurnLatency,
)
from backend.services.chat_durable_qualification_evidence import (
    ChatDurableQualificationEvidenceService,
    ChatQualificationEvidenceRepository,
    QualificationEvidenceUnavailable,
    QUALIFICATION_STALE_SEAMS,
    record_qualification_event_safely,
)

START = datetime(2026, 8, 30, 12, tzinfo=UTC)
END = START + timedelta(minutes=1)


def _settings() -> Settings:
    return Settings(environment="staging", release_id="0123456789ab-staging")


@pytest.fixture
def engine():
    value = create_engine("sqlite+pysqlite:///:memory:")
    ChatTurnLatency.__table__.create(value)
    ChatSandboxComputeInterval.__table__.create(value)
    ChatQualificationScope.__table__.create(value)
    ChatQualificationEvidenceEvent.__table__.create(value)
    return value


SCOPE_ID = uuid.UUID("d0000000-0000-4000-8000-000000000001")


def _scope(
    *,
    scope_id: uuid.UUID = SCOPE_ID,
    run_id: str = "qualified-f32",
    profile: str = "32-functional-turns",
):
    return ChatQualificationScope(
        id=scope_id,
        run_id=run_id,
        profile=profile,
        app_release_id="0123456789ab-staging",
        window_started_at=START,
        expires_at=END + timedelta(hours=1),
    )


def _latency(
    index: int,
    *,
    run_id: str = "qualified-f32",
    scope_id: uuid.UUID = SCOPE_ID,
    workload: str | None = None,
    profile: str = "32-functional-turns",
):
    if workload is None:
        workload = "no_tool" if index < 16 else "read" if index < 24 else "bash"
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
        qualification_scope_id=scope_id,
        qualification_run_id=run_id,
        qualification_profile=profile,
        qualification_workload=workload,
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


def _add_valid_functional_evidence(
    db: Session,
    *,
    omit_eviction: int | None = None,
    add_no_tool_operation: bool = False,
) -> None:
    db.add(_scope())
    db.add_all(_latency(index) for index in range(32))
    db.add_all(
        _interval(index, started_at=START, terminal_at=END) for index in range(16, 32)
    )
    db.flush()
    repository = ChatQualificationEvidenceRepository()
    for index in range(32):
        item = _latency(index)
        repository.record(
            db,
            turn_id=item.turn_id,
            chat_session_id=item.chat_session_id,
            event_type="admitted_no_queue",
            occurred_at=START + timedelta(milliseconds=1),
        )
    for index in range(16, 32):
        item = _latency(index)
        for event_type in (
            "workspace_created" if index == 16 else "workspace_reused",
            "executor_started",
            *(() if index == omit_eviction else ("workspace_evicted",)),
        ):
            repository.record(
                db,
                turn_id=item.turn_id,
                chat_session_id=item.chat_session_id,
                event_type=event_type,
                operation_id=(
                    f"operation-{index}" if event_type == "executor_started" else None
                ),
                occurred_at=START + timedelta(seconds=2),
            )
    if add_no_tool_operation:
        item = _latency(0)
        repository.record(
            db,
            turn_id=item.turn_id,
            chat_session_id=item.chat_session_id,
            event_type="executor_started",
            operation_id="forbidden-no-tool-operation",
            occurred_at=START + timedelta(seconds=2),
        )


def test_exact_cohort_aggregates_cross_session_writes_and_clips_billed_lifetime(engine):
    with Session(engine) as first, first.begin():
        first.add(_scope())
        first.add_all(_latency(index) for index in range(32))
        first.add(
            _interval(
                16,
                started_at=START - timedelta(seconds=10),
                terminal_at=START + timedelta(seconds=50),
            )
        )
        first.add(
            _interval(17, started_at=START + timedelta(seconds=10), terminal_at=None)
        )
        first.add_all(
            _interval(index, started_at=START, terminal_at=END)
            for index in range(18, 32)
        )
    with Session(engine) as second, second.begin():
        repository = ChatQualificationEvidenceRepository()
        for index in range(32):
            latency = _latency(index)
            assert repository.record(
                second,
                turn_id=latency.turn_id,
                chat_session_id=latency.chat_session_id,
                event_type="admitted_no_queue",
                occurred_at=START + timedelta(milliseconds=1),
            )
        for index in range(16, 32):
            latency = _latency(index)
            assert repository.record(
                second,
                turn_id=latency.turn_id,
                chat_session_id=latency.chat_session_id,
                event_type="workspace_created" if index == 16 else "workspace_reused",
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
            assert repository.record(
                second,
                turn_id=latency.turn_id,
                chat_session_id=latency.chat_session_id,
                event_type="workspace_evicted",
                occurred_at=START + timedelta(seconds=3),
            )
        unrelated_scope_id = uuid.uuid4()
        second.add(_scope(scope_id=unrelated_scope_id, run_id="unrelated-f32"))
        unrelated = _latency(99, run_id="unrelated-f32", scope_id=unrelated_scope_id)
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
        service = ChatDurableQualificationEvidenceService(reader, now=lambda: END)
        with pytest.raises(QualificationEvidenceUnavailable, match="still open"):
            service.collect(scope_id=SCOPE_ID, settings=_settings())
        reader.rollback()
        interval = reader.get(
            ChatSandboxComputeInterval,
            reader.execute(
                select(ChatSandboxComputeInterval.id).where(
                    ChatSandboxComputeInterval.modal_sandbox_id == "sb-17"
                )
            ).scalar_one(),
        )
        interval.terminal_at = END
        reader.commit()
        evidence = service.collect(scope_id=SCOPE_ID, settings=_settings())

    assert evidence.admitted_turns == evidence.terminal_turns == 32
    assert evidence.executor_starts == 16
    assert evidence.duplicate_executor_starts == 0
    assert evidence.workspace_creates == 1
    assert evidence.workspace_reuses == 15
    assert evidence.workspace_evictions == 16
    assert evidence.stale_fences == 0
    assert evidence.billed_duration_ms == 940_000


def test_admission_profile_requires_exact_100_no_tool_denominator(engine):
    run_id = "qualified-a100"
    with Session(engine) as db, db.begin():
        db.add(_scope(run_id=run_id, profile="100-immediate-admission"))
        db.add_all(
            _latency(
                index,
                run_id=run_id,
                workload="no_tool",
                profile="100-immediate-admission",
            )
            for index in range(100)
        )
        db.flush()
        repository = ChatQualificationEvidenceRepository()
        for index in range(100):
            row = _latency(
                index,
                run_id=run_id,
                workload="no_tool",
                profile="100-immediate-admission",
            )
            repository.record(
                db,
                turn_id=row.turn_id,
                chat_session_id=row.chat_session_id,
                event_type="admitted_no_queue",
                occurred_at=START + timedelta(milliseconds=1),
            )

    with Session(engine) as db:
        evidence = ChatDurableQualificationEvidenceService(db, now=lambda: END).collect(
            scope_id=SCOPE_ID, settings=_settings()
        )
    assert evidence.admitted_turns == evidence.admission_denominator_events == 100
    assert evidence.executor_starts == evidence.workspace_creates == 0


def test_missing_cohort_refuses(engine):
    with Session(engine) as db:
        with pytest.raises(QualificationEvidenceUnavailable, match="unavailable"):
            ChatDurableQualificationEvidenceService(db, now=lambda: END).collect(
                scope_id=uuid.uuid4(), settings=_settings()
            )


def test_functional_cohort_rejects_executor_operations_concentrated_on_one_turn(engine):
    with Session(engine) as db, db.begin():
        _add_valid_functional_evidence(db)
        concentrated = _latency(16)
        for index in range(17, 32):
            item = _latency(index)
            db.query(ChatQualificationEvidenceEvent).filter_by(
                turn_id=item.turn_id, event_type="executor_started"
            ).delete()
            ChatQualificationEvidenceRepository().record(
                db,
                turn_id=concentrated.turn_id,
                chat_session_id=concentrated.chat_session_id,
                event_type="executor_started",
                operation_id=f"concentrated-{index}",
                occurred_at=START + timedelta(seconds=2),
            )

    with Session(engine) as db:
        with pytest.raises(QualificationEvidenceUnavailable, match="per-turn"):
            ChatDurableQualificationEvidenceService(db, now=lambda: END).collect(
                scope_id=SCOPE_ID, settings=_settings()
            )


@pytest.mark.parametrize(
    "corruption",
    ("no_tool_operation", "missing_eviction"),
)
def test_functional_cohort_rejects_per_turn_lifecycle_corruption(engine, corruption):
    with Session(engine) as db, db.begin():
        _add_valid_functional_evidence(
            db,
            omit_eviction=31 if corruption == "missing_eviction" else None,
            add_no_tool_operation=corruption == "no_tool_operation",
        )

    with Session(engine) as db:
        with pytest.raises(QualificationEvidenceUnavailable, match="per-turn"):
            ChatDurableQualificationEvidenceService(db, now=lambda: END).collect(
                scope_id=SCOPE_ID, settings=_settings()
            )


def test_exact_scope_teardown_is_isolated_and_idempotent(engine):
    with Session(engine) as db, db.begin():
        _add_valid_functional_evidence(db)
        db.query(ChatQualificationEvidenceEvent).filter_by(
            event_type="workspace_evicted"
        ).delete()
        for interval in db.query(ChatSandboxComputeInterval):
            interval.terminal_at = None

    class Manager:
        def __init__(self):
            self.sessions = []

        async def snapshot_and_terminate(self, session_id):
            self.sessions.append(session_id)
            with Session(engine) as db, db.begin():
                interval = db.scalar(
                    select(ChatSandboxComputeInterval).where(
                        ChatSandboxComputeInterval.chat_session_id == session_id
                    )
                )
                assert interval is not None
                interval.terminal_at = END
            return len(self.sessions) <= 16

    manager = Manager()
    with Session(engine) as db:
        service = ChatDurableQualificationEvidenceService(db, now=lambda: END)
        first = asyncio.run(
            service.teardown_scope(
                scope_id=SCOPE_ID, settings=_settings(), sandbox_manager=manager
            )
        )
        db.commit()
    with Session(engine) as db:
        service = ChatDurableQualificationEvidenceService(db, now=lambda: END)
        second = asyncio.run(
            service.teardown_scope(
                scope_id=SCOPE_ID, settings=_settings(), sandbox_manager=manager
            )
        )
        evictions = (
            db.query(ChatQualificationEvidenceEvent)
            .filter_by(event_type="workspace_evicted")
            .count()
        )

    expected_sessions = {_latency(index).chat_session_id for index in range(16, 32)}
    assert set(manager.sessions) == expected_sessions
    assert first == second
    assert first.expected_tool_turns == first.closed_intervals == 16
    assert evictions == 16


def test_qualification_evidence_migration_matches_content_free_model_contract():
    sql = (
        Path(__file__).parents[1]
        / "database/migrations/add_chat_qualification_evidence_events.sql"
    ).read_text()

    assert "chat_qualification_evidence_event_type_check" in sql
    assert "chat_qualification_evidence_operation_shape_check" in sql
    assert "idx_chat_qualification_evidence_session_time" in sql
    assert "idx_chat_qualification_evidence_turn_event" in sql
    assert (
        "REVOKE ALL ON chat_qualification_scopes, chat_qualification_evidence_events"
        in sql
    )
    assert "message" not in sql.lower()


def test_forward_repair_is_additive_ordered_idempotent_and_refuses_lossy_data():
    sql = (
        Path(__file__).parents[1]
        / "database/migrations/repair_chat_qualification_evidence_contract.sql"
    ).read_text()

    child_drop = sql.index(
        "DROP CONSTRAINT IF EXISTS chat_qualification_evidence_scope_fkey"
    )
    parent_repair = sql.index(
        "DROP CONSTRAINT IF EXISTS chat_qualification_scopes_pkey"
    )
    assert child_drop < parent_repair
    assert "ADD COLUMN IF NOT EXISTS qualification_workload VARCHAR(16)" in sql
    assert "PRIMARY KEY (id)" in sql
    assert "RAISE EXCEPTION 'refusing populated qualification column conversion" in sql
    assert "RAISE EXCEPTION 'refusing lossy qualification" in sql
    assert "DROP TABLE" not in sql
    assert "DELETE FROM" not in sql
    assert "DROP INDEX IF EXISTS" in sql


def test_expected_evidence_store_outage_is_non_disruptive_but_programming_error_is_visible(
    monkeypatch,
):
    import backend.services.chat_durable_qualification_evidence as evidence_module

    monkeypatch.setattr(
        evidence_module,
        "record_qualification_event",
        lambda **_kwargs: (_ for _ in ()).throw(
            OperationalError("insert", {}, OSError("database unavailable"))
        ),
    )
    assert record_qualification_event_safely(event_type="stale_fence") is False

    monkeypatch.setattr(
        evidence_module,
        "record_qualification_event",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("programming defect")),
    )
    with pytest.raises(ValueError, match="programming defect"):
        record_qualification_event_safely(event_type="stale_fence")


@pytest.mark.parametrize("seam", QUALIFICATION_STALE_SEAMS, ids=lambda seam: seam.name)
def test_stale_seam_inventory_is_closed_and_has_a_durable_emitter(seam):
    assert seam.name in {
        "gateway_turn_claim",
        "workspace_pre_acquire_turn_claim",
        "workspace_post_health_turn_claim",
        "workspace_release_ownership",
        "external_reservation_claim",
        "external_worker_claim",
    }
    assert seam.rejection
    assert seam.emitter


def test_scope_collision_and_bounded_expiry_cleanup(engine):
    settings = _settings()
    with Session(engine) as db:
        service = ChatDurableQualificationEvidenceService(db, now=lambda: START)
        created = service.create_scope(
            run_id="one-f32", profile="32-functional-turns", settings=settings
        )
        db.commit()
        assert created.app_release_id == settings.release_id
        with pytest.raises(QualificationEvidenceUnavailable, match="already used"):
            service.create_scope(
                run_id="one-f32",
                profile="32-functional-turns",
                settings=settings,
            )
        db.rollback()

    with Session(engine) as db, db.begin():
        db.add_all(
            _scope(scope_id=uuid.uuid4(), run_id=f"expired-{index}")
            for index in range(3)
        )
    with Session(engine) as db, db.begin():
        deleted = ChatDurableQualificationEvidenceService(
            db, now=lambda: END + timedelta(hours=2)
        ).cleanup_expired(limit=2)
        assert deleted == 2
        assert db.query(ChatQualificationScope).count() == 2
    with pytest.raises(ValueError, match="limit"):
        ChatDurableQualificationEvidenceService(Session(engine)).cleanup_expired(
            limit=1001
        )
