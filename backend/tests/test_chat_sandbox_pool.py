from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.chat_sandbox_worker.protocol import encode_frame
from backend.config import Settings
from backend.models.database import (
    ChatSandboxLease,
    ChatSandboxPool,
    ChatSession,
)
from backend.services import chat_sandbox_service
from backend.services.chat_sandbox_pool_coordinator import PoolMaintenanceResult
from backend.services.chat_sandbox_service import (
    SandboxError,
    SandboxSessionManager,
    WorkerClaim,
)


def _settings(**overrides) -> Settings:
    values = {
        "environment": "staging",
        "release_id": "release-a",
        "chat_persistent_worker_enabled": True,
        "chat_blank_pool_enabled": True,
        "chat_blank_pool_min": 1,
        "chat_blank_pool_max": 1,
        "chat_blank_pool_min_remaining_seconds": 240,
        "chat_blank_pool_rotate_before_seconds": 3600,
        "chat_blank_pool_refill_concurrency": 1,
        "chat_blank_pool_monthly_budget_usd": 35,
        "chat_blank_pool_reported_month_to_date_usd": 0,
        "chat_sandbox_total_live_cap": 2,
        "chat_modal_image_version": "im-current",
        "chat_worker_contract_version": "14",
        "chat_sandbox_cpu": 0.125,
        "chat_sandbox_cpu_limit": 1,
        "chat_sandbox_memory_mib": 512,
        "chat_sandbox_memory_limit_mib": 2048,
    }
    values.update(overrides)
    return Settings(**values)


