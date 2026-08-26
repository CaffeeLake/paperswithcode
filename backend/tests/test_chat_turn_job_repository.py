import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, Lock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateIndex, CreateTable

from backend.models.database import ChatSession, ChatTurnJob
from backend.services.chat_turn_job_repository import (
    AccountBusy,
    ChatOverload,
    ChatTurnJobRepository,
    IdempotencyMismatch,
    StaleTurnClaim,
    TurnNotClaimable,
)

NOW = datetime(2026, 8, 26, 12, tzinfo=UTC)


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    ChatSession.__table__.create(engine)
    ChatTurnJob.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


def _session(db: Session, *, owner: str = "owner-1") -> ChatSession:
    row = ChatSession(
        id=uuid.uuid4(),
        hf_user_id=owner,
        hf_username=owner,
        selected_model="model",
    )
    db.add(row)
    db.flush()
    return row


def _admit(
    repository: ChatTurnJobRepository,
    db: Session,
    session: ChatSession,
    *,
    turn_id: uuid.UUID | None = None,
    request_id: str | None = None,
    capacity: int = 8,
):
    return repository.admit(
        db,
        turn_id=turn_id or uuid.uuid4(),
        chat_session_id=session.id,
        hf_user_id=session.hf_user_id,
        request_id=request_id or f"request-{uuid.uuid4()}",
        revision=1,
        dispatch_class="interactive",
        dispatch_route="external-pi",
        app_release_id="release-a",
        worker_contract_version="external-pi-v1",
        now=NOW,
        emergency_capacity=capacity,
    )


def test_turn_job_model_has_durable_state_and_owner_guards():
    table = ChatTurnJob.__table__
    ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
    indexes = "\n".join(
        str(CreateIndex(index).compile(dialect=postgresql.dialect()))
        for index in table.indexes
    )

    assert table.primary_key.columns.keys() == ["turn_id"]
    assert table.c.request_id.unique
    assert "revision > 0" in ddl
    assert "lease_generation > 0" in ddl
    assert (
        "admitted', 'leased', 'running', 'waiting_model', 'waiting_tool', "
        "'cancelling', 'completed', 'failed', 'interrupted"
    ) in ddl
    assert "uq_chat_turn_jobs_nonterminal_owner" in indexes
    assert (
        "state IN "
        "('admitted','leased','running','waiting_model','waiting_tool','cancelling')"
    ) in indexes


def test_matching_admission_is_idempotent_and_mismatch_fails_closed(db):
    lock_order = []
    repository = ChatTurnJobRepository(
        advisory_locker=lambda _db, key: lock_order.append(key)
    )
    session = _session(db)
    turn_id = uuid.uuid4()

    first = _admit(repository, db, session, turn_id=turn_id, request_id="request-1")
    replay = _admit(repository, db, session, turn_id=turn_id, request_id="request-1")

    assert first.created is True
    assert replay.created is False
    assert replay.job.turn_id == turn_id
    assert lock_order == ["chat-user:owner-1", "chat-global-active-turns"] * 2
    with pytest.raises(IdempotencyMismatch):
        _admit(repository, db, session, request_id="request-1")
    with pytest.raises(IdempotencyMismatch):
        _admit(repository, db, session, turn_id=turn_id, request_id="request-2")
    assert db.query(ChatTurnJob).count() == 1


def test_admission_rejects_busy_owner_and_capacity_edge_without_insert(db):
    repository = ChatTurnJobRepository(advisory_locker=lambda *_args: None)
    owner_session = _session(db)
    other_session = _session(db, owner="owner-2")
    third_session = _session(db, owner="owner-3")
    _admit(repository, db, owner_session, capacity=2)

    with pytest.raises(AccountBusy) as busy:
        _admit(repository, db, owner_session, capacity=2)
    _admit(repository, db, other_session, capacity=2)
    with pytest.raises(ChatOverload) as overload:
        _admit(repository, db, third_session, capacity=2)

    assert busy.value.code == "account_busy"
    assert overload.value.code == "chat_overload"
    assert db.query(ChatTurnJob).count() == 2


def test_concurrent_same_owner_admission_has_one_typed_winner(tmp_path):
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'turn-jobs.db'}",
        connect_args={"check_same_thread": False},
    )
    ChatSession.__table__.create(engine)
    ChatTurnJob.__table__.create(engine)
    session_ids = [uuid.uuid4(), uuid.uuid4()]
    with Session(engine) as setup:
        setup.add_all(
            [
                ChatSession(
                    id=session_id,
                    hf_user_id="shared-owner",
                    hf_username="shared-owner",
                    selected_model="model",
                )
                for session_id in session_ids
            ]
        )
        setup.commit()

    ready = Barrier(2)
    transaction_lock = Lock()  # boundary double for PG transaction advisory locks

    def attempt(index: int) -> str:
        repository = ChatTurnJobRepository(advisory_locker=lambda *_args: None)
        with Session(engine, expire_on_commit=False) as transaction:
            session = transaction.get(ChatSession, session_ids[index])
            ready.wait()
            with transaction_lock:
                try:
                    _admit(repository, transaction, session)
                    transaction.commit()
                    return "admitted"
                except AccountBusy as error:
                    transaction.rollback()
                    return error.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(attempt, range(2)))

    assert sorted(outcomes) == ["account_busy", "admitted"]
    with Session(engine) as verify:
        assert verify.query(ChatTurnJob).count() == 1


