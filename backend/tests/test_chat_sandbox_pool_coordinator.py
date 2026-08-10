from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from itertools import count
from types import SimpleNamespace

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
from backend.services.chat_sandbox_pool_coordinator import (
    ChatSandboxPoolCoordinator,
)
from backend.services.chat_sandbox_pool_repository import (
    ChatSandboxPoolRepository,
    PoolTerminationClaim,
)
from backend.services.chat_sandbox_provider import SandboxError
from backend.services.chat_sandbox_spend_service import ChatSandboxSpendService
from backend.services.chat_sandbox_worker_transport import (
    ChatSandboxWorkerTransport,
    SessionControl,
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
        "chat_blank_pool_refill_concurrency": 2,
        "chat_sandbox_total_live_cap": 4,
        "chat_sandbox_cpu": 0.125,
        "chat_sandbox_cpu_limit": 1,
        "chat_sandbox_memory_mib": 512,
        "chat_sandbox_memory_limit_mib": 2048,
        "chat_sandbox_spend_enforcement_enabled": False,
        "chat_sandbox_budget_attestation": "attested",
        "chat_workspace_snapshots_enabled": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


class _TrackedSession(Session):
    pass


class _TransactionProbe:
    def __init__(self) -> None:
        self.active = 0
        self.provider_calls: list[str] = []

    def attach(self, sessions) -> None:
        def after_begin(db, transaction, _connection):
            if transaction.parent is None and not db.info.get("probe_active"):
                db.info["probe_active"] = True
                self.active += 1

        def after_transaction_end(db, transaction):
            if transaction.parent is None and db.info.pop("probe_active", False):
                self.active -= 1

        event.listen(sessions.class_, "after_begin", after_begin)
        event.listen(sessions.class_, "after_transaction_end", after_transaction_end)

    def outside_transaction(self, operation: str) -> None:
        assert self.active == 0, f"{operation} ran inside a database transaction"
        self.provider_calls.append(operation)


def _database(probe: _TransactionProbe):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    for table in (
        ChatSession.__table__,
        ChatSandboxPool.__table__,
        ChatSandboxLease.__table__,
        ChatSandboxBudgetState.__table__,
        ChatSandboxComputeInterval.__table__,
        ChatSandboxCircuitEvent.__table__,
    ):
        table.create(engine)
    sessions = sessionmaker(
        bind=engine,
        expire_on_commit=False,
        class_=_TrackedSession,
    )
    probe.attach(sessions)
    return sessions


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
        self.tick = 100.0

    def utcnow(self) -> datetime:
        return self.now

    def monotonic(self) -> float:
        return self.tick

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)
        self.tick += seconds


class _Provider:
    def __init__(self, probe: _TransactionProbe) -> None:
        self.probe = probe
        self.sandboxes: dict[str, object] = {}
        self.poll_result = None
        self.health_result = True
        self.termination_confirmed = True
        self.termination_calls: list[str] = []
        self.termination_hook = None

    async def create(self, **_kwargs):
        raise AssertionError("increment-A coordinator must not create providers")

    async def resolve(self, sandbox_id: str):
        self.probe.outside_transaction("provider.resolve")
        await asyncio.sleep(0)
        return self.sandboxes.setdefault(
            sandbox_id,
            SimpleNamespace(object_id=sandbox_id),
        )

    async def poll(self, _sandbox):
        self.probe.outside_transaction("provider.poll")
        await asyncio.sleep(0)
        return self.poll_result

    async def health(self, _sandbox, *, persistent, worker_generation):
        self.probe.outside_transaction("provider.health")
        assert persistent is True
        assert worker_generation
        await asyncio.sleep(0)
        return self.health_result

    async def terminate(self, sandbox_id: str, _sandbox=None):
        self.probe.outside_transaction("provider.terminate")
        self.termination_calls.append(sandbox_id)
        call_number = len(self.termination_calls)
        if self.termination_hook is not None:
            await self.termination_hook(call_number, sandbox_id)
        return self.termination_confirmed

    async def open_persistent_connection(self, *_args, **_kwargs):
        raise AssertionError("not used by increment-A coordinator tests")

    async def open_turn_process(self, *_args, **_kwargs):
        raise AssertionError("not used by increment-A coordinator tests")

    async def get_tags(self, _sandbox):
        raise AssertionError("not used by increment-A coordinator tests")

    async def iter_sandboxes(self, **_kwargs):
        if False:
            yield None


