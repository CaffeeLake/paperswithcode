from __future__ import annotations

import asyncio
from types import SimpleNamespace
import uuid

from backend.services.chat_external_executor_workspace import (
    ChatExternalExecutorWorkspaceManager,
)
from backend.services.chat_sandbox_provider import SandboxLaunchMode
from backend.services.chat_turn_job_repository import StaleTurnClaim, TurnLeaseClaim
from backend.tests.test_chat_sandbox_acquisition_coordinator import _coordinator
from backend.tests.test_chat_sandbox_capacity_acquisition import (
    _Provider,
    _database,
    _session,
    _settings,
)


class RecordingProvider(_Provider):
    def __init__(self, *, transactions):
        super().__init__(transactions=transactions)
        self.create_options = []

    async def create(self, **options):
        self.create_options.append(options)
        return await super().create(**options)


class ExecutorHealth:
    def __init__(self, *statuses: str):
        self.statuses = list(statuses or ("ok",))
        self.sandboxes = []

    async def health(self, sandbox):
        self.sandboxes.append(sandbox)
        return self.statuses.pop(0) if self.statuses else "ok"


class LiveTurns:
    def __init__(self):
        self.claims = []

    def require_live_claim(self, _db, *, claim, now):
        self.claims.append((claim, now))


class ExpiringTurn(LiveTurns):
    def require_live_claim(self, _db, *, claim, now):
        super().require_live_claim(_db, claim=claim, now=now)
        if len(self.claims) == 2:
            raise StaleTurnClaim("expired")


TURN_CLAIM = TurnLeaseClaim(uuid.uuid4(), "worker", 3, 7)


def setup_manager(*, health: ExecutorHealth | None = None):
    settings = _settings(chat_workspace_snapshots_enabled=False)
    sessions = _database()
    session_id = uuid.uuid4()
    with sessions() as db, db.begin():
        db.add(_session(session_id))
    provider = RecordingProvider(transactions=[])
    acquisition = _coordinator(settings, sessions, provider)
    manager = ChatExternalExecutorWorkspaceManager(
        settings=settings,
        session_factory=acquisition.session_factory,
        state_repository=acquisition.state_repository,
        acquisition=acquisition,
        lifecycle=acquisition.lease_maintenance.lifecycle,
        maintenance=acquisition.lease_maintenance,
        executor=health or ExecutorHealth(),
        turn_repository=LiveTurns(),
    )
    return manager, sessions, session_id, provider


def test_first_bash_creates_executor_and_later_turn_reuses_exact_workspace():
    manager, sessions, session_id, provider = setup_manager()

    async def exercise():
        first = await manager.acquire(session_id=session_id, turn_claim=TURN_CLAIM)
        assert await manager.release(first)
        second = await manager.acquire(session_id=session_id, turn_claim=TURN_CLAIM)
        assert await manager.release(second)
        return first, second

    first, second = asyncio.run(exercise())

    assert first.sandbox_id == second.sandbox_id
    assert first.workspace_generation == second.workspace_generation
    assert first.worker_generation == second.worker_generation
    assert len(provider.create_options) == 1
    assert provider.create_options[0]["launch_mode"] is SandboxLaunchMode.EXECUTOR
    with sessions() as db:
        lease = manager.state_repository.load_lease(db, session_id, lock=False)
        assert lease is not None
        assert lease.state == "idle"
        assert lease.modal_sandbox_id == first.sandbox_id
        assert lease.workspace_snapshot_id is None


def test_concurrent_acquisition_waits_for_existing_busy_workspace():
    manager, _sessions, session_id, provider = setup_manager()

    async def exercise():
        first = await manager.acquire(session_id=session_id, turn_claim=TURN_CLAIM)
        waiting = asyncio.create_task(
            manager.acquire(session_id=session_id, turn_claim=TURN_CLAIM)
        )
        await asyncio.sleep(0.01)
        assert not waiting.done()
        assert await manager.release(first)
        second = await waiting
        assert await manager.release(second)
        return first, second

    first, second = asyncio.run(exercise())

    assert second.sandbox_id == first.sandbox_id
    assert len(provider.create_options) == 1


def test_failed_executor_health_uses_fenced_termination_before_one_replacement():
    health = ExecutorHealth("draining", "ok")
    manager, _sessions, session_id, provider = setup_manager(health=health)
    provider.created = SimpleNamespace(object_id="sb-created")

    async def exercise():
        handle = await manager.acquire(session_id=session_id, turn_claim=TURN_CLAIM)
        assert await manager.release(handle)

    asyncio.run(exercise())

    assert len(provider.create_options) == 2
    assert [call[0] for call in provider.calls].count("terminate") == 1
    terminate_index = next(
        index for index, call in enumerate(provider.calls) if call[0] == "terminate"
    )
    create_indices = [
        index for index, call in enumerate(provider.calls) if call[0] == "create"
    ]
    assert create_indices[0] < terminate_index < create_indices[1]


def test_identity_failure_invalidates_only_the_exact_busy_claim():
    manager, sessions, session_id, provider = setup_manager()

    async def exercise():
        handle = await manager.acquire(session_id=session_id, turn_claim=TURN_CLAIM)
        await manager.invalidate(handle)

    asyncio.run(exercise())

    assert [call[0] for call in provider.calls].count("terminate") == 1
    with sessions() as db:
        lease = manager.state_repository.load_lease(db, session_id, lock=False)
        assert lease is not None
        assert lease.state == "failed"
        assert lease.modal_sandbox_id is None


def test_turn_fence_expiring_during_acquisition_releases_workspace_to_idle():
    manager, sessions, session_id, provider = setup_manager()
    manager.turn_repository = ExpiringTurn()

    async def exercise():
        await manager.acquire(session_id=session_id, turn_claim=TURN_CLAIM)

    try:
        asyncio.run(exercise())
    except StaleTurnClaim:
        pass
    else:  # pragma: no cover - the fake always expires on the second fence
        raise AssertionError("turn claim should expire")

    assert [call[0] for call in provider.calls].count("terminate") == 0
    with sessions() as db:
        lease = manager.state_repository.load_lease(db, session_id, lock=False)
        assert lease is not None
        assert lease.state == "idle"


def test_idle_executor_workspace_is_reclaimed_by_existing_eviction_lifecycle():
    manager, sessions, session_id, provider = setup_manager()

    async def exercise():
        handle = await manager.acquire(session_id=session_id, turn_claim=TURN_CLAIM)
        assert await manager.release(handle)
        return await manager.lifecycle.idle_eviction.evict_idle(session_id)

    outcome = asyncio.run(exercise())

    assert outcome.acquired is True
    assert [call[0] for call in provider.calls].count("terminate") == 1
    with sessions() as db:
        lease = manager.state_repository.load_lease(db, session_id, lock=False)
        assert lease is not None
        assert lease.state == "terminated"
        assert lease.modal_sandbox_id is None
