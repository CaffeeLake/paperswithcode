from __future__ import annotations

import json
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import BinaryIO

from backend.chat_sandbox_worker.executor_daemon import (
    EXECUTOR_BOOTSTRAP_PREFIX,
    ExecutorServer,
)
from backend.chat_sandbox_worker.executor_protocol import (
    PROTOCOL,
    decode_response,
    encode_request,
)


def _read_frames(connection: socket.socket) -> list[dict[str, object]]:
    data = b""
    while True:
        chunk = connection.recv(64 * 1024)
        if not chunk:
            break
        data += chunk
    return [decode_response(line + b"\n") for line in data.splitlines()]


IDENTITY = {
    "workspace_id": "workspace-1",
    "workspace_generation": 1,
    "session_id": "session-1",
    "turn_id": "turn-1",
    "execution_id": "execution-1",
    "tool_call_id": "tool-1",
}


class _Broker:
    def __init__(self) -> None:
        self.active = False

    def __call__(self, payload: dict[str, object]) -> dict[str, object]:
        if payload["operation"] == "install":
            assert not self.active
            self.active = True
        elif payload["operation"] == "clear":
            assert self.active
            self.active = False
        return {"ok": True, "active": self.active}


def _operation(
    socket_path: Path,
    request: dict[str, object],
    *,
    capability: str = "synthetic-capability",
) -> list[dict[str, object]]:
    bootstrap = {
        "operation": "executor_connect",
        "capability": capability,
        "workspace_id": request["workspace_id"],
        "workspace_generation": request["workspace_generation"],
        "session_id": request["session_id"],
        "turn_id": request["turn_id"],
        "worker_generation": "worker-1",
    }
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.connect(str(socket_path))
        connection.sendall(
            EXECUTOR_BOOTSTRAP_PREFIX
            + json.dumps(bootstrap, separators=(",", ":")).encode()
            + b"\n"
            + encode_request(request)
        )
        connection.shutdown(socket.SHUT_WR)
        return _read_frames(connection)


def _open_operation(
    socket_path: Path, request: dict[str, object]
) -> tuple[socket.socket, BinaryIO]:
    bootstrap = {
        "operation": "executor_connect",
        "capability": "synthetic-capability",
        "workspace_id": request["workspace_id"],
        "workspace_generation": request["workspace_generation"],
        "session_id": request["session_id"],
        "turn_id": request["turn_id"],
        "worker_generation": "worker-1",
    }
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.connect(str(socket_path))
    connection.sendall(
        EXECUTOR_BOOTSTRAP_PREFIX
        + json.dumps(bootstrap, separators=(",", ":")).encode()
        + b"\n"
        + encode_request(request)
    )
    connection.shutdown(socket.SHUT_WR)
    reader = connection.makefile("rb")
    return connection, reader


