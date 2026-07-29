from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.models.database import Base, ChatSession, ChatTurnLatency
from backend.services.chat_latency_service import ChatLatencyService


def _settings():
    return SimpleNamespace(
        release_id="release-test",
        chat_modal_image_version="im-test",
        chat_worker_contract_version="worker-v2",
        chat_pwc_cli_version="0.2.0",
        chat_system_prompt_sha256="a" * 64,
    )


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[ChatSession.__table__, ChatTurnLatency.__table__],
    )
    with Session(engine) as session:
        yield session


def _session(db: Session, owner_id: str = "owner-1") -> uuid.UUID:
    session_id = uuid.uuid4()
    db.add(
        ChatSession(
            id=session_id,
            hf_user_id=owner_id,
            hf_username="owner",
            selected_model="model",
            execution_backend="modal_cli",
        )
    )
    db.flush()
    return session_id


def _admit(
    db: Session,
    *,
    session_id: uuid.UUID,
    request_id: uuid.UUID | None = None,
    turn_id: uuid.UUID | None = None,
    is_new_chat: bool = True,
) -> ChatTurnLatency:
    return ChatLatencyService(db).admit(
        turn_id=turn_id or uuid.uuid4(),
        session_id=session_id,
        request_id=str(request_id or uuid.uuid4()),
        settings=_settings(),
        model_route="provider/model:route",
        execution_backend="modal_cli",
        is_new_chat=is_new_chat,
    )


def test_admit_stores_only_required_opaque_identifiers_and_versions(db):
    session_id = _session(db)
    turn_id = uuid.uuid4()
    request_id = uuid.uuid4()

    row = _admit(
        db,
        session_id=session_id,
        turn_id=turn_id,
        request_id=request_id,
        is_new_chat=False,
    )

    assert row.turn_id == turn_id
    assert row.request_id == request_id
    assert row.chat_session_id == session_id
    assert row.traffic_class == "followup"
    assert row.acquisition_outcome == "pending"
    assert row.model_route == "provider/model:route"
    assert row.app_release_id == "release-test"
    assert row.sandbox_image_version == "im-test"
    assert row.worker_contract_version == "worker-v2"
    assert row.pwc_cli_version == "0.2.0"
    assert row.system_prompt_sha256 == "a" * 64
    columns = set(ChatTurnLatency.__table__.columns.keys())
    assert not columns & {
        "prompt",
        "user_id",
        "owner_id",
        "capability",
        "command",
        "tool_output",
        "provider_token",
        "transcript",
    }


def test_record_phase_and_finalize_are_first_write_only(db):
    session_id = _session(db)
    request_id = uuid.uuid4()
    row = _admit(db, session_id=session_id, request_id=request_id)
    service = ChatLatencyService(db)

    assert service.record_phase(
        str(request_id),
        "pool_lookup_completed",
        17,
        acquisition_outcome="pool_hit",
    )
    assert not service.record_phase(
        str(request_id),
        "pool_lookup_completed",
        99,
        acquisition_outcome="pool_miss",
    )
    assert service.finalize(str(request_id), "complete", 321)
    assert not service.finalize(str(request_id), "error", 400)
    db.refresh(row)

    assert row.pool_lookup_completed_ms == 17
    assert row.acquisition_outcome == "pool_hit"
    assert row.terminal_status == "complete"
    assert row.total_ms == 321
    assert row.completed_at is not None
    assert not service.record_phase(str(request_id), "first_worker_delta", 200)


def test_gateway_can_record_by_turn_and_derive_admission_delta(db):
    session_id = _session(db)
    row = _admit(db, session_id=session_id)
    row.admitted_at = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)
    db.flush()
    service = ChatLatencyService(db)

    assert service.record_gateway_received(
        row.turn_id,
        datetime(2026, 7, 29, 12, 0, 1, 250_000, tzinfo=UTC),
    )
    assert service.record_phase_for_turn(row.turn_id, "upstream_response_headers", 800)
    db.refresh(row)

    assert row.provider_gateway_received_ms == 1_250
    assert row.upstream_response_headers_ms == 800


def test_browser_update_validates_owner_and_never_overwrites_a_timing_class(db):
    session_id = _session(db)
    request_id = uuid.uuid4()
    row = _admit(db, session_id=session_id, request_id=request_id)
    service = ChatLatencyService(db)

    first = SimpleNamespace(
        submission_to_stream_start_ms=40.6,
        submission_to_first_visible_delta_ms=None,
        terminal_classification=None,
    )
    second = SimpleNamespace(
        submission_to_stream_start_ms=900,
        submission_to_first_visible_delta_ms=1_200,
        terminal_classification="complete",
    )
    assert not service.update_browser("another-owner", str(request_id), first)
    assert service.update_browser("owner-1", str(request_id), first)
    assert service.update_browser("owner-1", str(request_id), second)
    assert service.update_browser("owner-1", str(request_id), second)
    db.refresh(row)

    assert row.browser_stream_start_ms == 41
    assert row.browser_first_visible_delta_ms == 1_200
    assert row.browser_terminal_classification == "complete"


def test_cleanup_deletes_only_one_bounded_thirty_day_batch(db):
    session_id = _session(db)
    service = ChatLatencyService(db)
    now = datetime(2026, 7, 29, tzinfo=UTC)
    old = [_admit(db, session_id=session_id, request_id=uuid.uuid4()) for _ in range(3)]
    recent = _admit(db, session_id=session_id, request_id=uuid.uuid4())
    for index, row in enumerate(old):
        row.admitted_at = now - timedelta(days=31, seconds=index)
    recent.admitted_at = now - timedelta(days=29)
    db.flush()

    assert service.cleanup(batch_size=2, now=now) == 2
    assert service.cleanup(batch_size=2, now=now) == 1
    assert service.cleanup(batch_size=2, now=now) == 0
    assert (
        db.scalar(
            select(ChatTurnLatency).where(ChatTurnLatency.turn_id == recent.turn_id)
        )
        is recent
    )


def test_latency_migration_is_staging_scoped_and_least_privilege():
    migration = (
        Path(__file__).parents[1]
        / "database"
        / "migrations"
        / "add_chat_turn_latency.sql"
    ).read_text()

    assert "current_schema() <> 'staging'" in migration
    assert "OWNER TO pwc_staging_owner" in migration
    assert "TO pwc_staging;" in migration
    assert "FROM paperswithcode_user;" in migration
