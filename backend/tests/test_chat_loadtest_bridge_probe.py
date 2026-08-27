from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from backend.config import Settings
from backend.loadtests.durable_bridge_probe import run_durable_bridge_probe
from backend.models.database import ChatSession, ChatTurnJob
from backend.scripts.qualify_chat_durable_dispatch import SchemaAudit


def _settings(**updates) -> Settings:
    return Settings(
        environment="staging",
        release_id="release-staging",
        db_search_path="staging,public",
        chat_durable_turn_dispatch_enabled=True,
        chat_worker_contract_version="worker-v1",
        chat_max_concurrency=2,
    ).model_copy(update=updates)


def _factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    ChatSession.__table__.create(engine)
    ChatTurnJob.__table__.create(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _audit(**updates) -> SchemaAudit:
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


def test_probe_exercises_admission_ownership_terminal_and_exact_cleanup() -> None:
    factory = _factory()
    with factory() as db:
        unrelated = ChatSession(
            id=uuid.uuid4(),
            hf_user_id="unrelated",
            hf_username="unrelated",
            selected_model="qualification",
        )
        db.add(unrelated)
        db.commit()
        unrelated_id = unrelated.id

    result = run_durable_bridge_probe(
        session_factory=factory,
        settings=_settings(),
        release_id="release-staging",
        worker_contract_version="worker-v1",
        schema_audit=_audit(),
        opaque_identity="loadtest-opaque-a",
    )

    assert result.success is True
    assert [(metric.name, metric.success) for metric in result.metrics] == [
        ("bridge.admission", True),
        ("bridge.ownership", True),
        ("bridge.terminal", True),
        ("bridge.cleanup", True),
    ]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ChatTurnJob)) == 0
        assert db.scalar(select(func.count()).select_from(ChatSession)) == 1
        assert db.get(ChatSession, unrelated_id) is not None


def test_probe_refuses_disabled_bridge_before_writing_rows() -> None:
    factory = _factory()

    result = run_durable_bridge_probe(
        session_factory=factory,
        settings=_settings(chat_durable_turn_dispatch_enabled=False),
        release_id="release-staging",
        worker_contract_version="worker-v1",
        schema_audit=_audit(),
        opaque_identity="loadtest-opaque-a",
    )

    assert result.success is False
    assert result.metrics[-1].name == "bridge.cleanup"
    assert result.metrics[-1].success is True
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ChatTurnJob)) == 0
        assert db.scalar(select(func.count()).select_from(ChatSession)) == 0


def test_probe_refuses_schema_mismatch_before_writing_rows() -> None:
    factory = _factory()

    result = run_durable_bridge_probe(
        session_factory=factory,
        settings=_settings(),
        release_id="release-staging",
        worker_contract_version="worker-v1",
        schema_audit=_audit(indexes=False),
        opaque_identity="loadtest-opaque-a",
    )

    assert result.success is False
    assert all(not metric.success for metric in result.metrics[:3])


def test_rejected_admission_cleans_only_the_probe_session() -> None:
    factory = _factory()
    unrelated_session_id = uuid.uuid4()
    unrelated_turn_id = uuid.uuid4()
    with factory() as db:
        db.add(
            ChatSession(
                id=unrelated_session_id,
                hf_user_id="unrelated",
                hf_username="unrelated",
                selected_model="qualification",
            )
        )
        db.add(
            ChatTurnJob(
                turn_id=unrelated_turn_id,
                chat_session_id=unrelated_session_id,
                hf_user_id="unrelated",
                request_id=f"unrelated-{uuid.uuid4().hex}",
                revision=1,
                dispatch_class="interactive",
                dispatch_route="test",
                state="admitted",
                app_release_id="release-staging",
                worker_contract_version="worker-v1",
                admitted_at=datetime.now(UTC),
            )
        )
        db.commit()

    result = run_durable_bridge_probe(
        session_factory=factory,
        settings=_settings(chat_max_concurrency=1),
        release_id="release-staging",
        worker_contract_version="worker-v1",
        schema_audit=_audit(),
        opaque_identity="loadtest-opaque-a",
    )

    assert result.success is False
    assert result.metrics[0].success is False
    assert result.metrics[-1].success is True
    with factory() as db:
        assert db.get(ChatTurnJob, unrelated_turn_id) is not None
        assert db.get(ChatSession, unrelated_session_id) is not None
        assert db.scalar(select(func.count()).select_from(ChatTurnJob)) == 1
        assert db.scalar(select(func.count()).select_from(ChatSession)) == 1
