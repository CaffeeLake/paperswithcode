from __future__ import annotations

import asyncio
import json
import uuid
from types import SimpleNamespace

import pytest

from backend.chat_sandbox_worker.protocol import ProtocolError, encode_frame
from backend.chat_sandbox_worker.supervisor import SUPERVISOR_PREFIX
from backend.config import Settings
from backend.services.chat_sandbox_provider import SandboxError
from backend.services.chat_sandbox_service import SandboxSessionManager
from backend.services.chat_sandbox_state_repository import WorkerClaim
from backend.services.chat_sandbox_worker_transport import (
    ChatSandboxWorkerTransport,
    RunningWorker,
    SessionControl,
)


class _AsyncConnection:
    def __init__(self):
        self.incoming: asyncio.Queue[bytes | None] = asyncio.Queue()
        self.sent: list[bytes] = []
        self.close_calls = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        item = await self.incoming.get()
        if item is None:
            raise StopAsyncIteration
        return item

    async def send(self, payload: bytes) -> None:
        self.sent.append(payload)

    async def close(self) -> None:
        self.close_calls += 1
        await self.incoming.put(None)


class _CloseProcess:
    def __init__(self, *, wait_to_close: bool = False):
        self.close_calls = 0
        self.close_started = asyncio.Event()
        self.allow_close = asyncio.Event()
        if not wait_to_close:
            self.allow_close.set()

    async def aclose(self) -> None:
        self.close_calls += 1
        self.close_started.set()
        await self.allow_close.wait()


def _transport(*, clock=None):
    async def unexpected_open(_sandbox, _worker_generation):
        raise AssertionError("this test must not open a provider connection")

    provider = SimpleNamespace(
        open_persistent_connection=unexpected_open,
        open_turn_process=None,
    )
    options = {}
    if clock is not None:
        options["clock"] = clock
    return ChatSandboxWorkerTransport(provider, **options)


def _control(sandbox_id: str, process=None) -> SessionControl:
    return SessionControl(
        process=process or _CloseProcess(),
        sandbox=SimpleNamespace(object_id=sandbox_id),
        sandbox_id=sandbox_id,
        stderr_task=None,
        reader_task=None,
        queues={},
        resume_id=None,
    )


def _running(request_id: str) -> RunningWorker:
    return RunningWorker(
        process=object(),
        request_id=request_id,
        claim=WorkerClaim("sb-worker", "claim-token"),
        done=asyncio.Event(),
    )


async def _wait_until(predicate) -> None:
    for _ in range(20):
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("condition was not reached")


def test_session_control_cleanup_is_identity_safe_and_session_scoped():
    async def exercise():
        transport = _transport()
        first_session = uuid.uuid4()
        second_session = uuid.uuid4()
        stale = _control("sb-first")
        replacement = _control("sb-first")
        other = _control("sb-other")

        transport.register_session_control(first_session, stale)
        transport.register_session_control(first_session, replacement)
        transport.register_session_control(second_session, other)

        transport.drop_session_control(first_session, expected=stale)
        await asyncio.sleep(0)
        assert transport.session_control(first_session) is replacement
        assert transport.session_control(second_session) is other
        assert stale.process.close_calls == 0
        assert replacement.process.close_calls == 0

        transport.drop_session_control(first_session, expected=replacement)
        await replacement.process.close_started.wait()
        assert transport.session_control(first_session) is None
        assert transport.session_control(second_session) is other
        assert replacement.process.close_calls == 1

        transport.drop_session_control(second_session, expected=other)
        await other.process.close_started.wait()

    asyncio.run(exercise())


def test_drop_by_sandbox_never_closes_an_unrelated_session_control():
    async def exercise():
        transport = _transport()
        matching_session = uuid.uuid4()
        unrelated_session = uuid.uuid4()
        matching = _control("sb-target")
        unrelated = _control("sb-other")
        transport.register_session_control(matching_session, matching)
        transport.register_session_control(unrelated_session, unrelated)

        transport.drop_session_controls_by_sandbox("sb-target")
        await matching.process.close_started.wait()

        assert transport.session_control(matching_session) is None
        assert transport.session_control(unrelated_session) is unrelated
        assert matching.process.close_calls == 1
        assert unrelated.process.close_calls == 0

        transport.drop_session_control(unrelated_session, expected=unrelated)
        await unrelated.process.close_started.wait()

    asyncio.run(exercise())