def test_claim_mutations_are_fenced_and_terminal_is_idempotent(db):
    repository = ChatTurnJobRepository(advisory_locker=lambda *_args: None)
    session = _session(db)
    admitted = _admit(repository, db, session).job
    claim = repository.claim(
        db,
        turn_id=admitted.turn_id,
        worker_id="worker-1",
        worker_generation=7,
        now=NOW + timedelta(seconds=1),
        lease_seconds=15,
    )

    assert claim.lease_generation == 1
    assert repository.load_by_request(db, admitted.request_id).state == "leased"
    repository.transition(
        db, claim=claim, state="running", now=NOW + timedelta(seconds=2)
    )
    repository.heartbeat(
        db, claim=claim, now=NOW + timedelta(seconds=3), lease_seconds=15
    )
    repository.transition(
        db,
        claim=claim,
        state="waiting_model",
        now=NOW + timedelta(seconds=4),
        last_agent_session_id=uuid.uuid4(),
        last_resume_boundary_id="entry-42",
    )
    stale_claims = (
        claim.__class__(
            turn_id=claim.turn_id,
            worker_id=claim.worker_id,
            worker_generation=claim.worker_generation + 1,
            lease_generation=claim.lease_generation,
        ),
        claim.__class__(
            turn_id=claim.turn_id,
            worker_id=claim.worker_id,
            worker_generation=claim.worker_generation,
            lease_generation=claim.lease_generation + 1,
        ),
    )
    for stale in stale_claims:
        with pytest.raises(StaleTurnClaim):
            repository.heartbeat(
                db, claim=stale, now=NOW + timedelta(seconds=5), lease_seconds=15
            )

    terminal = repository.write_terminal(
        db,
        claim=claim,
        state="completed",
        now=NOW + timedelta(seconds=6),
    )
    replay = repository.write_terminal(
        db,
        claim=claim,
        state="completed",
        now=NOW + timedelta(seconds=7),
    )
    assert terminal is replay
    assert terminal.terminal_at == NOW + timedelta(seconds=6)
    assert terminal.lease_expires_at is None
    with pytest.raises(TurnNotClaimable):
        repository.claim(
            db,
            turn_id=admitted.turn_id,
            worker_id="worker-1",
            worker_generation=7,
            now=NOW + timedelta(seconds=8),
            lease_seconds=15,
        )


def test_expired_lease_is_interrupted_and_never_claimable(db):
    repository = ChatTurnJobRepository(advisory_locker=lambda *_args: None)
    session = _session(db)
    job = _admit(repository, db, session).job
    claim = repository.claim(
        db,
        turn_id=job.turn_id,
        worker_id="worker-1",
        worker_generation=1,
        now=NOW,
        lease_seconds=5,
    )

    with pytest.raises(StaleTurnClaim):
        repository.write_terminal(
            db,
            claim=claim,
            state="completed",
            now=NOW + timedelta(seconds=5),
        )

    interrupted = repository.interrupt_expired(
        db, now=NOW + timedelta(seconds=5), limit=10
    )

    assert interrupted == 1
    loaded = repository.load_by_turn(db, job.turn_id)
    assert loaded.state == "interrupted"
    assert loaded.failure_code == "lease_expired"
    assert loaded.lease_expires_at is None
    assert (
        repository.interrupt_expired(db, now=NOW + timedelta(seconds=6), limit=10) == 0
    )
    with pytest.raises(TurnNotClaimable):
        repository.claim(
            db,
            turn_id=job.turn_id,
            worker_id="worker-2",
            worker_generation=1,
            now=NOW + timedelta(seconds=6),
            lease_seconds=5,
        )


def test_turn_job_migration_is_guarded_and_preserves_schema_ownership():
    migration = (
        Path(__file__).parents[1] / "database/migrations/add_chat_turn_jobs.sql"
    ).read_text()

    assert "current_schema() NOT IN ('staging', 'public')" in migration
    assert "CREATE TABLE IF NOT EXISTS chat_turn_jobs" in migration
    assert "uq_chat_turn_jobs_nonterminal_owner" in migration
    assert "OWNER TO pwc_staging_owner" in migration
    assert "TO pwc_staging;" in migration
    assert "FROM paperswithcode_user;" in migration
    assert "OWNER TO paperswithcode_user" in migration
    assert "FROM pwc_staging;" in migration
