from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.config import Settings
from backend.models.database import (
    ChatSandboxBudgetState,
    ChatSandboxCircuitEvent,
    ChatSandboxComputeInterval,
    ChatSandboxLease,
    ChatSandboxPool,
    ChatSession,
)
from backend.services.chat_sandbox_spend_service import (
    ChatComputeDisabled,
    ChatSandboxSpendService,
)
from backend.services.chat_sandbox_pool_repository import (
    BlankPoolCandidate,
    BlankPoolClaim,
    ChatSandboxPoolRepository,
    PoolCompatibility,
    PoolEvictionRequired,
    PoolLandingOutcome,
    PoolReservationUnavailable,
    PoolStartReservation,
    PoolTerminationClaim,
    PoolTerminationFinishOutcome,
)


def _settings(**overrides) -> Settings:
    values = {
        "environment": "staging",
        "release_id": "release-current",
        "chat_modal_image_version": "im-current",
        "chat_worker_contract_version": "worker-v1",
        "chat_persistent_worker_enabled": True,
        "chat_blank_pool_enabled": True,
        "chat_blank_pool_min": 1,
        "chat_blank_pool_max": 2,
        "chat_blank_pool_min_remaining_seconds": 240,
        "chat_sandbox_total_live_cap": 3,
        "chat_sandbox_cpu": 0.125,
        "chat_sandbox_cpu_limit": 1,
        "chat_sandbox_memory_mib": 512,
        "chat_sandbox_memory_limit_mib": 2048,
        "chat_sandbox_spend_enforcement_enabled": False,
        "chat_workspace_snapshots_enabled": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _create_schema(engine) -> None:
    ChatSession.__table__.create(engine)
    ChatSandboxPool.__table__.create(engine)
    ChatSandboxLease.__table__.create(engine)
    ChatSandboxBudgetState.__table__.create(engine)
    ChatSandboxComputeInterval.__table__.create(engine)
    ChatSandboxCircuitEvent.__table__.create(engine)


def _database(*, session_class=Session):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    _create_schema(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, class_=session_class)


def _file_database(path, *, session_class=Session):
    engine = create_engine(
        f"sqlite+pysqlite:///{path}",
        connect_args={"check_same_thread": False},
    )
    _create_schema(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, class_=session_class)


def _session(session_id: uuid.UUID) -> ChatSession:
    return ChatSession(
        id=session_id,
        hf_user_id=f"owner-{session_id}",
        hf_username=f"owner-{session_id}",
        selected_model="google/gemma-4-31B-it",
        execution_backend="modal_cli",
    )


def _pool(
    settings: Settings,
    *,
    state: str = "blank_ready",
    sandbox_id: str | None = "sb-blank",
    ready_at: datetime | None = None,
    expires_at: datetime | None = None,
    generation: str = "generation-a",
) -> ChatSandboxPool:
    now = datetime.now(UTC)
    return ChatSandboxPool(
        id=uuid.uuid4(),
        modal_sandbox_id=sandbox_id,
        state=state,
        image_version=settings.chat_modal_image_version,
        worker_contract_version=settings.chat_worker_contract_version,
        worker_generation=generation,
        app_release_id=settings.release_id,
        created_at=now - timedelta(minutes=2),
        ready_at=(ready_at or now - timedelta(minutes=1))
        if state != "starting"
        else None,
        expires_at=expires_at or now + timedelta(hours=1),
        updated_at=now,
        cpu_request=settings.chat_sandbox_cpu,
        cpu_limit=settings.chat_sandbox_cpu_limit or settings.chat_sandbox_cpu,
        memory_request_mib=settings.chat_sandbox_memory_mib,
        memory_limit_mib=(
            settings.chat_sandbox_memory_limit_mib or settings.chat_sandbox_memory_mib
        ),
        billing_month=now.date().replace(day=1),
    )


def _interval(
    settings: Settings,
    worker_generation: str,
    now: datetime,
    *,
    sandbox_id: str | None = None,
) -> ChatSandboxComputeInterval:
    return ChatSandboxComputeInterval(
        id=uuid.uuid4(),
        modal_sandbox_id=sandbox_id,
        environment=settings.environment,
        modal_app="pwc-chat-sandboxes",
        app_release_id=settings.release_id,
        image_version=settings.chat_modal_image_version,
        worker_generation=worker_generation,
        origin="blank_pool",
        cpu_request_millicores=round(settings.chat_sandbox_cpu * 1000),
        cpu_limit_millicores=round(
            (settings.chat_sandbox_cpu_limit or settings.chat_sandbox_cpu) * 1000
        ),
        memory_request_mib=settings.chat_sandbox_memory_mib,
        memory_limit_mib=(
            settings.chat_sandbox_memory_limit_mib or settings.chat_sandbox_memory_mib
        ),
        reserved_at=now,
        provider_created_at=now if sandbox_id is not None else None,
        billing_cycle=now.date().replace(day=1),
        reserved_microusd=1,
        updated_at=now,
    )


class _CommitForbiddenSession(Session):
    def commit(self) -> None:
        raise AssertionError("pool repository must not commit")


class _OrderRecordingSession(Session):
    def execute(self, statement, *args, **kwargs):
        sql = str(statement)
        order = self.info.setdefault("lock_order", [])
        if "FROM chat_sandbox_leases" in sql:
            order.append("lease")
        elif "FROM chat_sandbox_pool" in sql:
            order.append("pool")
        return super().execute(statement, *args, **kwargs)


def _compatibility(settings: Settings) -> PoolCompatibility:
    return PoolCompatibility(
        image_version=settings.chat_modal_image_version,
        worker_contract_version=settings.chat_worker_contract_version,
        cpu_request=settings.chat_sandbox_cpu,
        cpu_limit=settings.chat_sandbox_cpu_limit or settings.chat_sandbox_cpu,
        memory_request_mib=settings.chat_sandbox_memory_mib,
        memory_limit_mib=(
            settings.chat_sandbox_memory_limit_mib or settings.chat_sandbox_memory_mib
        ),
    )


def _repository(
    settings: Settings,
    *,
    capacity_locker=None,
    tokens=(),
    generations=(),
    pool_ids=(),
) -> ChatSandboxPoolRepository:
    token_values = iter(tokens)
    generation_values = iter(generations)
    id_values = iter(pool_ids)
    return ChatSandboxPoolRepository(
        settings,
        capacity_locker=capacity_locker or (lambda _db, *, wait=True: True),
        token_factory=lambda: next(token_values, "operation-token"),
        worker_generation_factory=lambda: next(
            generation_values, "generation-reserved"
        ),
        pool_id_factory=lambda: next(id_values, uuid.uuid4()),
    )


def test_compatible_candidates_are_oldest_ready_first_and_release_agnostic():
    settings = _settings()
    sessions = _database()
    now = datetime.now(UTC)
    oldest = _pool(
        settings,
        sandbox_id="sb-oldest",
        ready_at=now - timedelta(minutes=3),
    )
    previous_release = _pool(
        settings,
        sandbox_id="sb-previous-release",
        ready_at=now - timedelta(minutes=2),
    )
    previous_release.app_release_id = "release-previous"
    newest = _pool(
        settings,
        sandbox_id="sb-newest",
        ready_at=now - timedelta(minutes=1),
    )
    wrong_state = _pool(settings, state="draining", sandbox_id="sb-draining")
    wrong_image = _pool(settings, sandbox_id="sb-wrong-image")
    wrong_image.image_version = "im-other"
    wrong_contract = _pool(settings, sandbox_id="sb-wrong-contract")
    wrong_contract.worker_contract_version = "worker-v0"
    wrong_resources = _pool(settings, sandbox_id="sb-wrong-resources")
    wrong_resources.cpu_limit = 2
    expiring = _pool(
        settings,
        sandbox_id="sb-expiring",
        expires_at=now + timedelta(seconds=30),
    )
    with sessions() as db, db.begin():
        db.add_all(
            [
                newest,
                wrong_state,
                wrong_image,
                previous_release,
                expiring,
                wrong_contract,
                oldest,
                wrong_resources,
            ]
        )

    repository = _repository(settings)
    with sessions() as db:
        candidates = repository.list_claim_candidates(
            db,
            _compatibility(settings),
            minimum_expires_at=now + timedelta(minutes=4),
            limit=2,
        )

    assert list(candidates) == [
        BlankPoolCandidate(
            pool_id=oldest.id,
            sandbox_id="sb-oldest",
            worker_generation="generation-a",
            claim_generation=0,
            token_hash=None,
        ),
        BlankPoolCandidate(
            pool_id=previous_release.id,
            sandbox_id="sb-previous-release",
            worker_generation="generation-a",
            claim_generation=0,
            token_hash=None,
        ),
    ]


def test_claim_blank_exactly_claims_row_and_creates_one_ready_lease():
    settings = _settings()
    sessions = _database()
    now = datetime.now(UTC)
    session_id = uuid.uuid4()
    row = _pool(settings)
    with sessions() as db, db.begin():
        db.add_all([_session(session_id), row])
    repository = _repository(settings, tokens=("claim-operation",))
    with sessions() as db:
        candidate = repository.list_claim_candidates(
            db,
            _compatibility(settings),
            minimum_expires_at=now + timedelta(minutes=4),
            limit=1,
        )[0]

    with sessions() as db, db.begin():
        claim = repository.claim_blank(
            db,
            candidate,
            session_id,
            _compatibility(settings),
            minimum_expires_at=now + timedelta(minutes=4),
            now=now,
        )

    assert isinstance(claim, BlankPoolClaim)
    assert claim.pool_id == row.id
    assert claim.sandbox_id == "sb-blank"
    assert claim.worker_generation == "generation-a"
    assert claim.claim_generation == 1
    assert claim.token_hash
    with sessions() as db:
        claimed = db.get(ChatSandboxPool, row.id)
        leases = list(db.execute(select(ChatSandboxLease)).scalars())
    assert claimed.state == "claimed"
    assert claimed.claim_generation == claim.claim_generation
    assert claimed.claim_token_hash == claim.token_hash
    assert claimed.claimed_at is not None
    assert len(leases) == 1
    assert leases[0].chat_session_id == session_id
    assert leases[0].modal_sandbox_id == claim.sandbox_id
    assert leases[0].worker_generation == claim.worker_generation
    assert leases[0].state == "ready"


@pytest.mark.parametrize(
    "mutation",
    [
        "state",
        "sandbox_id",
        "generation",
        "claim_generation",
        "token",
        "image",
    ],
)
def test_claim_blank_rejects_every_stale_candidate_identity(mutation):
    settings = _settings()
    sessions = _database()
    now = datetime.now(UTC)
    session_id = uuid.uuid4()
    row = _pool(settings)
    with sessions() as db, db.begin():
        db.add_all([_session(session_id), row])
    repository = _repository(settings)
    with sessions() as db:
        candidate = repository.list_claim_candidates(
            db,
            _compatibility(settings),
            minimum_expires_at=now + timedelta(minutes=4),
            limit=1,
        )[0]
    with sessions() as db, db.begin():
        successor = db.get(ChatSandboxPool, row.id)
        if mutation == "state":
            successor.state = "draining"
        elif mutation == "sandbox_id":
            successor.modal_sandbox_id = "sb-successor"
        elif mutation == "generation":
            successor.worker_generation = "generation-successor"
        elif mutation == "claim_generation":
            successor.claim_generation += 1
        elif mutation == "token":
            successor.claim_token_hash = "successor-token"
        elif mutation == "image":
            successor.image_version = "im-successor"

    with sessions() as db, db.begin():
        claim = repository.claim_blank(
            db,
            candidate,
            session_id,
            _compatibility(settings),
            minimum_expires_at=now + timedelta(minutes=4),
            now=now,
        )

    assert claim is None
    with sessions() as db:
        lease_count = db.scalar(select(func.count()).select_from(ChatSandboxLease))
    assert lease_count == 0


def test_claim_lock_order_is_capacity_then_lease_then_pool_row():
    settings = _settings()
    sessions = _database(session_class=_OrderRecordingSession)
    now = datetime.now(UTC)
    session_id = uuid.uuid4()
    row = _pool(settings)
    with sessions() as db, db.begin():
        db.add_all([_session(session_id), row])

    def lock_capacity(db, *, wait=True):
        assert wait is True
        db.info.setdefault("lock_order", []).append("capacity")
        return True

    repository = _repository(settings, capacity_locker=lock_capacity)
    with sessions() as db:
        candidate = repository.list_claim_candidates(
            db,
            _compatibility(settings),
            minimum_expires_at=now + timedelta(minutes=4),
            limit=1,
        )[0]
    with sessions() as db, db.begin():
        assert (
            repository.claim_blank(
                db,
                candidate,
                session_id,
                _compatibility(settings),
                minimum_expires_at=now + timedelta(minutes=4),
                now=now,
            )
            is not None
        )
        assert db.info["lock_order"][:3] == ["capacity", "lease", "pool"]


def test_concurrent_claims_create_one_pool_claim_and_one_lease(tmp_path):
    settings = _settings()
    sessions = _file_database(tmp_path / "pool-claim.db")
    now = datetime.now(UTC)
    first_session_id, second_session_id = uuid.uuid4(), uuid.uuid4()
    row = _pool(settings)
    with sessions() as db, db.begin():
        interval = _interval(
            settings,
            row.worker_generation,
            now - timedelta(minutes=2),
            sandbox_id=row.modal_sandbox_id,
        )
        db.add_all(
            [
                _session(first_session_id),
                _session(second_session_id),
                row,
                interval,
            ]
        )
    capacity_lock = threading.Lock()

    def lock_capacity(db, *, wait=True):
        assert wait is True
        capacity_lock.acquire()
        db.info["capacity_lock_held"] = True
        return True

    def release_capacity_lock(db, transaction):
        if transaction.parent is None and db.info.pop("capacity_lock_held", False):
            capacity_lock.release()

    event.listen(sessions.class_, "after_transaction_end", release_capacity_lock)
    repository = _repository(
        settings,
        capacity_locker=lock_capacity,
        tokens=("claim-first", "claim-second"),
    )
    with sessions() as db:
        candidate = repository.list_claim_candidates(
            db,
            _compatibility(settings),
            minimum_expires_at=now + timedelta(minutes=4),
            limit=1,
        )[0]

    def claim(session_id):
        with sessions() as db, db.begin():
            outcome = repository.claim_blank(
                db,
                candidate,
                session_id,
                _compatibility(settings),
                minimum_expires_at=now + timedelta(minutes=4),
                now=now,
            )
            if isinstance(outcome, BlankPoolClaim):
                ChatSandboxSpendService(db, settings).claim(
                    outcome.sandbox_id,
                    session_id,
                    now,
                )
            return outcome

    with ThreadPoolExecutor(max_workers=2) as workers:
        outcomes = list(workers.map(claim, (first_session_id, second_session_id)))

    assert sum(isinstance(outcome, BlankPoolClaim) for outcome in outcomes) == 1
    with sessions() as db:
        claimed = db.get(ChatSandboxPool, row.id)
        leases = list(db.execute(select(ChatSandboxLease)).scalars())
        assigned_interval = db.get(ChatSandboxComputeInterval, interval.id)
    assert claimed.state == "claimed"
    assert claimed.claim_generation == 1
    assert len(leases) == 1
    assert leases[0].chat_session_id in {first_session_id, second_session_id}
    assert assigned_interval.chat_session_id == leases[0].chat_session_id
    assert assigned_interval.claimed_at is not None


def test_reserve_starting_blank_creates_one_owned_row_then_satisfies_target():
    settings = _settings(chat_blank_pool_min=1, chat_blank_pool_max=2)
    sessions = _database()
    now = datetime.now(UTC)
    pool_id = uuid.uuid4()
    repository = _repository(
        settings,
        tokens=("reserve-operation",),
        generations=("generation-reservation",),
        pool_ids=(pool_id,),
    )

    with sessions() as db, db.begin():
        reservation = repository.reserve_starting_blank(db, now=now)
        second = repository.reserve_starting_blank(db, now=now)

    assert isinstance(reservation, PoolStartReservation)
    assert reservation.pool_id == pool_id
    assert reservation.worker_generation == "generation-reservation"
    assert reservation.token_hash
    assert reservation.compatibility == _compatibility(settings)
    assert reservation.app_release_id == settings.release_id
    assert reservation.claim_generation == 0
    assert second is PoolReservationUnavailable.TARGET_SATISFIED
    with sessions() as db:
        rows = list(db.execute(select(ChatSandboxPool)).scalars())
        interval_count = db.scalar(
            select(func.count()).select_from(ChatSandboxComputeInterval)
        )
    assert len(rows) == 1
    assert rows[0].id == pool_id
    assert rows[0].state == "starting"
    assert rows[0].modal_sandbox_id is None
    assert rows[0].claim_token_hash == reservation.token_hash
    assert rows[0].worker_generation == reservation.worker_generation
    assert interval_count == 0


def test_reservation_returns_oldest_idle_eviction_at_total_capacity():
    settings = _settings(
        chat_blank_pool_min=1,
        chat_blank_pool_max=2,
        chat_sandbox_total_live_cap=2,
    )
    sessions = _database()
    now = datetime.now(UTC)
    oldest_id, newest_id = uuid.uuid4(), uuid.uuid4()
    with sessions() as db, db.begin():
        db.add_all(
            [
                _session(oldest_id),
                _session(newest_id),
                ChatSandboxLease(
                    chat_session_id=oldest_id,
                    modal_sandbox_id="sb-oldest",
                    app_release_id=settings.release_id,
                    image_version=settings.chat_modal_image_version,
                    worker_contract_version=settings.chat_worker_contract_version,
                    worker_generation="generation-oldest",
                    state="idle",
                    last_activity_at=now - timedelta(minutes=2),
                ),
                ChatSandboxLease(
                    chat_session_id=newest_id,
                    modal_sandbox_id="sb-newest",
                    app_release_id=settings.release_id,
                    image_version=settings.chat_modal_image_version,
                    worker_contract_version=settings.chat_worker_contract_version,
                    worker_generation="generation-newest",
                    state="idle",
                    last_activity_at=now - timedelta(minutes=1),
                ),
            ]
        )

    with sessions() as db, db.begin():
        outcome = _repository(settings).reserve_starting_blank(db, now=now)

    assert outcome == PoolEvictionRequired(oldest_id)
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(ChatSandboxPool)) == 0


