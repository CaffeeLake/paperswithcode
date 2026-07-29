from __future__ import annotations

import asyncio
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from types import SimpleNamespace

from backend.services import chat_sandbox_service
from backend.services import chat_turn_runner
from backend.services.chat_sandbox_service import SandboxSessionManager, WorkerClaim
from backend.chat_sandbox_worker.protocol import encode_frame


class _Context:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _DB(_Context):
    def __init__(self, rows=None):
        self.rows = rows or []

    def begin(self):
        return _Context()

    def add(self, _value):
        return None

    def execute(self, _query):
        return _Result(list(self.rows))


class _LeaseStore:
    def __init__(self):
        self.lease = None
        self.add_calls = 0
        self.advisory_lock = threading.Lock()
        self.first_missing_read = threading.Event()


class _Transaction(_Context):
    def __init__(self, db):
        self.db = db

    def __exit__(self, error_type, *_args):
        if error_type is None and self.db.pending is not None:
            self.db.store.lease = self.db.pending
        if self.db.holds_advisory_lock:
            self.db.store.advisory_lock.release()
        return False


class _TransactionalDB(_Context):
    def __init__(self, store):
        self.store = store
        self.pending = None
        self.holds_advisory_lock = False

    def begin(self):
        return _Transaction(self)

    def add(self, value):
        self.store.add_calls += 1
        self.pending = value

    def execute(self, _query):
        self.store.advisory_lock.acquire()
        self.holds_advisory_lock = True
        return _Result([])


class _AsyncCall:
    def __init__(self, function):
        self.aio = function


class _Probe:
    returncode = 0

    def __init__(self):
        self.wait = _AsyncCall(self._wait)

    async def _wait(self):
        return None


class _Sandbox:
    def __init__(self, object_id: str):
        self.object_id = object_id
        self.poll = _AsyncCall(self._poll)
        self.exec = _AsyncCall(self._exec)
        self.terminate = _AsyncCall(self._terminate)

    async def _poll(self):
        return None

    async def _exec(self, *_args, **_kwargs):
        return _Probe()

    async def _terminate(self, *, wait):
        assert wait is False


def _lease(*, state: str, sandbox_id: str | None):
    return SimpleNamespace(
        modal_sandbox_id=sandbox_id,
        app_release_id="old-release",
        image_version="im-current",
        worker_contract_version="worker-v1",
        worker_generation="generation-a",
        state=state,
        lease_token_hash=None,
        lease_expires_at=None,
        last_activity_at=datetime.now(UTC),
        workspace_snapshot_id=None,
        snapshot_image_version=None,
        snapshot_updated_at=None,
        workspace_dirty=False,
        failure_code=None,
        updated_at=datetime.now(UTC),
    )


def _manager(lease, *, rows=None):
    manager = SandboxSessionManager.__new__(SandboxSessionManager)
    manager.settings = SimpleNamespace(
        release_id="current-release",
        chat_modal_image_version="im-current",
        chat_worker_contract_version="worker-v1",
        chat_workspace_snapshots_enabled=False,
        chat_sandbox_ready_timeout_seconds=2,
    )
    manager.session_factory = lambda: _DB(rows)
    manager.snapshots = SimpleNamespace()
    manager._lease = lambda _db, _session_id, *, lock: lease

    async def enforce_warm_cap():
        return 0

    manager.enforce_warm_cap = enforce_warm_cap
    return manager


