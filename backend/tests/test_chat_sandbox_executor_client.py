from __future__ import annotations

import asyncio
import json

import pytest

from backend.chat_sandbox_worker.executor_daemon import EXECUTOR_BOOTSTRAP_PREFIX
from backend.chat_sandbox_worker.executor_protocol import (
    PROTOCOL,
    ProtocolError,
    decode_request,
    encode_response,
)
from backend.services.chat_sandbox_executor import (
    MAX_EXECUTOR_RESPONSE_FRAMES,
    ExecutorContext,
    ExecutorExecutionLost,
    SandboxExecutorClient,
)


IDENTITY = {
    "workspace_id": "workspace-a",
    "workspace_generation": 7,
    "session_id": "session-a",
    "turn_id": "turn-a",
    "execution_id": "execution-a",
    "tool_call_id": "tool-a",
}


class _AsyncCall:
    def __init__(self, function):
        self.aio = function


class _Input:
    def __init__(self):
        self.writes: list[bytes] = []
        self.drain = _AsyncCall(self._drain)

    def write(self, value: bytes) -> None:
        self.writes.append(value)

    async def _drain(self) -> None:
        return None


class _Output:
    def __init__(self, chunks: list[bytes], error: Exception | None = None):
        self.chunks = chunks
        self.error = error

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for chunk in self.chunks:
            yield chunk
        if self.error is not None:
            raise self.error


class _Process:
    def __init__(
        self,
        frames: list[dict],
        *,
        error: Exception | None = None,
        trailing: bytes = b"",
    ):
        self.stdin = _Input()
        self.stdout = _Output(
            [encode_response(frame) for frame in frames] + [trailing], error
        )
        self.returncode = 0
        self.wait = _AsyncCall(self._wait)

    async def _wait(self) -> None:
        return None


class _Provider:
    def __init__(self, processes: list[_Process]):
        self.processes = processes
        self.calls: list[tuple[object, int]] = []

    async def open_executor_relay(self, sandbox, *, timeout_seconds):
        self.calls.append((sandbox, timeout_seconds))
        return self.processes.pop(0)


def _context() -> ExecutorContext:
    return ExecutorContext(
        sandbox=object(),
        worker_generation="worker-a",
        capability="synthetic-capability",
        **IDENTITY,
    )


def _response(kind: str, **fields) -> dict:
    return {
        "protocol": PROTOCOL,
        "type": kind,
        "request_id": "request-a",
        **IDENTITY,
        **fields,
    }


def test_exec_sends_fenced_bootstrap_and_returns_validated_output():
    process = _Process(
        [
            _response("acknowledged", operation="exec"),
            _response("output", sequence=1, stream="stdout", data="synthetic\n"),
            _response("terminal", status="completed", exit_code=0, error=None),
        ]
    )
    provider = _Provider([process])
    client = SandboxExecutorClient(provider, request_id_factory=lambda: "request-a")
    context = _context()

    result = asyncio.run(
        client.exec(context, command="pwc paper list", timeout_ms=9000)
    )

    assert result.outputs == (
        {"sequence": 1, "stream": "stdout", "data": "synthetic\n"},
    )
    assert result.terminal == {
        "status": "completed",
        "exit_code": 0,
        "error": None,
    }
    bootstrap_line, request_line = process.stdin.writes[0].splitlines(keepends=True)
    assert bootstrap_line.startswith(EXECUTOR_BOOTSTRAP_PREFIX)
    assert json.loads(bootstrap_line[len(EXECUTOR_BOOTSTRAP_PREFIX) :]) == {
        "operation": "executor_connect",
        "capability": "synthetic-capability",
        "workspace_id": "workspace-a",
        "workspace_generation": 7,
        "session_id": "session-a",
        "turn_id": "turn-a",
        "worker_generation": "worker-a",
    }
    assert decode_request(request_line) == {
        "protocol": PROTOCOL,
        "type": "exec",
        "request_id": "request-a",
        **IDENTITY,
        "command": "pwc paper list",
        "timeout_ms": 9000,
    }
    assert provider.calls == [(context.sandbox, 14)]


def test_exec_disconnect_after_ack_is_typed_lost_and_is_not_retried():
    process = _Process(
        [_response("acknowledged", operation="exec")],
        error=ConnectionResetError("synthetic disconnect"),
    )
    provider = _Provider([process])
    client = SandboxExecutorClient(provider, request_id_factory=lambda: "request-a")

    with pytest.raises(ExecutorExecutionLost) as exc_info:
        asyncio.run(client.exec(_context(), command="pwc task list", timeout_ms=1000))

    assert exc_info.value.code == "execution_lost"
    assert len(provider.calls) == 1
    assert len(process.stdin.writes) == 1