def test_concurrent_reservations_create_one_starting_row_and_one_spend_interval(
    tmp_path,
):
    settings = _settings(chat_blank_pool_min=1, chat_blank_pool_max=2)
    sessions = _file_database(tmp_path / "pool-reservation.db")
    now = datetime.now(UTC)
    capacity_lock = threading.Lock()

    def lock_capacity(db, *, wait=True):
        acquired = capacity_lock.acquire(blocking=wait)
        if acquired:
            db.info["capacity_lock_held"] = True
        return acquired

    def release_capacity_lock(db, transaction):
        if transaction.parent is None and db.info.pop("capacity_lock_held", False):
            capacity_lock.release()

    event.listen(sessions.class_, "after_transaction_end", release_capacity_lock)
    repository = _repository(
        settings,
        capacity_locker=lock_capacity,
        tokens=("reserve-operation",),
        generations=("generation-reservation",),
        pool_ids=(uuid.uuid4(),),
    )

    def reserve():
        with sessions() as db, db.begin():
            spend = ChatSandboxSpendService(db, settings)
            return repository.reserve_starting_blank(
                db,
                now=now,
                interval_reserver=lambda generation: spend.reserve_interval(
                    origin="blank_pool",
                    worker_generation=generation,
                    now=now,
                    capacity_locked=True,
                ),
            )

    with ThreadPoolExecutor(max_workers=2) as workers:
        outcomes = [workers.submit(reserve), workers.submit(reserve)]
        outcomes = [future.result(timeout=2) for future in outcomes]

    assert sum(isinstance(item, PoolStartReservation) for item in outcomes) == 1
    with sessions() as db:
        pool_rows = list(db.execute(select(ChatSandboxPool)).scalars())
        intervals = list(db.execute(select(ChatSandboxComputeInterval)).scalars())
    assert len(pool_rows) == 1
    assert pool_rows[0].state == "starting"
    assert len(intervals) == 1
    assert intervals[0].worker_generation == pool_rows[0].worker_generation
    reservation = next(
        item for item in outcomes if isinstance(item, PoolStartReservation)
    )
    assert reservation.interval_id == intervals[0].id


