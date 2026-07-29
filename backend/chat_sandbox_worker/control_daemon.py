"""Root-only persistent sandbox control daemon."""

from __future__ import annotations

import json
import hmac
import os
import select
import secrets
import socket
import subprocess
import sys
from pathlib import Path

from backend.chat_sandbox_worker.protocol import decode_frame, encode_frame
from backend.chat_sandbox_worker.supervisor import (
    SUPERVISOR_PREFIX,
    _agent_environment,
    _demote,
    _harden_proc,
    _not_dumpable,
    _safe_environment,
    _wait_for_broker,
)

CONTROL_SOCKET = Path("/run/pwc-chat/control.sock")
BROKER_CONTROL_SOCKET = Path("/var/empty/pwc-broker/control.sock")
MAX_PRIVATE_FRAME_BYTES = 64 * 1024
BROKER_CONTROL_TIMEOUT_SECONDS = 25


def _readline(connection: socket.socket, maximum: int) -> bytes:
    value = bytearray()
    while len(value) < maximum:
        chunk = connection.recv(1)
        if not chunk:
            break
        value.extend(chunk)
        if chunk == b"\n":
            return bytes(value)
    if len(value) >= maximum:
        raise RuntimeError("Persistent control frame is too large")
    return bytes(value)


def _broker_control(payload: dict) -> dict:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(BROKER_CONTROL_TIMEOUT_SECONDS)
        connection.connect(str(BROKER_CONTROL_SOCKET))
        connection.sendall(json.dumps(payload, separators=(",", ":")).encode() + b"\n")
        response = json.loads(_readline(connection, 16 * 1024))
    if response.get("ok") is not True:
        raise RuntimeError("Broker control operation failed")
    return response


