from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.config import Settings
from backend.models.database import (
    ChatSandboxLease,
    ChatSandboxPool,
    ChatSession,
)
from backend.chat_sandbox_worker.protocol import encode_frame
from backend.services.chat_sandbox_service import (
    SandboxError,
    SandboxSessionManager,
    WorkerClaim,
)
from backend.services import chat_sandbox_service


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
        selected_model="deepseek-ai/DeepSeek-V4-Flash",
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
    manager._lock_pool_maintenance = lambda _db: True
    manager._spawn_pool_replenishment = lambda: None

    async def healthy(sandbox_id: str, _worker_generation: str):
        return SimpleNamespace(object_id=sandbox_id)

    manager._pool_sandbox_health = healthy
    return manager


def test_concurrent_claims_bind_one_blank_to_exactly_one_session():
    factory = _database()
    settings = _settings()
    first_id, second_id = uuid.uuid4(), uuid.uuid4()
    with factory() as db, db.begin():
        db.add_all([_session(first_id), _session(second_id), _blank(settings)])
    manager = _manager(factory, settings)

    async def run():
        return await asyncio.gather(
            manager.claim_blank(first_id),
            manager.claim_blank(second_id),
        )

    claims = asyncio.run(run())
    assert sum(claim is not None for claim in claims) == 1
    with factory() as db:
        row = db.execute(select(ChatSandboxPool)).scalar_one()
        leases = list(db.execute(select(ChatSandboxLease)).scalars())
    assert row.state == "claimed"
    assert row.claim_generation == 1
    assert row.claim_token_hash
    assert len(leases) == 1
    assert leases[0].modal_sandbox_id == "sb-blank"


def test_failed_precommit_claim_leaves_worker_blank():
    factory = _database()
    settings = _settings()
    session_id = uuid.uuid4()
    blank = _blank(settings)
    with factory() as db, db.begin():
        db.add_all([_session(session_id), blank])
    manager = _manager(factory, settings)
    original_lease = manager._lease

    def fail_during_claim(db, candidate_session_id, *, lock):
        if lock:
            raise RuntimeError("simulated transaction failure")
        return original_lease(db, candidate_session_id, lock=lock)

    manager._lease = fail_during_claim
    with pytest.raises(RuntimeError, match="simulated transaction failure"):
        asyncio.run(manager.claim_blank(session_id))

    with factory() as db:
        row = db.get(ChatSandboxPool, blank.id)
        lease_count = db.scalar(select(func.count()).select_from(ChatSandboxLease))
    assert row.state == "blank_ready"
    assert row.claimed_at is None
    assert lease_count == 0


def test_incompatible_release_cannot_be_claimed():
    factory = _database()
    settings = _settings()
    session_id = uuid.uuid4()
    with factory() as db, db.begin():
        db.add_all(
            [
                _session(session_id),
                _blank(settings, release_id="previous-release"),
            ]
        )
    manager = _manager(factory, settings)

    assert asyncio.run(manager.claim_blank(session_id)) is None
    with factory() as db:
        row = db.execute(select(ChatSandboxPool)).scalar_one()
    assert row.state == "blank_ready"


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


def test_claim_transfers_preopened_blank_control():
    factory = _database()
    settings = _settings()
    session_id = uuid.uuid4()
    with factory() as db, db.begin():
        db.add_all([_session(session_id), _blank(settings)])
    manager = _manager(factory, settings)
    control = SimpleNamespace(sandbox_id="sb-blank")
    manager._blank_controls["sb-blank"] = control

    assert asyncio.run(manager.claim_blank(session_id)) is not None
    assert "sb-blank" not in manager._blank_controls
    assert manager._controls[session_id] is control