def test_exec_truncated_frame_after_ack_is_typed_lost():
    provider = _Provider(
        [
            _Process(
                [_response("acknowledged", operation="exec")],
                trailing=b'{"protocol":"sandbox-executor-v1"',
            )
        ]
    )
    client = SandboxExecutorClient(provider, request_id_factory=lambda: "request-a")

    with pytest.raises(ExecutorExecutionLost):
        asyncio.run(client.exec(_context(), command="pwc task list", timeout_ms=1000))

    assert len(provider.calls) == 1


def test_exec_rejects_uncorrelated_response():
    response = _response("acknowledged", operation="exec")
    response["workspace_generation"] = 8
    provider = _Provider([_Process([response])])
    client = SandboxExecutorClient(provider, request_id_factory=lambda: "request-a")

    with pytest.raises(ProtocolError, match="Uncorrelated"):
        asyncio.run(client.exec(_context(), command="pwc task list", timeout_ms=1000))


def test_exec_rejects_uncorrelated_output_instead_of_classifying_it_lost():
    output = _response("output", sequence=1, stream="stdout", data="synthetic")
    output["workspace_generation"] = 8
    provider = _Provider(
        [
            _Process(
                [
                    _response("acknowledged", operation="exec"),
                    output,
                ]
            )
        ]
    )
    client = SandboxExecutorClient(provider, request_id_factory=lambda: "request-a")

    with pytest.raises(ProtocolError, match="Uncorrelated"):
        asyncio.run(client.exec(_context(), command="pwc task list", timeout_ms=1000))


def test_executor_client_exposes_health_ensure_attach_cancel_and_read():
    operation_frames = [
        [
            {
                "protocol": PROTOCOL,
                "type": "health_result",
                "request_id": "request-a",
                "execution_id": "request-a",
                "status": "ok",
            }
        ],
        [_response("acknowledged", operation="ensure_workspace")],
        [
            _response("acknowledged", operation="attach_execution"),
            _response("terminal", status="completed", exit_code=0, error=None),
        ],
        [
            _response("acknowledged", operation="cancel_execution"),
            _response("terminal", status="cancelled", exit_code=None, error=None),
        ],
        [
            _response("acknowledged", operation="read_file"),
            _response(
                "read_result",
                path="notes.txt",
                offset=3,
                data="safe text",
                eof=True,
            ),
        ],
    ]
    processes = [_Process(frames) for frames in operation_frames]
    provider = _Provider(processes.copy())
    client = SandboxExecutorClient(provider, request_id_factory=lambda: "request-a")
    context = _context()

    assert asyncio.run(client.health(context.sandbox)) == "ok"
    asyncio.run(client.ensure_workspace(context))
    attached = asyncio.run(client.attach_execution(context, offset=4))
    cancelled = asyncio.run(client.cancel_execution(context))
    read = asyncio.run(
        client.read_file(context, path="notes.txt", offset=3, max_bytes=20)
    )

    assert attached.terminal["status"] == "completed"
    assert cancelled.terminal["status"] == "cancelled"

    assert read.path == "notes.txt"
    assert read.offset == 3
    assert read.data == "safe text"
    assert read.eof is True
    request_types = []
    for index, process in enumerate(processes):
        wire = process.stdin.writes[0]
        if index == 0:
            request_types.append(decode_request(wire)["type"])
        else:
            request_types.append(
                decode_request(wire.splitlines(keepends=True)[1])["type"]
            )
    assert request_types == [
        "health",
        "ensure_workspace",
        "attach_execution",
        "cancel_execution",
        "read_file",
    ]


def test_attach_rejects_output_that_does_not_advance_requested_cursor():
    provider = _Provider(
        [
            _Process(
                [
                    _response("acknowledged", operation="attach_execution"),
                    _response("output", sequence=4, stream="stdout", data="synthetic"),
                    _response("terminal", status="completed", exit_code=0, error=None),
                ]
            )
        ]
    )
    client = SandboxExecutorClient(provider, request_id_factory=lambda: "request-a")

    with pytest.raises(ProtocolError, match="advance its cursor"):
        asyncio.run(client.attach_execution(_context(), offset=4))


def test_executor_client_bounds_the_complete_response_stream():
    frame = {
        "protocol": PROTOCOL,
        "type": "health_result",
        "request_id": "request-a",
        "execution_id": "request-a",
        "status": "ok",
    }
    provider = _Provider([_Process([frame] * (MAX_EXECUTOR_RESPONSE_FRAMES + 1))])
    client = SandboxExecutorClient(provider, request_id_factory=lambda: "request-a")

    with pytest.raises(ProtocolError, match="too many frames"):
        asyncio.run(client.health(object()))
