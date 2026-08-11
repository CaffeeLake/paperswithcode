from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from backend.chat_sandbox_worker.protocol import encode_frame
from backend.config import Settings
from backend.services import chat_sandbox_service, chat_turn_runner
from backend.services.chat_sandbox_service import (
    SandboxSessionManager,
    WorkerClaim,
)
from backend.services.chat_sandbox_state_repository import ChatSandboxStateRepository


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


def test_persistent_turns_reuse_one_control_attachment():
    class Connection:
        def __init__(self):
            self.chunks: asyncio.Queue[bytes] = asyncio.Queue()
            self.sent: list[bytes] = []
            self.closed = False

        def __aiter__(self):
            return self

        async def __anext__(self):
            return await self.chunks.get()

        async def send(self, payload):
            self.sent.append(payload)
            request_id = f"request-{len(self.sent)}"
            await self.chunks.put(
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

        async def close(self):
            self.closed = True

    async def run():
        connection = Connection()
        sandbox = SimpleNamespace(object_id="sb-persistent")
        start_calls = 0

        class Provider:
            async def open_persistent_connection(self, candidate, worker_generation):
                nonlocal start_calls
                start_calls += 1
                assert candidate is sandbox
                assert worker_generation == "generation-a"
                return connection

        settings = Settings(
            _env_file=None,
            chat_workspace_snapshots_enabled=False,
            chat_persistent_worker_enabled=True,
            chat_persistent_sandbox_lifetime_seconds=86400,
            chat_agent_timeout_seconds=2,
            chat_gateway_url="https://gateway.example.test",
        )
        manager = SandboxSessionManager(settings, sandbox_provider=Provider())
        ensure_calls = 0

        async def ensure_ready(_session_id, **kwargs):
            nonlocal ensure_calls
            assert kwargs["budget_prechecked"] is True
            ensure_calls += 1
            return sandbox, 1, False, "reused_session", None

        manager.ensure_ready = ensure_ready
        manager._claim_worker = lambda *_args: WorkerClaim(
            sandbox_id="sb-persistent",
            token_hash="claim",
            worker_generation="generation-a",
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
            if index == 2:
                manager._controls[session_id].resume_id = "failed-branch"
            events = []
            turn_id = uuid.uuid4()
            stream = manager.run_turn(
                chat_session_id=session_id,
                turn_id=turn_id,
                request_id=f"request-{index}",
                prompt="prompt",
                model="model",
                resume="durable-branch",
                capability=SimpleNamespace(token="capability"),
            )
            async for event in stream:
                events.append(event)
                if event["type"] == "done":
                    assert manager._processes[turn_id].done.is_set()
            assert [(event["type"], event.get("phase")) for event in events] == [
                ("sandbox_start", None),
                ("_latency", "sandbox_acquisition_ms"),
                ("sandbox_ready", None),
                ("_latency", "capability_install_ms"),
                ("_latency", "worker_ready_ms"),
                ("_latency", "sdk_dispatch_ms"),
                ("workspace_ready", None),
                ("done", None),
            ]
            assert released == index
        manager._drop_control(session_id)
        transport = manager._worker_transport()
        if transport.close_tasks:
            await asyncio.gather(*transport.close_tasks, return_exceptions=True)
        assert start_calls == 1
        assert ensure_calls == 1
        assert len(connection.sent) == 2
        assert connection.closed is True

    asyncio.run(run())


def test_turn_runners_share_session_manager_for_one_settings_instance(monkeypatch):
    created: list[object] = []

    class Manager:
        def __init__(self, settings, **_kwargs):
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

    manager = SandboxSessionManager(
        Settings(_env_file=None, chat_workspace_snapshots_enabled=False)
    )
    manager._worker_transport_state.register_running_worker(
        turn_id,
        chat_sandbox_service.RunningWorker(
            process=SimpleNamespace(stdin=Input()),
            request_id="request",
            claim=claim,
            done=asyncio.Event(),
        ),
    )

    async def terminate(_session_id, _claim, *, failure_code):
        terminated.append(failure_code)
        return True

    manager._terminate_worker = terminate

    assert asyncio.run(manager.cancel(session_id, turn_id)) is True
    assert terminated == ["cancel_control_lost"]


def test_stale_successful_worker_cannot_release_a_successor_or_termination():
    lease = _lease(state="busy", sandbox_id="sb-old")
    lease.lease_token_hash = "worker-old"
    repository = ChatSandboxStateRepository(
        Settings(_env_file=None, chat_workspace_snapshots_enabled=False)
    )
    stale_claim = WorkerClaim("sb-old", "worker-old")

    lease.modal_sandbox_id = "sb-new"
    lease.lease_token_hash = "worker-new"
    assert not repository.release_worker(
        lease,
        claim=stale_claim,
        now=datetime.now(UTC),
    )
    assert lease.state == "busy"
    assert lease.modal_sandbox_id == "sb-new"
    assert lease.lease_token_hash == "worker-new"
    assert not lease.workspace_dirty

    lease.state = "terminating"
    lease.modal_sandbox_id = "sb-old"
    lease.lease_token_hash = "termination-new"
    assert not repository.release_worker(
        lease,
        claim=stale_claim,
        now=datetime.now(UTC),
    )
    assert lease.state == "terminating"
    assert lease.modal_sandbox_id == "sb-old"
    assert lease.lease_token_hash == "termination-new"
    assert not lease.workspace_dirty