def test_blank_control_health_and_promotion_have_one_owner():
    clock_values = iter([10.0, 30.0])

    async def exercise():
        transport = _transport(clock=lambda: next(clock_values))
        session_id = uuid.uuid4()
        control = _control("sb-blank")
        other = _control("sb-other")

        transport.register_blank_control("sb-blank", control)
        transport.register_blank_control("sb-other", other, checked_at=20.0)
        assert transport.blank_health_checked_at("sb-blank") == 10.0
        assert transport.blank_health_checked_at("sb-other") == 20.0

        assert transport.mark_blank_healthy("sb-blank", expected=control)
        assert transport.blank_health_checked_at("sb-blank") == 30.0

        assert (
            transport.promote_blank_control("sb-blank", session_id, expected=control)
            is control
        )
        assert transport.blank_control("sb-blank") is None
        assert transport.blank_health_checked_at("sb-blank") is None
        assert transport.session_control(session_id) is control
        assert transport.blank_control("sb-other") is other
        assert control.process.close_calls == 0

        transport.drop_session_control(session_id, expected=control)
        transport.drop_blank_control("sb-other", expected=other)
        await asyncio.gather(
            control.process.close_started.wait(),
            other.process.close_started.wait(),
        )

    asyncio.run(exercise())


def test_missing_blank_control_cannot_be_promoted_into_a_session():
    transport = _transport()
    session_id = uuid.uuid4()
    expected = _control("sb-missing")

    assert (
        transport.promote_blank_control("sb-missing", session_id, expected=expected)
        is None
    )
    assert transport.blank_control("sb-missing") is None
    assert transport.blank_health_checked_at("sb-missing") is None
    assert transport.session_control(session_id) is None
    assert expected.process.close_calls == 0


def test_stale_blank_cleanup_preserves_replacement_and_health_timestamp():
    async def exercise():
        transport = _transport()
        stale = _control("sb-blank")
        replacement = _control("sb-blank")
        transport.register_blank_control("sb-blank", stale, checked_at=10.0)
        transport.register_blank_control("sb-blank", replacement, checked_at=20.0)

        assert not transport.mark_blank_healthy(
            "sb-blank", expected=stale, checked_at=30.0
        )
        assert (
            transport.promote_blank_control("sb-blank", uuid.uuid4(), expected=stale)
            is None
        )
        transport.drop_blank_control("sb-blank", expected=stale)
        await asyncio.sleep(0)

        assert transport.blank_control("sb-blank") is replacement
        assert transport.blank_health_checked_at("sb-blank") == 20.0
        assert stale.process.close_calls == 0
        assert replacement.process.close_calls == 0

        transport.drop_blank_control("sb-blank", expected=replacement)
        await replacement.process.close_started.wait()

    asyncio.run(exercise())


def test_running_worker_cleanup_is_identity_safe_and_turn_scoped():
    transport = _transport()
    first_turn = uuid.uuid4()
    second_turn = uuid.uuid4()
    stale = _running("stale-request")
    replacement = _running("replacement-request")
    other = _running("other-request")

    transport.register_running_worker(first_turn, stale)
    transport.register_running_worker(first_turn, replacement)
    transport.register_running_worker(second_turn, other)

    transport.remove_running_worker(first_turn, expected=stale)
    assert transport.running_worker(first_turn) is replacement
    assert transport.running_worker(second_turn) is other

    transport.remove_running_worker(first_turn, expected=replacement)
    assert transport.running_worker(first_turn) is None
    assert transport.running_worker(second_turn) is other


def test_control_close_is_deduplicated_while_background_close_is_running():
    async def exercise():
        transport = _transport()
        session_id = uuid.uuid4()
        process = _CloseProcess(wait_to_close=True)
        control = _control("sb-shared", process)
        transport.register_session_control(session_id, control)
        transport.register_blank_control("sb-shared", control, checked_at=10.0)

        transport.drop_session_control(session_id, expected=control)
        transport.drop_blank_control("sb-shared", expected=control)
        await process.close_started.wait()
        assert process.close_calls == 1

        process.allow_close.set()
        await _wait_until(lambda: not transport.close_tasks)
        assert process.close_calls == 1

    asyncio.run(exercise())


def test_one_shot_process_open_forwards_exact_timeout_and_provider_result():
    async def exercise():
        sandbox = object()
        process = object()
        calls: list[tuple[object, int]] = []

        async def open_process(candidate, *, timeout_seconds):
            calls.append((candidate, timeout_seconds))
            return process

        provider = SimpleNamespace(
            open_persistent_connection=None,
            open_turn_process=open_process,
        )
        transport = ChatSandboxWorkerTransport(provider)

        assert await transport.open_turn_process(sandbox, timeout_seconds=47) is process
        assert calls == [(sandbox, 47)]

    asyncio.run(exercise())


def test_one_shot_process_open_preserves_provider_failure():
    async def exercise():
        failure = RuntimeError("provider process unavailable")

        async def open_process(_sandbox, *, timeout_seconds):
            assert timeout_seconds == 47
            raise failure

        provider = SimpleNamespace(
            open_persistent_connection=None,
            open_turn_process=open_process,
        )
        transport = ChatSandboxWorkerTransport(provider)

        with pytest.raises(RuntimeError) as raised:
            await transport.open_turn_process(object(), timeout_seconds=47)
        assert raised.value is failure

    asyncio.run(exercise())