class _Transport(ChatSandboxWorkerTransport):
    def __init__(self, provider: _Provider, probe: _TransactionProbe) -> None:
        super().__init__(provider, clock=lambda: 100.0)
        self.probe = probe
        self.ping_result = True
        self.ping_calls: list[tuple[str, str]] = []

    async def ping(self, control: SessionControl, worker_generation: str) -> bool:
        self.probe.outside_transaction("transport.ping")
        self.ping_calls.append((control.sandbox_id, worker_generation))
        await asyncio.sleep(0)
        return self.ping_result


class _Harness:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        capacity_locker=None,
        lease_loader=None,
        spend_factory=None,
    ) -> None:
        self.settings = settings or _settings()
        self.clock = _Clock()
        self.probe = _TransactionProbe()
        self.sessions = _database(self.probe)
        token_counter = count(1)
        self.repository = ChatSandboxPoolRepository(
            self.settings,
            capacity_locker=(capacity_locker or (lambda _db, *, wait=True: True)),
            lease_loader=lease_loader,
            token_factory=lambda: f"operation-{next(token_counter)}",
        )
        self.provider = _Provider(self.probe)
        self.transport = _Transport(self.provider, self.probe)
        self.coordinator = ChatSandboxPoolCoordinator(
            self.settings,
            session_factory=self.sessions,
            repository=self.repository,
            provider=self.provider,
            transport=self.transport,
            spend_factory=(
                spend_factory or (lambda db: ChatSandboxSpendService(db, self.settings))
            ),
            utcnow=self.clock.utcnow,
            monotonic=self.clock.monotonic,
        )


def _session(session_id: uuid.UUID) -> ChatSession:
    return ChatSession(
        id=session_id,
        hf_user_id=f"owner-{session_id}",
        hf_username=f"owner-{session_id}",
        selected_model="google/gemma-4-31B-it",
        execution_backend="modal_cli",
    )


def _pool(
    harness: _Harness,
    *,
    sandbox_id: str | None = "sb-blank",
    state: str = "blank_ready",
    release_id: str | None = None,
) -> ChatSandboxPool:
    now = harness.clock.utcnow()
    return ChatSandboxPool(
        id=uuid.uuid4(),
        modal_sandbox_id=sandbox_id,
        state=state,
        image_version=harness.settings.chat_modal_image_version,
        worker_contract_version=harness.settings.chat_worker_contract_version,
        worker_generation=f"generation-{uuid.uuid4().hex[:8]}",
        app_release_id=release_id or harness.settings.release_id,
        created_at=now - timedelta(minutes=2),
        ready_at=now - timedelta(minutes=1) if state != "starting" else None,
        expires_at=now + timedelta(hours=1),
        updated_at=now - timedelta(minutes=1),
        cpu_request=harness.settings.chat_sandbox_cpu,
        cpu_limit=(
            harness.settings.chat_sandbox_cpu_limit or harness.settings.chat_sandbox_cpu
        ),
        memory_request_mib=harness.settings.chat_sandbox_memory_mib,
        memory_limit_mib=(
            harness.settings.chat_sandbox_memory_limit_mib
            or harness.settings.chat_sandbox_memory_mib
        ),
        billing_month=now.date().replace(day=1),
    )