def test_spend_denial_commits_circuit_side_effect_without_pool_row():
    settings = _settings(
        chat_sandbox_spend_enforcement_enabled=True,
        chat_sandbox_budget_attestation="attested",
        chat_sandbox_warning_microusd=500_000,
        chat_sandbox_application_cap_microusd=1_000_000,
        chat_sandbox_environment_cap_microusd=2_000_000,
        chat_sandbox_workspace_cap_microusd=3_000_000,
    )
    sessions = _database()
    now = datetime.now(UTC)
    repository = _repository(settings)

    with sessions() as db, db.begin():
        spend = ChatSandboxSpendService(db, settings)
        with pytest.raises(ChatComputeDisabled):
            repository.reserve_starting_blank(
                db,
                now=now,
                interval_reserver=lambda generation: spend.reserve_interval(
                    origin="blank_pool",
                    worker_generation=generation,
                    now=now,
                    capacity_locked=True,
                ),
            )

    with sessions() as db:
        state = db.execute(select(ChatSandboxBudgetState)).scalar_one()
        event_row = db.execute(select(ChatSandboxCircuitEvent)).scalar_one()
        pool_count = db.scalar(select(func.count()).select_from(ChatSandboxPool))
        interval_count = db.scalar(
            select(func.count()).select_from(ChatSandboxComputeInterval)
        )
    assert state.circuit_state == "tripped"
    assert state.trip_reason == "safety_reserve"
    assert event_row.event_type == "circuit_tripped"
    assert pool_count == 0
    assert interval_count == 0