def test_concurrent_startup_waits_for_the_existing_owner(monkeypatch):
    async def run():
        lease = _lease(state="terminated", sandbox_id=None)
        manager = _manager(lease)
        created = _Sandbox("sb-created")
        creation_started = asyncio.Event()
        allow_creation = asyncio.Event()
        create_calls = 0

        async def create(*_args, **_kwargs):
            nonlocal create_calls
            create_calls += 1
            creation_started.set()
            await allow_creation.wait()
            return created

        async def from_id(sandbox_id):
            assert sandbox_id == "sb-created"
            return created

        monkeypatch.setattr(chat_sandbox_service, "create_isolated_sandbox", create)
        monkeypatch.setattr(
            chat_sandbox_service.modal.Sandbox,
            "from_id",
            _AsyncCall(from_id),
        )

        session_id = uuid.uuid4()
        owner = asyncio.create_task(manager.ensure_ready(session_id))
        await creation_started.wait()
        waiter = asyncio.create_task(manager.ensure_ready(session_id))
        await asyncio.sleep(0.1)

        assert create_calls == 1
        assert lease.state == "starting"

        allow_creation.set()
        owner_result, waiter_result = await asyncio.gather(owner, waiter)
        assert owner_result[2] is True
        assert waiter_result[2] is False
        assert lease.state == "ready"
        assert lease.modal_sandbox_id == "sb-created"
        assert create_calls == 1

    asyncio.run(run())


def test_concurrent_startup_single_flights_initial_lease_insert(monkeypatch):
    store = _LeaseStore()
    manager = _manager(None)
    manager.session_factory = lambda: _TransactionalDB(store)

    def read_lease(_db, _session_id, *, lock):
        assert lock is True
        lease = store.lease
        if lease is None and not store.first_missing_read.is_set():
            store.first_missing_read.set()
            time.sleep(0.1)
        return lease

    manager._lease = read_lease
    created = _Sandbox("sb-created")
    create_calls = 0
    create_lock = threading.Lock()

    async def create(*_args, **_kwargs):
        nonlocal create_calls
        with create_lock:
            create_calls += 1
        return created

    async def from_id(sandbox_id):
        assert sandbox_id == "sb-created"
        return created

    monkeypatch.setattr(chat_sandbox_service, "create_isolated_sandbox", create)
    monkeypatch.setattr(
        chat_sandbox_service.modal.Sandbox,
        "from_id",
        _AsyncCall(from_id),
    )

    session_id = uuid.uuid4()
    with ThreadPoolExecutor(max_workers=2) as pool:
        owner = pool.submit(asyncio.run, manager.ensure_ready(session_id))
        assert store.first_missing_read.wait(timeout=1)
        waiter = pool.submit(asyncio.run, manager.ensure_ready(session_id))
        owner_result = owner.result(timeout=3)
        waiter_result = waiter.result(timeout=3)

    assert store.add_calls == 1
    assert create_calls == 1
    assert {owner_result[2], waiter_result[2]} == {True, False}
    assert store.lease.state == "ready"
    assert store.lease.modal_sandbox_id == "sb-created"


def test_stale_termination_cannot_clear_a_successor_lease(monkeypatch):
    async def run():
        lease = _lease(state="ready", sandbox_id="sb-old")
        manager = _manager(lease)
        termination_started = asyncio.Event()
        allow_termination = asyncio.Event()

        class BlockingSandbox(_Sandbox):
            async def _terminate(self, *, wait):
                assert wait is False
                termination_started.set()
                await allow_termination.wait()

        async def from_id(sandbox_id):
            assert sandbox_id == "sb-old"
            return BlockingSandbox(sandbox_id)

        monkeypatch.setattr(
            chat_sandbox_service.modal.Sandbox,
            "from_id",
            _AsyncCall(from_id),
        )

        stale_operation = asyncio.create_task(manager.terminate(uuid.uuid4()))
        await termination_started.wait()
        lease.state = "ready"
        lease.modal_sandbox_id = "sb-new"
        lease.lease_token_hash = None
        lease.lease_expires_at = None
        allow_termination.set()
        await stale_operation

        assert lease.state == "ready"
        assert lease.modal_sandbox_id == "sb-new"

    asyncio.run(run())


