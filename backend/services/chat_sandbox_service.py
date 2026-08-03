"""Durable Modal sandbox lifecycle and framed worker transport."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import secrets
import time
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import httpx
import modal
from modal.stream_type import StreamType
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.chat_sandbox_worker.contract import MODAL_APP_NAME
from backend.chat_sandbox_worker.protocol import (
    FRAME_PREFIX,
    ProtocolError,
    WorkerEventValidator,
    decode_frame,
    encode_frame,
)
from backend.chat_sandbox_worker.supervisor import SUPERVISOR_PREFIX
from backend.config import Settings
from backend.database.connection import db_manager
from backend.models.database import (
    ChatSandboxLease,
    ChatSandboxPool,
    ChatSession,
    ChatTurnCapability,
)
from backend.services.chat_capability_service import IssuedCapability
from backend.services.chat_runtime_contract import dedicated_gateway_hostname
from backend.services.chat_sandbox_spend_service import (
    ChatComputeDisabled,
    ChatSandboxSpendService,
)

logger = logging.getLogger(__name__)

CAPACITY_LOCK_NAME = "chat-sandbox-capacity-v1"
POOL_MAINTENANCE_LOCK_NAME = "chat-sandbox-pool-maintenance-v1"
POOL_TERMINAL_RETENTION_DAYS = 35
POOL_CLEANUP_BATCH_SIZE = 100
POOL_ACCOUNTING_SAFETY_SECONDS = 120
POOL_LOCAL_HEALTH_MAX_AGE_SECONDS = 15
MODAL_CPU_USD_PER_CORE_SECOND = 0.00003942
MODAL_MEMORY_USD_PER_GIB_SECOND = 0.00000672


class SandboxError(RuntimeError):
    def __init__(self, code: str, message: str, *, uncertain: bool = False):
        super().__init__(message)
        self.code = code
        self.uncertain = uncertain


@dataclass(frozen=True)
class WorkerClaim:
    sandbox_id: str
    token_hash: str
    assignment_token: str = ""
    worker_generation: str = ""


@dataclass
class RunningWorker:
    process: object
    request_id: str
    claim: WorkerClaim
    cancel_requested: bool = False
    done: asyncio.Event | None = None


def _cancelled_terminal_event(running: RunningWorker | None) -> dict[str, str] | None:
    """Let an accepted user cancellation win over a concurrent worker exit."""
    if running is None or not running.cancel_requested:
        return None
    if running.done is not None:
        running.done.set()
    return {"type": "_cancelled"}


@dataclass
class SessionControl:
    process: object
    sandbox: object
    sandbox_id: str
    stderr_task: asyncio.Task
    reader_task: asyncio.Task | None
    queues: dict[str, asyncio.Queue]
    resume_id: str | None


@dataclass(frozen=True)
class StartClaim:
    token_hash: str
    stale_sandbox_id: str | None
    snapshot_id: str | None
    worker_generation: str = ""


async def resolve_modal_image(image_reference: str):
    if image_reference.startswith("im-"):
        return modal.Image.from_id(image_reference)
    return modal.Image.from_name(image_reference)


def sandbox_environment(settings: Settings) -> dict[str, str]:
    return {
        "PWC_CHAT_GATEWAY_URL": settings.chat_gateway_url,
        "PWC_CHAT_PREFLIGHT_MODEL": settings.chat_gemma_route,
        "PWC_CHAT_MAX_TURNS": str(settings.chat_max_turns),
        "PWC_CHAT_MAX_TOOL_CALLS": str(settings.chat_max_tool_calls),
        "PWC_CHAT_MAX_DIRECT_SEARCH_CALLS": str(settings.chat_max_direct_search_calls),
        "PWC_CHAT_TOOL_RESULT_MAX_BYTES": str(settings.chat_tool_result_max_bytes),
        "PWC_CHAT_TURN_TOOL_OUTPUT_MAX_BYTES": str(
            settings.chat_turn_tool_output_max_bytes
        ),
        "PWC_CHAT_BASH_TIMEOUT_SECONDS": str(settings.chat_bash_timeout_seconds),
        "PWC_CHAT_AGENT_TIMEOUT_SECONDS": str(settings.chat_agent_timeout_seconds),
        "PWC_CHAT_SANDBOX_PIDS_MAX": str(settings.chat_sandbox_pids_max),
    }


async def create_isolated_sandbox(
    settings: Settings,
    *,
    name: str,
    tags: dict[str, str],
    worker_generation: str | None = None,
):
    try:
        gateway_host = dedicated_gateway_hostname(settings.chat_gateway_url)
    except ValueError as error:
        raise SandboxError(
            "gateway_unavailable", "The research gateway is not configured"
        ) from error
    app, image = await asyncio.gather(
        modal.App.lookup.aio(MODAL_APP_NAME, create_if_missing=False),
        resolve_modal_image(settings.chat_modal_image_version),
    )
    persistent_enabled = bool(
        getattr(settings, "chat_persistent_worker_enabled", False)
    )
    worker_generation = worker_generation or secrets.token_hex(16)
    command = (
        ("python", "-m", "backend.chat_sandbox_worker.control_daemon")
        if persistent_enabled
        else ("sleep", "infinity")
    )
    cpu_limit = (
        getattr(settings, "chat_sandbox_cpu_limit", None) or settings.chat_sandbox_cpu
    )
    memory_limit = (
        getattr(settings, "chat_sandbox_memory_limit_mib", None)
        or settings.chat_sandbox_memory_mib
    )
    if cpu_limit < settings.chat_sandbox_cpu:
        raise SandboxError("sandbox_resource_invalid", "CPU limit is below request")
    if memory_limit < settings.chat_sandbox_memory_mib:
        raise SandboxError("sandbox_resource_invalid", "Memory limit is below request")
    sandbox = await modal.Sandbox.create.aio(
        *command,
        app=app,
        image=image,
        env={
            **sandbox_environment(settings),
            "PWC_CHAT_WORKER_GENERATION": worker_generation,
        },
        name=name,
        tags=tags,
        timeout=(
            settings.chat_persistent_sandbox_lifetime_seconds
            if persistent_enabled
            else 3600
        ),
        idle_timeout=(
            settings.chat_persistent_sandbox_lifetime_seconds
            if persistent_enabled
            else max(60, settings.chat_sandbox_warm_seconds)
        ),
        workdir="/workspace",
        cpu=(settings.chat_sandbox_cpu, cpu_limit),
        memory=(
            settings.chat_sandbox_memory_mib,
            memory_limit,
        ),
        outbound_domain_allowlist=[gateway_host],
        inbound_cidr_allowlist=[],
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
    deadline = time.monotonic() + settings.chat_worker_ready_timeout_seconds
    while time.monotonic() < deadline:
        try:
            probe = await sandbox.exec.aio(
                "python",
                "-m",
                "backend.chat_sandbox_worker.relay",
                "--ping",
                worker_generation,
                timeout=5,
            )
            await probe.wait.aio()
            if probe.returncode == 0:
                return sandbox
        except Exception:
            pass
        if await sandbox.poll.aio() is not None:
            break
        await asyncio.sleep(0.05)
    await sandbox.terminate.aio(wait=settings.chat_sandbox_spend_enforcement_enabled)
    raise SandboxError(
        "sandbox_worker_not_ready", "Persistent worker readiness timed out"
    )


class WorkspaceSnapshotProvider:
    """Directory-only snapshots; never capture processes or the full filesystem."""

    supported = True

    def __init__(self, *, ttl_days: int = 30):
        self.ttl_seconds = ttl_days * 24 * 60 * 60

    async def save(self, sandbox, _chat_session_id: uuid.UUID) -> str:
        image = await sandbox.snapshot_directory.aio(
            "/workspace",
            timeout=55,
            ttl=self.ttl_seconds,
        )
        await image.hydrate.aio()
        return image.object_id

    async def restore(self, sandbox, snapshot_id: str) -> None:
        image = modal.Image.from_id(snapshot_id)
        await sandbox.mount_image.aio("/workspace", image)

    async def delete(self, _snapshot_id: str) -> None:
        # Modal Image currently has no early-delete API. Dropping the durable
        # reference revokes application access; provider TTL performs deletion.
        return


class SandboxSessionManager:
    MAINTENANCE_CONCURRENCY = 8

    def __init__(
        self,
        settings: Settings,
        *,
        session_factory: Callable[[], Session] | None = None,
        snapshot_provider: WorkspaceSnapshotProvider | None = None,
    ):
        self.settings = settings
        self.session_factory = session_factory or db_manager.session_local
        self.snapshots = snapshot_provider or WorkspaceSnapshotProvider(
            ttl_days=settings.chat_workspace_snapshot_inactivity_days
        )
        self._processes: dict[uuid.UUID, RunningWorker] = {}
        self._controls: dict[uuid.UUID, SessionControl] = {}
        self._blank_controls: dict[str, SessionControl] = {}
        self._blank_health_at: dict[str, float] = {}
        self._background_tasks: set[asyncio.Task] = set()
        self._last_spend_reconciliation_at: datetime | None = None
        if settings.chat_workspace_snapshots_enabled and not self.snapshots.supported:
            raise SandboxError(
                "snapshot_unsupported",
                "Configured workspace snapshots require a Directory Snapshot provider",
            )

    async def _terminate_provider_sandbox(
        self, sandbox_id: str, sandbox: object | None = None
    ) -> bool:
        """Wait for provider confirmation whenever spend enforcement is active."""
        try:
            target = sandbox or await modal.Sandbox.from_id.aio(sandbox_id)
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

    @staticmethod
    def _billing_month(now: datetime) -> date:
        return now.date().replace(day=1)

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    @staticmethod
    def _next_month(now: datetime) -> datetime:
        if now.month == 12:
            return datetime(now.year + 1, 1, 1, tzinfo=UTC)
        return datetime(now.year, now.month + 1, 1, tzinfo=UTC)

    @staticmethod
    def _lock_capacity(db: Session, *, wait: bool = True) -> bool:
        function = (
            func.pg_advisory_xact_lock if wait else func.pg_try_advisory_xact_lock
        )
        result = db.scalar(
            select(function(func.hashtextextended(CAPACITY_LOCK_NAME, 0)))
        )
        return True if wait else bool(result)

    @staticmethod
    def _lock_pool_maintenance(db: Session) -> bool:
        return bool(
            db.scalar(
                select(
                    func.pg_try_advisory_xact_lock(
                        func.hashtextextended(POOL_MAINTENANCE_LOCK_NAME, 0)
                    )
                )
            )
        )

    def _pool_cost_per_second(self) -> float:
        return float(self.settings.chat_sandbox_cpu) * MODAL_CPU_USD_PER_CORE_SECOND + (
            float(self.settings.chat_sandbox_memory_mib)
            / 1024
            * MODAL_MEMORY_USD_PER_GIB_SECOND
        )

    def _finalize_pool_cost(
        self, row: ChatSandboxPool, now: datetime
    ) -> tuple[int, float]:
        created_at = row.created_at
        expires_at = row.expires_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        end = min(now, expires_at)
        seconds = max(0, round((end - created_at).total_seconds()))
        cost = seconds * (
            float(row.cpu_request) * MODAL_CPU_USD_PER_CORE_SECOND
            + (float(row.memory_request_mib) / 1024 * MODAL_MEMORY_USD_PER_GIB_SECOND)
        )
        row.blank_billable_seconds = seconds
        row.estimated_blank_cost_usd = cost
        return seconds, cost

    def pool_budget_status(self) -> dict[str, float | bool | str]:
        now = datetime.now(UTC)
        if not getattr(self.settings, "chat_sandbox_spend_enforcement_enabled", False):
            with self.session_factory() as db, db.begin():
                rows = list(
                    db.execute(
                        select(ChatSandboxPool).where(
                            ChatSandboxPool.billing_month == self._billing_month(now)
                        )
                    ).scalars()
                )
                accrued = sum(
                    self._finalize_pool_cost(row, now)[1]
                    if row.state in {"starting", "blank_ready", "draining"}
                    else float(row.estimated_blank_cost_usd)
                    for row in rows
                )
            reported = float(self.settings.chat_blank_pool_reported_month_to_date_usd)
            projected = (
                max(accrued, reported)
                + max(0, (self._next_month(now) - now).total_seconds())
                * self._pool_cost_per_second()
                * self.settings.chat_blank_pool_min
            )
            budget = float(self.settings.chat_blank_pool_monthly_budget_usd)
            return {
                "billing_month": self._billing_month(now).isoformat(),
                "accrued_usd": accrued,
                "reported_usd": reported,
                "effective_accrued_usd": max(accrued, reported),
                "projected_usd": projected,
                "budget_usd": budget,
                "within_budget": projected <= budget,
            }
        with self.session_factory() as db, db.begin():
            status = ChatSandboxSpendService(db, self.settings).status(now)
        return {
            "billing_month": status["billing_cycle"],
            "accrued_usd": status["estimated_microusd"] / 1_000_000,
            "reported_usd": status["provider_floor_microusd"] / 1_000_000,
            "effective_accrued_usd": status["effective_microusd"] / 1_000_000,
            "projected_usd": (
                status["effective_microusd"]
                + status["outstanding_reservation_microusd"]
            )
            / 1_000_000,
            "budget_usd": status["application_cap_microusd"] / 1_000_000,
            "within_budget": status["circuit_state"] != "tripped",
        }

    def _spawn_pool_replenishment(self) -> None:
        if not self.blank_pool_enabled:
            return
        task = asyncio.create_task(self.replenish_pool())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

        def report_failure(completed: asyncio.Task) -> None:
            if completed.cancelled():
                return
            error = completed.exception()
            if error is not None:
                logger.warning(
                    "chat blank pool replenishment failed error=%s",
                    type(error).__name__,
                )

        task.add_done_callback(report_failure)

    async def _pool_sandbox_health(self, sandbox_id: str, worker_generation: str):
        try:
            control = getattr(self, "_blank_controls", {}).get(sandbox_id)
            if control is not None:
                if control.sandbox_id != sandbox_id:
                    return None
                checked_at = getattr(self, "_blank_health_at", {}).get(sandbox_id)
                if (
                    checked_at is not None
                    and time.monotonic() - checked_at
                    <= POOL_LOCAL_HEALTH_MAX_AGE_SECONDS
                ):
                    return control.sandbox
                if await self._ping_control(control, worker_generation):
                    self._blank_health_at[sandbox_id] = time.monotonic()
                    return control.sandbox
                return None
            sandbox = await modal.Sandbox.from_id.aio(sandbox_id)
            if await sandbox.poll.aio() is not None:
                return None
            probe = await sandbox.exec.aio(
                "python",
                "-m",
                "backend.chat_sandbox_worker.relay",
                "--ping",
                worker_generation,
                timeout=5,
            )
            await probe.wait.aio()
            return sandbox if probe.returncode == 0 else None
        except Exception:
            return None

    async def _start_persistent_control(self, sandbox) -> SessionControl:
        async def drain_stderr(stream) -> None:
            async for _chunk in stream:
                pass

        process = await sandbox.exec.aio(
            "python",
            "-m",
            "backend.chat_sandbox_worker.relay",
            stdout=StreamType.PIPE,
            stderr=StreamType.PIPE,
            timeout=self.settings.chat_persistent_sandbox_lifetime_seconds,
            workdir="/workspace",
            text=False,
        )
        stderr_task = asyncio.create_task(drain_stderr(process.stderr))
        control = SessionControl(
            process=process,
            sandbox=sandbox,
            sandbox_id=sandbox.object_id,
            stderr_task=stderr_task,
            reader_task=None,
            queues={},
            resume_id=None,
        )
        control.reader_task = asyncio.create_task(self._read_control(control))
        return control

    async def _ping_control(
        self, control: SessionControl, worker_generation: str
    ) -> bool:
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

    async def _terminate_pool_row(
        self,
        pool_id: uuid.UUID,
        sandbox_id: str | None,
        *,
        failure_code: str | None,
    ) -> bool:
        operation_token_hash = self._token_hash(secrets.token_urlsafe(24))
        now = datetime.now(UTC)
        with self.session_factory() as db, db.begin():
            self._lock_capacity(db)
            row = db.execute(
                select(ChatSandboxPool)
                .where(ChatSandboxPool.id == pool_id)
                .with_for_update()
            ).scalar_one_or_none()
            if row is None or row.state not in {
                "starting",
                "blank_ready",
                "draining",
            }:
                return False
            if sandbox_id and row.modal_sandbox_id != sandbox_id:
                return False
            row.state = "draining"
            row.claim_token_hash = operation_token_hash
            row.failure_code = failure_code
            row.updated_at = now
        if sandbox_id:
            self._drop_blank_control(sandbox_id)
            confirmed = await self._terminate_provider_sandbox(sandbox_id)
            if getattr(self.settings, "chat_sandbox_spend_enforcement_enabled", False):
                with self.session_factory() as db, db.begin():
                    ChatSandboxSpendService(db, self.settings).terminate(
                        sandbox_id, failure_code, confirmed=confirmed
                    )
            if not confirmed:
                failure_code = "termination_uncertain"
        now = datetime.now(UTC)
        with self.session_factory() as db, db.begin():
            self._lock_capacity(db)
            row = db.execute(
                select(ChatSandboxPool)
                .where(ChatSandboxPool.id == pool_id)
                .with_for_update()
            ).scalar_one_or_none()
            if (
                row is None
                or row.state != "draining"
                or row.claim_token_hash != operation_token_hash
            ):
                return False
            if sandbox_id and row.modal_sandbox_id != sandbox_id:
                return False
            self._finalize_pool_cost(row, now)
            row.state = "failed" if failure_code else "terminated"
            row.failure_code = failure_code
            row.terminated_at = now
            row.updated_at = now
            return True

    async def claim_blank(
        self, chat_session_id: uuid.UUID
    ) -> tuple[object, int] | None:
        """Health-check and atomically bind one compatible blank worker."""

        if not (
            self.blank_pool_enabled and self.settings.chat_persistent_worker_enabled
        ):
            return None
        started = time.perf_counter()
        now = datetime.now(UTC)
        minimum_expiry = now + timedelta(
            seconds=self.settings.chat_blank_pool_min_remaining_seconds
        )
        with self.session_factory() as db:
            candidates = list(
                db.execute(
                    select(
                        ChatSandboxPool.id,
                        ChatSandboxPool.modal_sandbox_id,
                        ChatSandboxPool.worker_generation,
                    )
                    .where(
                        ChatSandboxPool.state == "blank_ready",
                        ChatSandboxPool.image_version
                        == self.settings.chat_modal_image_version,
                        ChatSandboxPool.worker_contract_version
                        == self.settings.chat_worker_contract_version,
                        ChatSandboxPool.app_release_id == self.settings.release_id,
                        ChatSandboxPool.cpu_request == self.settings.chat_sandbox_cpu,
                        ChatSandboxPool.cpu_limit
                        == (
                            self.settings.chat_sandbox_cpu_limit
                            or self.settings.chat_sandbox_cpu
                        ),
                        ChatSandboxPool.memory_request_mib
                        == self.settings.chat_sandbox_memory_mib,
                        ChatSandboxPool.memory_limit_mib
                        == (
                            self.settings.chat_sandbox_memory_limit_mib
                            or self.settings.chat_sandbox_memory_mib
                        ),
                        ChatSandboxPool.expires_at > minimum_expiry,
                    )
                    .order_by(ChatSandboxPool.ready_at)
                    .limit(self.settings.chat_blank_pool_max)
                ).all()
            )
        for pool_id, sandbox_id, worker_generation in candidates:
            if not sandbox_id:
                await self._terminate_pool_row(
                    pool_id, None, failure_code="sandbox_lost"
                )
                continue
            sandbox = await self._pool_sandbox_health(sandbox_id, worker_generation)
            if sandbox is None:
                await self._terminate_pool_row(
                    pool_id, sandbox_id, failure_code="sandbox_lost"
                )
                continue
            claimed = False
            now = datetime.now(UTC)
            with self.session_factory() as db, db.begin():
                self._lock_capacity(db)
                if getattr(
                    self.settings, "chat_sandbox_spend_enforcement_enabled", False
                ):
                    try:
                        ChatSandboxSpendService(db, self.settings).assert_available(now)
                    except ChatComputeDisabled as error:
                        raise SandboxError(error.code, str(error)) from error
                existing_lease = self._lease(db, chat_session_id, lock=True)
                row = db.execute(
                    select(ChatSandboxPool)
                    .where(
                        ChatSandboxPool.id == pool_id,
                        ChatSandboxPool.state == "blank_ready",
                        ChatSandboxPool.modal_sandbox_id == sandbox_id,
                        ChatSandboxPool.image_version
                        == self.settings.chat_modal_image_version,
                        ChatSandboxPool.worker_contract_version
                        == self.settings.chat_worker_contract_version,
                        ChatSandboxPool.app_release_id == self.settings.release_id,
                        ChatSandboxPool.cpu_request == self.settings.chat_sandbox_cpu,
                        ChatSandboxPool.cpu_limit
                        == (
                            self.settings.chat_sandbox_cpu_limit
                            or self.settings.chat_sandbox_cpu
                        ),
                        ChatSandboxPool.memory_request_mib
                        == self.settings.chat_sandbox_memory_mib,
                        ChatSandboxPool.memory_limit_mib
                        == (
                            self.settings.chat_sandbox_memory_limit_mib
                            or self.settings.chat_sandbox_memory_mib
                        ),
                        ChatSandboxPool.expires_at
                        > now
                        + timedelta(
                            seconds=self.settings.chat_blank_pool_min_remaining_seconds
                        ),
                    )
                    .with_for_update(skip_locked=True)
                ).scalar_one_or_none()
                if row is not None and existing_lease is None:
                    claim_token = secrets.token_urlsafe(24)
                    row.state = "claimed"
                    row.claim_generation += 1
                    row.claim_token_hash = self._token_hash(claim_token)
                    row.claimed_at = now
                    row.last_health_checked_at = now
                    row.updated_at = now
                    self._finalize_pool_cost(row, now)
                    db.add(
                        ChatSandboxLease(
                            chat_session_id=chat_session_id,
                            modal_sandbox_id=sandbox_id,
                            app_release_id=self.settings.release_id,
                            image_version=self.settings.chat_modal_image_version,
                            worker_contract_version=self.settings.chat_worker_contract_version,
                            worker_generation=row.worker_generation,
                            state="ready",
                            last_activity_at=now,
                            workspace_dirty=False,
                            created_at=now,
                            updated_at=now,
                        )
                    )
                    if getattr(
                        self.settings, "chat_sandbox_spend_enforcement_enabled", False
                    ):
                        ChatSandboxSpendService(db, self.settings).claim(
                            sandbox_id, chat_session_id, now
                        )
                    claimed = True
            if claimed:
                blank_control = getattr(self, "_blank_controls", {}).pop(
                    sandbox_id, None
                )
                getattr(self, "_blank_health_at", {}).pop(sandbox_id, None)
                if blank_control is not None:
                    self._controls[chat_session_id] = blank_control
                self._spawn_pool_replenishment()
                return sandbox, round((time.perf_counter() - started) * 1000)
        return None

    async def replenish_pool(self) -> int:
        """Reserve and initialize at most one blank worker without request blocking."""

        refill_started = time.perf_counter()
        if not (
            self.blank_pool_enabled
            and self.settings.chat_persistent_worker_enabled
            and self.settings.chat_blank_pool_min > 0
        ):
            return 0
        now = datetime.now(UTC)
        pool_id: uuid.UUID | None = None
        interval_id: uuid.UUID | None = None
        evict_session_id: uuid.UUID | None = None
        with self.session_factory() as db, db.begin():
            if not self._lock_pool_maintenance(db):
                return 0
            if not self._lock_capacity(db, wait=False):
                return 0
            live_pool = (
                db.scalar(
                    select(func.count())
                    .select_from(ChatSandboxPool)
                    .where(
                        ChatSandboxPool.state.in_(
                            ["starting", "blank_ready", "draining"]
                        )
                    )
                )
                or 0
            )
            if (
                live_pool >= self.settings.chat_blank_pool_min
                or live_pool >= self.settings.chat_blank_pool_max
            ):
                return 0
            live_assigned = (
                db.scalar(
                    select(func.count())
                    .select_from(ChatSandboxLease)
                    .where(
                        ChatSandboxLease.state.in_(
                            ["starting", "ready", "busy", "idle", "terminating"]
                        )
                    )
                )
                or 0
            )
            if live_pool + live_assigned >= self.settings.chat_sandbox_total_live_cap:
                evict_session_id = db.execute(
                    select(ChatSandboxLease.chat_session_id)
                    .where(ChatSandboxLease.state == "idle")
                    .order_by(ChatSandboxLease.last_activity_at)
                    .limit(1)
                ).scalar_one_or_none()
            else:
                pool_id = uuid.uuid4()
                worker_generation = secrets.token_hex(16)
                if getattr(
                    self.settings, "chat_sandbox_spend_enforcement_enabled", False
                ):
                    try:
                        interval_id = ChatSandboxSpendService(
                            db, self.settings
                        ).reserve_interval(
                            origin="blank_pool",
                            worker_generation=worker_generation,
                            now=now,
                        )
                    except ChatComputeDisabled:
                        return 0
                cpu_limit = (
                    self.settings.chat_sandbox_cpu_limit
                    or self.settings.chat_sandbox_cpu
                )
                memory_limit = (
                    self.settings.chat_sandbox_memory_limit_mib
                    or self.settings.chat_sandbox_memory_mib
                )
                claim_token = secrets.token_urlsafe(24)
                db.add(
                    ChatSandboxPool(
                        id=pool_id,
                        state="starting",
                        image_version=self.settings.chat_modal_image_version,
                        worker_contract_version=self.settings.chat_worker_contract_version,
                        worker_generation=worker_generation,
                        app_release_id=self.settings.release_id,
                        claim_generation=0,
                        claim_token_hash=self._token_hash(claim_token),
                        created_at=now,
                        expires_at=now
                        + timedelta(
                            seconds=self.settings.chat_persistent_sandbox_lifetime_seconds
                        ),
                        updated_at=now,
                        cpu_request=self.settings.chat_sandbox_cpu,
                        cpu_limit=cpu_limit,
                        memory_request_mib=self.settings.chat_sandbox_memory_mib,
                        memory_limit_mib=memory_limit,
                        billing_month=self._billing_month(now),
                    )
                )
        if evict_session_id is not None:
            if await self.snapshot_and_terminate(evict_session_id):
                return await self.replenish_pool()
            return 0
        if pool_id is None:
            return 0
        try:
            sandbox = await create_isolated_sandbox(
                self.settings,
                name=f"chat-blank-{pool_id}",
                tags={
                    "service": "pwc-chat",
                    "environment": getattr(self.settings, "environment", "staging"),
                    "pool": "blank",
                    "pool_id": str(pool_id),
                    "release": self.settings.release_id,
                    "image": self.settings.chat_modal_image_version,
                    "contract": self.settings.chat_worker_contract_version,
                },
                worker_generation=worker_generation,
            )
            control = await self._start_persistent_control(sandbox)
            if not await self._ping_control(control, worker_generation):
                raise SandboxError(
                    "sandbox_worker_not_ready",
                    "Persistent blank worker health check failed",
                )
            self._blank_controls[sandbox.object_id] = control
            self._blank_health_at[sandbox.object_id] = time.monotonic()
        except Exception:
            provider_sandbox = (
                sandbox
                if "sandbox" in locals() and hasattr(sandbox, "terminate")
                else None
            )
            confirmed = False
            if provider_sandbox is not None:
                confirmed = await self._terminate_provider_sandbox(
                    provider_sandbox.object_id, provider_sandbox
                )
            await self._terminate_pool_row(
                pool_id, None, failure_code="sandbox_start_failed"
            )
            if interval_id is not None:
                with self.session_factory() as db, db.begin():
                    spend = ChatSandboxSpendService(db, self.settings)
                    if provider_sandbox is None:
                        spend.abort_reservation(interval_id, "sandbox_start_failed")
                    else:
                        spend.provider_created(interval_id, provider_sandbox.object_id)
                        spend.terminate(
                            provider_sandbox.object_id,
                            "sandbox_start_failed",
                            confirmed=confirmed,
                        )
            return 0
        sandbox_id = sandbox.object_id
        landed = False
        now = datetime.now(UTC)
        with self.session_factory() as db, db.begin():
            self._lock_capacity(db)
            row = db.execute(
                select(ChatSandboxPool)
                .where(ChatSandboxPool.id == pool_id)
                .with_for_update()
            ).scalar_one_or_none()
            if (
                row is not None
                and row.state == "starting"
                and row.modal_sandbox_id is None
                and row.image_version == self.settings.chat_modal_image_version
                and row.worker_contract_version
                == self.settings.chat_worker_contract_version
                and row.app_release_id == self.settings.release_id
            ):
                row.modal_sandbox_id = sandbox_id
                row.state = "blank_ready"
                row.ready_at = now
                row.last_health_checked_at = now
                row.updated_at = now
                self._finalize_pool_cost(row, now)
                if interval_id is not None:
                    ChatSandboxSpendService(db, self.settings).provider_created(
                        interval_id, sandbox_id, now
                    )
                landed = True
        if not landed:
            confirmed = await self._terminate_provider_sandbox(sandbox_id, sandbox)
            if interval_id is not None:
                with self.session_factory() as db, db.begin():
                    spend = ChatSandboxSpendService(db, self.settings)
                    spend.provider_created(interval_id, sandbox_id)
                    spend.terminate(
                        sandbox_id, "ownership_changed", confirmed=confirmed
                    )
            return 0
        logger.info(
            "chat blank pool refill ready pool_id=%s sandbox_id=%s refill_ms=%d",
            pool_id,
            sandbox_id,
            round((time.perf_counter() - refill_started) * 1000),
        )
        return 1

    async def reconcile_pool_orphans(self) -> int:
        """Terminate provider pool sandboxes not represented by durable state."""

        now = datetime.now(UTC)
        with self.session_factory() as db:
            known_ids = set(
                db.execute(
                    select(ChatSandboxPool.modal_sandbox_id).where(
                        ChatSandboxPool.modal_sandbox_id.is_not(None),
                        ChatSandboxPool.state.in_(
                            ["starting", "blank_ready", "draining"]
                        ),
                    )
                ).scalars()
            )
            known_ids.update(
                db.execute(
                    select(ChatSandboxLease.modal_sandbox_id).where(
                        ChatSandboxLease.modal_sandbox_id.is_not(None),
                        ChatSandboxLease.state.in_(
                            ["starting", "ready", "busy", "idle", "terminating"]
                        ),
                    )
                ).scalars()
            )
            creation_in_flight = bool(
                db.execute(
                    select(ChatSandboxPool.id)
                    .where(
                        ChatSandboxPool.state == "starting",
                        ChatSandboxPool.updated_at
                        > now - timedelta(seconds=self.ready_timeout_seconds + 15),
                    )
                    .limit(1)
                ).first()
            )
        if creation_in_flight:
            # create_isolated_sandbox waits for worker readiness before it can
            # persist the provider ID. Concurrency one means an unknown tagged
            # sandbox during this bounded window may be that legitimate start.
            return 0
        terminated = 0
        async for sandbox in self._listed_pool_sandboxes():
            if sandbox.object_id in known_ids:
                continue
            try:
                confirmed = await self._terminate_provider_sandbox(
                    sandbox.object_id, sandbox
                )
                if not confirmed:
                    raise RuntimeError("provider termination was not confirmed")
                if self.settings.chat_sandbox_spend_enforcement_enabled:
                    with self.session_factory() as db, db.begin():
                        ChatSandboxSpendService(db, self.settings).terminate(
                            sandbox.object_id,
                            "pool_orphan_reconciled",
                            confirmed=True,
                        )
                terminated += 1
            except Exception:
                if self.settings.chat_sandbox_spend_enforcement_enabled:
                    with self.session_factory() as db, db.begin():
                        ChatSandboxSpendService(db, self.settings).terminate(
                            sandbox.object_id,
                            "termination_uncertain",
                            confirmed=False,
                        )
        return terminated

    async def _listed_pool_sandboxes(self):
        async for sandbox in modal.Sandbox.list.aio(
            tags={"service": "pwc-chat", "pool": "blank"}
        ):
            yield sandbox

    async def maintain_pool(self) -> dict[str, int]:
        """Drain stale blanks, reconcile provider loss, and replenish safely."""

        enabled = self.blank_pool_enabled
        now = datetime.now(UTC)
        drain: list[tuple[uuid.UUID, str | None, str | None]] = []
        health_candidates: list[tuple[uuid.UUID, str, str]] = []
        budget_blocked = not enabled
        with self.session_factory() as db, db.begin():
            if not self._lock_pool_maintenance(db):
                return {
                    "drained": 0,
                    "lost": 0,
                    "orphaned": 0,
                    "cleaned": 0,
                    "replenished": 0,
                }
            self._lock_capacity(db)
            if enabled:
                try:
                    ChatSandboxSpendService(db, self.settings).assert_available(now)
                except ChatComputeDisabled:
                    budget_blocked = True
            rows = list(
                db.execute(
                    select(ChatSandboxPool)
                    .where(
                        ChatSandboxPool.state.in_(
                            ["starting", "blank_ready", "draining"]
                        )
                    )
                    .with_for_update()
                ).scalars()
            )
            for row in rows:
                failure_code: str | None = None
                incompatible = (
                    row.image_version != self.settings.chat_modal_image_version
                    or row.worker_contract_version
                    != self.settings.chat_worker_contract_version
                    or row.app_release_id != self.settings.release_id
                    or row.cpu_request != self.settings.chat_sandbox_cpu
                    or row.cpu_limit
                    != (
                        self.settings.chat_sandbox_cpu_limit
                        or self.settings.chat_sandbox_cpu
                    )
                    or row.memory_request_mib != self.settings.chat_sandbox_memory_mib
                    or row.memory_limit_mib
                    != (
                        self.settings.chat_sandbox_memory_limit_mib
                        or self.settings.chat_sandbox_memory_mib
                    )
                )
                rotation_due = self._as_utc(row.expires_at) <= now + timedelta(
                    seconds=self.settings.chat_blank_pool_rotate_before_seconds
                )
                creation_expired = row.state == "starting" and self._as_utc(
                    row.updated_at
                ) <= now - timedelta(seconds=self.ready_timeout_seconds + 15)
                if creation_expired:
                    failure_code = "sandbox_start_failed"
                if (
                    row.state == "draining"
                    or not enabled
                    or incompatible
                    or rotation_due
                    or row.billing_month != self._billing_month(now)
                    or budget_blocked
                    or creation_expired
                ):
                    row.state = "draining"
                    row.failure_code = failure_code
                    row.updated_at = now
                    drain.append((row.id, row.modal_sandbox_id, failure_code))
                elif row.state == "blank_ready" and row.modal_sandbox_id:
                    health_candidates.append(
                        (row.id, row.modal_sandbox_id, row.worker_generation)
                    )
        drained = 0
        for pool_id, sandbox_id, failure_code in drain:
            drained += bool(
                await self._terminate_pool_row(
                    pool_id, sandbox_id, failure_code=failure_code
                )
            )
        lost = 0
        for pool_id, sandbox_id, worker_generation in health_candidates:
            sandbox = await self._pool_sandbox_health(sandbox_id, worker_generation)
            if sandbox is None:
                lost += bool(
                    await self._terminate_pool_row(
                        pool_id, sandbox_id, failure_code="sandbox_lost"
                    )
                )
                continue
            with self.session_factory() as db, db.begin():
                row = db.execute(
                    select(ChatSandboxPool)
                    .where(
                        ChatSandboxPool.id == pool_id,
                        ChatSandboxPool.state == "blank_ready",
                        ChatSandboxPool.modal_sandbox_id == sandbox_id,
                    )
                    .with_for_update()
                ).scalar_one_or_none()
                if row is not None:
                    row.last_health_checked_at = datetime.now(UTC)
                    row.updated_at = datetime.now(UTC)
                    self._finalize_pool_cost(row, datetime.now(UTC))
        cutoff = now - timedelta(days=POOL_TERMINAL_RETENTION_DAYS)
        cleaned = 0
        with self.session_factory() as db, db.begin():
            terminal_ids = list(
                db.execute(
                    select(ChatSandboxPool.id)
                    .where(
                        ChatSandboxPool.state.in_(["claimed", "terminated", "failed"]),
                        ChatSandboxPool.updated_at < cutoff,
                    )
                    .order_by(ChatSandboxPool.updated_at)
                    .limit(POOL_CLEANUP_BATCH_SIZE)
                ).scalars()
            )
            if terminal_ids:
                cleaned = (
                    db.execute(
                        delete(ChatSandboxPool).where(
                            ChatSandboxPool.id.in_(terminal_ids)
                        )
                    ).rowcount
                    or 0
                )
        orphaned = await self.reconcile_pool_orphans()
        replenished = 0 if budget_blocked else await self.replenish_pool()
        return {
            "drained": drained,
            "lost": lost,
            "orphaned": orphaned,
            "cleaned": cleaned,
            "replenished": replenished,
        }

    @property
    def ready_timeout_seconds(self) -> float:
        if getattr(self.settings, "chat_persistent_worker_enabled", False):
            return getattr(
                self.settings,
                "chat_worker_ready_timeout_seconds",
                self.settings.chat_sandbox_ready_timeout_seconds,
            )
        return self.settings.chat_sandbox_ready_timeout_seconds

    @property
    def blank_pool_enabled(self) -> bool:
        return bool(getattr(self.settings, "chat_blank_pool_enabled", False))

    async def validate_image_reference(self) -> None:
        try:
            await modal.App.lookup.aio(MODAL_APP_NAME, create_if_missing=False)
            await resolve_modal_image(self.settings.chat_modal_image_version)
        except Exception as error:
            raise SandboxError(
                "sandbox_image_unresolved",
                "The pinned sandbox image could not be resolved",
            ) from error

    def _lease(self, db: Session, chat_session_id: uuid.UUID, *, lock: bool):
        query = select(ChatSandboxLease).where(
            ChatSandboxLease.chat_session_id == chat_session_id
        )
        if lock:
            query = query.with_for_update()
        return db.execute(query).scalar_one_or_none()

    @staticmethod
    def _lock_start_claim(db: Session, chat_session_id: uuid.UUID) -> None:
        """Serialize start claims even before the lease row exists."""

        db.execute(
            select(
                func.pg_advisory_xact_lock(
                    func.hashtextextended(f"chat-sandbox:{chat_session_id}", 0)
                )
            )
        )

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def _claim_start(
        self,
        lease: ChatSandboxLease,
        *,
        creation_token: str,
        now: datetime,
    ) -> StartClaim:
        snapshot_id = None
        if (
            self.settings.chat_workspace_snapshots_enabled
            and lease.workspace_snapshot_id
            and lease.snapshot_image_version == self.settings.chat_modal_image_version
        ):
            snapshot_id = lease.workspace_snapshot_id
        elif lease.workspace_snapshot_id:
            lease.workspace_snapshot_id = None
            lease.snapshot_image_version = None
            lease.snapshot_updated_at = None

        token_hash = self._token_hash(creation_token)
        worker_generation = secrets.token_hex(16)
        claim = StartClaim(
            token_hash,
            lease.modal_sandbox_id,
            snapshot_id,
            worker_generation,
        )
        lease.state = "starting"
        lease.modal_sandbox_id = None
        lease.app_release_id = self.settings.release_id
        lease.image_version = self.settings.chat_modal_image_version
        lease.worker_contract_version = self.settings.chat_worker_contract_version
        lease.worker_generation = worker_generation
        lease.lease_token_hash = token_hash
        lease.lease_expires_at = now + timedelta(
            seconds=self.ready_timeout_seconds + 15
        )
        lease.failure_code = None
        lease.updated_at = now
        return claim

    @staticmethod
    def _unexpired(lease: ChatSandboxLease, now: datetime) -> bool:
        expires_at = lease.lease_expires_at
        if expires_at is None:
            return False
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return expires_at > now

    def _finish_owned_operation(
        self,
        chat_session_id: uuid.UUID,
        *,
        token_hash: str,
        expected_state: str,
        expected_sandbox_id: str | None,
        state: str,
        failure_code: str | None,
        clear_sandbox: bool,
    ) -> bool:
        with self.session_factory() as db, db.begin():
            if self.blank_pool_enabled:
                self._lock_capacity(db)
            lease = self._lease(db, chat_session_id, lock=True)
            if not (
                lease
                and lease.state == expected_state
                and lease.lease_token_hash == token_hash
                and lease.modal_sandbox_id == expected_sandbox_id
            ):
                return False
            if clear_sandbox:
                lease.modal_sandbox_id = None
            lease.state = state
            lease.failure_code = failure_code
            lease.lease_token_hash = None
            lease.lease_expires_at = None
            lease.updated_at = datetime.now(UTC)
            return True

    async def ensure_ready(
        self,
        chat_session_id: uuid.UUID,
        *,
        allow_pool: bool = False,
        pool_miss: bool = False,
        pool_lookup_ms: int | None = None,
    ) -> tuple[object, int, bool, str, int | None]:
        started = time.perf_counter()
        if getattr(self.settings, "chat_sandbox_spend_enforcement_enabled", False):
            with self.session_factory() as db, db.begin():
                try:
                    ChatSandboxSpendService(db, self.settings).assert_available()
                except ChatComputeDisabled as error:
                    raise SandboxError(error.code, str(error)) from error
        if allow_pool:
            with self.session_factory() as db:
                pool_eligible = self._lease(db, chat_session_id, lock=False) is None
            if pool_eligible:
                lookup_started = time.perf_counter()
                claimed = await self.claim_blank(chat_session_id)
                pool_lookup_ms = round((time.perf_counter() - lookup_started) * 1000)
                if claimed is not None:
                    sandbox, _claim_ms = claimed
                    return (
                        sandbox,
                        round((time.perf_counter() - started) * 1000),
                        False,
                        "pool_hit",
                        pool_lookup_ms,
                    )
                pool_miss = True
        deadline = time.monotonic() + self.ready_timeout_seconds
        claim: StartClaim | None = None
        interval_id: uuid.UUID | None = None
        sandbox_id: str | None = None
        worker_generation: str | None = None
        while claim is None and sandbox_id is None:
            creation_token = secrets.token_urlsafe(24)
            now = datetime.now(UTC)
            waiting_for_owner = False
            evict_session_id: uuid.UUID | None = None
            with self.session_factory() as db, db.begin():
                if self.blank_pool_enabled:
                    self._lock_capacity(db)
                self._lock_start_claim(db, chat_session_id)
                lease = self._lease(db, chat_session_id, lock=True)
                compatible = bool(
                    lease
                    and lease.image_version == self.settings.chat_modal_image_version
                    and lease.worker_contract_version
                    == self.settings.chat_worker_contract_version
                    and lease.worker_generation is not None
                )
                if (
                    lease
                    and compatible
                    and lease.modal_sandbox_id
                    and lease.state in {"ready", "idle", "busy"}
                ):
                    sandbox_id = lease.modal_sandbox_id
                    worker_generation = lease.worker_generation
                elif (
                    lease
                    and compatible
                    and lease.state == "starting"
                    and lease.lease_token_hash
                    and self._unexpired(lease, now)
                ):
                    waiting_for_owner = True
                elif lease is None or lease.state not in {
                    "starting",
                    "ready",
                    "busy",
                    "idle",
                    "terminating",
                }:
                    if self.blank_pool_enabled:
                        live_assigned = (
                            db.scalar(
                                select(func.count())
                                .select_from(ChatSandboxLease)
                                .where(
                                    ChatSandboxLease.state.in_(
                                        [
                                            "starting",
                                            "ready",
                                            "busy",
                                            "idle",
                                            "terminating",
                                        ]
                                    )
                                )
                            )
                            or 0
                        )
                        live_pool = (
                            db.scalar(
                                select(func.count())
                                .select_from(ChatSandboxPool)
                                .where(
                                    ChatSandboxPool.state.in_(
                                        ["starting", "blank_ready", "draining"]
                                    )
                                )
                            )
                            or 0
                        )
                        if (
                            live_assigned + live_pool
                            >= self.settings.chat_sandbox_total_live_cap
                        ):
                            evict_session_id = db.execute(
                                select(ChatSandboxLease.chat_session_id)
                                .where(ChatSandboxLease.state == "idle")
                                .order_by(ChatSandboxLease.last_activity_at)
                                .limit(1)
                            ).scalar_one_or_none()
                            if evict_session_id is None:
                                raise SandboxError(
                                    "sandbox_capacity",
                                    "Secure workspace capacity is temporarily full",
                                )
                    if evict_session_id is None:
                        if lease is None:
                            token_hash = self._token_hash(creation_token)
                            lease = ChatSandboxLease(
                                chat_session_id=chat_session_id,
                                app_release_id=self.settings.release_id,
                                image_version=self.settings.chat_modal_image_version,
                                worker_contract_version=(
                                    self.settings.chat_worker_contract_version
                                ),
                                worker_generation=secrets.token_hex(16),
                                state="starting",
                                lease_token_hash=token_hash,
                                lease_expires_at=now
                                + timedelta(seconds=self.ready_timeout_seconds + 15),
                                last_activity_at=now,
                            )
                            db.add(lease)
                            claim = StartClaim(
                                token_hash,
                                None,
                                None,
                                lease.worker_generation or "",
                            )
                        else:
                            claim = self._claim_start(
                                lease,
                                creation_token=creation_token,
                                now=now,
                            )
                        if claim is not None:
                            if getattr(
                                self.settings,
                                "chat_sandbox_spend_enforcement_enabled",
                                False,
                            ):
                                try:
                                    interval_id = ChatSandboxSpendService(
                                        db, self.settings
                                    ).reserve_interval(
                                        origin="direct",
                                        worker_generation=claim.worker_generation,
                                        chat_session_id=chat_session_id,
                                        now=now,
                                    )
                                except ChatComputeDisabled as error:
                                    raise SandboxError(
                                        error.code, str(error)
                                    ) from error
                else:
                    claim = self._claim_start(
                        lease, creation_token=creation_token, now=now
                    )
            if evict_session_id is not None:
                if await self.snapshot_and_terminate(evict_session_id):
                    continue
                if time.monotonic() >= deadline:
                    raise SandboxError(
                        "sandbox_capacity",
                        "Secure workspace capacity is temporarily full",
                    )
                await asyncio.sleep(0.05)
            elif waiting_for_owner:
                if time.monotonic() >= deadline:
                    raise SandboxError(
                        "sandbox_timeout", "Secure workspace startup timed out"
                    )
                await asyncio.sleep(0.05)

        if claim and claim.stale_sandbox_id:
            confirmed = await self._terminate_provider_sandbox(claim.stale_sandbox_id)
            if self.settings.chat_sandbox_spend_enforcement_enabled:
                with self.session_factory() as db, db.begin():
                    ChatSandboxSpendService(db, self.settings).terminate(
                        claim.stale_sandbox_id,
                        "stale_replaced",
                        confirmed=confirmed,
                    )
        await self.enforce_warm_cap()

        if sandbox_id:
            assert worker_generation is not None
            control = getattr(self, "_controls", {}).get(chat_session_id)
            if (
                getattr(self.settings, "chat_persistent_worker_enabled", False)
                and control is not None
                and control.sandbox_id == sandbox_id
            ):
                return (
                    control.sandbox,
                    round((time.perf_counter() - started) * 1000),
                    False,
                    "reused_session",
                    pool_lookup_ms,
                )
            try:
                sandbox = await modal.Sandbox.from_id.aio(sandbox_id)
                if await sandbox.poll.aio() is None:
                    probe = await sandbox.exec.aio(
                        *(
                            (
                                "python",
                                "-m",
                                "backend.chat_sandbox_worker.relay",
                                "--ping",
                                worker_generation,
                            )
                            if getattr(
                                self.settings, "chat_persistent_worker_enabled", False
                            )
                            else ("test", "-x", "/usr/local/bin/pwc")
                        ),
                        timeout=5,
                    )
                    await probe.wait.aio()
                    if probe.returncode == 0:
                        return (
                            sandbox,
                            round((time.perf_counter() - started) * 1000),
                            False,
                            "reused_session",
                            pool_lookup_ms,
                        )
            except Exception:
                pass
            with self.session_factory() as db, db.begin():
                lease = self._lease(db, chat_session_id, lock=True)
                if (
                    lease
                    and lease.modal_sandbox_id == sandbox_id
                    and lease.state in {"ready", "idle", "busy"}
                ):
                    claim = self._claim_start(
                        lease,
                        creation_token=secrets.token_urlsafe(24),
                        now=datetime.now(UTC),
                    )
            if claim is None:
                return await self.ensure_ready(
                    chat_session_id,
                    pool_miss=pool_miss,
                    pool_lookup_ms=pool_lookup_ms,
                )

        assert claim is not None
        try:
            async with asyncio.timeout(self.ready_timeout_seconds):
                sandbox = await create_isolated_sandbox(
                    self.settings,
                    name=f"chat-{chat_session_id}",
                    tags={
                        "service": "pwc-chat",
                        "environment": getattr(self.settings, "environment", "staging"),
                        "chat_session_hash": hashlib.sha256(
                            str(chat_session_id).encode()
                        ).hexdigest()[:16],
                        "release": self.settings.release_id,
                        "image": self.settings.chat_modal_image_version,
                    },
                    worker_generation=claim.worker_generation,
                )
                if claim.snapshot_id:
                    try:
                        await self.snapshots.restore(sandbox, claim.snapshot_id)
                    except Exception:
                        with self.session_factory() as db, db.begin():
                            lease = self._lease(db, chat_session_id, lock=True)
                            if (
                                lease
                                and lease.state == "starting"
                                and lease.lease_token_hash == claim.token_hash
                            ):
                                lease.workspace_snapshot_id = None
                                lease.snapshot_image_version = None
                                lease.snapshot_updated_at = None
        except TimeoutError as error:
            self._mark_start_failed(
                chat_session_id, claim.token_hash, "sandbox_timeout"
            )
            if interval_id is not None:
                with self.session_factory() as db, db.begin():
                    ChatSandboxSpendService(db, self.settings).abort_reservation(
                        interval_id, "sandbox_timeout"
                    )
            raise SandboxError(
                "sandbox_timeout", "Secure workspace startup timed out"
            ) from error
        except Exception as error:
            self._mark_start_failed(
                chat_session_id, claim.token_hash, "sandbox_start_failed"
            )
            if interval_id is not None:
                with self.session_factory() as db, db.begin():
                    ChatSandboxSpendService(db, self.settings).abort_reservation(
                        interval_id, "sandbox_start_failed"
                    )
            raise SandboxError(
                "sandbox_start_failed", "Secure workspace startup failed"
            ) from error

        sandbox_id = sandbox.object_id
        landed = False
        with self.session_factory() as db, db.begin():
            lease = self._lease(db, chat_session_id, lock=True)
            if (
                lease
                and lease.state == "starting"
                and lease.lease_token_hash == claim.token_hash
                and lease.modal_sandbox_id is None
            ):
                lease.modal_sandbox_id = sandbox_id
                lease.state = "ready"
                lease.lease_token_hash = None
                lease.lease_expires_at = None
                lease.last_activity_at = datetime.now(UTC)
                lease.workspace_dirty = False
                lease.updated_at = datetime.now(UTC)
                if interval_id is not None:
                    ChatSandboxSpendService(db, self.settings).provider_created(
                        interval_id, sandbox_id
                    )
                landed = True
        if not landed:
            confirmed = await self._terminate_provider_sandbox(sandbox_id, sandbox)
            if interval_id is not None:
                with self.session_factory() as db, db.begin():
                    spend = ChatSandboxSpendService(db, self.settings)
                    spend.provider_created(interval_id, sandbox_id)
                    spend.terminate(
                        sandbox_id, "ownership_changed", confirmed=confirmed
                    )
            raise SandboxError(
                "sandbox_start_failed", "Secure workspace ownership changed"
            )
        return (
            sandbox,
            round((time.perf_counter() - started) * 1000),
            True,
            "pool_miss" if pool_miss else "created",
            pool_lookup_ms,
        )

    def _mark_start_failed(
        self, chat_session_id: uuid.UUID, token_hash: str, code: str
    ) -> bool:
        return self._finish_owned_operation(
            chat_session_id,
            token_hash=token_hash,
            expected_state="starting",
            expected_sandbox_id=None,
            state="failed",
            failure_code=code,
            clear_sandbox=False,
        )

    def _claim_worker(self, chat_session_id: uuid.UUID, sandbox_id: str) -> WorkerClaim:
        assignment_token = secrets.token_urlsafe(24)
        claim: WorkerClaim | None = None
        with self.session_factory() as db, db.begin():
            lease = self._lease(db, chat_session_id, lock=True)
            if not (
                lease
                and lease.state in {"ready", "idle"}
                and lease.modal_sandbox_id == sandbox_id
                and lease.lease_token_hash is None
            ):
                raise SandboxError("sandbox_lost", "Secure workspace is unavailable")
            if not lease.worker_generation:
                raise SandboxError(
                    "sandbox_lost", "Secure workspace generation is unavailable"
                )
            claim = WorkerClaim(
                sandbox_id=sandbox_id,
                token_hash=self._token_hash(assignment_token),
                assignment_token=assignment_token,
                worker_generation=lease.worker_generation,
            )
            lease.state = "busy"
            lease.lease_token_hash = claim.token_hash
            lease.lease_expires_at = None
            lease.last_activity_at = datetime.now(UTC)
            lease.updated_at = datetime.now(UTC)
        assert claim is not None
        return claim

    def _release_worker(self, chat_session_id: uuid.UUID, claim: WorkerClaim) -> bool:
        with self.session_factory() as db, db.begin():
            lease = self._lease(db, chat_session_id, lock=True)
            if not (
                lease
                and lease.state == "busy"
                and lease.modal_sandbox_id == claim.sandbox_id
                and lease.lease_token_hash == claim.token_hash
            ):
                return False
            lease.state = "idle"
            lease.lease_token_hash = None
            lease.lease_expires_at = None
            lease.last_activity_at = datetime.now(UTC)
            # A completed turn may have changed /workspace through arbitrary
            # Bash, so conservatively mark it dirty.
            lease.workspace_dirty = True
            lease.updated_at = datetime.now(UTC)
            return True

    async def _terminate_worker(
        self,
        chat_session_id: uuid.UUID,
        claim: WorkerClaim,
        *,
        failure_code: str,
    ) -> bool:
        termination_token_hash = self._token_hash(secrets.token_urlsafe(24))
        with self.session_factory() as db, db.begin():
            lease = self._lease(db, chat_session_id, lock=True)
            if not (
                lease
                and lease.state == "busy"
                and lease.modal_sandbox_id == claim.sandbox_id
                and lease.lease_token_hash == claim.token_hash
            ):
                return False
            lease.state = "terminating"
            lease.failure_code = failure_code
            lease.lease_token_hash = termination_token_hash
            lease.lease_expires_at = datetime.now(UTC) + timedelta(
                seconds=self.ready_timeout_seconds + 15
            )
            lease.updated_at = datetime.now(UTC)
        self._drop_control(chat_session_id)
        await self._terminate_owned_sandbox(
            chat_session_id,
            sandbox_id=claim.sandbox_id,
            token_hash=termination_token_hash,
            failure_code=failure_code,
        )
        return True

    def _drop_control(self, chat_session_id: uuid.UUID) -> None:
        controls = getattr(self, "_controls", {})
        control = controls.pop(chat_session_id, None)
        if control is not None:
            control.stderr_task.cancel()
            if control.reader_task is not None:
                control.reader_task.cancel()

    def _drop_control_by_sandbox(self, sandbox_id: str) -> None:
        controls = getattr(self, "_controls", {})
        for session_id, control in list(controls.items()):
            if control.sandbox_id == sandbox_id:
                self._drop_control(session_id)

    def _drop_blank_control(self, sandbox_id: str) -> None:
        control = getattr(self, "_blank_controls", {}).pop(sandbox_id, None)
        getattr(self, "_blank_health_at", {}).pop(sandbox_id, None)
        if control is not None:
            control.stderr_task.cancel()
            if control.reader_task is not None:
                control.reader_task.cancel()

    async def _read_control(self, control: SessionControl) -> None:
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
        except BaseException as error:
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

    async def run_turn(
        self,
        *,
        chat_session_id: uuid.UUID,
        turn_id: uuid.UUID,
        request_id: str,
        prompt: str,
        model: str,
        resume: str | None,
        capability: IssuedCapability,
    ) -> AsyncIterator[dict]:
        if getattr(self.settings, "chat_sandbox_spend_enforcement_enabled", False):
            with self.session_factory() as db, db.begin():
                try:
                    ChatSandboxSpendService(db, self.settings).assert_available()
                except ChatComputeDisabled as error:
                    raise SandboxError(error.code, str(error)) from error
        retrying_pool_assignment = False
        while True:
            try:
                async for event in self._run_turn_once(
                    chat_session_id=chat_session_id,
                    turn_id=turn_id,
                    request_id=request_id,
                    prompt=prompt,
                    model=model,
                    resume=resume,
                    capability=capability,
                    allow_pool=not retrying_pool_assignment,
                    forced_pool_miss=retrying_pool_assignment,
                ):
                    if (
                        retrying_pool_assignment
                        and event.get("type") == "sandbox_start"
                    ):
                        continue
                    yield event
                return
            except SandboxError as error:
                if error.code != "pool_assignment_failed" or retrying_pool_assignment:
                    raise
                retrying_pool_assignment = True

    async def _run_turn_once(
        self,
        *,
        chat_session_id: uuid.UUID,
        turn_id: uuid.UUID,
        request_id: str,
        prompt: str,
        model: str,
        resume: str | None,
        capability: IssuedCapability,
        allow_pool: bool,
        forced_pool_miss: bool,
    ) -> AsyncIterator[dict]:
        turn_started = time.perf_counter()
        yield {"type": "sandbox_start", "session_id": str(chat_session_id)}
        existing_control = getattr(self, "_controls", {}).get(chat_session_id)
        if (
            existing_control is not None
            and resume is not None
            and existing_control.resume_id is not None
            and existing_control.resume_id != resume
        ):
            await self.snapshot_and_terminate(chat_session_id)
        persistent = bool(
            getattr(self.settings, "chat_persistent_worker_enabled", False)
        )
        (
            sandbox,
            cold_start_ms,
            created,
            acquisition_outcome,
            pool_lookup_ms,
        ) = await self.ensure_ready(
            chat_session_id,
            pool_miss=forced_pool_miss,
            allow_pool=bool(
                allow_pool and persistent and self.blank_pool_enabled and resume is None
            ),
        )
        if pool_lookup_ms is not None:
            yield {
                "type": "_latency",
                "phase": "pool_lookup_completed",
                "elapsed_ms": pool_lookup_ms,
            }
        yield {
            "type": "_latency",
            "phase": "sandbox_acquisition_ms",
            "elapsed_ms": round((time.perf_counter() - turn_started) * 1000),
            "acquisition_outcome": acquisition_outcome,
        }
        if acquisition_outcome == "pool_hit":
            yield {
                "type": "_latency",
                "phase": "session_assignment_completed",
                "elapsed_ms": round((time.perf_counter() - turn_started) * 1000),
            }
        if created:
            yield {
                "type": "_latency",
                "phase": "modal_create_ms",
                "elapsed_ms": cold_start_ms,
            }
        yield {
            "type": "sandbox_ready",
            "session_id": str(chat_session_id),
            "cold_start_ms": cold_start_ms,
        }
        claim: WorkerClaim | None = None
        running_worker: RunningWorker | None = None
        stderr_task: asyncio.Task | None = None
        control: SessionControl | None = None
        terminal = False
        pending_terminal_event: dict | None = None
        sdk_dispatched = False
        first_worker_delta_recorded = False
        validator = WorkerEventValidator()
        try:
            claim = self._claim_worker(chat_session_id, sandbox.object_id)

            async def drain_stderr(stream) -> None:
                async for _chunk in stream:
                    pass

            controls = getattr(self, "_controls", None)
            if controls is None:
                controls = self._controls = {}
            control = controls.get(chat_session_id) if persistent else None
            if control is not None and control.sandbox_id != sandbox.object_id:
                self._drop_control(chat_session_id)
                control = None
            if control is None:
                worker_module = (
                    "backend.chat_sandbox_worker.relay"
                    if persistent
                    else "backend.chat_sandbox_worker.supervisor"
                )
                process = await sandbox.exec.aio(
                    "python",
                    "-m",
                    worker_module,
                    stdout=StreamType.PIPE,
                    stderr=StreamType.PIPE,
                    timeout=(
                        self.settings.chat_persistent_sandbox_lifetime_seconds
                        if persistent
                        else round(self.settings.chat_agent_timeout_seconds + 15)
                    ),
                    workdir="/workspace",
                    text=False,
                )
                stderr_task = asyncio.create_task(drain_stderr(process.stderr))
                if persistent:
                    control = SessionControl(
                        process=process,
                        sandbox=sandbox,
                        sandbox_id=sandbox.object_id,
                        stderr_task=stderr_task,
                        reader_task=None,
                        queues={},
                        resume_id=None,
                    )
                    control.reader_task = asyncio.create_task(
                        self._read_control(control)
                    )
                    self._controls[chat_session_id] = control
            else:
                process = control.process
                stderr_task = control.stderr_task
            assert claim is not None
            running_worker = RunningWorker(
                process, request_id, claim, done=asyncio.Event()
            )
            self._processes[turn_id] = running_worker
            launch = {
                "capability": capability.token,
                "gateway_url": self.settings.chat_gateway_url,
                "session_id": str(chat_session_id),
                "turn_id": str(turn_id),
            }
            if persistent:
                launch.update(
                    {
                        "assignment_token": claim.assignment_token,
                        "worker_generation": claim.worker_generation,
                    }
                )
            run = {
                "v": 1,
                "type": "run_turn",
                "request_id": request_id,
                "chat_session_id": str(chat_session_id),
                "prompt": prompt,
                "model": model,
                "resume": resume,
            }
            if persistent:
                run.update(
                    {
                        "turn_id": str(turn_id),
                        "assignment_token": claim.assignment_token,
                        "worker_generation": claim.worker_generation,
                    }
                )
            queue: asyncio.Queue | None = None
            if persistent:
                assert control is not None
                if request_id in control.queues:
                    raise ProtocolError("Duplicate persistent request identifier")
                queue = asyncio.Queue()
                control.queues[request_id] = queue
            process.stdin.write(
                SUPERVISOR_PREFIX
                + json.dumps(launch, separators=(",", ":")).encode()
                + b"\n"
                + encode_frame(run)
            )
            await process.stdin.drain.aio()
            yield {
                "type": "_latency",
                "phase": "capability_install_ms",
                "elapsed_ms": round((time.perf_counter() - turn_started) * 1000),
            }

            async with asyncio.timeout(self.settings.chat_agent_timeout_seconds):
                if persistent:
                    assert queue is not None

                    async def persistent_events():
                        while True:
                            item = await queue.get()
                            if isinstance(item, BaseException):
                                raise item
                            if item.get("type") == "_control_failure":
                                logger.warning(
                                    "persistent worker control failed stage=%s",
                                    item.get("stage"),
                                )
                                raise SandboxError(
                                    "sandbox_worker_failed",
                                    "The persistent worker control failed",
                                    uncertain=True,
                                )
                            yield item
                            if item.get("type") == "worker_done":
                                return

                    events = persistent_events()
                else:

                    async def one_shot_events():
                        buffer = b""
                        async for chunk in process.stdout:
                            buffer += chunk
                            while b"\n" in buffer:
                                line, buffer = buffer.split(b"\n", 1)
                                if not line or not line.startswith(
                                    FRAME_PREFIX.encode()
                                ):
                                    continue
                                yield decode_frame(line)

                    events = one_shot_events()

                async for event in events:
                    if event.get("request_id") != request_id:
                        raise ProtocolError("Uncorrelated worker frame")
                    validator.accept(
                        event,
                        allow_terminal_less_stop=running_worker.cancel_requested,
                    )
                    if event["type"] == "worker_done":
                        terminal = True
                        running_worker.done.set()
                        if event.get("status") == "stopped":
                            yield {"type": "_cancelled"}
                        elif pending_terminal_event is not None:
                            yield {
                                key: value
                                for key, value in pending_terminal_event.items()
                                if key not in {"v", "request_id"}
                            }
                        break
                    if persistent and event["type"] == "_sdk_session":
                        assert control is not None
                        sdk_session_id = str(event.get("session_id") or "")
                        if (
                            control.resume_id is not None
                            and control.resume_id != sdk_session_id
                        ):
                            raise ProtocolError(
                                "SDK session changed inside persistent control"
                            )
                        control.resume_id = sdk_session_id
                    if running_worker.cancel_requested:
                        continue
                    if event["type"] == "workspace_ready":
                        sdk_dispatched = True
                        elapsed_ms = round((time.perf_counter() - turn_started) * 1000)
                        yield {
                            "type": "_latency",
                            "phase": "worker_ready_ms",
                            "elapsed_ms": elapsed_ms,
                        }
                        yield {
                            "type": "_latency",
                            "phase": "sdk_dispatch_ms",
                            "elapsed_ms": elapsed_ms,
                        }
                    if not first_worker_delta_recorded and event["type"] in {
                        "reasoning_delta",
                        "tool_call",
                        "answer_delta",
                    }:
                        first_worker_delta_recorded = True
                        yield {
                            "type": "_latency",
                            "phase": "first_worker_delta",
                            "elapsed_ms": round(
                                (time.perf_counter() - turn_started) * 1000
                            ),
                        }
                    if event["type"] in {"done", "error", "_mirror_error"}:
                        pending_terminal_event = event
                        continue
                    yield {
                        key: value
                        for key, value in event.items()
                        if key not in {"v", "request_id"}
                    }
                if not persistent:
                    await process.wait.aio()
            if not terminal:
                raise SandboxError(
                    "sandbox_worker_failed",
                    "The secure workspace worker ended unexpectedly",
                    uncertain=True,
                )
        except (TimeoutError, ProtocolError, SandboxError) as error:
            if cancelled := _cancelled_terminal_event(running_worker):
                yield cancelled
                return
            if acquisition_outcome == "pool_hit" and not sdk_dispatched:
                raise SandboxError(
                    "pool_assignment_failed",
                    "The blank workspace assignment failed",
                    uncertain=True,
                ) from error
            if isinstance(error, TimeoutError):
                raise SandboxError(
                    "sandbox_timeout", "The research run timed out", uncertain=True
                ) from error
            if isinstance(error, ProtocolError):
                raise SandboxError(
                    "sandbox_worker_failed",
                    "The worker protocol failed",
                    uncertain=True,
                ) from error
            raise
        except Exception as error:
            if cancelled := _cancelled_terminal_event(running_worker):
                yield cancelled
                return
            if acquisition_outcome == "pool_hit" and not sdk_dispatched:
                raise SandboxError(
                    "pool_assignment_failed",
                    "The blank workspace assignment failed",
                    uncertain=True,
                ) from error
            raise
        finally:
            if persistent and control is not None:
                control.queues.pop(request_id, None)
            if stderr_task and not getattr(
                self.settings, "chat_persistent_worker_enabled", False
            ):
                stderr_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await stderr_task
            self._processes.pop(turn_id, None)
            if not terminal:
                if claim is not None:
                    await self._terminate_worker(
                        chat_session_id,
                        claim,
                        failure_code=(
                            "cancelled"
                            if running_worker.cancel_requested
                            else "sandbox_worker_failed"
                        ),
                    )
                elif acquisition_outcome == "pool_hit":
                    await self.terminate(
                        chat_session_id, failure_code="pool_assignment_failed"
                    )
            elif claim is not None and self._release_worker(chat_session_id, claim):
                await self.enforce_warm_cap()

    async def cancel(self, chat_session_id: uuid.UUID, turn_id: uuid.UUID) -> bool:
        running = self._processes.get(turn_id)
        if running is None:
            return False
        running.cancel_requested = True
        process = running.process
        try:
            process.stdin.write(
                encode_frame(
                    {
                        "v": 1,
                        "type": "cancel",
                        "request_id": running.request_id,
                    }
                )
            )
            await process.stdin.drain.aio()
        except Exception:
            await self._terminate_worker(
                chat_session_id,
                running.claim,
                failure_code="cancel_control_lost",
            )
            if running.done is not None:
                running.done.set()
            return True
        try:
            async with asyncio.timeout(self.settings.chat_cancel_grace_seconds):
                if running.done is not None:
                    await running.done.wait()
                else:
                    await process.wait.aio()
        except TimeoutError:
            await self._terminate_worker(
                chat_session_id,
                running.claim,
                failure_code="cancel_timeout",
            )
        return True

    async def terminate(
        self, chat_session_id: uuid.UUID, *, failure_code: str | None = None
    ) -> None:
        sandbox_id: str | None = None
        token_hash: str | None = None
        with self.session_factory() as db, db.begin():
            lease = self._lease(db, chat_session_id, lock=True)
            if lease:
                sandbox_id = lease.modal_sandbox_id
                token_hash = self._token_hash(secrets.token_urlsafe(24))
                lease.state = "terminating"
                lease.failure_code = failure_code
                lease.lease_token_hash = token_hash
                lease.lease_expires_at = datetime.now(UTC) + timedelta(
                    seconds=self.ready_timeout_seconds + 15
                )
        if token_hash:
            self._drop_control(chat_session_id)
            await self._terminate_owned_sandbox(
                chat_session_id,
                sandbox_id=sandbox_id,
                token_hash=token_hash,
                failure_code=failure_code,
            )

    async def _terminate_owned_sandbox(
        self,
        chat_session_id: uuid.UUID,
        *,
        sandbox_id: str | None,
        token_hash: str,
        failure_code: str | None,
    ) -> None:
        if sandbox_id:
            confirmed = await self._terminate_provider_sandbox(sandbox_id)
            if getattr(self.settings, "chat_sandbox_spend_enforcement_enabled", False):
                with self.session_factory() as db, db.begin():
                    ChatSandboxSpendService(db, self.settings).terminate(
                        sandbox_id, failure_code, confirmed=confirmed
                    )
            if not confirmed:
                failure_code = "termination_uncertain"
        self._finish_owned_operation(
            chat_session_id,
            token_hash=token_hash,
            expected_state="terminating",
            expected_sandbox_id=sandbox_id,
            state="failed" if failure_code else "terminated",
            failure_code=failure_code,
            clear_sandbox=True,
        )

    async def cleanup_deleted(
        self, sandbox_id: str | None, snapshot_id: str | None
    ) -> None:
        if sandbox_id:
            self._drop_control_by_sandbox(sandbox_id)
            confirmed = await self._terminate_provider_sandbox(sandbox_id)
            if self.settings.chat_sandbox_spend_enforcement_enabled:
                with self.session_factory() as db, db.begin():
                    ChatSandboxSpendService(db, self.settings).terminate(
                        sandbox_id, "session_deleted", confirmed=confirmed
                    )
        if snapshot_id:
            await self.snapshots.delete(snapshot_id)

    async def reap_idle(self) -> int:
        cutoff = datetime.now(UTC) - timedelta(
            seconds=self.settings.chat_sandbox_warm_seconds
        )
        with self.session_factory() as db:
            ids = list(
                db.execute(
                    select(ChatSandboxLease.chat_session_id)
                    .where(
                        ChatSandboxLease.state == "idle",
                        ChatSandboxLease.last_activity_at < cutoff,
                    )
                    .order_by(ChatSandboxLease.last_activity_at)
                ).scalars()
            )
        return await self._terminate_many(ids)

    async def _terminate_many(self, chat_session_ids: list[uuid.UUID]) -> int:
        semaphore = asyncio.Semaphore(self.MAINTENANCE_CONCURRENCY)

        async def terminate_one(chat_session_id: uuid.UUID) -> bool:
            async with semaphore:
                return await self.snapshot_and_terminate(chat_session_id)

        results = await asyncio.gather(
            *(terminate_one(session_id) for session_id in chat_session_ids)
        )
        return sum(results)

    async def snapshot_and_terminate(self, chat_session_id: uuid.UUID) -> bool:
        token_hash = self._token_hash(secrets.token_urlsafe(24))
        with self.session_factory() as db, db.begin():
            lease = self._lease(db, chat_session_id, lock=True)
            if lease is None or lease.state != "idle" or not lease.modal_sandbox_id:
                return False
            sandbox_id = lease.modal_sandbox_id
            should_snapshot = bool(
                self.settings.chat_workspace_snapshots_enabled and lease.workspace_dirty
            )
            lease.state = "terminating"
            lease.lease_token_hash = token_hash
            lease.lease_expires_at = datetime.now(UTC) + timedelta(
                seconds=self.ready_timeout_seconds + 15
            )
        if should_snapshot and sandbox_id:
            try:
                sandbox = await modal.Sandbox.from_id.aio(sandbox_id)
                snapshot_id = await self.snapshots.save(sandbox, chat_session_id)
                with self.session_factory() as db, db.begin():
                    lease = self._lease(db, chat_session_id, lock=True)
                    if (
                        lease
                        and lease.state == "terminating"
                        and lease.modal_sandbox_id == sandbox_id
                        and lease.lease_token_hash == token_hash
                    ):
                        lease.workspace_snapshot_id = snapshot_id
                        lease.snapshot_image_version = (
                            self.settings.chat_modal_image_version
                        )
                        lease.snapshot_updated_at = datetime.now(UTC)
                        lease.workspace_dirty = False
            except Exception:
                # Workspace continuity is recoverable; the transcript remains
                # authoritative and the next sandbox safely starts empty.
                pass
        self._drop_control(chat_session_id)
        confirmed = await self._terminate_provider_sandbox(sandbox_id)
        if self.settings.chat_sandbox_spend_enforcement_enabled:
            with self.session_factory() as db, db.begin():
                ChatSandboxSpendService(db, self.settings).terminate(
                    sandbox_id, "snapshot_complete", confirmed=confirmed
                )
        self._finish_owned_operation(
            chat_session_id,
            token_hash=token_hash,
            expected_state="terminating",
            expected_sandbox_id=sandbox_id,
            state="terminated",
            failure_code=None,
            clear_sandbox=True,
        )
        return True

    async def enforce_warm_cap(self) -> int:
        with self.session_factory() as db:
            counted = (
                db.scalar(
                    select(func.count())
                    .select_from(ChatSandboxLease)
                    .where(
                        ChatSandboxLease.state.in_(
                            [
                                "starting",
                                "ready",
                                "idle",
                                "terminating",
                            ]
                        )
                    )
                )
                or 0
            )
            idle = list(
                db.execute(
                    select(ChatSandboxLease.chat_session_id)
                    .where(ChatSandboxLease.state == "idle")
                    .order_by(ChatSandboxLease.last_activity_at.desc())
                ).scalars()
            )
        excess = max(0, counted - self.settings.chat_sandbox_max_warm)
        evict = list(reversed(idle[-excess:])) if excess else []
        return await self._terminate_many(evict)

    async def enforce_spend_cap(self) -> dict[str, int | str]:
        """Apply the durable trip time to every worker and tagged provider orphan."""
        with self.session_factory() as db, db.begin():
            status = ChatSandboxSpendService(db, self.settings).status()
        if status["circuit_state"] != "tripped":
            return {"state": status["circuit_state"], "terminated": 0, "uncertain": 0}
        now = datetime.now(UTC)
        tripped_at = status["tripped_at"] or now
        if tripped_at.tzinfo is None:
            tripped_at = tripped_at.replace(tzinfo=UTC)
        deadline = tripped_at + timedelta(
            seconds=self.settings.chat_sandbox_drain_grace_seconds
        )
        with self.session_factory() as db:
            immediate = list(
                db.execute(
                    select(ChatSandboxLease.chat_session_id).where(
                        ChatSandboxLease.state.in_(
                            ["starting", "ready", "idle", "terminating"]
                        )
                    )
                ).scalars()
            )
            blanks = list(
                db.execute(
                    select(ChatSandboxPool.id, ChatSandboxPool.modal_sandbox_id).where(
                        ChatSandboxPool.state.in_(
                            ["starting", "blank_ready", "draining"]
                        )
                    )
                ).all()
            )

        async def terminate_budget_session(session_id: uuid.UUID) -> bool:
            await self.terminate(session_id, failure_code="chat_disabled_interrupted")
            return True

        terminated = (
            sum(
                await asyncio.gather(
                    *(terminate_budget_session(session_id) for session_id in immediate)
                )
            )
            if immediate
            else 0
        )
        for pool_id, sandbox_id in blanks:
            terminated += bool(
                await self._terminate_pool_row(
                    pool_id, sandbox_id, failure_code="chat_disabled_interrupted"
                )
            )
        remaining = (deadline - datetime.now(UTC)).total_seconds()
        if remaining > 0:
            await asyncio.sleep(
                min(remaining, self.settings.chat_sandbox_watchdog_seconds)
            )
        if datetime.now(UTC) >= deadline:
            for running in list(self._processes.values()):
                running.cancel_requested = True
                with contextlib.suppress(Exception):
                    running.process.stdin.write(
                        encode_frame(
                            {"v": 1, "type": "cancel", "request_id": running.request_id}
                        )
                    )
                    await running.process.stdin.drain.aio()
            with self.session_factory() as db, db.begin():
                db.query(ChatTurnCapability).filter(
                    ChatTurnCapability.revoked_at.is_(None)
                ).update(
                    {ChatTurnCapability.revoked_at: datetime.now(UTC)},
                    synchronize_session=False,
                )
                busy = list(
                    db.execute(
                        select(ChatSandboxLease.chat_session_id).where(
                            ChatSandboxLease.state == "busy"
                        )
                    ).scalars()
                )
            if busy:
                terminated += sum(
                    await asyncio.gather(
                        *(terminate_budget_session(session_id) for session_id in busy)
                    )
                )
        uncertain = 0
        async for sandbox in modal.Sandbox.list.aio(
            tags={"service": "pwc-chat", "environment": self.settings.environment}
        ):
            try:
                confirmed = await self._terminate_provider_sandbox(
                    sandbox.object_id, sandbox
                )
                if not confirmed:
                    raise RuntimeError("provider termination was not confirmed")
                with self.session_factory() as db, db.begin():
                    ChatSandboxSpendService(db, self.settings).terminate(
                        sandbox.object_id, "chat_disabled_interrupted", confirmed=True
                    )
                terminated += 1
            except Exception:
                uncertain += 1
                with self.session_factory() as db, db.begin():
                    ChatSandboxSpendService(db, self.settings).terminate(
                        sandbox.object_id, "termination_uncertain", confirmed=False
                    )
        with self.session_factory() as db, db.begin():
            remaining_live = (
                db.scalar(
                    select(func.count())
                    .select_from(ChatSandboxLease)
                    .where(
                        ChatSandboxLease.state.in_(
                            ["starting", "ready", "busy", "idle", "terminating"]
                        )
                    )
                )
                or 0
            ) + (
                db.scalar(
                    select(func.count())
                    .select_from(ChatSandboxPool)
                    .where(
                        ChatSandboxPool.state.in_(
                            ["starting", "blank_ready", "draining"]
                        )
                    )
                )
                or 0
            )
            ChatSandboxSpendService(db, self.settings).record_kill_sweep(
                complete=uncertain == 0 and remaining_live == 0
            )
        return {"state": "tripped", "terminated": terminated, "uncertain": uncertain}

    async def deliver_spend_alerts(self) -> int:
        """Deliver bounded, content-free circuit transitions without blocking kill sweeps."""
        from backend.models.database import ChatSandboxCircuitEvent

        with self.session_factory() as db:
            now = datetime.now(UTC)
            events = list(
                db.execute(
                    select(ChatSandboxCircuitEvent)
                    .where(
                        ChatSandboxCircuitEvent.delivery_state.in_(
                            ["pending", "retry"]
                        ),
                        ChatSandboxCircuitEvent.delivery_attempts < 5,
                        (
                            ChatSandboxCircuitEvent.next_delivery_attempt_at.is_(None)
                            | (ChatSandboxCircuitEvent.next_delivery_attempt_at <= now)
                        ),
                    )
                    .order_by(ChatSandboxCircuitEvent.created_at)
                    .limit(10)
                ).scalars()
            )
            event_ids = [event.id for event in events]
        delivered = 0
        for event_id in event_ids:
            with self.session_factory() as db, db.begin():
                event = db.execute(
                    select(ChatSandboxCircuitEvent)
                    .where(ChatSandboxCircuitEvent.id == event_id)
                    .with_for_update()
                ).scalar_one_or_none()
                if event is None or event.delivery_state not in {"pending", "retry"}:
                    continue
                event.delivery_attempts += 1
                payload = {
                    "text": (
                        f"PwC chat compute {event.severity}: {event.event_type}; "
                        f"environment={event.details.get('environment')}; cycle={event.details.get('billing_cycle')}; "
                        f"release={event.details.get('release')}; effective_microusd={event.details.get('effective_microusd')}; "
                        f"threshold_microusd={event.details.get('threshold_microusd')}; "
                        f"provider_reserve_microusd={event.details.get('remaining_provider_reserve_microusd')}; "
                        f"state={event.details.get('circuit_state')}; live={event.details.get('live_count')}; "
                        f"uncertain={event.details.get('uncertain_count')}; event_id={event.id}; "
                        f"dashboard=/cron-dashboard; runbook={self.settings.chat_sandbox_runbook_url}"
                    )
                }
            try:
                if not self.settings.chat_sandbox_slack_webhook_url:
                    raise RuntimeError("Slack webhook is not configured")
                async with httpx.AsyncClient(timeout=5) as client:
                    response = await client.post(
                        self.settings.chat_sandbox_slack_webhook_url, json=payload
                    )
                    response.raise_for_status()
            except Exception as error:
                logger.critical(
                    "chat spend alert delivery failed event_id=%s error=%s",
                    event_id,
                    type(error).__name__,
                )
                with self.session_factory() as db, db.begin():
                    event = db.get(ChatSandboxCircuitEvent, event_id)
                    if event:
                        event.delivery_state = (
                            "failed" if event.delivery_attempts >= 5 else "retry"
                        )
                        event.next_delivery_attempt_at = datetime.now(UTC) + timedelta(
                            seconds=min(300, 15 * (2**event.delivery_attempts))
                        )
                continue
            with self.session_factory() as db, db.begin():
                event = db.get(ChatSandboxCircuitEvent, event_id)
                if event:
                    event.delivery_state = "delivered"
                    event.next_delivery_attempt_at = None
                    event.delivered_at = datetime.now(UTC)
                    delivered += 1
        return delivered

    async def reconcile_spend_provider(self) -> bool:
        """Refresh the provider floor at most hourly; local metering remains authoritative."""
        now = datetime.now(UTC)
        if (
            self._last_spend_reconciliation_at
            and now - self._last_spend_reconciliation_at < timedelta(hours=1)
        ):
            return False
        self._last_spend_reconciliation_at = now
        cycle = now.date().replace(day=1)
        start = datetime(cycle.year, cycle.month, 1, tzinfo=UTC)
        try:
            items = await modal.Workspace.from_context().billing.report.aio(
                start=start, end=now, resolution="h"
            )
            dollars = sum(
                item.cost
                for item in items
                if item.description == MODAL_APP_NAME
                and item.environment_name
                in {"main", self.settings.chat_sandbox_modal_environment}
            )
            floor_microusd = round(dollars * 1_000_000)
            with self.session_factory() as db, db.begin():
                ChatSandboxSpendService(db, self.settings).reconcile_provider_floor(
                    floor_microusd, now
                )
            return True
        except Exception as error:
            logger.error(
                "chat spend provider reconciliation unavailable error=%s",
                type(error).__name__,
            )
            with self.session_factory() as db, db.begin():
                ChatSandboxSpendService(db, self.settings).reconciliation_unavailable(
                    now
                )
            return False

    async def reconcile(self) -> int:
        """Converge expired creations and provider-lost sandbox leases."""

        now = datetime.now(UTC)
        with self.session_factory() as db:
            stale_operations = list(
                db.execute(
                    select(
                        ChatSandboxLease.chat_session_id,
                        ChatSandboxLease.modal_sandbox_id,
                        ChatSandboxLease.state,
                    )
                    .join(
                        ChatSession,
                        ChatSession.id == ChatSandboxLease.chat_session_id,
                    )
                    .where(
                        (
                            (ChatSandboxLease.state == "busy")
                            & (
                                ChatSession.active_turn_expires_at.is_(None)
                                | (ChatSession.active_turn_expires_at <= now)
                            )
                        )
                        | (
                            (ChatSandboxLease.state == "terminating")
                            & (
                                ChatSandboxLease.lease_expires_at.is_(None)
                                | (ChatSandboxLease.lease_expires_at <= now)
                            )
                        )
                    )
                ).all()
            )
        repaired = 0
        for operation in stale_operations:
            # Lightweight lifecycle test doubles return the later reconcile
            # projection for every SELECT; only this query's three-column
            # projection represents a stale operation.
            if len(operation) != 3:
                continue
            session_id, sandbox_id, state = operation
            token_hash = self._token_hash(secrets.token_urlsafe(24))
            failure_code: str | None = None
            with self.session_factory() as db, db.begin():
                lease = self._lease(db, session_id, lock=True)
                session = db.execute(
                    select(ChatSession)
                    .where(ChatSession.id == session_id)
                    .with_for_update()
                ).scalar_one_or_none()
                if (
                    lease is None
                    or session is None
                    or lease.state != state
                    or lease.modal_sandbox_id != sandbox_id
                ):
                    continue
                current = datetime.now(UTC)
                if state == "busy":
                    active_expiry = session.active_turn_expires_at
                    if (
                        active_expiry is not None
                        and self._as_utc(active_expiry) > current
                    ):
                        continue
                    failure_code = "sandbox_worker_failed"
                else:
                    lease_expiry = lease.lease_expires_at
                    if (
                        lease_expiry is not None
                        and self._as_utc(lease_expiry) > current
                    ):
                        continue
                    failure_code = lease.failure_code
                lease.state = "terminating"
                lease.failure_code = failure_code
                lease.lease_token_hash = token_hash
                lease.lease_expires_at = current + timedelta(
                    seconds=self.ready_timeout_seconds + 15
                )
                lease.updated_at = current
            self._drop_control(session_id)
            await self._terminate_owned_sandbox(
                session_id,
                sandbox_id=sandbox_id,
                token_hash=token_hash,
                failure_code=failure_code,
            )
            repaired += 1

        with self.session_factory() as db:
            candidates = list(
                db.execute(
                    select(
                        ChatSandboxLease.chat_session_id,
                        ChatSandboxLease.modal_sandbox_id,
                        ChatSandboxLease.state,
                        ChatSandboxLease.lease_token_hash,
                    ).where(
                        (ChatSandboxLease.state == "starting")
                        & (
                            ChatSandboxLease.lease_expires_at.is_(None)
                            | (ChatSandboxLease.lease_expires_at < datetime.now(UTC))
                        )
                        | ChatSandboxLease.state.in_(["ready", "idle"])
                    )
                ).all()
            )
        for session_id, sandbox_id, state, token_hash in candidates:
            if state == "starting":
                if token_hash and self._mark_start_failed(
                    session_id, token_hash, "sandbox_start_failed"
                ):
                    repaired += 1
                continue
            if not sandbox_id:
                with self.session_factory() as db, db.begin():
                    lease = self._lease(db, session_id, lock=True)
                    if (
                        lease
                        and lease.state == state
                        and lease.modal_sandbox_id is None
                    ):
                        lease.state = "failed"
                        lease.failure_code = "sandbox_lost"
                        lease.updated_at = datetime.now(UTC)
                        repaired += 1
                continue
            try:
                sandbox = await modal.Sandbox.from_id.aio(sandbox_id)
                alive = await sandbox.poll.aio() is None
            except Exception:
                alive = False
            if not alive:
                with self.session_factory() as db, db.begin():
                    lease = self._lease(db, session_id, lock=True)
                    if (
                        lease
                        and lease.state == state
                        and lease.modal_sandbox_id == sandbox_id
                    ):
                        lease.modal_sandbox_id = None
                        lease.state = "failed"
                        lease.failure_code = "sandbox_lost"
                        lease.updated_at = datetime.now(UTC)
                        repaired += 1
        return repaired

    async def expire_inactive_snapshots(self) -> int:
        cutoff = datetime.now(UTC) - timedelta(
            days=self.settings.chat_workspace_snapshot_inactivity_days
        )
        with self.session_factory() as db:
            rows = list(
                db.execute(
                    select(
                        ChatSandboxLease.chat_session_id,
                        ChatSandboxLease.workspace_snapshot_id,
                    )
                    .join(
                        ChatSession,
                        ChatSession.id == ChatSandboxLease.chat_session_id,
                    )
                    .where(
                        ChatSandboxLease.workspace_snapshot_id.is_not(None),
                        ChatSession.updated_at < cutoff,
                    )
                ).all()
            )
        expired = 0
        for session_id, snapshot_id in rows:
            if snapshot_id:
                await self.snapshots.delete(snapshot_id)
            with self.session_factory() as db, db.begin():
                lease = self._lease(db, session_id, lock=True)
                if lease and lease.workspace_snapshot_id == snapshot_id:
                    lease.workspace_snapshot_id = None
                    lease.snapshot_image_version = None
                    lease.snapshot_updated_at = None
                    expired += 1
        return expired