def test_land_provider_creation_requires_and_lands_exact_reservation():
    settings = _settings()
    sessions = _database()
    reserved_at = datetime.now(UTC)
    landed_at = reserved_at + timedelta(seconds=5)
    repository = _repository(
        settings,
        tokens=("reserve-operation",),
        generations=("generation-reservation",),
        pool_ids=(uuid.uuid4(),),
    )
    with sessions() as db, db.begin():
        reservation = repository.reserve_starting_blank(db, now=reserved_at)
    assert isinstance(reservation, PoolStartReservation)

    with sessions() as db, db.begin():
        outcome = repository.land_provider_creation(
            db,
            reservation,
            "sb-landed",
            now=landed_at,
        )

    assert outcome is PoolLandingOutcome.LANDED
    with sessions() as db:
        row = db.get(ChatSandboxPool, reservation.pool_id)
    assert row.state == "blank_ready"
    assert row.modal_sandbox_id == "sb-landed"
    assert row.worker_generation == reservation.worker_generation
    assert row.claim_token_hash == reservation.token_hash
    assert row.ready_at is not None
    assert row.last_health_checked_at is not None


@pytest.mark.parametrize(
    "mutation",
    [
        "state",
        "sandbox_id",
        "token",
        "generation",
        "claim_generation",
        "image",
        "contract",
        "release",
        "resources",
    ],
)
def test_stale_landing_cannot_overwrite_any_successor_identity(mutation):
    settings = _settings()
    sessions = _database()
    now = datetime.now(UTC)
    repository = _repository(
        settings,
        tokens=("reserve-operation",),
        generations=("generation-reservation",),
        pool_ids=(uuid.uuid4(),),
    )
    with sessions() as db, db.begin():
        reservation = repository.reserve_starting_blank(db, now=now)
    assert isinstance(reservation, PoolStartReservation)
    with sessions() as db, db.begin():
        successor = db.get(ChatSandboxPool, reservation.pool_id)
        if mutation == "state":
            successor.state = "draining"
        elif mutation == "sandbox_id":
            successor.modal_sandbox_id = "sb-successor"
        elif mutation == "token":
            successor.claim_token_hash = "successor-token"
        elif mutation == "generation":
            successor.worker_generation = "generation-successor"
        elif mutation == "claim_generation":
            successor.claim_generation += 1
        elif mutation == "image":
            successor.image_version = "im-successor"
        elif mutation == "contract":
            successor.worker_contract_version = "worker-successor"
        elif mutation == "release":
            successor.app_release_id = "release-successor"
        elif mutation == "resources":
            successor.memory_limit_mib += 1

    with sessions() as db, db.begin():
        outcome = repository.land_provider_creation(
            db,
            reservation,
            "sb-stale-provider",
            now=now + timedelta(seconds=5),
        )

    assert outcome is PoolLandingOutcome.OWNERSHIP_CHANGED
    with sessions() as db:
        row = db.get(ChatSandboxPool, reservation.pool_id)
    assert row.modal_sandbox_id != "sb-stale-provider"