def test_persistent_control_ping_preserves_framing_and_correlation():
    async def exercise():
        connection = _AsyncConnection()
        calls: list[tuple[object, str]] = []

        async def open_connection(sandbox, worker_generation):
            calls.append((sandbox, worker_generation))
            return connection

        transport = ChatSandboxWorkerTransport(
            SimpleNamespace(
                open_persistent_connection=open_connection,
                open_turn_process=None,
            )
        )
        sandbox = SimpleNamespace(object_id="sb-open")
        control = await transport.open_persistent_control(sandbox, "generation-a")

        ping = asyncio.create_task(transport.ping(control, "generation-a"))
        await _wait_until(lambda: bool(connection.sent))
        wire = connection.sent[0]
        assert wire.startswith(SUPERVISOR_PREFIX)
        request = json.loads(wire[len(SUPERVISOR_PREFIX) :].rstrip(b"\n"))
        await connection.incoming.put(
            encode_frame(
                {
                    "v": 1,
                    "type": "worker_health",
                    "request_id": request["request_id"],
                    "assigned": False,
                }
            )
        )

        assert await ping is True
        assert calls == [(sandbox, "generation-a")]
        assert request == {
            "operation": "ping",
            "worker_generation": "generation-a",
            "request_id": request["request_id"],
        }
        assert control.queues == {}

        transport.schedule_close(control)
        await _wait_until(lambda: connection.close_calls == 1)

    asyncio.run(exercise())


def test_cancelled_ping_removes_its_request_queue():
    async def exercise():
        connection = _AsyncConnection()

        async def open_connection(_sandbox, _worker_generation):
            return connection

        transport = ChatSandboxWorkerTransport(
            SimpleNamespace(
                open_persistent_connection=open_connection,
                open_turn_process=None,
            )
        )
        control = await transport.open_persistent_control(
            SimpleNamespace(object_id="sb-open"), "generation-a"
        )
        ping = asyncio.create_task(transport.ping(control, "generation-a"))
        await _wait_until(lambda: bool(control.queues))

        ping.cancel()
        with pytest.raises(asyncio.CancelledError):
            await ping
        assert control.queues == {}

        transport.schedule_close(control)
        await _wait_until(lambda: connection.close_calls == 1)

    asyncio.run(exercise())


def test_reader_cancellation_wakes_all_correlated_requests_and_propagates():
    async def exercise():
        connection = _AsyncConnection()

        async def open_connection(_sandbox, _worker_generation):
            return connection

        transport = ChatSandboxWorkerTransport(
            SimpleNamespace(
                open_persistent_connection=open_connection,
                open_turn_process=None,
            )
        )
        control = await transport.open_persistent_control(
            SimpleNamespace(object_id="sb-open"), "generation-a"
        )
        first: asyncio.Queue = asyncio.Queue()
        second: asyncio.Queue = asyncio.Queue()
        control.queues.update({"request-a": first, "request-b": second})

        assert control.reader_task is not None
        await asyncio.sleep(0)
        control.reader_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await control.reader_task

        failures = [await first.get(), await second.get()]
        assert all(isinstance(error, SandboxError) for error in failures)
        assert all(error.code == "sandbox_worker_failed" for error in failures)
        assert all(error.uncertain for error in failures)

        transport.schedule_close(control)
        await _wait_until(lambda: connection.close_calls == 1)

    asyncio.run(exercise())


def test_uncorrelated_frame_fails_every_live_request_without_cross_routing():
    async def exercise():
        connection = _AsyncConnection()

        async def open_connection(_sandbox, _worker_generation):
            return connection

        transport = ChatSandboxWorkerTransport(
            SimpleNamespace(
                open_persistent_connection=open_connection,
                open_turn_process=None,
            )
        )
        control = await transport.open_persistent_control(
            SimpleNamespace(object_id="sb-open"), "generation-a"
        )
        first: asyncio.Queue = asyncio.Queue()
        second: asyncio.Queue = asyncio.Queue()
        control.queues.update({"request-a": first, "request-b": second})

        await connection.incoming.put(
            encode_frame(
                {
                    "v": 1,
                    "type": "worker_ready",
                    "request_id": "unknown-request",
                }
            )
        )
        assert control.reader_task is not None
        await control.reader_task

        failures = [await first.get(), await second.get()]
        assert all(isinstance(error, ProtocolError) for error in failures)
        assert all("Uncorrelated" in str(error) for error in failures)
        assert first.empty()
        assert second.empty()

        transport.schedule_close(control)
        await _wait_until(lambda: connection.close_calls == 1)

    asyncio.run(exercise())


def test_manager_control_facade_keeps_existing_lifecycle_contract():
    async def exercise():
        manager = SandboxSessionManager(
            Settings(_env_file=None, chat_workspace_snapshots_enabled=False)
        )
        session_id = uuid.uuid4()
        control = _control("sb-manager")
        manager._controls[session_id] = control

        manager._drop_control(session_id)
        await control.process.close_started.wait()

        assert session_id not in manager._controls
        assert control.process.close_calls == 1

    asyncio.run(exercise())