def test_health_is_served_over_a_private_unix_socket(tmp_path: Path) -> None:
    socket_path = tmp_path / "private" / "executor.sock"
    state_path = tmp_path / "state"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    server = ExecutorServer(
        socket_path=socket_path,
        state_path=state_path,
        workspace_root=workspace,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.connect(str(socket_path))
        connection.sendall(
            encode_request(
                {
                    "protocol": PROTOCOL,
                    "type": "health",
                    "request_id": "request-health",
                    "execution_id": "execution-health",
                }
            )
        )
        connection.shutdown(socket.SHUT_WR)
        responses = _read_frames(connection)

    assert responses == [
        {
            "protocol": PROTOCOL,
            "type": "health_result",
            "request_id": "request-health",
            "execution_id": "execution-health",
            "status": "ok",
        }
    ]
    assert socket_path.stat().st_mode & 0o777 == 0o600
    assert socket_path.parent.stat().st_mode & 0o777 == 0o700
    assert state_path.stat().st_mode & 0o777 == 0o700
    server.shutdown()
    thread.join(timeout=2)


def test_duplicate_exec_reattaches_without_repeating_side_effect(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    broker = _Broker()
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=broker,
        command_preexec=None,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)
    request = {
        "protocol": PROTOCOL,
        "type": "exec",
        "request_id": "request-1",
        **IDENTITY,
        "command": "printf x >> side-effect; printf 'one\\ntwo\\n'",
        "timeout_ms": 2_000,
    }

    first = _operation(server.socket_path, request)
    duplicate = _operation(
        server.socket_path,
        {**request, "request_id": "request-2"},
    )

    assert (workspace / "side-effect").read_text() == "x"
    assert first[0]["type"] == "acknowledged"
    assert first[-1]["type"] == "terminal"
    assert (
        "".join(str(frame["data"]) for frame in first if frame["type"] == "output")
        == "one\ntwo\n"
    )
    assert first[-1]["status"] == "completed"
    assert duplicate[0]["request_id"] == "request-2"
    assert (
        "".join(str(frame["data"]) for frame in duplicate if frame["type"] == "output")
        == "one\ntwo\n"
    )
    assert duplicate[-1]["status"] == "completed"
    assert not broker.active
    server.shutdown()
    thread.join(timeout=2)


def test_read_is_bounded_and_descriptor_contained(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "note.txt").write_text("abcdef")
    (workspace / "outside-link").symlink_to(tmp_path / "outside.txt")
    (tmp_path / "outside.txt").write_text("secret")
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-1",
        command_preexec=None,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)
    base = {
        "protocol": PROTOCOL,
        "type": "read_file",
        "request_id": "request-read",
        **IDENTITY,
        "offset": 2,
        "max_bytes": 3,
    }

    valid = _operation(server.socket_path, {**base, "path": "note.txt"})
    traversal = _operation(server.socket_path, {**base, "path": "../outside.txt"})
    symlink = _operation(server.socket_path, {**base, "path": "outside-link"})

    assert valid[1]["type"] == "read_result"
    assert valid[1]["offset"] == 2
    assert valid[1]["data"] == "cde"
    assert valid[1]["eof"] is False
    assert traversal[-1]["error"] == "invalid_workspace_path"
    assert symlink[-1]["error"] == "invalid_workspace_path"
    server.shutdown()
    thread.join(timeout=2)


def test_cancel_terminates_the_process_group_before_side_effect(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    broker = _Broker()
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=broker,
        command_preexec=None,
        terminate_grace=0.05,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)
    request = {
        "protocol": PROTOCOL,
        "type": "exec",
        "request_id": "request-run",
        **IDENTITY,
        "command": "sleep 5; printf late > after-cancel",
        "timeout_ms": 10_000,
    }
    connection, reader = _open_operation(server.socket_path, request)
    acknowledged = decode_response(reader.readline())
    assert acknowledged["type"] == "acknowledged"

    cancelled = _operation(
        server.socket_path,
        {
            "protocol": PROTOCOL,
            "type": "cancel_execution",
            "request_id": "request-cancel",
            **IDENTITY,
        },
    )
    terminal = decode_response(reader.readline())
    reader.close()
    connection.close()

    assert cancelled[-1]["status"] == "cancelled"
    assert terminal["status"] == "cancelled"
    assert not (workspace / "after-cancel").exists()
    assert not broker.active
    server.shutdown()
    thread.join(timeout=2)


def test_timeout_is_terminal_and_does_not_run_later_side_effect(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    broker = _Broker()
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=broker,
        command_preexec=None,
        terminate_grace=0.05,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)

    responses = _operation(
        server.socket_path,
        {
            "protocol": PROTOCOL,
            "type": "exec",
            "request_id": "request-timeout",
            **IDENTITY,
            "command": "sleep 5; printf late > after-timeout",
            "timeout_ms": 50,
        },
    )

    assert responses[-1]["status"] == "failed"
    assert responses[-1]["error"] == "execution_timeout"
    assert not (workspace / "after-timeout").exists()
    assert not broker.active
    server.shutdown()
    thread.join(timeout=2)


