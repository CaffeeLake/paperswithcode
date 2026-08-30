import uuid
import asyncio
import os
import threading
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy import text
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
    record_qualification_event_safely,
)
from backend.services.runtime_validation import (
    validate_qualification_evidence_schema,
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
                operation_kind=(
                    ("read" if index < 24 else "bash")
                    if event_type == "executor_started"
                    else None
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
            operation_kind="read",
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
                operation_kind="read" if index < 24 else "bash",
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
                operation_kind="read" if index < 24 else "bash",
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


@pytest.mark.parametrize("wrong_kind", ("read", "bash"))
def test_functional_cohort_rejects_executor_kind_that_does_not_match_workload(
    engine, wrong_kind
):
    with Session(engine) as db, db.begin():
        _add_valid_functional_evidence(db)
        target = _latency(24 if wrong_kind == "read" else 16)
        event = db.scalar(
            select(ChatQualificationEvidenceEvent).where(
                ChatQualificationEvidenceEvent.turn_id == target.turn_id,
                ChatQualificationEvidenceEvent.event_type == "executor_started",
            )
        )
        event.operation_kind = wrong_kind

    with Session(engine) as db:
        with pytest.raises(QualificationEvidenceUnavailable, match="operation kind"):
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
    lock_requests = []

    class LockedService(ChatDurableQualificationEvidenceService):
        def require_active_scope(self, scope_id, *, settings, lock=False):
            lock_requests.append(lock)
            return super().require_active_scope(scope_id, settings=settings, lock=lock)

    with Session(engine) as db:
        service = LockedService(db, now=lambda: END)
        first = asyncio.run(
            service.teardown_scope(
                scope_id=SCOPE_ID, settings=_settings(), sandbox_manager=manager
            )
        )
        db.commit()
    with Session(engine) as db:
        service = LockedService(db, now=lambda: END)
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
    assert lock_requests == [True, True]
    assert first.expected_tool_turns == first.closed_intervals == 16
    assert evictions == 16


@pytest.mark.parametrize("event_type", ("stale_fence", "workspace_evicted"))
def test_scope_turn_fence_events_are_atomically_unique(engine, event_type):
    from sqlalchemy.exc import IntegrityError

    with Session(engine) as db, db.begin():
        db.add(_scope())
        db.add(_latency(16))
    row = _latency(16)
    with Session(engine) as db:
        db.add_all(
            ChatQualificationEvidenceEvent(
                id=uuid.uuid4(),
                qualification_scope_id=SCOPE_ID,
                turn_id=row.turn_id,
                chat_session_id=row.chat_session_id,
                event_type=event_type,
                occurred_at=START,
            )
            for _ in range(2)
        )
        with pytest.raises(IntegrityError):
            db.flush()


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
    create_events = sql.split(
        "CREATE TABLE IF NOT EXISTS chat_qualification_evidence_events (", 1
    )[1].split(");", 1)[0]
    assert " REFERENCES " not in create_events


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


def test_postgresql_fresh_evidence_catalog_and_repair_are_exact_and_idempotent():
    url = os.getenv("PWC_QUALIFICATION_TEST_DATABASE_URL")
    if not url:
        pytest.skip("explicit disposable qualification PostgreSQL URL is required")
    configured = create_engine(url)
    if configured.dialect.name != "postgresql" or not configured.url.database.endswith(
        "_test"
    ):
        pytest.fail("qualification catalog proof requires a disposable test DB")
    database_name = f"pwc_qualification_catalog_{uuid.uuid4().hex}_test"
    admin = create_engine(
        configured.url.set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    initial_sql = (
        Path(__file__).parents[1]
        / "database/migrations/add_chat_qualification_evidence_events.sql"
    ).read_text()
    repair_sql = (
        Path(__file__).parents[1]
        / "database/migrations/repair_chat_qualification_evidence_contract.sql"
    ).read_text()
    database = None
    try:
        with admin.connect() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
        database = create_engine(configured.url.set(database=database_name))
        with database.begin() as connection:
            connection.exec_driver_sql(
                """
                DO $$ BEGIN
                  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'paperswithcode_user') THEN
                    CREATE ROLE paperswithcode_user;
                  END IF;
                  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging') THEN
                    CREATE ROLE pwc_staging;
                  END IF;
                END $$;
                CREATE TABLE chat_sessions (id UUID PRIMARY KEY);
                CREATE TABLE chat_turn_jobs (turn_id UUID PRIMARY KEY);
                CREATE TABLE chat_turn_latency (
                  turn_id UUID PRIMARY KEY, admitted_at TIMESTAMPTZ NOT NULL
                );
                """
            )
        for _ in range(2):
            with database.connect() as connection:
                connection.exec_driver_sql(initial_sql)

        with database.connect() as connection:
            constraints = {
                name: " ".join(definition.lower().replace('"', "").split())
                for name, definition in connection.execute(
                    text(
                        """
                        SELECT conname, pg_get_constraintdef(oid)
                        FROM pg_constraint
                        WHERE connamespace = current_schema()::regnamespace
                          AND conrelid IN (
                            'chat_qualification_scopes'::regclass,
                            'chat_qualification_evidence_events'::regclass
                          )
                        """
                    )
                ).all()
            }
            indexes = {
                name: (unique, tuple(columns), predicate)
                for name, unique, columns, predicate in connection.execute(
                    text(
                        """
                        SELECT index_class.relname, index_meta.indisunique,
                               ARRAY(
                                 SELECT attribute.attname
                                 FROM unnest(index_meta.indkey) WITH ORDINALITY
                                      AS key(attnum, position)
                                 JOIN pg_attribute attribute
                                   ON attribute.attrelid = table_class.oid
                                  AND attribute.attnum = key.attnum
                                 ORDER BY key.position
                               ),
                               pg_get_expr(index_meta.indpred, index_meta.indrelid)
                        FROM pg_index index_meta
                        JOIN pg_class index_class ON index_class.oid = index_meta.indexrelid
                        JOIN pg_class table_class ON table_class.oid = index_meta.indrelid
                        JOIN pg_namespace namespace ON namespace.oid = table_class.relnamespace
                        WHERE namespace.nspname = current_schema()
                          AND table_class.relname IN (
                            'chat_qualification_scopes',
                            'chat_qualification_evidence_events'
                          )
                        """
                    )
                ).all()
            }

        assert constraints == {
            "chat_qualification_scopes_pkey": "primary key (id)",
            "chat_qualification_scopes_run_id_key": "unique (run_id)",
            "chat_qualification_scopes_profile_check": "check (((profile)::text = any ((array['32-functional-turns'::character varying, '100-immediate-admission'::character varying])::text[])))",
            "chat_qualification_scopes_window_check": "check (((window_ended_at is null) or (window_ended_at >= window_started_at)))",
            "chat_qualification_scopes_expiry_check": "check ((expires_at > window_started_at))",
            "chat_qualification_evidence_events_pkey": "primary key (id)",
            "chat_qualification_evidence_scope_fkey": "foreign key (qualification_scope_id) references chat_qualification_scopes(id) on delete cascade",
            "chat_qualification_evidence_turn_fkey": "foreign key (turn_id) references chat_turn_jobs(turn_id) on delete cascade",
            "chat_qualification_evidence_session_fkey": "foreign key (chat_session_id) references chat_sessions(id) on delete cascade",
            "chat_qualification_evidence_event_type_check": "check (((event_type)::text = any ((array['admitted_no_queue'::character varying, 'executor_started'::character varying, 'stale_fence'::character varying, 'queued'::character varying, 'workspace_created'::character varying, 'workspace_reused'::character varying, 'workspace_evicted'::character varying])::text[])))",
            "chat_qualification_evidence_operation_shape_check": "check ((((event_type)::text = 'executor_started'::text) = ((operation_digest is not null) and (operation_kind is not null) and ((operation_kind)::text = any ((array['read'::character varying, 'bash'::character varying])::text[])))))",
        }
        assert indexes == {
            "chat_qualification_scopes_pkey": (True, ("id",), None),
            "chat_qualification_scopes_run_id_key": (True, ("run_id",), None),
            "idx_chat_qualification_scopes_expiry": (False, ("expires_at",), None),
            "idx_chat_qualification_scopes_release_profile": (
                False,
                ("app_release_id", "profile"),
                None,
            ),
            "chat_qualification_evidence_events_pkey": (True, ("id",), None),
            "idx_chat_qualification_evidence_scope_event_time": (
                False,
                ("qualification_scope_id", "event_type", "occurred_at"),
                None,
            ),
            "idx_chat_qualification_evidence_session_time": (
                False,
                ("chat_session_id", "occurred_at"),
                None,
            ),
            "idx_chat_qualification_evidence_turn_event": (
                False,
                ("turn_id", "event_type"),
                None,
            ),
            "uq_chat_qualification_evidence_stale_turn": (
                True,
                ("qualification_scope_id", "turn_id"),
                "((event_type)::text = 'stale_fence'::text)",
            ),
            "uq_chat_qualification_evidence_eviction_turn": (
                True,
                ("qualification_scope_id", "turn_id"),
                "((event_type)::text = 'workspace_evicted'::text)",
            ),
        }
        for _ in range(2):
            raw_connection = database.raw_connection()
            try:
                with raw_connection.cursor() as cursor:
                    cursor.execute(repair_sql)
            finally:
                raw_connection.close()
        with Session(database) as db:
            validate_qualification_evidence_schema(db)
    finally:
        configured.dispose()
        if database is not None:
            database.dispose()
        with admin.connect() as connection:
            connection.exec_driver_sql(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname = '{database_name}' AND pid <> pg_backend_pid()"
            )
            connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{database_name}"')
        admin.dispose()


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


def test_high_level_stale_boundary_catches_all_ownership_rejections_exactly_once():
    from backend.services.chat_external_worker_capacity import (
        ExternalWorkerCapacityUnavailable,
    )
    from backend.services.chat_external_worker_registry import (
        StaleWorkerClaim,
        WorkerLeaseUnavailable,
    )
    from backend.services.chat_qualification_stale_boundary import (
        QUALIFIED_OWNERSHIP_REJECTIONS,
        QualificationStaleFenceBoundary,
    )
    from backend.services.chat_sandbox_state_repository import (
        LeaseUnavailable,
        WorkerGenerationUnavailable,
    )
    from backend.services.chat_turn_job_repository import StaleTurnClaim

    assert set(QUALIFIED_OWNERSHIP_REJECTIONS) == {
        StaleTurnClaim,
        StaleWorkerClaim,
        WorkerLeaseUnavailable,
        ExternalWorkerCapacityUnavailable,
        LeaseUnavailable,
        WorkerGenerationUnavailable,
    }
    for rejection in QUALIFIED_OWNERSHIP_REJECTIONS:
        recorded = []
        boundary = QualificationStaleFenceBoundary(
            turn_id=_latency(16).turn_id,
            chat_session_id=_latency(16).chat_session_id,
            recorder=lambda **event: recorded.append(event) or True,
        )

        async def reject():
            boundary.reject()
            raise rejection("fenced")

        with pytest.raises(rejection):
            asyncio.run(boundary.call(reject()))
        assert [event["event_type"] for event in recorded] == ["stale_fence"]


def test_high_level_stale_boundary_does_not_hide_programming_errors():
    from backend.services.chat_qualification_stale_boundary import (
        QualificationStaleFenceBoundary,
    )

    recorded = []
    boundary = QualificationStaleFenceBoundary(
        turn_id=_latency(16).turn_id,
        chat_session_id=_latency(16).chat_session_id,
        recorder=lambda **event: recorded.append(event) or True,
    )

    async def fail():
        raise ValueError("programming defect")

    with pytest.raises(ValueError, match="programming defect"):
        asyncio.run(boundary.call(fail()))
    assert recorded == []


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


def test_postgresql_concurrent_teardown_serializes_scope_and_keeps_one_eviction_per_turn():
    url = os.getenv("PWC_QUALIFICATION_TEST_DATABASE_URL")
    if not url:
        pytest.skip("explicit disposable qualification PostgreSQL URL is required")
    postgres = create_engine(url)
    if postgres.dialect.name != "postgresql" or not postgres.url.database.endswith(
        "_test"
    ):
        pytest.fail("qualification concurrency proof requires a disposable test DB")
    schema = "qualification_concurrency"
    with postgres.begin() as connection:
        connection.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        connection.execute(text(f"CREATE SCHEMA {schema}"))
        connection.execute(text(f"SET search_path TO {schema}"))
        connection.execute(
            text(
                """
                CREATE TABLE chat_qualification_scopes (
                  id UUID PRIMARY KEY, run_id VARCHAR(64) NOT NULL UNIQUE,
                  profile VARCHAR(32) NOT NULL, app_release_id VARCHAR(255) NOT NULL,
                  window_started_at TIMESTAMPTZ NOT NULL,
                  window_ended_at TIMESTAMPTZ, expires_at TIMESTAMPTZ NOT NULL,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                CREATE TABLE chat_turn_latency (
                  turn_id UUID PRIMARY KEY, chat_session_id UUID NOT NULL,
                  terminal_status VARCHAR(32), qualification_workload VARCHAR(16),
                  qualification_scope_id UUID, qualification_run_id VARCHAR(64),
                  qualification_profile VARCHAR(32), qualification_scenario VARCHAR(32),
                  app_release_id VARCHAR(255), admitted_at TIMESTAMPTZ
                );
                CREATE TABLE chat_sandbox_compute_intervals (
                  id UUID PRIMARY KEY, chat_session_id UUID,
                  terminal_at TIMESTAMPTZ, app_release_id VARCHAR(255)
                );
                CREATE TABLE chat_qualification_evidence_events (
                  id UUID PRIMARY KEY, qualification_scope_id UUID NOT NULL,
                  turn_id UUID NOT NULL, chat_session_id UUID NOT NULL,
                  event_type VARCHAR(32) NOT NULL, operation_digest VARCHAR(64),
                  operation_kind VARCHAR(8), occurred_at TIMESTAMPTZ NOT NULL
                );
                CREATE UNIQUE INDEX uq_chat_qualification_evidence_eviction_turn
                  ON chat_qualification_evidence_events (qualification_scope_id, turn_id)
                  WHERE event_type = 'workspace_evicted';
                """
            )
        )
        connection.execute(
            text(
                "INSERT INTO chat_qualification_scopes "
                "(id,run_id,profile,app_release_id,window_started_at,expires_at) "
                "VALUES (:id,'qualified-f32','32-functional-turns',:release,:start,:expiry)"
            ),
            {
                "id": SCOPE_ID,
                "release": _settings().release_id,
                "start": START,
                "expiry": END + timedelta(hours=1),
            },
        )
        connection.execute(
            text(
                "INSERT INTO chat_turn_latency "
                "(turn_id,chat_session_id,terminal_status,qualification_workload,"
                "qualification_scope_id,qualification_run_id,qualification_profile,"
                "qualification_scenario,app_release_id,admitted_at) VALUES "
                "(:turn_id,:session_id,'complete',:workload,:scope_id,'qualified-f32',"
                "'32-functional-turns','reliability',:release,:admitted_at)"
            ),
            [
                {
                    "turn_id": _latency(index).turn_id,
                    "session_id": _latency(index).chat_session_id,
                    "workload": _latency(index).qualification_workload,
                    "scope_id": SCOPE_ID,
                    "release": _settings().release_id,
                    "admitted_at": START,
                }
                for index in range(32)
            ],
        )
        connection.execute(
            text(
                "INSERT INTO chat_sandbox_compute_intervals "
                "(id,chat_session_id,terminal_at,app_release_id) "
                "VALUES (:id,:session_id,:terminal_at,:release)"
            ),
            [
                {
                    "id": uuid.uuid4(),
                    "session_id": _latency(index).chat_session_id,
                    "terminal_at": END,
                    "release": _settings().release_id,
                }
                for index in range(16, 32)
            ],
        )

    active = 0
    maximum_active = 0
    active_lock = threading.Lock()

    class Manager:
        async def snapshot_and_terminate(self, _session_id):
            nonlocal active, maximum_active
            with active_lock:
                active += 1
                maximum_active = max(maximum_active, active)
            await asyncio.sleep(0.002)
            with active_lock:
                active -= 1

    attempted = threading.Barrier(2)
    proofs = []

    def teardown():
        with Session(postgres) as db, db.begin():
            db.execute(text(f"SET search_path TO {schema}"))
            attempted.wait(timeout=5)
            proofs.append(
                asyncio.run(
                    ChatDurableQualificationEvidenceService(
                        db, now=lambda: END
                    ).teardown_scope(
                        scope_id=SCOPE_ID,
                        settings=_settings(),
                        sandbox_manager=Manager(),
                    )
                )
            )

    threads = [threading.Thread(target=teardown) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()
    with postgres.connect() as connection:
        connection.execute(text(f"SET search_path TO {schema}"))
        count = connection.scalar(
            text(
                "SELECT count(*) FROM chat_qualification_evidence_events "
                "WHERE event_type = 'workspace_evicted'"
            )
        )
    with postgres.begin() as connection:
        connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
    postgres.dispose()

    assert len(proofs) == 2
    assert proofs[0] == proofs[1]
    assert maximum_active == 1
    assert count == 16
