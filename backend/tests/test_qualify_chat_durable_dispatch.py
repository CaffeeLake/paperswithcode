import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.config import Settings
from backend.models.database import ChatSession, ChatTurnJob
from backend.scripts.qualify_chat_durable_dispatch import (
    CONFIRMATION,
    QualificationRefused,
    SchemaAudit,
    inspect_postgresql_contract,
    parser,
    run_qualification,
    validate_schema_audit,
    validate_operator_context,
)


def _settings(**updates) -> Settings:
    return Settings(
        environment="staging",
        release_id="abc123-staging",
        db_search_path="staging,public",
        chat_durable_turn_dispatch_enabled=True,
        chat_worker_contract_version="worker-v1",
    ).model_copy(update=updates)


@pytest.mark.parametrize(
    ("confirmation", "settings", "release_id", "worker_contract", "message"),
    [
        ("wrong", _settings(), "abc123-staging", "worker-v1", "confirmation"),
        (
            CONFIRMATION,
            _settings(environment="production"),
            "abc123-staging",
            "worker-v1",
            "staging",
        ),
        (CONFIRMATION, _settings(), "other-staging", "worker-v1", "release"),
        (CONFIRMATION, _settings(), "abc123-staging", "worker-v2", "contract"),
        (
            CONFIRMATION,
            _settings(chat_durable_turn_dispatch_enabled=False),
            "abc123-staging",
            "worker-v1",
            "disabled",
        ),
        (
            CONFIRMATION,
            _settings(db_search_path="public"),
            "abc123-staging",
            "worker-v1",
            "search path",
        ),
    ],
)
def test_operator_context_refuses_unsafe_execution(
    confirmation, settings, release_id, worker_contract, message
):
    with pytest.raises(QualificationRefused, match=message):
        validate_operator_context(
            confirmation=confirmation,
            environment=settings,
            release_id=release_id,
            worker_contract_version=worker_contract,
        )


def _session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    ChatSession.__table__.create(engine)
    ChatTurnJob.__table__.create(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _valid_audit(**updates) -> SchemaAudit:
    values = {
        "schema": True,
        "role": True,
        "owner": True,
        "privileges": True,
        "indexes": True,
        "constraints": True,
    }
    values.update(updates)
    return SchemaAudit(**values)


@pytest.mark.parametrize(
    "field", ["schema", "role", "owner", "privileges", "indexes", "constraints"]
)
def test_schema_audit_refuses_each_postgresql_contract_mismatch(field):
    with pytest.raises(QualificationRefused, match=field):
        validate_schema_audit(_valid_audit(**{field: False}))


def test_qualification_exercises_lifecycle_cleans_rows_and_sanitizes_report():
    factory = _session_factory()

    report = run_qualification(
        session_factory=factory,
        release_id="abc123-staging",
        worker_contract_version="worker-v1",
        schema_audit=_valid_audit(),
    )

    assert set(report) == {
        "release",
        "scenarios",
        "outcomes",
        "timing_ms",
        "cleanup",
        "schema_audit",
    }
    assert report["release"] == {
        "release_id": "abc123-staging",
        "worker_contract_version": "worker-v1",
    }
    assert report["scenarios"] == {"requested": 7, "passed": 7, "failed": 0}
    assert report["outcomes"] == {
        "idempotent_admission": "replayed",
        "same_owner_contention": "account_busy",
        "global_capacity": "chat_overload",
        "claim_heartbeat_transition": "waiting_model",
        "stale_fence": "stale_turn_claim",
        "terminal_write": "completed",
        "expiry_interruption": "lease_expired",
    }
    assert report["timing_ms"]["count"] == 7
    assert 0 <= report["timing_ms"]["min"] <= report["timing_ms"]["p50"]
    assert report["timing_ms"]["p50"] <= report["timing_ms"]["max"]
    assert report["cleanup"] == {
        "clean": True,
        "jobs_deleted": 2,
        "sessions_deleted": 4,
    }
    assert report["schema_audit"] == {
        "schema": True,
        "role": True,
        "owner": True,
        "privileges": True,
        "indexes": True,
        "constraints": True,
    }
    serialized = json.dumps(report)
    assert "qualify-" not in serialized
    with factory() as db:
        assert db.query(ChatTurnJob).count() == 0
        assert db.query(ChatSession).count() == 0


def test_qualification_cleans_rows_when_a_repository_scenario_fails(monkeypatch):
    factory = _session_factory()

    def fail_heartbeat(*_args, **_kwargs):
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(
        "backend.scripts.qualify_chat_durable_dispatch.ChatTurnJobRepository.heartbeat",
        fail_heartbeat,
    )

    with pytest.raises(RuntimeError, match="synthetic failure"):
        run_qualification(
            session_factory=factory,
            release_id="abc123-staging",
            worker_contract_version="worker-v1",
            schema_audit=_valid_audit(),
        )

    with factory() as db:
        assert db.query(ChatTurnJob).count() == 0
        assert db.query(ChatSession).count() == 0


def test_cli_requires_release_directory_and_exact_confirmation(tmp_path):
    release = tmp_path / "release"
    arguments = parser().parse_args(
        [
            "--release-dir",
            str(release),
            "--confirm",
            CONFIRMATION,
        ]
    )

    assert arguments.release_dir == release
    assert arguments.confirm == CONFIRMATION


def test_postgresql_catalog_boundary_maps_only_aggregate_audit_booleans():
    class Result:
        def mappings(self):
            return self

        def one(self):
            return {
                "schema": True,
                "role": True,
                "owner": True,
                "privileges": True,
                "indexes": True,
                "constraints": True,
            }

    class Bind:
        class Dialect:
            name = "postgresql"

        dialect = Dialect()

    class Database:
        bind = Bind()

        def execute(self, _statement):
            return Result()

    assert inspect_postgresql_contract(Database()) == _valid_audit()


def test_catalog_audit_refuses_a_non_postgresql_database():
    class Bind:
        class Dialect:
            name = "sqlite"

        dialect = Dialect()

    class Database:
        bind = Bind()

    with pytest.raises(QualificationRefused, match="PostgreSQL"):
        inspect_postgresql_contract(Database())