def test_attach_cursor_and_mismatch_fencing(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=_Broker(),
        command_preexec=None,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)
    request = {
        "protocol": PROTOCOL,
        "type": "exec",
        "request_id": "request-run",
        **IDENTITY,
        "command": "printf first; sleep .05; printf second >&2",
        "timeout_ms": 2_000,
    }
    original = _operation(server.socket_path, request)
    outputs = [frame for frame in original if frame["type"] == "output"]
    assert len(outputs) == 2

    attached = _operation(
        server.socket_path,
        {
            "protocol": PROTOCOL,
            "type": "attach_execution",
            "request_id": "request-attach",
            **IDENTITY,
            "offset": outputs[0]["sequence"],
        },
    )
    mismatch = _operation(
        server.socket_path,
        {
            **request,
            "request_id": "request-mismatch",
            "execution_id": "execution-other",
            "command": "printf bad > mismatched-side-effect",
        },
    )

    assert [frame["data"] for frame in attached if frame["type"] == "output"] == [
        "second"
    ]
    assert attached[-1]["status"] == "completed"
    assert mismatch[-1]["error"] == "execution_identity_mismatch"
    assert not (workspace / "mismatched-side-effect").exists()
    server.shutdown()
    thread.join(timeout=2)


def test_output_is_sanitized_ordered_and_bounded(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=_Broker(),
        command_preexec=None,
        capture_limit=8,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)

    responses = _operation(
        server.socket_path,
        {
            "protocol": PROTOCOL,
            "type": "exec",
            "request_id": "request-output",
            **IDENTITY,
            "command": "printf '\\033[31mabcdefghijklmnop\\000'",
            "timeout_ms": 2_000,
        },
    )
    outputs = [frame for frame in responses if frame["type"] == "output"]

    assert [frame["sequence"] for frame in outputs] == list(range(1, len(outputs) + 1))
    assert sum(len(str(frame["data"]).encode()) for frame in outputs) <= 8
    assert all(
        "\x1b" not in str(frame["data"]) and "\x00" not in str(frame["data"])
        for frame in outputs
    )
    assert responses[-1]["type"] == "terminal"
    server.shutdown()
    thread.join(timeout=2)


def test_command_environment_strips_provider_credentials_and_uses_workspace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PWC_CHAT_OPENAI_API_KEY", "must-not-enter")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=_Broker(),
        command_preexec=None,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)

    responses = _operation(
        server.socket_path,
        {
            "protocol": PROTOCOL,
            "type": "exec",
            "request_id": "request-env",
            **IDENTITY,
            "command": 'printf \'%s|%s\' "$PWD" "${PWC_CHAT_OPENAI_API_KEY-unset}"',
            "timeout_ms": 2_000,
        },
    )

    output = "".join(
        str(frame["data"]) for frame in responses if frame["type"] == "output"
    )
    assert output == f"{workspace}|unset"
    server.shutdown()
    thread.join(timeout=2)


