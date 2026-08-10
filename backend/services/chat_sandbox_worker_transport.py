"""In-process worker controls and process registries for chat sandboxes."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from typing import Protocol

from backend.chat_sandbox_worker.protocol import (
    FRAME_PREFIX,
    ProtocolError,
    decode_frame,
)
from backend.chat_sandbox_worker.supervisor import SUPERVISOR_PREFIX
from backend.services.chat_sandbox_provider import SandboxError
from backend.services.chat_sandbox_state_repository import WorkerClaim


class _SandboxIdentity(Protocol):
    object_id: str


class WorkerTransportProvider(Protocol):
    async def open_persistent_connection(
        self, sandbox: object, worker_generation: str
    ) -> object: ...

    async def open_turn_process(
        self, sandbox: object, *, timeout_seconds: int
    ) -> object: ...


@dataclass
class RunningWorker:
    process: object
    request_id: str
    claim: WorkerClaim
    cancel_requested: bool = False
    done: asyncio.Event | None = None


@dataclass
class SessionControl:
    process: object
    sandbox: object
    sandbox_id: str
    stderr_task: asyncio.Task | None
    reader_task: asyncio.Task | None
    queues: dict[str, asyncio.Queue]
    resume_id: str | None
    close_scheduled: bool = False


class _WebSocketDrain:
    def __init__(self, writer: _WebSocketWriter):
        self._writer = writer

    async def aio(self) -> None:
        await self._writer.flush()


class _WebSocketWriter:
    def __init__(self, connection: object):
        self._connection = connection
        self._pending = bytearray()
        self.drain = _WebSocketDrain(self)

    def write(self, data: bytes) -> None:
        self._pending.extend(data)

    async def flush(self) -> None:
        if not self._pending:
            return
        payload = bytes(self._pending)
        self._pending.clear()
        await self._connection.send(payload)


class _WebSocketProcess:
    def __init__(self, connection: object):
        self._connection = connection
        self.stdin = _WebSocketWriter(connection)
        self.stdout = connection

    async def aclose(self) -> None:
        await self._connection.close()


class ChatSandboxWorkerTransport:
    """Own live worker controls without owning provider or persistence policy."""

    def __init__(
        self,
        provider: WorkerTransportProvider,
        *,
        clock=time.monotonic,
    ):
        self.provider = provider
        self.clock = clock
        self.processes: dict[uuid.UUID, RunningWorker] = {}
        self.session_controls: dict[uuid.UUID, SessionControl] = {}
        self.blank_controls: dict[str, SessionControl] = {}
        self.blank_health_at: dict[str, float] = {}
        self.close_tasks: set[asyncio.Task] = set()

    async def open_persistent_control(
        self, sandbox: _SandboxIdentity, worker_generation: str
    ) -> SessionControl:
        connection = await self.provider.open_persistent_connection(
            sandbox, worker_generation
        )
        process = _WebSocketProcess(connection)
        control = SessionControl(
            process=process,
            sandbox=sandbox,
            sandbox_id=sandbox.object_id,
            stderr_task=None,
            reader_task=None,
            queues={},
            resume_id=None,
        )
        control.reader_task = asyncio.create_task(self.read_control(control))
        return control

    async def open_turn_process(
        self, sandbox: object, *, timeout_seconds: int
    ) -> object:
        return await self.provider.open_turn_process(
            sandbox, timeout_seconds=timeout_seconds
        )

    async def ping(self, control: SessionControl, worker_generation: str) -> bool:
        request_id = f"health-{uuid.uuid4()}"
        queue: asyncio.Queue = asyncio.Queue()
        control.queues[request_id] = queue
        try:
            control.process.stdin.write(
                SUPERVISOR_PREFIX
                + json.dumps(
                    {
                        "operation": "ping",
                        "worker_generation": worker_generation,
                        "request_id": request_id,
                    },
                    separators=(",", ":"),
                ).encode()
                + b"\n"
            )
            await control.process.stdin.drain.aio()
            async with asyncio.timeout(5):
                response = await queue.get()
            return bool(
                isinstance(response, dict)
                and response.get("type") == "worker_health"
                and response.get("request_id") == request_id
                and response.get("assigned") is False
            )
        except Exception:
            return False
        finally:
            control.queues.pop(request_id, None)

    async def read_control(self, control: SessionControl) -> None:
        buffer = b""
        failure: BaseException | None = None
        try:
            async for chunk in control.process.stdout:
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if not line or not line.startswith(FRAME_PREFIX.encode()):
                        continue
                    event = decode_frame(line)
                    request_id = str(event.get("request_id") or "")
                    queue = control.queues.get(request_id)
                    if queue is None:
                        raise ProtocolError("Uncorrelated persistent worker frame")
                    await queue.put(event)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            failure = error
        finally:
            if failure is None:
                failure = SandboxError(
                    "sandbox_worker_failed",
                    "The persistent worker control stream ended",
                    uncertain=True,
                )
            for queue in list(control.queues.values()):
                await queue.put(failure)

    def running_worker(self, turn_id: uuid.UUID) -> RunningWorker | None:
        return self.processes.get(turn_id)

    def register_running_worker(
        self, turn_id: uuid.UUID, running: RunningWorker
    ) -> None:
        self.processes[turn_id] = running

    def remove_running_worker(
        self, turn_id: uuid.UUID, *, expected: RunningWorker
    ) -> RunningWorker | None:
        running = self.processes.get(turn_id)
        if running is not expected:
            return None
        return self.processes.pop(turn_id)

    def session_control(self, chat_session_id: uuid.UUID) -> SessionControl | None:
        return self.session_controls.get(chat_session_id)

    def register_session_control(
        self, chat_session_id: uuid.UUID, control: SessionControl
    ) -> None:
        self.session_controls[chat_session_id] = control

    def blank_control(self, sandbox_id: str) -> SessionControl | None:
        return self.blank_controls.get(sandbox_id)

    def register_blank_control(
        self,
        sandbox_id: str,
        control: SessionControl,
        *,
        checked_at: float | None = None,
    ) -> None:
        self.blank_controls[sandbox_id] = control
        self.blank_health_at[sandbox_id] = (
            self.clock() if checked_at is None else checked_at
        )

    def blank_health_checked_at(self, sandbox_id: str) -> float | None:
        return self.blank_health_at.get(sandbox_id)

    def mark_blank_healthy(
        self,
        sandbox_id: str,
        *,
        expected: SessionControl,
        checked_at: float | None = None,
    ) -> bool:
        control = self.blank_controls.get(sandbox_id)
        if control is not expected:
            return False
        self.blank_health_at[sandbox_id] = (
            self.clock() if checked_at is None else checked_at
        )
        return True

    def promote_blank_control(
        self,
        sandbox_id: str,
        chat_session_id: uuid.UUID,
        *,
        expected: SessionControl,
    ) -> SessionControl | None:
        control = self.blank_controls.get(sandbox_id)
        if control is None or control is not expected:
            return None
        self.blank_controls.pop(sandbox_id)
        self.blank_health_at.pop(sandbox_id, None)
        if control is not None:
            self.session_controls[chat_session_id] = control
        return control

    def drop_session_control(
        self,
        chat_session_id: uuid.UUID,
        *,
        expected: SessionControl | None = None,
    ) -> SessionControl | None:
        control = self.session_controls.get(chat_session_id)
        if control is None or (expected is not None and control is not expected):
            return None
        self.session_controls.pop(chat_session_id)
        self._close_control(control)
        return control

    def drop_session_controls_by_sandbox(self, sandbox_id: str) -> int:
        removed = 0
        for session_id, control in list(self.session_controls.items()):
            if control.sandbox_id != sandbox_id:
                continue
            removed += (
                self.drop_session_control(session_id, expected=control) is not None
            )
        return removed

    def drop_blank_control(
        self,
        sandbox_id: str,
        *,
        expected: SessionControl | None = None,
    ) -> SessionControl | None:
        control = self.blank_controls.get(sandbox_id)
        if control is None or (expected is not None and control is not expected):
            return None
        self.blank_controls.pop(sandbox_id)
        self.blank_health_at.pop(sandbox_id, None)
        self._close_control(control)
        return control

    def schedule_close(self, control: SessionControl) -> None:
        if control.close_scheduled:
            return
        close = getattr(control.process, "aclose", None)
        if close is None:
            return
        control.close_scheduled = True
        task = asyncio.create_task(close())
        self.close_tasks.add(task)

        def finished(completed: asyncio.Task) -> None:
            self.close_tasks.discard(completed)

        task.add_done_callback(finished)

    def _close_control(self, control: SessionControl) -> None:
        if control.stderr_task is not None:
            control.stderr_task.cancel()
        if control.reader_task is not None:
            control.reader_task.cancel()
        self.schedule_close(control)
