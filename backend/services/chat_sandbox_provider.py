"""Provider-only operations for Modal chat sandboxes."""

from __future__ import annotations

import asyncio
import secrets
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Protocol

import modal
from modal.stream_type import StreamType
from websockets.asyncio.client import connect as websocket_connect

from backend.chat_sandbox_worker.contract import (
    CHAT_SANDBOX_REGION,
    CONTROL_PORT,
    MODAL_APP_NAME,
    PROVIDER_OUTPUT_TOKEN_LIMIT,
)
from backend.config import Settings
from backend.services.chat_runtime_contract import dedicated_gateway_hostname

ImageResolver = Callable[[str], Awaitable[object]]
WebSocketConnector = Callable[..., Awaitable[object]]


class SandboxError(RuntimeError):
    def __init__(self, code: str, message: str, *, uncertain: bool = False):
        super().__init__(message)
        self.code = code
        self.uncertain = uncertain


class SandboxProvider(Protocol):
    async def create(
        self,
        *,
        name: str,
        tags: dict[str, str],
        worker_generation: str | None = None,
    ) -> object: ...

    async def resolve(self, sandbox_id: str) -> object: ...

    async def poll(self, sandbox: object) -> object | None: ...

    async def health(
        self,
        sandbox: object,
        *,
        persistent: bool,
        worker_generation: str | None,
    ) -> bool: ...

    async def terminate(
        self, sandbox_id: str, sandbox: object | None = None
    ) -> bool: ...

    async def open_persistent_connection(
        self, sandbox: object, worker_generation: str
    ) -> object: ...

    async def open_turn_process(
        self, sandbox: object, *, timeout_seconds: int
    ) -> object: ...

    def iter_sandboxes(self, *, tags: dict[str, str]) -> AsyncIterator[object]: ...

    async def get_tags(self, sandbox: object) -> dict[str, str]: ...


async def resolve_modal_image(image_reference: str) -> object:
    if image_reference.startswith("im-"):
        return modal.Image.from_id(image_reference)
    return modal.Image.from_name(image_reference)


def sandbox_environment(settings: Settings) -> dict[str, str]:
    return {
        "PWC_CHAT_GATEWAY_URL": settings.chat_gateway_url,
        "PWC_CHAT_PREFLIGHT_MODEL": settings.chat_deepseek_v4_flash_route,
        "PWC_CHAT_MAX_TURNS": str(settings.chat_max_turns),
        "PWC_CHAT_MAX_TOOL_CALLS": str(settings.chat_max_tool_calls),
        "PWC_CHAT_MAX_DIRECT_SEARCH_CALLS": str(settings.chat_max_direct_search_calls),
        "PWC_CHAT_MAX_WEB_SEARCH_CALLS": str(settings.chat_web_search_max_calls),
        "PWC_CHAT_TOOL_RESULT_MAX_BYTES": str(settings.chat_tool_result_max_bytes),
        "PWC_CHAT_TURN_TOOL_OUTPUT_MAX_BYTES": str(
            settings.chat_turn_tool_output_max_bytes
        ),
        "PWC_CHAT_BASH_TIMEOUT_SECONDS": str(settings.chat_bash_timeout_seconds),
        "PWC_CHAT_AGENT_TIMEOUT_SECONDS": str(settings.chat_agent_timeout_seconds),
        "PWC_CHAT_SANDBOX_PIDS_MAX": str(settings.chat_sandbox_pids_max),
        "PWC_CHAT_MAX_OUTPUT_TOKENS": str(PROVIDER_OUTPUT_TOKEN_LIMIT),
    }