def test_restart_turns_durable_acceptance_into_execution_lost(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    broker_entered = threading.Event()
    never_release = threading.Event()

    def blocked_broker(payload: dict[str, object]) -> dict[str, object]:
        if payload["operation"] == "install":
            broker_entered.set()
            never_release.wait()
        return {"ok": True, "active": payload["operation"] == "install"}

    state_path = tmp_path / "state"
    first = ExecutorServer(
        socket_path=tmp_path / "first" / "executor.sock",
        state_path=state_path,
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=blocked_broker,
        command_preexec=None,
    )
    first_thread = threading.Thread(target=first.serve_forever, daemon=True)
    first_thread.start()
    assert first.wait_until_ready(2)
    request = {
        "protocol": PROTOCOL,
        "type": "exec",
        "request_id": "request-before-crash",
        **IDENTITY,
        "command": "printf x >> must-not-run",
        "timeout_ms": 2_000,
    }
    connection, reader = _open_operation(first.socket_path, request)
    assert decode_response(reader.readline())["type"] == "acknowledged"
    assert broker_entered.wait(2)
    reader.close()
    connection.close()

    recovered = ExecutorServer(
        socket_path=tmp_path / "recovered" / "executor.sock",
        state_path=state_path,
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=_Broker(),
        command_preexec=None,
    )
    recovered_thread = threading.Thread(target=recovered.serve_forever, daemon=True)
    recovered_thread.start()
    assert recovered.wait_until_ready(2)
    attached = _operation(
        recovered.socket_path,
        {
            "protocol": PROTOCOL,
            "type": "attach_execution",
            "request_id": "request-after-crash",
            **IDENTITY,
            "offset": 0,
        },
    )

    assert attached[-1]["status"] == "failed"
    assert attached[-1]["error"] == "execution_lost"
    assert not (workspace / "must-not-run").exists()
    recovered.shutdown()
    recovered_thread.join(timeout=2)
    first.shutdown()


def test_relay_copies_bytes_through_a_real_unix_socket(tmp_path: Path) -> None:
    socket_path = tmp_path / "relay.sock"
    ready = threading.Event()

    def echo_server() -> None:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            listener.bind(str(socket_path))
            listener.listen(1)
            ready.set()
            connection, _ = listener.accept()
            with connection:
                data = b""
                while chunk := connection.recv(1024):
                    data += chunk
                connection.sendall(b"echo:" + data)

    thread = threading.Thread(target=echo_server, daemon=True)
    thread.start()
    assert ready.wait(2)
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; from pathlib import Path; "
                "from backend.chat_sandbox_worker.executor_relay import relay; "
                "raise SystemExit(relay(Path(sys.argv[1])))"
            ),
            str(socket_path),
        ],
        input=b"request-bytes",
        capture_output=True,
        timeout=2,
        check=False,
    )

    assert completed.returncode == 0
    assert completed.stdout == b"echo:request-bytes"
    assert completed.stderr == b""


def test_workspace_generation_fences_execution(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=_Broker(),
        command_preexec=None,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)
    ensured = _operation(
        server.socket_path,
        {
            "protocol": PROTOCOL,
            "type": "ensure_workspace",
            "request_id": "request-ensure",
            **IDENTITY,
        },
    )
    stale_identity = {**IDENTITY, "workspace_generation": 2}

    stale = _operation(
        server.socket_path,
        {
            "protocol": PROTOCOL,
            "type": "exec",
            "request_id": "request-stale",
            **stale_identity,
            "command": "printf bad > stale-side-effect",
            "timeout_ms": 2_000,
        },
    )

    assert [frame["type"] for frame in ensured] == ["acknowledged"]
    assert stale[-1]["status"] == "failed"
    assert stale[-1]["error"] == "workspace_generation_mismatch"
    assert not (workspace / "stale-side-effect").exists()
    server.shutdown()
    thread.join(timeout=2)


def test_capability_cleanup_failure_is_a_terminal_containment_failure(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    def cleanup_fails(payload: dict[str, object]) -> dict[str, object]:
        return {
            "ok": payload["operation"] == "install",
            "active": True,
        }

    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=cleanup_fails,
        command_preexec=None,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)

    responses = _operation(
        server.socket_path,
        {
            "protocol": PROTOCOL,
            "type": "exec",
            "request_id": "request-cleanup",
            **IDENTITY,
            "command": "printf ran > command-ran",
            "timeout_ms": 2_000,
        },
    )

    assert (workspace / "command-ran").read_text() == "ran"
    assert responses[-1]["status"] == "failed"
    assert responses[-1]["error"] == "capability_cleanup_failed"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.connect(str(server.socket_path))
        connection.sendall(
            encode_request(
                {
                    "protocol": PROTOCOL,
                    "type": "health",
                    "request_id": "request-contained-health",
                    "execution_id": "execution-contained-health",
                }
            )
        )
        connection.shutdown(socket.SHUT_WR)
        health = _read_frames(connection)
    assert health[0]["status"] == "draining"
    server.shutdown()
    thread.join(timeout=2)