def test_termination_uses_persisted_id_and_fresh_duplicate_cannot_downgrade():
    settings = _settings()
    sessions = _database()
    now = datetime.now(UTC)
    row = _pool(settings, sandbox_id="sb-persisted")
    with sessions() as db, db.begin():
        db.add(row)
    repository = _repository(
        settings,
        tokens=("termination-owner", "termination-duplicate"),
    )

    with sessions() as db, db.begin():
        claim = repository.claim_termination(
            db,
            row.id,
            None,
            failure_code=None,
            now=now,
            stale_draining_before=now - timedelta(seconds=30),
        )
    assert isinstance(claim, PoolTerminationClaim)
    assert claim.sandbox_id == "sb-persisted"

    with sessions() as db, db.begin():
        duplicate = repository.claim_termination(
            db,
            row.id,
            None,
            failure_code="duplicate_failure",
            now=now + timedelta(seconds=1),
            stale_draining_before=now - timedelta(seconds=30),
        )
    assert duplicate is None
    with sessions() as db:
        draining = db.get(ChatSandboxPool, row.id)
    assert draining.claim_token_hash == claim.token_hash
    assert draining.failure_code is None

    with sessions() as db, db.begin():
        finished = repository.finish_termination(
            db,
            claim,
            confirmed=True,
            now=now + timedelta(seconds=2),
        )
    assert finished is PoolTerminationFinishOutcome.FINISHED
    with sessions() as db, db.begin():
        replay = repository.finish_termination(
            db,
            claim,
            confirmed=False,
            now=now + timedelta(seconds=3),
        )
    assert replay is PoolTerminationFinishOutcome.OWNERSHIP_CHANGED
    with sessions() as db:
        terminated = db.get(ChatSandboxPool, row.id)
    assert terminated.state == "terminated"
    assert terminated.failure_code is None