def _start_children() -> tuple[subprocess.Popen, subprocess.Popen]:
    proxy_token = secrets.token_urlsafe(32)
    read_fd, write_fd = os.pipe()
    broker_environment = _safe_environment("/var/empty/pwc-broker")
    broker_environment["PWC_BROKER_CONFIG_FD"] = str(read_fd)
    broker = subprocess.Popen(
        [sys.executable, "-m", "backend.chat_sandbox_worker.broker"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=sys.stderr,
        env=broker_environment,
        pass_fds=(read_fd,),
        preexec_fn=_demote("pwc-broker"),
    )
    os.close(read_fd)
    os.write(
        write_fd,
        json.dumps(
            {
                "gateway_url": os.environ["PWC_CHAT_GATEWAY_URL"],
                "proxy_token": proxy_token,
            },
            separators=(",", ":"),
        ).encode(),
    )
    os.close(write_fd)
    _wait_for_broker(broker)

    agent_read_fd, agent_write_fd = os.pipe()
    agent_environment = _agent_environment()
    agent_environment["PWC_WEBFETCH_TOKEN_FD"] = str(agent_read_fd)
    agent_environment["PWC_CHAT_PERSISTENT_AGENT"] = "1"
    agent = subprocess.Popen(
        [sys.executable, "-m", "backend.chat_sandbox_worker.agent"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
        env=agent_environment,
        pass_fds=(agent_read_fd,),
        preexec_fn=_demote(
            "pwc-chat",
            pids_max=int(os.environ.get("PWC_CHAT_SANDBOX_PIDS_MAX", "64")),
        ),
        bufsize=0,
    )
    os.close(agent_read_fd)
    os.write(agent_write_fd, proxy_token.encode())
    os.close(agent_write_fd)
    assert agent.stdout is not None
    ready, _, _ = select.select([agent.stdout], [], [], 30)
    if not ready:
        raise RuntimeError("Persistent agent readiness timed out")
    startup = decode_frame(agent.stdout.readline())
    if startup != {
        "v": 1,
        "type": "worker_ready",
        "request_id": "startup",
    }:
        raise RuntimeError("Persistent agent readiness failed")
    return broker, agent


def _stop(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()


def _validate_assignment(
    launch: dict,
    run: dict,
    *,
    assigned_session_id: str | None,
) -> str:
    required = {
        "capability",
        "gateway_url",
        "session_id",
        "turn_id",
        "assignment_token",
        "worker_generation",
    }
    if set(launch) != required:
        raise RuntimeError("Invalid persistent control launch frame")
    if launch["gateway_url"] != os.environ["PWC_CHAT_GATEWAY_URL"]:
        raise RuntimeError("Gateway changed after sandbox creation")
    if not hmac.compare_digest(
        str(launch["worker_generation"]),
        os.environ["PWC_CHAT_WORKER_GENERATION"],
    ):
        raise RuntimeError("Persistent worker generation mismatch")
    assignment_token = str(launch["assignment_token"])
    if not assignment_token:
        raise RuntimeError("Persistent worker assignment token is missing")
    session_id = str(launch["session_id"])
    if assigned_session_id and assigned_session_id != session_id:
        raise RuntimeError("Persistent worker session ownership mismatch")
    if (
        run.get("type") != "run_turn"
        or run.get("chat_session_id") != session_id
        or run.get("request_id") is None
        or run.get("turn_id") != str(launch["turn_id"])
        or run.get("worker_generation") != str(launch["worker_generation"])
        or not hmac.compare_digest(
            str(run.get("assignment_token") or ""),
            assignment_token,
        )
    ):
        raise RuntimeError("Invalid persistent run frame")
    return session_id


def _serve_turn(
    connection: socket.socket,
    *,
    broker: subprocess.Popen,
    agent: subprocess.Popen,
    assigned_session_id: str | None,
) -> str:
    launch_line = _readline(connection, MAX_PRIVATE_FRAME_BYTES)
    if not launch_line.startswith(SUPERVISOR_PREFIX):
        raise RuntimeError("Missing persistent control launch frame")
    launch = json.loads(launch_line[len(SUPERVISOR_PREFIX) :])
    if launch.get("operation") == "ping" and frozenset(launch) in {
        frozenset({"operation", "worker_generation"}),
        frozenset({"operation", "worker_generation", "request_id"}),
    }:
        if not hmac.compare_digest(
            str(launch["worker_generation"]),
            os.environ["PWC_CHAT_WORKER_GENERATION"],
        ):
            raise RuntimeError("Persistent worker generation mismatch")
        if broker.poll() is not None or agent.poll() is not None:
            raise RuntimeError("Persistent worker child exited")
        broker_status = _broker_control({"operation": "status"})
        if broker_status.get("active"):
            raise RuntimeError("Persistent worker capability is still active")
        request_id = launch.get("request_id")
        if request_id is None:
            connection.sendall(b"ready\n")
        else:
            connection.sendall(
                encode_frame(
                    {
                        "v": 1,
                        "type": "worker_health",
                        "request_id": str(request_id),
                        "assigned": assigned_session_id is not None,
                    }
                )
            )
        return assigned_session_id or ""
    run_line = _readline(connection, 512 * 1024)
    run = decode_frame(run_line)
    session_id = _validate_assignment(
        launch,
        run,
        assigned_session_id=assigned_session_id,
    )
    _broker_control(
        {
            "operation": "install",
            "capability": str(launch["capability"]),
            "session_id": session_id,
            "turn_id": str(launch["turn_id"]),
        }
    )
    assert agent.stdin is not None and agent.stdout is not None
    agent.stdin.write(run_line)
    agent.stdin.flush()
    poller = select.poll()
    poller.register(connection, select.POLLIN | select.POLLHUP | select.POLLERR)
    poller.register(agent.stdout, select.POLLIN | select.POLLHUP | select.POLLERR)
    buffer = b""
    worker_done: bytes | None = None
    try:
        while worker_done is None:
            if agent.poll() is not None:
                raise RuntimeError("Persistent agent exited")
            for fd, event in poller.poll(250):
                if fd == connection.fileno():
                    if event & (select.POLLHUP | select.POLLERR):
                        raise ConnectionError("Backend control connection was lost")
                    data = connection.recv(64 * 1024)
                    if not data:
                        raise ConnectionError("Backend control connection was lost")
                    agent.stdin.write(data)
                    agent.stdin.flush()
                elif fd == agent.stdout.fileno():
                    if event & (select.POLLHUP | select.POLLERR):
                        raise RuntimeError("Persistent agent control was lost")
                    data = os.read(fd, 64 * 1024)
                    if not data:
                        raise RuntimeError("Persistent agent control was lost")
                    buffer += data
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        line += b"\n"
                        event_frame = decode_frame(line)
                        if event_frame.get("request_id") != run["request_id"]:
                            raise RuntimeError("Uncorrelated persistent worker frame")
                        if event_frame.get("type") == "worker_done":
                            worker_done = line
                            break
                        connection.sendall(line)
        _broker_control(
            {
                "operation": "clear",
                "session_id": session_id,
                "turn_id": str(launch["turn_id"]),
            }
        )
        connection.sendall(worker_done)
        return session_id
    except BaseException:
        try:
            _broker_control(
                {
                    "operation": "clear",
                    "session_id": session_id,
                    "turn_id": str(launch["turn_id"]),
                }
            )
        except Exception:
            pass
        raise


def main() -> int:
    _not_dumpable()
    _harden_proc()
    broker, agent = _start_children()
    CONTROL_SOCKET.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    CONTROL_SOCKET.unlink(missing_ok=True)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(CONTROL_SOCKET))
    CONTROL_SOCKET.chmod(0o600)
    server.listen(1)
    assigned_session_id: str | None = None
    try:
        while broker.poll() is None and agent.poll() is None:
            connection, _ = server.accept()
            with connection:
                while connection.recv(1, socket.MSG_PEEK):
                    assigned = _serve_turn(
                        connection,
                        broker=broker,
                        agent=agent,
                        assigned_session_id=assigned_session_id,
                    )
                    if assigned:
                        assigned_session_id = assigned
        raise RuntimeError("Persistent worker child exited")
    finally:
        server.close()
        CONTROL_SOCKET.unlink(missing_ok=True)
        _stop(agent)
        _stop(broker)


if __name__ == "__main__":
    raise SystemExit(main())