def test_malformed_or_uncorrelated_frames_execute_nothing(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=_Broker(),
        command_preexec=None,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.connect(str(server.socket_path))
        connection.sendall(b"not-json\n")
        connection.shutdown(socket.SHUT_WR)
        assert connection.recv(1) == b""
    stale = {
        "protocol": PROTOCOL,
        "type": "exec",
        "request_id": "request-stale-worker",
        **IDENTITY,
        "command": "printf bad > stale-worker-side-effect",
        "timeout_ms": 2_000,
    }
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.connect(str(server.socket_path))
        bootstrap = {
            "operation": "executor_connect",
            "capability": "synthetic-capability",
            "workspace_id": IDENTITY["workspace_id"],
            "workspace_generation": IDENTITY["workspace_generation"],
            "session_id": IDENTITY["session_id"],
            "turn_id": IDENTITY["turn_id"],
            "worker_generation": "worker-stale",
        }
        connection.sendall(
            EXECUTOR_BOOTSTRAP_PREFIX
            + json.dumps(bootstrap, separators=(",", ":")).encode()
            + b"\n"
            + encode_request(stale)
        )
        connection.shutdown(socket.SHUT_WR)
        assert connection.recv(1) == b""

    assert not (workspace / "stale-worker-side-effect").exists()
    server.shutdown()
    thread.join(timeout=2)


def test_only_one_command_runs_at_a_time_in_the_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=_Broker(),
        command_preexec=None,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)
    first_request = {
        "protocol": PROTOCOL,
        "type": "exec",
        "request_id": "request-first",
        **IDENTITY,
        "command": "sleep .1; printf ready > serialized-marker",
        "timeout_ms": 2_000,
    }
    second_identity = {
        **IDENTITY,
        "turn_id": "turn-2",
        "execution_id": "execution-2",
        "tool_call_id": "tool-2",
    }
    second_request = {
        "protocol": PROTOCOL,
        "type": "exec",
        "request_id": "request-second",
        **second_identity,
        "command": "test -f serialized-marker",
        "timeout_ms": 2_000,
    }
    results: dict[str, list[dict[str, object]]] = {}
    first_thread = threading.Thread(
        target=lambda: results.setdefault(
            "first", _operation(server.socket_path, first_request)
        )
    )
    second_thread = threading.Thread(
        target=lambda: results.setdefault(
            "second", _operation(server.socket_path, second_request)
        )
    )
    first_thread.start()
    time.sleep(0.02)
    second_thread.start()
    first_thread.join(timeout=2)
    second_thread.join(timeout=2)

    assert results["first"][-1]["exit_code"] == 0
    assert results["second"][-1]["exit_code"] == 0
    server.shutdown()
    thread.join(timeout=2)


def test_invalid_utf8_at_chunk_limit_still_reaches_terminal(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=_Broker(),
        command_preexec=None,
        capture_limit=64 * 1024,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)

    responses = _operation(
        server.socket_path,
        {
            "protocol": PROTOCOL,
            "type": "exec",
            "request_id": "request-invalid-utf8",
            **IDENTITY,
            "command": "python -c 'import os; os.write(1, b\"\\xff\" * 65536)'",
            "timeout_ms": 2_000,
        },
    )

    assert responses[-1]["type"] == "terminal"
    assert responses[-1]["status"] == "completed"
    assert all(
        len(str(frame["data"]).encode()) <= 64 * 1024
        for frame in responses
        if frame["type"] == "output"
    )
    server.shutdown()
    thread.join(timeout=2)