def _database():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    ChatSession.__table__.create(engine)
    ChatSandboxPool.__table__.create(engine)
    ChatSandboxLease.__table__.create(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _session(session_id: uuid.UUID) -> ChatSession:
    return ChatSession(
        id=session_id,
        hf_user_id=f"owner-{session_id}",
        hf_username=f"owner-{session_id}",
        selected_model="google/gemma-4-31B-it",
        execution_backend="modal_cli",
    )


def _blank(
    settings: Settings,
    *,
    sandbox_id: str = "sb-blank",
    release_id: str | None = None,
) -> ChatSandboxPool:
    now = datetime.now(UTC)
    return ChatSandboxPool(
        id=uuid.uuid4(),
        modal_sandbox_id=sandbox_id,
        state="blank_ready",
        image_version=settings.chat_modal_image_version,
        worker_contract_version=settings.chat_worker_contract_version,
        worker_generation="generation-a",
        app_release_id=release_id or settings.release_id,
        created_at=now - timedelta(minutes=1),
        ready_at=now - timedelta(seconds=50),
        expires_at=now + timedelta(hours=23),
        updated_at=now,
        cpu_request=settings.chat_sandbox_cpu,
        cpu_limit=settings.chat_sandbox_cpu_limit,
        memory_request_mib=settings.chat_sandbox_memory_mib,
        memory_limit_mib=settings.chat_sandbox_memory_limit_mib,
        billing_month=now.date().replace(day=1),
    )


def _manager(factory, settings: Settings) -> SandboxSessionManager:
    manager = SandboxSessionManager(settings, session_factory=factory)
    manager._lock_capacity = lambda _db, wait=True: True
    return manager


def test_claim_blank_facade_only_delegates_to_the_pool_coordinator():
    factory = _database()
    settings = _settings()
    manager = SandboxSessionManager(settings, session_factory=factory)
    session_id = uuid.uuid4()
    sandbox = SimpleNamespace(object_id="sb-claimed")
    delegated: list[uuid.UUID] = []

    class Coordinator:
        async def claim_blank(self, candidate_session_id):
            delegated.append(candidate_session_id)
            return sandbox, 7

    manager._sandbox_pool_coordinator = Coordinator()

    assert asyncio.run(manager.claim_blank(session_id)) == (sandbox, 7)
    assert delegated == [session_id]


def test_claim_blank_facade_does_not_spawn_refill_on_miss():
    manager = SandboxSessionManager(_settings(), session_factory=_database())
    session_id = uuid.uuid4()

    class Coordinator:
        async def claim_blank(self, candidate_session_id):
            assert candidate_session_id == session_id
            return None

    manager._sandbox_pool_coordinator = Coordinator()

    assert asyncio.run(manager.claim_blank(session_id)) is None


def test_replenish_pool_facade_only_delegates_to_the_pool_coordinator():
    manager = SandboxSessionManager(_settings(), session_factory=_database())
    calls = 0

    class Coordinator:
        async def replenish_pool(self):
            nonlocal calls
            calls += 1
            return 3

    manager._sandbox_pool_coordinator = Coordinator()

    assert asyncio.run(manager.replenish_pool()) == 3
    assert calls == 1


def test_maintenance_facades_only_delegate_to_the_pool_coordinator():
    manager = SandboxSessionManager(_settings(), session_factory=_database())
    calls: list[str] = []

    class Coordinator:
        async def maintain_pool(self):
            calls.append("maintain")
            return PoolMaintenanceResult(
                drained=1,
                lost=2,
                orphaned=3,
                abandoned=4,
                cleaned=5,
                replenished=6,
            )

        async def reconcile_pool_orphans(self):
            calls.append("orphans")
            return 7

    manager._sandbox_pool_coordinator = Coordinator()

    assert asyncio.run(manager.maintain_pool()) == {
        "drained": 1,
        "lost": 2,
        "orphaned": 3,
        "abandoned": 4,
        "cleaned": 5,
        "replenished": 6,
    }
    assert asyncio.run(manager.reconcile_pool_orphans()) == 7
    assert calls == ["maintain", "orphans"]


def test_incompatible_resource_envelope_cannot_be_claimed():
    factory = _database()
    settings = _settings()
    session_id = uuid.uuid4()
    blank = _blank(settings)
    blank.cpu_request = 0.25
    with factory() as db, db.begin():
        db.add_all([_session(session_id), blank])
    manager = _manager(factory, settings)

    assert asyncio.run(manager.claim_blank(session_id)) is None
    with factory() as db:
        row = db.execute(select(ChatSandboxPool)).scalar_one()
    assert row.state == "blank_ready"


def test_disposal_cannot_terminate_a_worker_after_claim_commit(monkeypatch):
    factory = _database()
    settings = _settings()
    claimed = _blank(settings)
    claimed.state = "claimed"
    claimed.claimed_at = datetime.now(UTC)
    with factory() as db, db.begin():
        db.add(claimed)
    manager = _manager(factory, settings)
    provider_lookups: list[str] = []

    async def from_id(sandbox_id: str):
        provider_lookups.append(sandbox_id)
        raise AssertionError("claimed provider worker must not be terminated")

    monkeypatch.setattr(
        chat_sandbox_service.modal.Sandbox,
        "from_id",
        SimpleNamespace(aio=from_id),
    )

    assert (
        asyncio.run(
            manager._terminate_pool_row(
                claimed.id,
                claimed.modal_sandbox_id,
                failure_code="sandbox_lost",
            )
        )
        is False
    )
    assert provider_lookups == []


def test_concurrent_replenishment_is_idempotent_and_blank(monkeypatch):
    factory = _database()
    settings = _settings()
    manager = _manager(factory, settings)
    creation_started = asyncio.Event()
    allow_creation = asyncio.Event()
    calls: list[tuple] = []

    coordinator = manager._pool_coordinator()

    async def create(*, name, tags, worker_generation):
        calls.append((name, tags))
        assert len(worker_generation) == 32
        creation_started.set()
        await allow_creation.wait()
        return SimpleNamespace(object_id="sb-new")

    monkeypatch.setattr(coordinator.provider, "create", create)
    sandbox = SimpleNamespace(object_id="sb-new")
    control = SimpleNamespace(sandbox_id="sb-new", sandbox=sandbox)

    async def start_control(_sandbox, worker_generation):
        assert len(worker_generation) == 32
        return control

    async def ping_control(candidate, _worker_generation):
        return candidate is control

    monkeypatch.setattr(
        coordinator.transport,
        "open_persistent_control",
        start_control,
    )
    monkeypatch.setattr(coordinator.transport, "ping", ping_control)

    async def run():
        first = asyncio.create_task(manager.replenish_pool())
        await creation_started.wait()
        second = asyncio.create_task(manager.replenish_pool())
        await asyncio.sleep(0)
        allow_creation.set()
        return await asyncio.gather(first, second)

    results = asyncio.run(run())
    assert sorted(results) == [0, 1]
    assert len(calls) == 1
    assert calls[0][0].startswith("chat-blank-")
    assert calls[0][1] == {
        "service": "pwc-chat",
        "environment": "staging",
        "pool": "blank",
        "pool_id": calls[0][0].removeprefix("chat-blank-"),
        "release": "release-a",
        "image": "im-current",
        "contract": "14",
    }
    with factory() as db:
        pool = db.execute(select(ChatSandboxPool)).scalar_one()
        lease_count = db.scalar(select(func.count()).select_from(ChatSandboxLease))
    assert pool.state == "blank_ready"
    assert pool.modal_sandbox_id == "sb-new"
    assert pool.last_health_checked_at is not None
    assert lease_count == 0
    assert manager._blank_controls == {"sb-new": control}


def test_reconcile_terminates_expired_busy_and_terminating_leases(monkeypatch):
    factory = _database()
    settings = _settings()
    manager = _manager(factory, settings)
    now = datetime.now(UTC)
    stale_busy_id, active_busy_id, terminating_id = (
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
    )
    stale_busy = _session(stale_busy_id)
    stale_busy.active_turn_id = uuid.uuid4()
    stale_busy.active_turn_expires_at = now - timedelta(minutes=1)
    active_busy = _session(active_busy_id)
    active_busy.active_turn_id = uuid.uuid4()
    active_busy.active_turn_expires_at = now + timedelta(minutes=1)
    terminating = _session(terminating_id)

    def lease(
        session_id: uuid.UUID,
        sandbox_id: str,
        state: str,
        *,
        expires_at: datetime | None = None,
    ) -> ChatSandboxLease:
        return ChatSandboxLease(
            chat_session_id=session_id,
            modal_sandbox_id=sandbox_id,
            app_release_id=settings.release_id,
            image_version=settings.chat_modal_image_version,
            worker_contract_version=settings.chat_worker_contract_version,
            worker_generation="generation-a",
            state=state,
            lease_expires_at=expires_at,
        )

    with factory() as db, db.begin():
        db.add_all(
            [
                stale_busy,
                active_busy,
                terminating,
                lease(stale_busy_id, "sb-stale-busy", "busy"),
                lease(active_busy_id, "sb-active-busy", "busy"),
                lease(
                    terminating_id,
                    "sb-terminating",
                    "terminating",
                    expires_at=now - timedelta(minutes=1),
                ),
            ]
        )

    terminated: list[str] = []

    class ProviderSandbox:
        def __init__(self, sandbox_id: str):
            async def terminate(*, wait):
                assert wait is False
                terminated.append(sandbox_id)

            self.terminate = SimpleNamespace(aio=terminate)

    async def from_id(sandbox_id: str):
        return ProviderSandbox(sandbox_id)

    monkeypatch.setattr(
        chat_sandbox_service.modal.Sandbox,
        "from_id",
        SimpleNamespace(aio=from_id),
    )

    assert asyncio.run(manager.reconcile()) == 2
    with factory() as db:
        stale_row = db.get(ChatSandboxLease, stale_busy_id)
        active_row = db.get(ChatSandboxLease, active_busy_id)
        terminating_row = db.get(ChatSandboxLease, terminating_id)
    assert sorted(terminated) == ["sb-stale-busy", "sb-terminating"]
    assert stale_row.state == "failed"
    assert stale_row.failure_code == "sandbox_worker_failed"
    assert stale_row.modal_sandbox_id is None
    assert active_row.state == "busy"
    assert active_row.modal_sandbox_id == "sb-active-busy"
    assert terminating_row.state == "terminated"
    assert terminating_row.modal_sandbox_id is None


def test_reported_modal_cost_is_a_floor_for_budget_enforcement():
    factory = _database()
    settings = _settings(chat_blank_pool_reported_month_to_date_usd=40)
    manager = _manager(factory, settings)

    status = manager.pool_budget_status()

    assert status["reported_usd"] == 40
    assert status["effective_accrued_usd"] == 40
    assert status["within_budget"] is False


def test_pool_miss_evicts_oldest_idle_worker_at_total_capacity(monkeypatch):
    factory = _database()
    settings = _settings()
    old_id, new_id = uuid.uuid4(), uuid.uuid4()
    now = datetime.now(UTC)
    starting_blank = _blank(settings)
    starting_blank.state = "starting"
    starting_blank.ready_at = None
    with factory() as db, db.begin():
        db.add_all(
            [
                _session(old_id),
                _session(new_id),
                starting_blank,
                ChatSandboxLease(
                    chat_session_id=old_id,
                    modal_sandbox_id="sb-old",
                    app_release_id=settings.release_id,
                    image_version=settings.chat_modal_image_version,
                    worker_contract_version=settings.chat_worker_contract_version,
                    worker_generation="generation-old",
                    state="idle",
                    last_activity_at=now - timedelta(minutes=1),
                    created_at=now - timedelta(minutes=2),
                    updated_at=now,
                ),
            ]
        )
    manager = _manager(factory, settings)
    manager._lock_start_claim = lambda *_args: None
    evicted: list[uuid.UUID] = []

    async def evict(session_id: uuid.UUID):
        evicted.append(session_id)
        with factory() as db, db.begin():
            lease = db.get(ChatSandboxLease, session_id)
            lease.modal_sandbox_id = None
            lease.state = "terminated"
        return True

    manager.snapshot_and_terminate = evict
    manager.enforce_warm_cap = lambda: asyncio.sleep(0, result=0)

    class Sandbox:
        object_id = "sb-new"
        terminate = SimpleNamespace(aio=lambda **_kwargs: asyncio.sleep(0))

    async def create(*_args, **_kwargs):
        return Sandbox()

    monkeypatch.setattr(chat_sandbox_service, "create_isolated_sandbox", create)

    result = asyncio.run(manager.ensure_ready(new_id, allow_pool=False, pool_miss=True))

    assert evicted == [old_id]
    assert result[0].object_id == "sb-new"
    assert result[3] == "pool_miss"
    with factory() as db:
        old_lease = db.get(ChatSandboxLease, old_id)
        new_lease = db.get(ChatSandboxLease, new_id)
    assert old_lease.state == "terminated"
    assert new_lease.state == "ready"
    assert new_lease.modal_sandbox_id == "sb-new"


def test_incompatible_session_lease_is_replaced_without_consuming_capacity(
    monkeypatch,
):
    factory = _database()
    settings = _settings()
    session_id = uuid.uuid4()
    now = datetime.now(UTC)
    with factory() as db, db.begin():
        db.add_all(
            [
                _session(session_id),
                _blank(settings),
                ChatSandboxLease(
                    chat_session_id=session_id,
                    modal_sandbox_id="sb-old",
                    app_release_id="release-old",
                    image_version="im-old",
                    worker_contract_version="13",
                    worker_generation="generation-old",
                    state="ready",
                    last_activity_at=now - timedelta(minutes=1),
                    created_at=now - timedelta(minutes=2),
                    updated_at=now,
                ),
            ]
        )
    manager = _manager(factory, settings)
    manager._lock_start_claim = lambda *_args: None
    terminated: list[str] = []

    async def terminate(sandbox_id: str):
        terminated.append(sandbox_id)
        return True

    manager._terminate_provider_sandbox = terminate
    manager.enforce_warm_cap = lambda: asyncio.sleep(0, result=0)

    class Sandbox:
        object_id = "sb-new"
        terminate = SimpleNamespace(aio=lambda **_kwargs: asyncio.sleep(0))

    async def create(*_args, **_kwargs):
        return Sandbox()

    monkeypatch.setattr(chat_sandbox_service, "create_isolated_sandbox", create)

    result = asyncio.run(manager.ensure_ready(session_id, allow_pool=False))

    assert terminated == ["sb-old"]
    assert result[0].object_id == "sb-new"
    with factory() as db:
        lease = db.get(ChatSandboxLease, session_id)
    assert lease.state == "ready"
    assert lease.image_version == settings.chat_modal_image_version
    assert lease.worker_contract_version == settings.chat_worker_contract_version
    assert lease.modal_sandbox_id == "sb-new"


def test_terminated_session_resume_evicts_oldest_idle_at_total_capacity(monkeypatch):
    factory = _database()
    settings = _settings()
    old_id, resumed_id = uuid.uuid4(), uuid.uuid4()
    now = datetime.now(UTC)
    with factory() as db, db.begin():
        db.add_all(
            [
                _session(old_id),
                _session(resumed_id),
                _blank(settings),
                ChatSandboxLease(
                    chat_session_id=old_id,
                    modal_sandbox_id="sb-old",
                    app_release_id=settings.release_id,
                    image_version=settings.chat_modal_image_version,
                    worker_contract_version=settings.chat_worker_contract_version,
                    worker_generation="generation-old",
                    state="idle",
                    last_activity_at=now - timedelta(minutes=1),
                    created_at=now - timedelta(minutes=2),
                    updated_at=now,
                ),
                ChatSandboxLease(
                    chat_session_id=resumed_id,
                    modal_sandbox_id=None,
                    app_release_id=settings.release_id,
                    image_version=settings.chat_modal_image_version,
                    worker_contract_version=settings.chat_worker_contract_version,
                    worker_generation="generation-terminated",
                    state="terminated",
                    last_activity_at=now - timedelta(seconds=30),
                    created_at=now - timedelta(minutes=1),
                    updated_at=now,
                ),
            ]
        )
    manager = _manager(factory, settings)
    manager._lock_start_claim = lambda *_args: None
    evicted: list[uuid.UUID] = []

    async def evict(session_id: uuid.UUID):
        evicted.append(session_id)
        with factory() as db, db.begin():
            lease = db.get(ChatSandboxLease, session_id)
            lease.modal_sandbox_id = None
            lease.state = "terminated"
        return True

    manager.snapshot_and_terminate = evict
    manager.enforce_warm_cap = lambda: asyncio.sleep(0, result=0)

    class Sandbox:
        object_id = "sb-resumed"
        terminate = SimpleNamespace(aio=lambda **_kwargs: asyncio.sleep(0))

    async def create(*_args, **_kwargs):
        return Sandbox()

    monkeypatch.setattr(chat_sandbox_service, "create_isolated_sandbox", create)

    result = asyncio.run(manager.ensure_ready(resumed_id, allow_pool=False))

    assert evicted == [old_id]
    assert result[0].object_id == "sb-resumed"
    assert result[3] == "created"
    with factory() as db:
        old_lease = db.get(ChatSandboxLease, old_id)
        resumed_lease = db.get(ChatSandboxLease, resumed_id)
        live_leases = (
            db.scalar(
                select(func.count())
                .select_from(ChatSandboxLease)
                .where(
                    ChatSandboxLease.state.in_(
                        ["starting", "ready", "busy", "idle", "terminating"]
                    )
                )
            )
            or 0
        )
        live_pool = (
            db.scalar(
                select(func.count())
                .select_from(ChatSandboxPool)
                .where(
                    ChatSandboxPool.state.in_(["starting", "blank_ready", "draining"])
                )
            )
            or 0
        )
    assert old_lease.state == "terminated"
    assert resumed_lease.state == "ready"
    assert resumed_lease.modal_sandbox_id == "sb-resumed"
    assert live_leases + live_pool == settings.chat_sandbox_total_live_cap


def test_terminated_session_resume_rejects_capacity_without_idle_worker():
    factory = _database()
    settings = _settings()
    busy_id, resumed_id = uuid.uuid4(), uuid.uuid4()
    now = datetime.now(UTC)
    with factory() as db, db.begin():
        db.add_all(
            [
                _session(busy_id),
                _session(resumed_id),
                _blank(settings),
                ChatSandboxLease(
                    chat_session_id=busy_id,
                    modal_sandbox_id="sb-busy",
                    app_release_id=settings.release_id,
                    image_version=settings.chat_modal_image_version,
                    worker_contract_version=settings.chat_worker_contract_version,
                    worker_generation="generation-busy",
                    state="busy",
                    last_activity_at=now,
                    created_at=now - timedelta(minutes=1),
                    updated_at=now,
                ),
                ChatSandboxLease(
                    chat_session_id=resumed_id,
                    modal_sandbox_id=None,
                    app_release_id=settings.release_id,
                    image_version=settings.chat_modal_image_version,
                    worker_contract_version=settings.chat_worker_contract_version,
                    worker_generation="generation-terminated",
                    state="terminated",
                    last_activity_at=now - timedelta(seconds=30),
                    created_at=now - timedelta(minutes=1),
                    updated_at=now,
                ),
            ]
        )
    manager = _manager(factory, settings)
    manager._lock_start_claim = lambda *_args: None

    with pytest.raises(SandboxError, match="capacity"):
        asyncio.run(manager.ensure_ready(resumed_id, allow_pool=False))

    with factory() as db:
        resumed_lease = db.get(ChatSandboxLease, resumed_id)
    assert resumed_lease.state == "terminated"
    assert resumed_lease.modal_sandbox_id is None


def test_postcommit_assignment_failure_destroys_blank_and_cold_starts():
    request_id = str(uuid.uuid4())
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    frames = b"".join(
        [
            encode_frame({"v": 1, "type": "workspace_ready", "request_id": request_id}),
            encode_frame({"v": 1, "type": "done", "request_id": request_id}),
            encode_frame(
                {
                    "v": 1,
                    "type": "worker_done",
                    "request_id": request_id,
                    "status": "complete",
                }
            ),
        ]
    )

    class Output:
        def __aiter__(self):
            async def chunks():
                yield frames

            return chunks()

    class Input:
        def write(self, _payload):
            return None

        drain = SimpleNamespace(aio=lambda: asyncio.sleep(0))

    class Process:
        stdin = Input()
        stdout = Output()
        stderr = Output()
        wait = SimpleNamespace(aio=lambda: asyncio.sleep(0))

    class Sandbox:
        def __init__(self, sandbox_id: str):
            self.object_id = sandbox_id

            async def execute(*_args, **_kwargs):
                return Process()

            self.exec = SimpleNamespace(aio=execute)

    manager = SandboxSessionManager.__new__(SandboxSessionManager)
    manager.settings = SimpleNamespace(
        chat_persistent_worker_enabled=False,
        chat_blank_pool_enabled=True,
        chat_agent_timeout_seconds=2,
        chat_gateway_url="https://gateway.example.test",
    )
    manager._processes = {}
    manager._controls = {}
    manager._background_tasks = set()
    acquisitions = [
        (Sandbox("sb-blank"), 5, False, "pool_hit", 2),
        (Sandbox("sb-cold"), 25, True, "pool_miss", None),
    ]

    async def ensure_ready(*_args, **_kwargs):
        return acquisitions.pop(0)

    manager.ensure_ready = ensure_ready
    claim_calls = 0

    def claim_worker(_session_id, sandbox_id):
        nonlocal claim_calls
        claim_calls += 1
        if claim_calls == 1:
            raise SandboxError("sandbox_lost", "simulated assignment loss")
        return WorkerClaim(sandbox_id=sandbox_id, token_hash="claim")

    manager._claim_worker = claim_worker
    terminations: list[tuple] = []

    async def terminate(*args, **kwargs):
        terminations.append((args, kwargs))

    manager.terminate = terminate
    manager._release_worker = lambda *_args: True
    manager.enforce_warm_cap = lambda: asyncio.sleep(0, result=0)

    async def run():
        return [
            event
            async for event in manager.run_turn(
                chat_session_id=session_id,
                turn_id=turn_id,
                request_id=request_id,
                prompt="prompt",
                model="model",
                resume=None,
                capability=SimpleNamespace(token="capability"),
            )
        ]

    events = asyncio.run(run())
    outcomes = [
        event["acquisition_outcome"]
        for event in events
        if event.get("phase") == "sandbox_acquisition_ms"
    ]
    assert outcomes == ["pool_hit", "pool_miss"]
    assert sum(event["type"] == "sandbox_start" for event in events) == 1
    assert sum(event["type"] == "workspace_ready" for event in events) == 1
    assert claim_calls == 2
    assert terminations[0][1]["failure_code"] == "pool_assignment_failed"


def test_reused_control_loss_before_sdk_dispatch_is_retryable():
    request_id = str(uuid.uuid4())
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()

    class Input:
        def __init__(self, control):
            self.control = control
            self.drain = SimpleNamespace(aio=self.flush)

        def write(self, _payload):
            return None

        async def flush(self):
            await self.control.queues[request_id].put(
                ConnectionError("persistent control closed")
            )

    sandbox = SimpleNamespace(object_id="sb-reused")
    control = SimpleNamespace(
        sandbox=sandbox,
        sandbox_id=sandbox.object_id,
        stderr_task=None,
        reader_task=None,
        queues={},
        resume_id="sdk-session",
    )
    control.process = SimpleNamespace(stdin=Input(control))
    manager = SandboxSessionManager.__new__(SandboxSessionManager)
    manager.settings = SimpleNamespace(
        chat_persistent_worker_enabled=True,
        chat_agent_timeout_seconds=2,
        chat_gateway_url="https://gateway.example.test",
    )
    manager._controls = {session_id: control}
    manager._processes = {}
    manager._background_tasks = set()
    manager._claim_worker = lambda *_args: WorkerClaim(
        sandbox_id=sandbox.object_id,
        token_hash="claim",
        assignment_token="assignment",
        worker_generation="generation",
    )
    terminations: list[str] = []

    async def terminate_worker(_session_id, _claim, *, failure_code):
        terminations.append(failure_code)
        manager._controls.pop(session_id, None)

    manager._terminate_worker = terminate_worker

    async def run():
        with pytest.raises(SandboxError) as raised:
            async for _event in manager._run_turn_once(
                chat_session_id=session_id,
                turn_id=turn_id,
                request_id=request_id,
                prompt="prompt",
                model="model",
                resume="sdk-session",
                capability=SimpleNamespace(token="capability"),
                allow_pool=False,
                forced_pool_miss=False,
            ):
                pass
        return raised.value

    error = asyncio.run(run())
    assert error.code == "pool_assignment_failed"
    assert terminations == ["sandbox_worker_failed"]
