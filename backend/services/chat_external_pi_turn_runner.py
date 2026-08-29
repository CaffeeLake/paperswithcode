"""External Pi turn transport with lazy, fenced sandbox tool execution."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from websockets.asyncio.client import connect as websocket_connect

from backend.chat_sandbox_worker.executor_protocol import ProtocolError
from backend.chat_sandbox_worker.mcp_app_registry import egress_policy_digest
from backend.config import Settings
from backend.database.connection import db_manager
from backend.services.chat_capability_service import (
    ChatCapabilityService,
    IssuedCapability,
)
from backend.services.chat_external_worker_registry import (
    ChatExternalWorkerRepository,
    ExternalWorkerClaim,
)
from backend.services.chat_sandbox_executor import (
    ExecutorContext,
    ExecutorExecutionLost,
    ExecutorOperationError,
    ExecutorTransportError,
    SandboxExecutorClient,
)
from backend.services.chat_sandbox_provider import (
    ModalSandboxProviderAdapter,
    SandboxError,
    SandboxLaunchMode,
)
from backend.services.chat_session_service import TurnAdmission

MAX_EXTERNAL_TURN_FRAME_BYTES = 2 * 1024 * 1024 + 256 * 1024


def _worker_websocket_url(base_url: str) -> str:
    parsed = urlsplit(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunsplit(
        (scheme, parsed.netloc, f"{parsed.path.rstrip('/')}/v1/turn", "", "")
    )


class ExternalPiChatTurnRunner:
    """Run Pi on the trusted host and create a Modal executor only on tool use."""

    sdk_directory = "/workspace"

    def __init__(
        self,
        *,
        settings: Settings,
        admission: TurnAdmission,
        prompt: str,
        request_id: str,
        resume_id: uuid.UUID | None,
        capability: IssuedCapability,
        hf_username: str,
        provider: Any | None = None,
        executor: SandboxExecutorClient | Any | None = None,
        websocket_connector: Callable[..., Any] = websocket_connect,
        worker_repository: ChatExternalWorkerRepository | Any | None = None,
        session_factory: Callable[[], AbstractContextManager[Any]] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.settings = settings
        self.admission = admission
        self.prompt = prompt
        self.request_id = request_id
        self.resume_id = resume_id
        self.capability = capability
        self.capability_id: uuid.UUID | None = capability.capability_id
        self.hf_username = hf_username
        self.provider = provider or ModalSandboxProviderAdapter(settings)
        self.executor = executor or SandboxExecutorClient(self.provider)
        self.websocket_connector = websocket_connector
        self.worker_repository = worker_repository or ChatExternalWorkerRepository(
            environment=settings.environment
        )
        self.session_factory = session_factory or db_manager.session_local
        self.now = now or (lambda: datetime.now(UTC))
        self.sandbox: object | None = None
        self.worker_generation = secrets.token_hex(16)
        self.workspace_generation = 1
        self.socket: Any | None = None
        self.active_context: ExecutorContext | None = None

    async def events(self) -> AsyncIterator[dict]:
        worker_claim = self._select_worker_claim()
        async with self.websocket_connector(
            _worker_websocket_url(self.settings.chat_external_pi_worker_url),
            additional_headers={
                "Authorization": (
                    f"Bearer {self.settings.chat_external_pi_worker_token}"
                ),
                "X-PWC-Worker-Generation": str(worker_claim.generation),
            },
            max_size=MAX_EXTERNAL_TURN_FRAME_BYTES,
            open_timeout=self.settings.chat_external_pi_startup_timeout_seconds,
            ping_interval=20,
            ping_timeout=20,
        ) as socket:
            self.socket = socket
            await socket.send(json.dumps(self._run_frame(), separators=(",", ":")))
            async for raw in socket:
                event = self._decode(raw)
                if event.get("type") == "tool_request":
                    await socket.send(
                        json.dumps(
                            await self._tool_result(event), separators=(",", ":")
                        )
                    )
                    continue
                if event.get("type") == "worker_done":
                    return
                yield event
        self.socket = None

    def _select_worker_claim(self) -> ExternalWorkerClaim:
        with self.session_factory() as db:
            selected_at = self.now()
            claim = self.worker_repository.select_ready_claim(db, now=selected_at)
            self.worker_repository.require_ready_claim(
                db,
                claim=claim,
                now=self.now(),
            )
            return claim

    def _run_frame(self) -> dict[str, object]:
        claim = self.admission.durable_claim
        if claim is None or claim.turn_id != self.admission.turn_id:
            raise RuntimeError("External Pi turn requires the durable turn claim")
        return {
            "v": 1,
            "type": "run_turn",
            "request_id": self.request_id,
            "chat_session_id": str(self.admission.session_id),
            "turn_id": str(self.admission.turn_id),
            "turnClaim": {
                "turnId": str(claim.turn_id),
                "workerId": claim.worker_id,
                "workerGeneration": claim.worker_generation,
                "leaseGeneration": claim.lease_generation,
            },
            "prompt": self.prompt,
            "model": self.settings.chat_route_provider_models[
                self.admission.model_route
            ],
            "provider_protocol": self.settings.chat_route_protocols[
                self.admission.model_route
            ],
            "resume": str(self.resume_id) if self.resume_id else None,
            "web_search_enabled": self.admission.web_search_enabled,
            "reader_mode": self.admission.reader_mode,
            "poster_mode": self.admission.poster_mode,
            "paper_artifacts_enabled": self.admission.paper_artifacts_enabled,
            "paper_descriptor": self.admission.paper_descriptor,
            "reasoning_effort": self.admission.reasoning_effort,
            "fetchable_urls": list(self.admission.fetchable_urls),
            "hf_username": self.hf_username,
            "agent_harness": "pi",
            "capability": self.capability.token,
            "gateway_url": self.settings.chat_gateway_url,
        }

    @staticmethod
    def _decode(raw: str | bytes) -> dict[str, object]:
        if isinstance(raw, bytes):
            if len(raw) > MAX_EXTERNAL_TURN_FRAME_BYTES:
                raise RuntimeError("External Pi frame is too large")
            raw = raw.decode("utf-8")
        elif len(raw.encode("utf-8")) > MAX_EXTERNAL_TURN_FRAME_BYTES:
            raise RuntimeError("External Pi frame is too large")
        value = json.loads(raw)
        if not isinstance(value, dict) or not isinstance(value.get("type"), str):
            raise RuntimeError("External Pi frame is invalid")
        return value

    async def _ensure_executor(
        self, tool_call_id: str, operation_id: str
    ) -> ExecutorContext:
        if self.sandbox is None:
            self.sandbox = await self.provider.create(
                name=f"chat-executor-{self.admission.session_id}",
                tags={
                    "service": "pwc-chat-executor",
                    "environment": self.settings.environment,
                    "chat_session_hash": hashlib.sha256(
                        str(self.admission.session_id).encode()
                    ).hexdigest()[:16],
                    "release": self.settings.release_id,
                    "image": self.settings.chat_modal_image_version,
                    "egress": egress_policy_digest(self.settings),
                },
                worker_generation=self.worker_generation,
                launch_mode=SandboxLaunchMode.EXECUTOR,
            )
        context = ExecutorContext(
            sandbox=self.sandbox,
            workspace_id=str(self.admission.session_id),
            workspace_generation=self.workspace_generation,
            session_id=str(self.admission.session_id),
            turn_id=str(self.admission.turn_id),
            execution_id=operation_id,
            tool_call_id=tool_call_id,
            worker_generation=self.worker_generation,
            capability=self.capability.token,
        )
        await self.executor.ensure_workspace(context)
        self.active_context = context
        return context

    async def _tool_result(self, request: dict[str, object]) -> dict[str, object]:
        operation_id = str(request.get("operation_id") or "")
        tool_call_id = str(request.get("tool_call_id") or "")
        base: dict[str, object] = {
            "type": "tool_result",
            "operation_id": operation_id,
        }
        if not operation_id or not tool_call_id:
            raise ValueError("invalid_tool_identity")
        operation = request.get("operation")
        if operation not in {"exec", "read"}:
            raise ValueError("unsupported_tool_operation")
        try:
            context = await self._ensure_executor(tool_call_id, operation_id)
            if operation == "exec":
                result = await self.executor.exec(
                    context,
                    command=str(request["command"]),
                    timeout_ms=int(request["timeout_ms"]),
                )
                terminal = dict(result.terminal)
                return {
                    **base,
                    "ok": terminal.get("status") == "completed",
                    "outputs": list(result.outputs),
                    "terminal": terminal,
                    **(
                        {"error": str(terminal["error"])}
                        if terminal.get("error")
                        else {}
                    ),
                }
            if operation == "read":
                result = await self.executor.read_file(
                    context,
                    path=str(request["path"]),
                    offset=int(request["offset"]),
                    max_bytes=int(request["max_bytes"]),
                )
                return {
                    **base,
                    "ok": True,
                    "data_base64": base64.b64encode(result.data).decode("ascii"),
                    "eof": result.eof,
                }
            raise AssertionError("validated tool operation was not handled")
        except (
            ExecutorExecutionLost,
            ExecutorOperationError,
            ExecutorTransportError,
            ProtocolError,
            SandboxError,
        ) as error:
            return {**base, "ok": False, "error": getattr(error, "code", "tool_failed")}
        finally:
            self.active_context = None

    def _revoke(self) -> None:
        if self.capability_id is None:
            return
        with db_manager.session_local() as db:
            ChatCapabilityService(db).revoke(self.capability_id)
            db.commit()
        self.capability_id = None

    async def cancel(self) -> None:
        self._revoke()
        if self.socket is not None:
            await self.socket.send(
                json.dumps({"type": "cancel", "request_id": self.request_id})
            )
        if self.active_context is not None:
            await self.executor.cancel_execution(self.active_context)

    async def close(self) -> None:
        self._revoke()
        if self.sandbox is None:
            return
        sandbox_id = str(getattr(self.sandbox, "object_id", ""))
        if sandbox_id:
            await self.provider.terminate(sandbox_id, self.sandbox)
        self.sandbox = None