def test_persistent_turns_reuse_one_control_attachment():
    class Output:
        def __init__(self):
            self.chunks: asyncio.Queue[bytes] = asyncio.Queue()

        def __aiter__(self):
            return self

        async def __anext__(self):
            return await self.chunks.get()

    class Input:
        def __init__(self, output):
            self.output = output
            self.writes = 0
            self.drain = _AsyncCall(self._drain)

        def write(self, _payload):
            self.writes += 1

        async def _drain(self):
            request_id = f"request-{self.writes}"
            await self.output.chunks.put(
                b"".join(
                    [
                        encode_frame(
                            {
                                "v": 1,
                                "type": "workspace_ready",
                                "request_id": request_id,
                            }
                        ),
                        encode_frame(
                            {
                                "v": 1,
                                "type": "done",
                                "request_id": request_id,
                            }
                        ),
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
            )

    class Stderr:
        def __aiter__(self):
            return self

        async def __anext__(self):
            await asyncio.Future()

    class Process:
        def __init__(self):
            self.stdout = Output()
            self.stderr = Stderr()
            self.stdin = Input(self.stdout)

    async def run():
        process = Process()
        exec_calls = 0

        async def execute(*_args, **_kwargs):
            nonlocal exec_calls
            exec_calls += 1
            return process

        sandbox = SimpleNamespace(
            object_id="sb-persistent",
            exec=_AsyncCall(execute),
        )
        manager = SandboxSessionManager.__new__(SandboxSessionManager)
        manager.settings = SimpleNamespace(
            chat_persistent_worker_enabled=True,
            chat_persistent_sandbox_lifetime_seconds=86400,
            chat_agent_timeout_seconds=2,
            chat_gateway_url="https://gateway.example.test",
        )
        manager._processes = {}
        manager._controls = {}
        manager.ensure_ready = lambda _session_id, **_kwargs: asyncio.sleep(
            0, result=(sandbox, 1, False, "reused_session", None)
        )
        manager._claim_worker = lambda *_args: WorkerClaim(
            sandbox_id="sb-persistent", token_hash="claim"
        )
        released = 0

        def release_worker(*_args):
            nonlocal released
            released += 1
            return True

        manager._release_worker = release_worker
        manager.enforce_warm_cap = lambda: asyncio.sleep(0, result=0)

        session_id = uuid.uuid4()
        for index in (1, 2):
            events = []
            turn_id = uuid.uuid4()
            stream = manager.run_turn(
                chat_session_id=session_id,
                turn_id=turn_id,
                request_id=f"request-{index}",
                prompt="prompt",
                model="model",
                resume="resume",
                capability=SimpleNamespace(token="capability"),
            )
            async for event in stream:
                events.append(event)
                if event["type"] == "done":
                    assert manager._processes[turn_id].done.is_set()
            assert any(event["type"] == "workspace_ready" for event in events)
            assert released == index
        manager._drop_control(session_id)
        assert exec_calls == 1

    asyncio.run(run())


def test_turn_runners_share_session_manager_for_one_settings_instance(monkeypatch):
    created: list[object] = []

    class Manager:
        def __init__(self, settings):
            self.settings = settings
            created.append(settings)

    monkeypatch.setattr(chat_turn_runner, "SandboxSessionManager", Manager)
    monkeypatch.setattr(chat_turn_runner, "_manager", None)
    monkeypatch.setattr(chat_turn_runner, "_manager_settings", None)
    first_settings = object()
    second_settings = object()

    first = chat_turn_runner.shared_sandbox_manager(first_settings)
    assert chat_turn_runner.shared_sandbox_manager(first_settings) is first
    second = chat_turn_runner.shared_sandbox_manager(second_settings)

    assert second is not first
    assert created == [first_settings, second_settings]


def test_cancel_control_write_failure_terminates_worker():
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    claim = WorkerClaim(sandbox_id="sb-cancel", token_hash="claim")
    terminated: list[str] = []

    class Input:
        def __init__(self):
            self.drain = _AsyncCall(self._drain)

        def write(self, _payload):
            pass

        async def _drain(self):
            raise RuntimeError("control closed")

    manager = SandboxSessionManager.__new__(SandboxSessionManager)
    manager._processes = {
        turn_id: chat_sandbox_service.RunningWorker(
            process=SimpleNamespace(stdin=Input()),
            request_id="request",
            claim=claim,
            done=asyncio.Event(),
        )
    }

    async def terminate(_session_id, _claim, *, failure_code):
        terminated.append(failure_code)
        return True

    manager._terminate_worker = terminate

    assert asyncio.run(manager.cancel(session_id, turn_id)) is True
    assert terminated == ["cancel_control_lost"]


def test_reconcile_does_not_mark_a_replaced_sandbox_lost(monkeypatch):
    async def run():
        session_id = uuid.uuid4()
        lease = _lease(state="ready", sandbox_id="sb-old")
        rows = [(session_id, "sb-old", "ready", None)]
        manager = _manager(lease, rows=rows)
        poll_started = asyncio.Event()
        allow_poll = asyncio.Event()

        class LostSandbox(_Sandbox):
            async def _poll(self):
                poll_started.set()
                await allow_poll.wait()
                return 1

        async def from_id(sandbox_id):
            assert sandbox_id == "sb-old"
            return LostSandbox(sandbox_id)

        monkeypatch.setattr(
            chat_sandbox_service.modal.Sandbox,
            "from_id",
            _AsyncCall(from_id),
        )

        stale_reconcile = asyncio.create_task(manager.reconcile())
        await poll_started.wait()
        lease.state = "ready"
        lease.modal_sandbox_id = "sb-new"
        allow_poll.set()

        assert await stale_reconcile == 0
        assert lease.state == "ready"
        assert lease.modal_sandbox_id == "sb-new"

    asyncio.run(run())


def test_stale_failed_worker_cannot_terminate_a_successor(monkeypatch):
    async def run():
        lease = _lease(state="busy", sandbox_id="sb-old")
        lease.lease_token_hash = "worker-old"
        manager = _manager(lease)
        stale_claim = WorkerClaim("sb-old", "worker-old")
        provider_calls = 0

        async def from_id(_sandbox_id):
            nonlocal provider_calls
            provider_calls += 1
            return _Sandbox("sb-old")

        monkeypatch.setattr(
            chat_sandbox_service.modal.Sandbox,
            "from_id",
            _AsyncCall(from_id),
        )

        lease.state = "busy"
        lease.modal_sandbox_id = "sb-new"
        lease.lease_token_hash = "worker-new"

        assert not await manager._terminate_worker(
            uuid.uuid4(),
            stale_claim,
            failure_code="sandbox_worker_failed",
        )
        assert lease.state == "busy"
        assert lease.modal_sandbox_id == "sb-new"
        assert lease.lease_token_hash == "worker-new"
        assert provider_calls == 0

    asyncio.run(run())


def test_stale_successful_worker_cannot_release_a_successor_or_termination():
    lease = _lease(state="busy", sandbox_id="sb-old")
    lease.lease_token_hash = "worker-old"
    manager = _manager(lease)
    stale_claim = WorkerClaim("sb-old", "worker-old")
    session_id = uuid.uuid4()

    lease.modal_sandbox_id = "sb-new"
    lease.lease_token_hash = "worker-new"
    assert not manager._release_worker(session_id, stale_claim)
    assert lease.state == "busy"
    assert lease.modal_sandbox_id == "sb-new"
    assert lease.lease_token_hash == "worker-new"
    assert not lease.workspace_dirty

    lease.state = "terminating"
    lease.modal_sandbox_id = "sb-old"
    lease.lease_token_hash = "termination-new"
    assert not manager._release_worker(session_id, stale_claim)
    assert lease.state == "terminating"
    assert lease.modal_sandbox_id == "sb-old"
    assert lease.lease_token_hash == "termination-new"
    assert not lease.workspace_dirty