def test_stale_termination_takeover_preserves_first_failure_and_fences_finisher():
    settings = _settings()
    sessions = _database()
    now = datetime.now(UTC)
    row = _pool(settings)
    row.failure_code = "first_failure"
    with sessions() as db, db.begin():
        db.add(row)
    repository = _repository(
        settings,
        tokens=("termination-first", "termination-successor"),
    )

    with sessions() as db, db.begin():
        first = repository.claim_termination(
            db,
            row.id,
            row.modal_sandbox_id,
            failure_code="second_failure",
            now=now,
            stale_draining_before=now - timedelta(seconds=30),
        )
    assert isinstance(first, PoolTerminationClaim)
    assert first.failure_code == "first_failure"

    with sessions() as db, db.begin():
        successor = repository.claim_termination(
            db,
            row.id,
            row.modal_sandbox_id,
            failure_code="third_failure",
            now=now + timedelta(minutes=1),
            stale_draining_before=now + timedelta(seconds=30),
        )
    assert isinstance(successor, PoolTerminationClaim)
    assert successor.token_hash != first.token_hash
    assert successor.failure_code == "first_failure"

    with sessions() as db, db.begin():
        stale_finish = repository.finish_termination(
            db,
            first,
            confirmed=True,
            now=now + timedelta(minutes=1, seconds=1),
        )
    assert stale_finish is PoolTerminationFinishOutcome.OWNERSHIP_CHANGED
    with sessions() as db:
        still_owned = db.get(ChatSandboxPool, row.id)
    assert still_owned.state == "draining"
    assert still_owned.claim_token_hash == successor.token_hash

    with sessions() as db, db.begin():
        finish = repository.finish_termination(
            db,
            successor,
            confirmed=True,
            now=now + timedelta(minutes=1, seconds=2),
        )
    assert finish is PoolTerminationFinishOutcome.FINISHED
    with sessions() as db:
        failed = db.get(ChatSandboxPool, row.id)
    assert failed.state == "failed"
    assert failed.failure_code == "first_failure"


