from __future__ import annotations

import asyncio
import json
import socket
import threading
from dataclasses import replace
from pathlib import Path

import pytest

from backend.chat_sandbox_worker.executor_daemon import (
    EXECUTOR_BOOTSTRAP_PREFIX,
    ExecutorServer,
)
from backend.chat_sandbox_worker.executor_protocol import (
    MAX_EXECUTION_OUTPUT_FRAMES,
    MAX_EXECUTION_RESPONSE_FRAMES,
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


class _SocketProcess:
    def __init__(self, connection: socket.socket):
        self.connection = connection
        self.stdin = _SocketInput(connection)
        self.stdout = _SocketOutput(connection)
        self.wait = _AsyncCall(self._wait)

    async def _wait(self) -> None:
        self.connection.close()


class _SocketInput:
    def __init__(self, connection: socket.socket):
        self.connection = connection
        self.drain = _AsyncCall(self._drain)

    def write(self, value: bytes) -> None:
        self.connection.sendall(value)
        self.connection.shutdown(socket.SHUT_WR)

    async def _drain(self) -> None:
        return None


class _SocketOutput:
    def __init__(self, connection: socket.socket):
        self.connection = connection

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        while data := await asyncio.to_thread(self.connection.recv, 64 * 1024):
            yield data


class _SocketProvider:
    def __init__(self, socket_path: Path):
        self.socket_path = socket_path
        self.calls = 0

    async def open_executor_relay(self, _sandbox, *, timeout_seconds):
        assert timeout_seconds in {7, 10}
        self.calls += 1
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.connect(str(self.socket_path))
        return _SocketProcess(connection)


class _Broker:
    def __init__(self):
        self.active = False

    def __call__(self, request):
        if request["operation"] == "install":
            self.active = True
        elif request["operation"] == "clear":
            self.active = False
        return {"ok": True, "active": self.active}


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
                data_base64="c2FmZSB0ZXh0",
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
    assert read.data == b"safe text"
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


def test_daemon_tiny_chunks_fit_shared_client_frame_budget_end_to_end(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-a",
        broker_control=_Broker(),
        command_preexec=None,
        read_chunk_size=1,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)
    provider = _SocketProvider(server.socket_path)
    client = SandboxExecutorClient(provider, request_id_factory=lambda: "request-a")

    result = asyncio.run(
        client.exec(
            _context(),
            command="for ((i=0; i<1023; i++)); do printf x; done",
            timeout_ms=2000,
        )
    )

    assert MAX_EXECUTION_OUTPUT_FRAMES == MAX_EXECUTION_RESPONSE_FRAMES - 2
    assert len(result.outputs) == MAX_EXECUTION_OUTPUT_FRAMES
    assert "".join(str(output["data"]) for output in result.outputs) == (
        "x" * MAX_EXECUTION_OUTPUT_FRAMES
    )
    assert result.terminal == {"status": "completed", "exit_code": 0, "error": None}
    assert provider.calls == 1
    server.shutdown()
    thread.join(timeout=2)


def test_binary_read_round_trips_through_daemon_socket_and_client(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "bytes.bin").write_bytes(b"\xff\xc3\xa9\x00Z")
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-a",
        broker_control=_Broker(),
        command_preexec=None,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)
    provider = _SocketProvider(server.socket_path)
    client = SandboxExecutorClient(provider, request_id_factory=lambda: "request-a")

    result = asyncio.run(
        client.read_file(_context(), path="bytes.bin", offset=0, max_bytes=4)
    )

    assert result.data == b"\xff\xc3\xa9\x00"
    assert result.offset == 0
    assert result.eof is False
    assert provider.calls == 1
    server.shutdown()
    thread.join(timeout=2)


def test_read_rejects_decoded_data_larger_than_the_requested_byte_limit():
    provider = _Provider(
        [
            _Process(
                [
                    _response("acknowledged", operation="read_file"),
                    _response(
                        "read_result",
                        path="notes.txt",
                        offset=0,
                        data_base64="YWJjZA==",
                        eof=False,
                    ),
                ]
            )
        ]
    )
    client = SandboxExecutorClient(provider, request_id_factory=lambda: "request-a")

    with pytest.raises(ProtocolError, match="requested byte limit"):
        asyncio.run(
            client.read_file(_context(), path="notes.txt", offset=0, max_bytes=3)
        )


@pytest.mark.parametrize(
    ("data_base64", "expected", "max_bytes"),
    [("YWJj", b"abc", 3), ("/8OpAA==", b"\xff\xc3\xa9\x00", 4)],
)
def test_read_accepts_exact_binary_data_at_the_requested_byte_limit(
    data_base64, expected, max_bytes
):
    provider = _Provider(
        [
            _Process(
                [
                    _response("acknowledged", operation="read_file"),
                    _response(
                        "read_result",
                        path="notes.txt",
                        offset=0,
                        data_base64=data_base64,
                        eof=True,
                    ),
                ]
            )
        ]
    )
    client = SandboxExecutorClient(provider, request_id_factory=lambda: "request-a")

    result = asyncio.run(
        client.read_file(_context(), path="notes.txt", offset=0, max_bytes=max_bytes)
    )

    assert result.data == expected


@pytest.mark.parametrize("capability", ["", "x" * (64 * 1024)])
def test_invalid_bootstrap_is_rejected_before_opening_provider_relay(capability):
    provider = _Provider([])
    client = SandboxExecutorClient(provider, request_id_factory=lambda: "request-a")
    context = replace(_context(), capability=capability)

    with pytest.raises(ProtocolError, match="Invalid executor bootstrap"):
        asyncio.run(client.exec(context, command="true", timeout_ms=1000))

    assert provider.calls == []