def _interval(
    harness: _Harness,
    row: ChatSandboxPool,
    *,
    reserved_microusd: int = 1,
) -> ChatSandboxComputeInterval:
    now = harness.clock.utcnow()
    return ChatSandboxComputeInterval(
        id=uuid.uuid4(),
        modal_sandbox_id=row.modal_sandbox_id,
        environment=harness.settings.environment,
        modal_app="pwc-chat-sandboxes",
        app_release_id=harness.settings.release_id,
        image_version=harness.settings.chat_modal_image_version,
        worker_generation=row.worker_generation,
        origin="blank_pool",
        cpu_request_millicores=round(harness.settings.chat_sandbox_cpu * 1000),
        cpu_limit_millicores=round(
            (
                harness.settings.chat_sandbox_cpu_limit
                or harness.settings.chat_sandbox_cpu
            )
            * 1000
        ),
        memory_request_mib=harness.settings.chat_sandbox_memory_mib,
        memory_limit_mib=(
            harness.settings.chat_sandbox_memory_limit_mib
            or harness.settings.chat_sandbox_memory_mib
        ),
        reserved_at=now - timedelta(minutes=2),
        provider_created_at=now - timedelta(minutes=2),
        billing_cycle=now.date().replace(day=1),
        reserved_microusd=reserved_microusd,
        updated_at=now,
    )


def _control(sandbox: object) -> SessionControl:
    return SessionControl(
        process=SimpleNamespace(),
        sandbox=sandbox,
        sandbox_id=sandbox.object_id,
        stderr_task=None,
        reader_task=None,
        queues={},
        resume_id=None,
    )


def test_coordinator_requires_provider_and_transport_identity():
    harness = _Harness()
    other_provider = _Provider(harness.probe)

    with pytest.raises(ValueError, match="provider and transport must be shared"):
        ChatSandboxPoolCoordinator(
            harness.settings,
            session_factory=harness.sessions,
            repository=harness.repository,
            provider=other_provider,
            transport=harness.transport,
            spend_factory=lambda db: ChatSandboxSpendService(db, harness.settings),
        )


def test_fresh_local_health_claim_promotes_the_exact_control():
    harness = _Harness()
    session_id = uuid.uuid4()
    row = _pool(harness)
    sandbox = SimpleNamespace(object_id=row.modal_sandbox_id)
    control = _control(sandbox)
    harness.transport.register_blank_control(
        row.modal_sandbox_id,
        control,
        checked_at=harness.clock.monotonic(),
    )
    with harness.sessions() as db, db.begin():
        db.add_all([_session(session_id), row])

    result = asyncio.run(harness.coordinator.claim_blank(session_id))

    assert result == (sandbox, 0)
    assert harness.probe.provider_calls == []
    assert harness.transport.blank_control(row.modal_sandbox_id) is None
    assert harness.transport.session_control(session_id) is control


def test_provider_health_claim_is_release_agnostic_and_outside_transactions():
    harness = _Harness()
    session_id = uuid.uuid4()
    row = _pool(harness, release_id="release-previous")
    with harness.sessions() as db, db.begin():
        db.add_all([_session(session_id), row])

    result = asyncio.run(harness.coordinator.claim_blank(session_id))

    assert result is not None
    assert result[0].object_id == row.modal_sandbox_id
    assert harness.probe.provider_calls == [
        "provider.resolve",
        "provider.poll",
        "provider.health",
    ]
    with harness.sessions() as db:
        claimed = db.get(ChatSandboxPool, row.id)
        lease = db.get(ChatSandboxLease, session_id)
    assert claimed.state == "claimed"
    assert claimed.app_release_id == "release-previous"
    assert lease.modal_sandbox_id == row.modal_sandbox_id


def test_concurrent_claims_commit_one_exact_claim_and_spend_assignment():
    harness = _Harness(settings=_settings(chat_sandbox_spend_enforcement_enabled=True))
    first_id, second_id = uuid.uuid4(), uuid.uuid4()
    row = _pool(harness)
    interval = _interval(harness, row)
    with harness.sessions() as db, db.begin():
        db.add_all([_session(first_id), _session(second_id), row, interval])

    async def run():
        return await asyncio.gather(
            harness.coordinator.claim_blank(first_id),
            harness.coordinator.claim_blank(second_id),
        )

    results = asyncio.run(run())

    assert sum(result is not None for result in results) == 1
    with harness.sessions() as db:
        leases = list(db.scalars(select(ChatSandboxLease)))
        assigned_interval = db.get(ChatSandboxComputeInterval, interval.id)
        claimed = db.get(ChatSandboxPool, row.id)
    assert claimed.state == "claimed"
    assert claimed.claim_generation == 1
    assert len(leases) == 1
    assert assigned_interval.chat_session_id == leases[0].chat_session_id
    assert assigned_interval.claimed_at is not None