@pytest.mark.parametrize("mutation", ["pool_id", "state", "sandbox_id", "token"])
def test_finish_termination_requires_exact_owned_identity(mutation):
    settings = _settings()
    sessions = _database()
    now = datetime.now(UTC)
    row = _pool(settings)
    with sessions() as db, db.begin():
        db.add(row)
    repository = _repository(settings, tokens=("termination-owner",))
    with sessions() as db, db.begin():
        claim = repository.claim_termination(
            db,
            row.id,
            row.modal_sandbox_id,
            failure_code=None,
            now=now,
            stale_draining_before=now - timedelta(seconds=30),
        )
    assert isinstance(claim, PoolTerminationClaim)

    stale_claim = claim
    if mutation == "pool_id":
        stale_claim = replace(claim, pool_id=uuid.uuid4())
    elif mutation == "sandbox_id":
        stale_claim = replace(claim, sandbox_id="sb-successor")
    elif mutation == "token":
        stale_claim = replace(claim, token_hash="successor-token")
    else:
        with sessions() as db, db.begin():
            db.get(ChatSandboxPool, row.id).state = "blank_ready"

    with sessions() as db, db.begin():
        outcome = repository.finish_termination(
            db,
            stale_claim,
            confirmed=True,
            now=now + timedelta(seconds=1),
        )

    assert outcome is PoolTerminationFinishOutcome.OWNERSHIP_CHANGED
    with sessions() as db:
        current = db.get(ChatSandboxPool, row.id)
    assert current.terminated_at is None
    assert current.failure_code is None


