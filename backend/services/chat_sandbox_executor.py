"""Trusted backend client for the isolated sandbox executor relay."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Protocol

from backend.chat_sandbox_worker.executor_daemon import EXECUTOR_BOOTSTRAP_PREFIX
from backend.chat_sandbox_worker.executor_protocol import (
    MAX_EXECUTION_RESPONSE_FRAMES,
    MAX_FRAME_BYTES,
    PROTOCOL,
    ProtocolError,
    ResponseSequenceValidator,
    decode_read_result_data,
    decode_response,
    encode_request,
)

MAX_EXECUTOR_RESPONSE_BYTES = 2 * MAX_FRAME_BYTES
MAX_EXECUTOR_RESPONSE_FRAMES = MAX_EXECUTION_RESPONSE_FRAMES


class ExecutorRelayProvider(Protocol):
    async def open_executor_relay(
        self, sandbox: object, *, timeout_seconds: int
    ) -> object: ...


@dataclass(frozen=True)
class ExecutorContext:
    sandbox: object = field(repr=False, compare=False)
    workspace_id: str
    workspace_generation: int
    session_id: str
    turn_id: str
    execution_id: str
    tool_call_id: str
    worker_generation: str
    capability: str = field(repr=False)

    @property
    def operation_identity(self) -> dict[str, object]:
        return {
            "workspace_id": self.workspace_id,
            "workspace_generation": self.workspace_generation,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "execution_id": self.execution_id,
            "tool_call_id": self.tool_call_id,
        }


@dataclass(frozen=True)
class ExecutorExecutionResult:
    outputs: tuple[dict[str, object], ...]
    terminal: dict[str, object]


@dataclass(frozen=True)
class ExecutorReadResult:
    path: str
    offset: int
    data: bytes
    eof: bool


class ExecutorTransportError(RuntimeError):
    """The trusted client could not prove a complete relay exchange."""

    def __init__(self, responses: tuple[dict[str, object], ...] = ()) -> None:
        super().__init__("Sandbox executor transport was lost")
        self.responses = responses


class ExecutorExecutionLost(RuntimeError):
    """An accepted Exec has uncertain completion and must never be retried."""

    code = "execution_lost"

    def __init__(self) -> None:
        super().__init__("Accepted sandbox execution was lost")


class ExecutorOperationError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__("Sandbox executor operation failed")
        self.code = code


class _ExecutorDisconnect(RuntimeError):
    pass


class SandboxExecutorClient:
    """Execute one strictly correlated request through a fresh sandbox relay."""

    def __init__(
        self,
        provider: ExecutorRelayProvider,
        *,
        request_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.provider = provider
        self.request_id_factory = request_id_factory or (lambda: uuid.uuid4().hex)

    async def health(self, sandbox: object) -> str:
        request_id = self.request_id_factory()
        request = {
            "protocol": PROTOCOL,
            "type": "health",
            "request_id": request_id,
            "execution_id": request_id,
        }
        responses = await self._exchange(
            sandbox,
            request,
            context=None,
            timeout_seconds=5,
        )
        if len(responses) != 1:
            raise ProtocolError("Invalid executor health response sequence")
        response = responses[0]
        if (
            response["type"] != "health_result"
            or response["request_id"] != request_id
            or response["execution_id"] != request_id
        ):
            raise ProtocolError("Uncorrelated executor health response")
        return str(response["status"])

    async def ensure_workspace(self, context: ExecutorContext) -> None:
        request = self._request(context, "ensure_workspace")
        responses = await self._exchange(
            context.sandbox, request, context=context, timeout_seconds=10
        )
        if len(responses) != 1:
            raise ProtocolError("Invalid ensure-workspace response sequence")
        self._validate_ack(responses[0], request, "ensure_workspace")

    async def exec(
        self,
        context: ExecutorContext,
        *,
        command: str,
        timeout_ms: int,
    ) -> ExecutorExecutionResult:
        request = self._request(
            context,
            "exec",
            command=command,
            timeout_ms=timeout_ms,
        )
        timeout_seconds = max(5, (timeout_ms + 999) // 1000 + 5)
        try:
            responses = await self._exchange(
                context.sandbox,
                request,
                context=context,
                timeout_seconds=timeout_seconds,
            )
        except ExecutorTransportError as error:
            if self._valid_execution_prefix(error.responses, request, "exec"):
                if error.responses[-1]["type"] == "terminal":
                    return self._execution_result(error.responses, request, "exec")
                raise ExecutorExecutionLost() from error
            raise
        if self._valid_execution_prefix(responses, request, "exec") and (
            not responses or responses[-1]["type"] != "terminal"
        ):
            raise ExecutorExecutionLost()
        return self._execution_result(responses, request, "exec")

    async def attach_execution(
        self, context: ExecutorContext, *, offset: int
    ) -> ExecutorExecutionResult:
        request = self._request(context, "attach_execution", offset=offset)
        responses = await self._exchange(
            context.sandbox, request, context=context, timeout_seconds=35
        )
        result = self._execution_result(responses, request, "attach_execution")
        if any(int(output["sequence"]) <= offset for output in result.outputs):
            raise ProtocolError("Executor attach response did not advance its cursor")
        return result

    async def cancel_execution(
        self, context: ExecutorContext
    ) -> ExecutorExecutionResult:
        request = self._request(context, "cancel_execution")
        responses = await self._exchange(
            context.sandbox, request, context=context, timeout_seconds=35
        )
        return self._execution_result(responses, request, "cancel_execution")

    async def read_file(
        self,
        context: ExecutorContext,
        *,
        path: str,
        offset: int,
        max_bytes: int,
    ) -> ExecutorReadResult:
        request = self._request(
            context,
            "read_file",
            path=path,
            offset=offset,
            max_bytes=max_bytes,
        )
        responses = await self._exchange(
            context.sandbox, request, context=context, timeout_seconds=10
        )
        if len(responses) != 2:
            raise ProtocolError("Invalid read response sequence")
        self._validate_ack(responses[0], request, "read_file")
        response = responses[1]
        self._validate_correlation(response, request)
        if response["type"] == "terminal":
            raise ExecutorOperationError(str(response["error"]))
        if response["type"] != "read_result":
            raise ProtocolError("Invalid read response sequence")
        if response["path"] != path or response["offset"] != offset:
            raise ProtocolError("Uncorrelated executor read response")
        data = decode_read_result_data(response["data_base64"])
        if len(data) > max_bytes:
            raise ProtocolError("Executor read exceeded the requested byte limit")
        return ExecutorReadResult(
            path=str(response["path"]),
            offset=int(response["offset"]),
            data=data,
            eof=bool(response["eof"]),
        )

    def _request(
        self, context: ExecutorContext, operation: str, **fields: object
    ) -> dict[str, object]:
        return {
            "protocol": PROTOCOL,
            "type": operation,
            "request_id": self.request_id_factory(),
            **context.operation_identity,
            **fields,
        }

    async def _exchange(
        self,
        sandbox: object,
        request: dict[str, object],
        *,
        context: ExecutorContext | None,
        timeout_seconds: int,
    ) -> tuple[dict[str, object], ...]:
        request_frame = encode_request(request)
        payload = request_frame
        if context is not None:
            payload = self._bootstrap(context) + request_frame
        process = await self.provider.open_executor_relay(
            sandbox, timeout_seconds=timeout_seconds
        )
        responses: list[dict[str, object]] = []
        try:
            process.stdin.write(payload)
            await process.stdin.drain.aio()
            async for response in self._responses(process.stdout):
                responses.append(response)
            await process.wait.aio()
        except ProtocolError:
            raise
        except Exception as error:
            raise ExecutorTransportError(tuple(responses)) from error
        return tuple(responses)

    @staticmethod
    def _bootstrap(context: ExecutorContext) -> bytes:
        if (
            not isinstance(context.capability, str)
            or not context.capability
            or not isinstance(context.worker_generation, str)
            or not context.worker_generation
        ):
            raise ProtocolError("Invalid executor bootstrap")
        value = {
            "operation": "executor_connect",
            "capability": context.capability,
            "workspace_id": context.workspace_id,
            "workspace_generation": context.workspace_generation,
            "session_id": context.session_id,
            "turn_id": context.turn_id,
            "worker_generation": context.worker_generation,
        }
        try:
            encoded = (
                EXECUTOR_BOOTSTRAP_PREFIX
                + json.dumps(value, separators=(",", ":")).encode("utf-8")
                + b"\n"
            )
        except (TypeError, UnicodeEncodeError) as error:
            raise ProtocolError("Invalid executor bootstrap") from error
        if len(encoded) > 64 * 1024:
            raise ProtocolError("Invalid executor bootstrap")
        return encoded

    @staticmethod
    async def _responses(stream: object) -> AsyncIterator[dict[str, object]]:
        buffer = b""
        received_bytes = 0
        received_frames = 0
        async for chunk in stream:
            if not isinstance(chunk, bytes):
                raise ProtocolError("Executor response stream must be bytes")
            received_bytes += len(chunk)
            if received_bytes > MAX_EXECUTOR_RESPONSE_BYTES:
                raise ProtocolError("Executor response stream is too large")
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                received_frames += 1
                if received_frames > MAX_EXECUTOR_RESPONSE_FRAMES:
                    raise ProtocolError("Executor response stream has too many frames")
                yield decode_response(line + b"\n")
            if len(buffer) > MAX_FRAME_BYTES:
                raise ProtocolError("Executor response frame is too large")
        if buffer:
            raise _ExecutorDisconnect("Executor response stream ended mid-frame")

    @staticmethod
    def _validate_correlation(
        response: dict[str, object], request: dict[str, object]
    ) -> None:
        for identity_field in (
            "request_id",
            "workspace_id",
            "workspace_generation",
            "session_id",
            "turn_id",
            "execution_id",
            "tool_call_id",
        ):
            if response[identity_field] != request[identity_field]:
                raise ProtocolError("Uncorrelated executor response")

    @classmethod
    def _validate_ack(
        cls,
        response: dict[str, object],
        request: dict[str, object],
        operation: str,
    ) -> None:
        cls._validate_correlation(response, request)
        if response["type"] != "acknowledged" or response["operation"] != operation:
            raise ProtocolError("Invalid executor acknowledgement")

    @classmethod
    def _valid_execution_prefix(
        cls,
        responses: tuple[dict[str, object], ...],
        request: dict[str, object],
        operation: str,
    ) -> bool:
        if not responses:
            return False
        cls._validate_ack(responses[0], request, operation)
        validator = ResponseSequenceValidator(
            str(request["request_id"]),
            workspace_id=str(request["workspace_id"]),
            workspace_generation=int(request["workspace_generation"]),
            session_id=str(request["session_id"]),
            turn_id=str(request["turn_id"]),
            execution_id=str(request["execution_id"]),
            tool_call_id=str(request["tool_call_id"]),
        )
        for response in responses:
            validator.accept(response)
        return True

    @classmethod
    def _execution_result(
        cls,
        responses: tuple[dict[str, object], ...],
        request: dict[str, object],
        operation: str,
    ) -> ExecutorExecutionResult:
        validator = ResponseSequenceValidator(
            str(request["request_id"]),
            workspace_id=str(request["workspace_id"]),
            workspace_generation=int(request["workspace_generation"]),
            session_id=str(request["session_id"]),
            turn_id=str(request["turn_id"]),
            execution_id=str(request["execution_id"]),
            tool_call_id=str(request["tool_call_id"]),
        )
        for response in responses:
            validator.accept(response)
        validator.finish()
        cls._validate_ack(responses[0], request, operation)
        outputs = tuple(
            {
                "sequence": response["sequence"],
                "stream": response["stream"],
                "data": response["data"],
            }
            for response in responses
            if response["type"] == "output"
        )
        terminal = responses[-1]
        return ExecutorExecutionResult(
            outputs=outputs,
            terminal={
                "status": terminal["status"],
                "exit_code": terminal["exit_code"],
                "error": terminal["error"],
            },
        )