def test_preopened_control_health_does_not_repeat_provider_poll():
    factory = _database()
    settings = _settings()
    manager = SandboxSessionManager(settings, session_factory=factory)
    sandbox = SimpleNamespace(object_id="sb-blank")
    control = SimpleNamespace(sandbox_id="sb-blank", sandbox=sandbox)
    manager._blank_controls["sb-blank"] = control
    manager._blank_health_at["sb-blank"] = chat_sandbox_service.time.monotonic()

    async def healthy(candidate, worker_generation):
        raise AssertionError("fresh local health must not be repeated")

    manager._ping_control = healthy

    assert (
        asyncio.run(manager._pool_sandbox_health("sb-blank", "generation-a")) is sandbox
    )


def test_unhealthy_blank_is_destroyed_instead_of_claimed(monkeypatch):
    factory = _database()
    settings = _settings()
    session_id = uuid.uuid4()
    blank = _blank(settings)
    with factory() as db, db.begin():
        db.add_all([_session(session_id), blank])
    manager = _manager(factory, settings)

    async def unhealthy(_sandbox_id: str, _worker_generation: str):
        return None

    manager._pool_sandbox_health = unhealthy

    class ProviderSandbox:
        terminate = SimpleNamespace(aio=lambda **_kwargs: asyncio.sleep(0))

    async def from_id(_sandbox_id: str):
        return ProviderSandbox()

    monkeypatch.setattr(
        chat_sandbox_service.modal.Sandbox,
        "from_id",
        SimpleNamespace(aio=from_id),
    )

    assert asyncio.run(manager.claim_blank(session_id)) is None
    with factory() as db:
        row = db.get(ChatSandboxPool, blank.id)
        lease_count = db.scalar(select(func.count()).select_from(ChatSandboxLease))
    assert row.state == "failed"
    assert row.failure_code == "sandbox_lost"
    assert lease_count == 0


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

    async def create(_settings, *, name, tags, worker_generation):
        calls.append((name, tags))
        assert len(worker_generation) == 32
        creation_started.set()
        await allow_creation.wait()
        return SimpleNamespace(object_id="sb-new")

    monkeypatch.setattr(chat_sandbox_service, "create_isolated_sandbox", create)
    control = SimpleNamespace(sandbox_id="sb-new")

    async def start_control(_sandbox):
        return control

    async def ping_control(candidate, _worker_generation):
        return candidate is control

    manager._start_persistent_control = start_control
    manager._ping_control = ping_control

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


def test_disabled_pool_drains_only_unassigned_workers(monkeypatch):
    factory = _database()
    settings = _settings(chat_blank_pool_enabled=False)
    blank = _blank(settings)
    assigned_session_id = uuid.uuid4()
    with factory() as db, db.begin():
        db.add_all(
            [
                blank,
                _session(assigned_session_id),
                ChatSandboxLease(
                    chat_session_id=assigned_session_id,
                    modal_sandbox_id="sb-assigned",
                    app_release_id=settings.release_id,
                    image_version=settings.chat_modal_image_version,
                    worker_contract_version=settings.chat_worker_contract_version,
                    state="idle",
                ),
            ]
        )
    manager = _manager(factory, settings)
    manager.reconcile_pool_orphans = lambda: asyncio.sleep(0, result=0)
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

    result = asyncio.run(manager.maintain_pool())

    assert result["drained"] == 1
    assert terminated == ["sb-blank"]
    with factory() as db:
        row = db.get(ChatSandboxPool, blank.id)
        assigned = db.get(ChatSandboxLease, assigned_session_id)
    assert row.state == "terminated"
    assert assigned.state == "idle"
    assert assigned.modal_sandbox_id == "sb-assigned"


def test_provider_orphan_is_terminated_after_start_window():
    factory = _database()
    manager = _manager(factory, _settings())
    terminated: list[bool] = []

    async def terminate(*, wait):
        terminated.append(wait)

    orphan = SimpleNamespace(
        object_id="sb-orphan",
        terminate=SimpleNamespace(aio=terminate),
    )

    async def listed():
        yield orphan

    manager._listed_pool_sandboxes = listed

    assert asyncio.run(manager.reconcile_pool_orphans()) == 1
    assert terminated == [False]


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