def test_unconfirmed_provider_termination_is_durably_uncertain():
    settings = _settings()
    sessions = _database()
    now = datetime.now(UTC)
    row = _pool(settings)
    with sessions() as db, db.begin():
        db.add(row)
    repository = _repository(settings, tokens=("termination-owner",))
    with sessions() as db, db.begin():
        claim = repository.claim_termination(
            db,
            row.id,
            row.modal_sandbox_id,
            failure_code="sandbox_lost",
            now=now,
            stale_draining_before=now - timedelta(seconds=30),
        )
    assert isinstance(claim, PoolTerminationClaim)

    with sessions() as db, db.begin():
        outcome = repository.finish_termination(
            db,
            claim,
            confirmed=False,
            now=now + timedelta(seconds=1),
        )

    assert outcome is PoolTerminationFinishOutcome.FINISHED
    with sessions() as db:
        failed = db.get(ChatSandboxPool, row.id)
    assert failed.state == "failed"
    assert failed.failure_code == "termination_uncertain"
    assert failed.terminated_at is not None


def test_repository_never_commits_or_touches_a_provider():
    settings = _settings()
    sessions = _database(session_class=_CommitForbiddenSession)
    now = datetime.now(UTC)
    repository = _repository(
        settings,
        tokens=("reserve-operation",),
        generations=("generation-reservation",),
        pool_ids=(uuid.uuid4(),),
    )

    class ProviderMustNotRun:
        def __getattr__(self, name):
            raise AssertionError(f"pool repository attempted provider I/O: {name}")

    repository.provider = ProviderMustNotRun()
    with sessions() as db:
        reservation = repository.reserve_starting_blank(db, now=now)
        assert isinstance(reservation, PoolStartReservation)
        db.flush()
        assert db.get(ChatSandboxPool, reservation.pool_id) is not None
        db.rollback()

    with sessions() as db:
        assert db.get(ChatSandboxPool, reservation.pool_id) is None