class ModalSandboxProviderAdapter:
    """Stateless Modal sandbox operations with no persistence side effects."""

    def __init__(
        self,
        settings: Settings,
        *,
        image_resolver: ImageResolver = resolve_modal_image,
        websocket_connector: WebSocketConnector = websocket_connect,
    ):
        self.settings = settings
        self.image_resolver = image_resolver
        self.websocket_connector = websocket_connector

    async def create(
        self,
        *,
        name: str,
        tags: dict[str, str],
        worker_generation: str | None = None,
    ) -> object:
        try:
            gateway_host = dedicated_gateway_hostname(self.settings.chat_gateway_url)
        except ValueError as error:
            raise SandboxError(
                "gateway_unavailable", "The research gateway is not configured"
            ) from error
        app, image = await asyncio.gather(
            modal.App.lookup.aio(MODAL_APP_NAME, create_if_missing=False),
            self.image_resolver(self.settings.chat_modal_image_version),
        )
        persistent_enabled = bool(
            getattr(self.settings, "chat_persistent_worker_enabled", False)
        )
        worker_generation = worker_generation or secrets.token_hex(16)
        command = (
            ("python", "-m", "backend.chat_sandbox_worker.control_daemon")
            if persistent_enabled
            else ("sleep", "infinity")
        )
        cpu_limit = (
            getattr(self.settings, "chat_sandbox_cpu_limit", None)
            or self.settings.chat_sandbox_cpu
        )
        memory_limit = (
            getattr(self.settings, "chat_sandbox_memory_limit_mib", None)
            or self.settings.chat_sandbox_memory_mib
        )
        if cpu_limit < self.settings.chat_sandbox_cpu:
            raise SandboxError("sandbox_resource_invalid", "CPU limit is below request")
        if memory_limit < self.settings.chat_sandbox_memory_mib:
            raise SandboxError(
                "sandbox_resource_invalid", "Memory limit is below request"
            )
        sandbox = await modal.Sandbox.create.aio(
            *command,
            app=app,
            image=image,
            env={
                **sandbox_environment(self.settings),
                "PWC_CHAT_WORKER_GENERATION": worker_generation,
            },
            name=name,
            tags=tags,
            region=CHAT_SANDBOX_REGION,
            timeout=(
                self.settings.chat_persistent_sandbox_lifetime_seconds
                if persistent_enabled
                else 3600
            ),
            idle_timeout=(
                self.settings.chat_persistent_sandbox_lifetime_seconds
                if persistent_enabled
                else max(60, self.settings.chat_sandbox_warm_seconds)
            ),
            workdir="/workspace",
            cpu=(self.settings.chat_sandbox_cpu, cpu_limit),
            memory=(self.settings.chat_sandbox_memory_mib, memory_limit),
            outbound_domain_allowlist=[gateway_host],
            inbound_cidr_allowlist=None if persistent_enabled else [],
            encrypted_ports=[],
            unencrypted_ports=[],
            include_oidc_identity_token=False,
            readiness_probe=modal.sandbox.Probe.with_exec(
                *(
                    (
                        "python",
                        "-m",
                        "backend.chat_sandbox_worker.relay",
                        "--ping",
                        worker_generation,
                    )
                    if persistent_enabled
                    else ("test", "-x", "/usr/local/bin/pwc")
                )
            ),
        )
        if not persistent_enabled:
            return sandbox
        deadline = time.monotonic() + self.settings.chat_worker_ready_timeout_seconds
        while time.monotonic() < deadline:
            try:
                if await self.health(
                    sandbox,
                    persistent=True,
                    worker_generation=worker_generation,
                ):
                    return sandbox
            except Exception:
                pass
            if await self.poll(sandbox) is not None:
                break
            await asyncio.sleep(0.05)
        await sandbox.terminate.aio(
            wait=self.settings.chat_sandbox_spend_enforcement_enabled
        )
        raise SandboxError(
            "sandbox_worker_not_ready", "Persistent worker readiness timed out"
        )

    async def resolve(self, sandbox_id: str) -> object:
        return await modal.Sandbox.from_id.aio(sandbox_id)

    async def poll(self, sandbox: object) -> object | None:
        return await sandbox.poll.aio()

    async def health(
        self,
        sandbox: object,
        *,
        persistent: bool,
        worker_generation: str | None,
    ) -> bool:
        if persistent:
            if not worker_generation:
                raise ValueError("Persistent sandbox health requires a generation")
            command = (
                "python",
                "-m",
                "backend.chat_sandbox_worker.relay",
                "--ping",
                worker_generation,
            )
        else:
            command = ("test", "-x", "/usr/local/bin/pwc")
        probe = await sandbox.exec.aio(*command, timeout=5)
        await probe.wait.aio()
        return probe.returncode == 0

    async def terminate(self, sandbox_id: str, sandbox: object | None = None) -> bool:
        try:
            target = sandbox or await self.resolve(sandbox_id)
            if getattr(self.settings, "chat_sandbox_spend_enforcement_enabled", False):
                async with asyncio.timeout(
                    getattr(
                        self.settings,
                        "chat_sandbox_termination_grace_seconds",
                        30,
                    )
                ):
                    await target.terminate.aio(wait=True)
            else:
                await target.terminate.aio(wait=False)
            return True
        except Exception:
            return False

    async def open_persistent_connection(
        self, sandbox: object, worker_generation: str
    ) -> object:
        credentials = await sandbox.create_connect_token.aio(
            user_metadata={"worker_generation": worker_generation},
            port=CONTROL_PORT,
        )
        websocket_url = credentials.url.replace("https://", "wss://", 1)
        return await self.websocket_connector(
            websocket_url,
            additional_headers={"Authorization": f"Bearer {credentials.token}"},
            compression=None,
            proxy=None,
            open_timeout=5,
            ping_interval=20,
            ping_timeout=20,
            max_size=1024 * 1024,
        )

    async def open_turn_process(
        self, sandbox: object, *, timeout_seconds: int
    ) -> object:
        return await sandbox.exec.aio(
            "python",
            "-m",
            "backend.chat_sandbox_worker.supervisor",
            stdout=StreamType.PIPE,
            stderr=StreamType.PIPE,
            timeout=timeout_seconds,
            workdir="/workspace",
            text=False,
        )

    async def iter_sandboxes(self, *, tags: dict[str, str]) -> AsyncIterator[object]:
        async for sandbox in modal.Sandbox.list.aio(tags=tags):
            yield sandbox

    async def get_tags(self, sandbox: object) -> dict[str, str]:
        return await sandbox.get_tags.aio()
