"""Authenticated WebSocket bridge to the root-only worker control socket."""

from __future__ import annotations

import hmac
import json
import os
import socket
import threading
from collections.abc import Callable

from websockets.sync.connection import Connection
from websockets.sync.server import Server, serve

from backend.chat_sandbox_worker.contract import CONTROL_PORT

CONTROL_SOCKET = "/run/pwc-chat/control.sock"
MAX_MESSAGE_BYTES = 1024 * 1024
VERIFIED_METADATA_HEADER = "X-Verified-User-Data"


def _verify_generation(connection: Connection) -> None:
    raw_metadata = connection.request.headers.get(VERIFIED_METADATA_HEADER)
    try:
        metadata = json.loads(raw_metadata or "")
    except (TypeError, json.JSONDecodeError) as error:
        raise PermissionError("Missing verified control metadata") from error
    if not isinstance(metadata, dict) or not hmac.compare_digest(
        str(metadata.get("worker_generation") or ""),
        os.environ["PWC_CHAT_WORKER_GENERATION"],
    ):
        raise PermissionError("Control worker generation mismatch")


def _bridge(connection: Connection) -> None:
    _verify_generation(connection)
    stopped = threading.Event()
    failure: list[BaseException] = []
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as control:
        control.connect(CONTROL_SOCKET)

        def websocket_to_control() -> None:
            try:
                for message in connection:
                    if not isinstance(message, bytes):
                        raise TypeError("Control WebSocket accepts binary frames only")
                    control.sendall(message)
            except Exception as error:
                failure.append(error)
            finally:
                stopped.set()
                try:
                    control.shutdown(socket.SHUT_WR)
                except OSError:
                    pass

        receiver = threading.Thread(target=websocket_to_control, daemon=True)
        receiver.start()
        control.settimeout(0.25)
        try:
            while not stopped.is_set():
                try:
                    chunk = control.recv(64 * 1024)
                except TimeoutError:
                    continue
                if not chunk:
                    break
                connection.send(chunk)
        finally:
            stopped.set()
            connection.close()
            receiver.join(timeout=1)
    if failure:
        raise failure[0]


def start_server(
    handler: Callable[[Connection], None] = _bridge,
) -> tuple[Server, threading.Thread]:
    server = serve(
        handler,
        "0.0.0.0",
        CONTROL_PORT,
        compression=None,
        max_size=MAX_MESSAGE_BYTES,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread
