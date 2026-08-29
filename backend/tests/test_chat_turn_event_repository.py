import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateIndex, CreateTable

from backend.models.database import ChatSession, ChatTurnEventChunk, ChatTurnJob
from backend.services.chat_turn_event_repository import (
    JournalLimitExceeded,
    TurnEventJournal,
    UnsequencedJournalEvent,
)
from backend.services.chat_turn_job_repository import (
    ChatTurnJobRepository,
    StaleTurnClaim,
    TurnLeaseClaim,
)

NOW = datetime(2026, 8, 29, 12, tzinfo=UTC)


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    ChatSession.__table__.create(engine)
    ChatTurnJob.__table__.create(engine)
    ChatTurnEventChunk.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


def _claimed_turn(db: Session) -> tuple[ChatTurnJob, TurnLeaseClaim]:
    session = ChatSession(
        id=uuid.uuid4(),
        hf_user_id="journal-owner",
        hf_username="journal-owner",
        selected_model="model",
    )
    db.add(session)
    job = ChatTurnJob(
        turn_id=uuid.uuid4(),
        chat_session_id=session.id,
        hf_user_id=session.hf_user_id,
        request_id=f"request-{uuid.uuid4()}",
        revision=1,
        dispatch_class="interactive",
        dispatch_route="external-pi",
        state="running",
        worker_id="worker-a",
        worker_generation=7,
        lease_generation=3,
        app_release_id="release-a",
        worker_contract_version="external-pi-v1",
        admitted_at=NOW - timedelta(seconds=2),
        dispatched_at=NOW - timedelta(seconds=2),
        started_at=NOW - timedelta(seconds=1),
        heartbeat_at=NOW,
        lease_expires_at=NOW + timedelta(seconds=30),
    )
    db.add(job)
    db.flush()
    return job, TurnLeaseClaim(job.turn_id, "worker-a", 7, 3)


def event(name: str, payload: dict[str, object]) -> UnsequencedJournalEvent:
    return UnsequencedJournalEvent(event=name, payload=payload)


def test_appends_receive_contiguous_sequences_and_reads_start_after_cursor(db):
    job, claim = _claimed_turn(db)
    repository = TurnEventJournal()

    first = repository.append(
        db, claim=claim, events=[event("delta", {"text": "a"})], now=NOW
    )
    second = repository.append(
        db, claim=claim, events=[event("delta", {"text": "b"})], now=NOW
    )

    assert [frame.sequence for frame in (*first, *second)] == [1, 2]
    assert (
        repository.read_after(db, turn_id=claim.turn_id, after_sequence=1, limit=10)
        == second
    )
    assert job.event_sequence == 2
    assert job.event_bytes == 106


def test_append_rejects_a_stale_lease_generation_without_mutation(db):
    job, claim = _claimed_turn(db)
    repository = TurnEventJournal()
    stale = TurnLeaseClaim(
        claim.turn_id,
        claim.worker_id,
        claim.worker_generation,
        claim.lease_generation - 1,
    )

    with pytest.raises(StaleTurnClaim):
        repository.append(
            db, claim=stale, events=[event("delta", {"text": "a"})], now=NOW
        )

    assert job.event_sequence == 0
    assert job.event_bytes == 0
    assert db.query(ChatTurnEventChunk).count() == 0


@pytest.mark.parametrize(
    ("limit_name", "limit_value", "events"),
    [
        ("MAX_FRAME_BYTES", 52, [event("delta", {"text": "a"})]),
        (
            "MAX_TURN_BYTES",
            105,
            [
                event("delta", {"text": "a"}),
                event("delta", {"text": "b"}),
            ],
        ),
        (
            "MAX_TURN_EVENTS",
            1,
            [
                event("delta", {"text": "a"}),
                event("delta", {"text": "b"}),
            ],
        ),
    ],
)
def test_limits_are_enforced_before_mutation(
    db, monkeypatch, limit_name, limit_value, events
):
    job, claim = _claimed_turn(db)
    repository = TurnEventJournal()
    monkeypatch.setattr(repository, limit_name, limit_value)

    with pytest.raises(JournalLimitExceeded) as raised:
        repository.append(db, claim=claim, events=events, now=NOW)

    assert raised.value.code == "event_journal_exhausted"
    assert job.event_sequence == 0
    assert job.event_bytes == 0
    assert db.query(ChatTurnEventChunk).count() == 0


def test_terminal_cleanup_deletes_chunks_without_deleting_turn_job(db):
    job, claim = _claimed_turn(db)
    journal = TurnEventJournal()
    journal.append(db, claim=claim, events=[event("delta", {"text": "a"})], now=NOW)
    ChatTurnJobRepository().write_terminal(
        db, claim=claim, state="completed", now=NOW + timedelta(seconds=1)
    )

    assert journal.delete_terminal(db, turn_id=claim.turn_id) == 1
    assert db.get(ChatTurnJob, claim.turn_id) is job
    assert db.query(ChatTurnEventChunk).count() == 0


def test_model_and_migration_define_the_bounded_event_journal():
    table = ChatTurnEventChunk.__table__
    ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
    indexes = "\n".join(
        str(CreateIndex(index).compile(dialect=postgresql.dialect()))
        for index in table.indexes
    )
    migration = (
        Path(__file__).parents[1] / "database/migrations/add_chat_turn_event_chunks.sql"
    ).read_text()

    assert str(ChatTurnJob.__table__.c.event_sequence.server_default.arg) == "0"
    assert str(ChatTurnJob.__table__.c.event_bytes.server_default.arg) == "0"
    assert "uq_chat_turn_event_chunk_start" in ddl
    assert "ck_chat_turn_event_chunk_range" in ddl
    assert "idx_chat_turn_event_chunks_after" in indexes
    assert "current_schema() NOT IN ('staging', 'public')" in migration
    assert (
        "ADD COLUMN IF NOT EXISTS event_sequence INTEGER NOT NULL DEFAULT 0"
        in migration
    )
    assert (
        "ADD COLUMN IF NOT EXISTS event_bytes INTEGER NOT NULL DEFAULT 0" in migration
    )
    assert "CREATE TABLE IF NOT EXISTS chat_turn_event_chunks" in migration
    assert "OWNER TO pwc_staging_owner" in migration
    assert "TO pwc_staging;" in migration
    assert "OWNER TO paperswithcode_user" in migration