def test_claim_orders_capacity_availability_lease_pool_and_spend():
    order: list[str] = []

    def lock_capacity(_db, *, wait=True):
        assert wait is True
        order.append("capacity")
        return True

    def load_lease(db, session_id, *, lock):
        assert lock is True
        order.append("lease")
        return db.get(ChatSandboxLease, session_id)

    class Spend:
        def assert_available(self, _now, *, capacity_locked):
            assert capacity_locked is True
            order.append("availability")

        def claim(self, _sandbox_id, _session_id, _now):
            order.append("spend")

    harness = _Harness(
        settings=_settings(chat_sandbox_spend_enforcement_enabled=True),
        capacity_locker=lock_capacity,
        lease_loader=load_lease,
        spend_factory=lambda _db: Spend(),
    )
    session_id = uuid.uuid4()
    row = _pool(harness)
    sandbox = SimpleNamespace(object_id=row.modal_sandbox_id)
    harness.transport.register_blank_control(
        row.modal_sandbox_id,
        _control(sandbox),
        checked_at=harness.clock.monotonic(),
    )
    with harness.sessions() as db, db.begin():
        db.add_all([_session(session_id), row])
    pool_selects = 0

    def record_pool_select(_connection, _cursor, statement, *_args):
        nonlocal pool_selects
        if statement.lstrip().startswith("SELECT") and "chat_sandbox_pool" in statement:
            pool_selects += 1
            order.append("candidate" if pool_selects == 1 else "pool")

    event.listen(
        harness.sessions.kw["bind"],
        "before_cursor_execute",
        record_pool_select,
    )

    assert asyncio.run(harness.coordinator.claim_blank(session_id)) == (sandbox, 0)
    assert order == [
        "candidate",
        "capacity",
        "availability",
        "lease",
        "pool",
        "spend",
    ]


def test_claim_transaction_rolls_back_when_injected_lease_loader_fails():
    def fail_lease_load(*_args, **_kwargs):
        raise RuntimeError("simulated lease failure")

    harness = _Harness(lease_loader=fail_lease_load)
    session_id = uuid.uuid4()
    row = _pool(harness)
    with harness.sessions() as db, db.begin():
        db.add_all([_session(session_id), row])

    with pytest.raises(RuntimeError, match="simulated lease failure"):
        asyncio.run(harness.coordinator.claim_blank(session_id))

    with harness.sessions() as db:
        unchanged = db.get(ChatSandboxPool, row.id)
        lease_count = db.scalar(select(func.count()).select_from(ChatSandboxLease))
    assert unchanged.state == "blank_ready"
    assert unchanged.claimed_at is None
    assert lease_count == 0


def test_spend_denial_commits_circuit_but_does_not_claim_blank():
    harness = _Harness(
        settings=_settings(
            chat_sandbox_spend_enforcement_enabled=True,
            chat_sandbox_warning_microusd=500_000,
            chat_sandbox_application_cap_microusd=1_000_000,
            chat_sandbox_environment_cap_microusd=2_000_000,
            chat_sandbox_workspace_cap_microusd=3_000_000,
        )
    )
    session_id = uuid.uuid4()
    row = _pool(harness)
    interval = _interval(harness, row, reserved_microusd=1_000_000)
    with harness.sessions() as db, db.begin():
        db.add_all([_session(session_id), row, interval])

    with pytest.raises(SandboxError) as raised:
        asyncio.run(harness.coordinator.claim_blank(session_id))

    assert raised.value.code == "chat_temporarily_disabled"
    with harness.sessions() as db:
        unchanged = db.get(ChatSandboxPool, row.id)
        state = db.execute(select(ChatSandboxBudgetState)).scalar_one()
        event_row = db.execute(select(ChatSandboxCircuitEvent)).scalar_one()
        lease_count = db.scalar(select(func.count()).select_from(ChatSandboxLease))
    assert unchanged.state == "blank_ready"
    assert state.circuit_state == "tripped"
    assert event_row.event_type == "circuit_tripped"
    assert lease_count == 0


