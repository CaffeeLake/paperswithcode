"""Minimal per-turn Modal exec relay for the root-only control socket."""

from __future__ import annotations

import json
import os
import select
import socket
import sys

from backend.chat_sandbox_worker.control_daemon import CONTROL_SOCKET
from backend.chat_sandbox_worker.supervisor import SUPERVISOR_PREFIX


def main() -> int:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.connect(str(CONTROL_SOCKET))
        if sys.argv[1:2] == ["--ping"] and len(sys.argv) == 3:
            generation = sys.argv[2]
            connection.sendall(
                SUPERVISOR_PREFIX
                + json.dumps(
                    {
                        "operation": "ping",
                        "worker_generation": generation,
                    },
                    separators=(",", ":"),
                ).encode()
                + b"\n"
            )
            return 0 if connection.recv(16) == b"ready\n" else 1
        poller = select.poll()
        poller.register(sys.stdin.buffer, select.POLLIN | select.POLLHUP)
        poller.register(connection, select.POLLIN | select.POLLHUP)
        stdin_open = True
        while True:
            for fd, event in poller.poll(250):
                if fd == sys.stdin.buffer.fileno():
                    if event & select.POLLIN:
                        data = os.read(fd, 64 * 1024)
                        if data:
                            connection.sendall(data)
                        else:
                            stdin_open = False
                    elif event & select.POLLHUP:
                        stdin_open = False
                elif fd == connection.fileno():
                    data = connection.recv(64 * 1024)
                    if not data:
                        return 0
                    sys.stdout.buffer.write(data)
                    sys.stdout.buffer.flush()
            if not stdin_open:
                connection.shutdown(socket.SHUT_WR)


if __name__ == "__main__":
    raise SystemExit(main())