def test_unhealthy_provider_blank_is_disposed_outside_the_claim_transaction():
    harness = _Harness()
    harness.provider.health_result = False
    session_id = uuid.uuid4()
    row = _pool(harness)
    with harness.sessions() as db, db.begin():
        db.add_all([_session(session_id), row])

    assert asyncio.run(harness.coordinator.claim_blank(session_id)) is None

    assert harness.probe.provider_calls == [
        "provider.resolve",
        "provider.poll",
        "provider.health",
        "provider.terminate",
    ]
    assert harness.provider.termination_calls == [row.modal_sandbox_id]
    with harness.sessions() as db:
        failed = db.get(ChatSandboxPool, row.id)
    assert failed.state == "failed"
    assert failed.failure_code == "sandbox_lost"


def test_termination_uses_persisted_sandbox_id_when_hint_is_none():
    harness = _Harness()
    row = _pool(harness, sandbox_id="sb-persisted")
    with harness.sessions() as db, db.begin():
        db.add(row)

    async def assert_preclaim_committed(_call_number, sandbox_id):
        with harness.sessions() as db:
            draining = db.get(ChatSandboxPool, row.id)
        assert sandbox_id == "sb-persisted"
        assert draining.state == "draining"
        assert draining.claim_token_hash is not None

    harness.provider.termination_hook = assert_preclaim_committed

    assert (
        asyncio.run(
            harness.coordinator.terminate_pool_row(
                row.id,
                None,
                failure_code=None,
            )
        )
        is True
    )
    assert harness.provider.termination_calls == ["sb-persisted"]
    with harness.sessions() as db:
        terminated = db.get(ChatSandboxPool, row.id)
    assert terminated.state == "terminated"


def test_fresh_duplicate_termination_cannot_steal_the_provider_claim():
    harness = _Harness()
    row = _pool(harness)
    with harness.sessions() as db, db.begin():
        db.add(row)

    async def run():
        started = asyncio.Event()
        release = asyncio.Event()

        async def block_first(call_number, _sandbox_id):
            if call_number == 1:
                started.set()
                await release.wait()

        harness.provider.termination_hook = block_first
        first = asyncio.create_task(
            harness.coordinator.terminate_pool_row(
                row.id,
                row.modal_sandbox_id,
                failure_code=None,
            )
        )
        await started.wait()
        duplicate = await harness.coordinator.terminate_pool_row(
            row.id,
            row.modal_sandbox_id,
            failure_code="duplicate_failure",
        )
        release.set()
        return await first, duplicate

    first, duplicate = asyncio.run(run())

    assert first is True
    assert duplicate is False
    assert harness.provider.termination_calls == [row.modal_sandbox_id]


def test_stale_takeover_changes_token_and_fences_the_first_finisher():
    harness = _Harness()
    row = _pool(harness)
    with harness.sessions() as db, db.begin():
        db.add(row)

    async def run():
        first_started = asyncio.Event()
        release_first = asyncio.Event()

        async def block_first(call_number, _sandbox_id):
            if call_number == 1:
                first_started.set()
                await release_first.wait()

        harness.provider.termination_hook = block_first
        first = asyncio.create_task(
            harness.coordinator.terminate_pool_row(
                row.id,
                row.modal_sandbox_id,
                failure_code="first_failure",
            )
        )
        await first_started.wait()
        with harness.sessions() as db:
            first_token = db.get(ChatSandboxPool, row.id).claim_token_hash
        harness.clock.advance(harness.coordinator.termination_claim_timeout_seconds + 1)
        successor = await harness.coordinator.terminate_pool_row(
            row.id,
            row.modal_sandbox_id,
            failure_code="second_failure",
        )
        with harness.sessions() as db:
            successor_token = db.get(ChatSandboxPool, row.id).claim_token_hash
        release_first.set()
        return await first, successor, first_token, successor_token

    first, successor, first_token, successor_token = asyncio.run(run())

    assert first is False
    assert successor is True
    assert successor_token != first_token
    with harness.sessions() as db:
        failed = db.get(ChatSandboxPool, row.id)
    assert failed.state == "failed"
    assert failed.failure_code == "first_failure"


def test_unconfirmed_termination_preserves_spend_reason_and_marks_uncertainty():
    harness = _Harness(settings=_settings(chat_sandbox_spend_enforcement_enabled=True))
    harness.provider.termination_confirmed = False
    row = _pool(harness)
    interval = _interval(harness, row)
    with harness.sessions() as db, db.begin():
        db.add_all([row, interval])

    assert (
        asyncio.run(
            harness.coordinator.terminate_pool_row(
                row.id,
                row.modal_sandbox_id,
                failure_code="sandbox_lost",
            )
        )
        is True
    )

    with harness.sessions() as db:
        failed = db.get(ChatSandboxPool, row.id)
        spend = db.get(ChatSandboxComputeInterval, interval.id)
    assert failed.state == "failed"
    assert failed.failure_code == "termination_uncertain"
    assert spend.terminal_reason == "sandbox_lost"
    assert spend.reconciliation_state == "termination_uncertain"


def test_exact_finish_ownership_loss_does_not_mutate_successor_or_spend():
    harness = _Harness(settings=_settings(chat_sandbox_spend_enforcement_enabled=True))
    row = _pool(harness)
    interval = _interval(harness, row)
    with harness.sessions() as db, db.begin():
        db.add_all([row, interval])
    with harness.sessions() as db, db.begin():
        claim = harness.repository.claim_termination(
            db,
            row.id,
            row.modal_sandbox_id,
            failure_code=None,
            now=harness.clock.utcnow(),
            stale_draining_before=harness.clock.utcnow() - timedelta(minutes=1),
        )
    assert isinstance(claim, PoolTerminationClaim)
    with harness.sessions() as db, db.begin():
        successor = db.get(ChatSandboxPool, row.id)
        successor.claim_token_hash = "successor-token"

    assert asyncio.run(harness.coordinator.terminate_claimed_pool_row(claim)) is False

    with harness.sessions() as db:
        successor = db.get(ChatSandboxPool, row.id)
        spend = db.get(ChatSandboxComputeInterval, interval.id)
    assert successor.state == "draining"
    assert successor.claim_token_hash == "successor-token"
    assert successor.terminated_at is None
    assert spend.termination_requested_at is None


def test_termination_batch_is_bounded_by_configured_concurrency():
    harness = _Harness(
        settings=_settings(
            chat_blank_pool_max=4,
            chat_blank_pool_refill_concurrency=2,
        )
    )
    rows = [_pool(harness, sandbox_id=f"sb-{index}") for index in range(5)]
    with harness.sessions() as db, db.begin():
        db.add_all(rows)
    claims = []
    with harness.sessions() as db, db.begin():
        for row in rows:
            claim = harness.repository.claim_termination(
                db,
                row.id,
                row.modal_sandbox_id,
                failure_code=None,
                now=harness.clock.utcnow(),
                stale_draining_before=harness.clock.utcnow() - timedelta(minutes=1),
            )
            assert isinstance(claim, PoolTerminationClaim)
            claims.append(claim)

    async def run():
        release = asyncio.Event()
        two_started = asyncio.Event()
        active = 0
        maximum = 0

        async def block(call_number, _sandbox_id):
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            if call_number == 2:
                two_started.set()
            await release.wait()
            active -= 1

        harness.provider.termination_hook = block
        task = asyncio.create_task(
            harness.coordinator.terminate_claimed_pool_rows(claims)
        )
        await two_started.wait()
        await asyncio.sleep(0)
        assert len(harness.provider.termination_calls) == 2
        release.set()
        return await task, maximum

    terminated, maximum = asyncio.run(run())

    assert harness.coordinator.termination_concurrency == 2
    assert terminated == 5
    assert maximum == 2
