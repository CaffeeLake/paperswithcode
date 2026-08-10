"""Durable Modal sandbox lifecycle and framed worker transport."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import secrets
import time
import uuid
from collections.abc import AsyncIterator, Callable
from datetime import UTC, date, datetime, timedelta

import httpx
import modal
from modal.client import _Client
from modal.exception import Error as ModalError
from modal.exception import NotFoundError
from modal_proto import api_pb2
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from websockets.asyncio.client import connect as websocket_connect

from backend.chat_sandbox_worker.contract import MODAL_APP_NAME
from backend.chat_sandbox_worker.protocol import ProtocolError
from backend.config import Settings
from backend.database.connection import db_manager
from backend.models.database import (
    ChatSandboxComputeInterval,
    ChatSandboxLease,
    ChatSandboxPool,
    ChatSession,
    ChatTurnCapability,
)
from backend.services.chat_capability_service import IssuedCapability
from backend.services.chat_sandbox_capacity_repository import (
    CapacityUnavailable,
    ChatSandboxCapacityRepository,
    EvictionRequired,
    LeaseDecisionChanged,
    RecoveryRequired,
    ReuseLease,
    StartAcquired,
    WaitForLease,
    lock_capacity,
)
from backend.services.chat_sandbox_provider import (
    ModalSandboxProviderAdapter,
    SandboxError,
    SandboxProvider,
    resolve_modal_image as _resolve_modal_image,
    sandbox_environment as _sandbox_environment,
)
from backend.services.chat_sandbox_pool_repository import (
    MODAL_CPU_USD_PER_CORE_SECOND,
    MODAL_MEMORY_USD_PER_GIB_SECOND,
    BlankPoolClaim,
    ChatSandboxPoolRepository,
    PoolEvictionRequired,
    PoolLandingOutcome,
    PoolReservationUnavailable,
    PoolStartReservation,
    PoolTerminationClaim,
    PoolTerminationFinishOutcome,
)
from backend.services.chat_sandbox_spend_service import (
    ChatComputeDisabled,
    ChatSandboxSpendService,
)
from backend.services.chat_sandbox_state_repository import (
    ChatSandboxStateRepository,
    LeaseStateClaim,
    LeaseUnavailable,
    SnapshotClaim,
    StartClaim,
    TerminationClaim,
    WorkerClaim,
    WorkerGenerationUnavailable,
)
from backend.services.chat_sandbox_worker_transport import (
    ChatSandboxWorkerTransport,
    RunningWorker,
    SessionControl,
    WorkerCancelStatus,
    WorkerTurnDispatchOutcome,
    WorkerTurnExecution,
    WorkerTurnMilestone,
    WorkerTurnMode,
    WorkerTurnRequest,
)

logger = logging.getLogger(__name__)

POOL_MAINTENANCE_LOCK_NAME = "chat-sandbox-pool-maintenance-v1"
POOL_TERMINAL_RETENTION_DAYS = 35
POOL_CLEANUP_BATCH_SIZE = 100
POOL_ACCOUNTING_SAFETY_SECONDS = 120
POOL_LOCAL_HEALTH_MAX_AGE_SECONDS = 15


async def resolve_modal_image(image_reference: str):
    """Compatibility export for qualification scripts and existing tests."""

    return await _resolve_modal_image(image_reference)


def sandbox_environment(settings: Settings) -> dict[str, str]:
    """Compatibility export for the provider worker environment."""

    return _sandbox_environment(settings)


async def _connect_provider_websocket(*args, **kwargs):
    """Resolve the legacy monkeypatch seam when the connection is opened."""

    return await websocket_connect(*args, **kwargs)


async def create_isolated_sandbox(
    settings: Settings,
    *,
    name: str,
    tags: dict[str, str],
    worker_generation: str | None = None,
):
    """Compatibility export backed by the provider adapter."""

    provider = ModalSandboxProviderAdapter(
        settings,
        image_resolver=resolve_modal_image,
        websocket_connector=_connect_provider_websocket,
    )
    return await provider.create(
        name=name,
        tags=tags,
        worker_generation=worker_generation,
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


class SandboxCleanupUnverified(RuntimeError):
    """The application could not confirm deletion of all provider state."""


class SandboxSessionManager:
    MAINTENANCE_CONCURRENCY = 8

    def __init__(
        self,
        settings: Settings,
        *,
        session_factory: Callable[[], Session] | None = None,
        snapshot_provider: WorkspaceSnapshotProvider | None = None,
        sandbox_provider: SandboxProvider | None = None,
        state_repository: ChatSandboxStateRepository | None = None,
        capacity_repository: ChatSandboxCapacityRepository | None = None,
        pool_repository: ChatSandboxPoolRepository | None = None,
        pool_maintenance_owner: Callable[[], bool] | None = None,
    ):
        self.settings = settings
        self.session_factory = session_factory or db_manager.session_local
        self._sandbox_provider = sandbox_provider
        self._sandbox_state = state_repository
        self._sandbox_capacity = capacity_repository
        self._sandbox_pool = pool_repository
        self.pool_maintenance_owner = pool_maintenance_owner or (lambda: True)
        self.snapshots = snapshot_provider or WorkspaceSnapshotProvider(
            ttl_days=settings.chat_workspace_snapshot_inactivity_days
        )
        self._worker_transport_state = ChatSandboxWorkerTransport(
            self._provider_adapter()
        )
        self._background_tasks: set[asyncio.Task] = set()
        if settings.chat_workspace_snapshots_enabled and not self.snapshots.supported:
            raise SandboxError(
                "snapshot_unsupported",
                "Configured workspace snapshots require a Directory Snapshot provider",
            )

    def _provider_adapter(self) -> SandboxProvider:
        provider = getattr(self, "_sandbox_provider", None)
        if provider is not None:
            return provider
        return ModalSandboxProviderAdapter(
            self.settings,
            image_resolver=resolve_modal_image,
            websocket_connector=_connect_provider_websocket,
        )

    def _worker_transport(self) -> ChatSandboxWorkerTransport:
        transport = getattr(self, "_worker_transport_state", None)
        if transport is None:
            transport = ChatSandboxWorkerTransport(self._provider_adapter())
            self._worker_transport_state = transport
        return transport

    @property
    def _processes(self) -> dict[uuid.UUID, RunningWorker]:
        """Compatibility view for established manager tests and callers."""

        return self._worker_transport().processes

    @_processes.setter
    def _processes(self, processes: dict[uuid.UUID, RunningWorker]) -> None:
        self._worker_transport().processes = processes

    @property
    def _controls(self) -> dict[uuid.UUID, SessionControl]:
        """Compatibility view; transport owns all production mutations."""

        return self._worker_transport().session_controls

    @_controls.setter
    def _controls(self, controls: dict[uuid.UUID, SessionControl]) -> None:
        self._worker_transport().session_controls = controls

    @property
    def _blank_controls(self) -> dict[str, SessionControl]:
        return self._worker_transport().blank_controls

    @_blank_controls.setter
    def _blank_controls(self, controls: dict[str, SessionControl]) -> None:
        self._worker_transport().blank_controls = controls

    @property
    def _blank_health_at(self) -> dict[str, float]:
        return self._worker_transport().blank_health_at

    @_blank_health_at.setter
    def _blank_health_at(self, checked_at: dict[str, float]) -> None:
        self._worker_transport().blank_health_at = checked_at

    def _state_repository(self) -> ChatSandboxStateRepository:
        repository = getattr(self, "_sandbox_state", None)
        if repository is None:
            repository = ChatSandboxStateRepository(self.settings)
            self._sandbox_state = repository
        return repository

    def _capacity_repository(self) -> ChatSandboxCapacityRepository:
        repository = getattr(self, "_sandbox_capacity", None)
        if repository is None:
            repository = ChatSandboxCapacityRepository(
                self.settings,
                self._state_repository(),
                capacity_locker=self._lock_capacity,
                start_locker=self._lock_start_claim,
                lease_loader=self._lease,
            )
            self._sandbox_capacity = repository
        return repository

    def _pool_repository(self) -> ChatSandboxPoolRepository:
        repository = getattr(self, "_sandbox_pool", None)
        if repository is None:
            repository = ChatSandboxPoolRepository(
                self.settings,
                capacity_locker=self._lock_capacity,
                lease_loader=self._lease,
            )
            self._sandbox_pool = repository
        return repository

    async def _create_provider_sandbox(
        self,
        *,
        name: str,
        tags: dict[str, str],
        worker_generation: str | None = None,
    ) -> object:
        provider = getattr(self, "_sandbox_provider", None)
        if provider is not None:
            return await provider.create(
                name=name,
                tags=tags,
                worker_generation=worker_generation,
            )
        return await create_isolated_sandbox(
            self.settings,
            name=name,
            tags=tags,
            worker_generation=worker_generation,
        )

    async def _terminate_provider_sandbox(
        self, sandbox_id: str, sandbox: object | None = None
    ) -> bool:
        """Wait for provider confirmation whenever spend enforcement is active."""
        return await self._provider_adapter().terminate(sandbox_id, sandbox)

    @staticmethod
    def _billing_month(now: datetime) -> date:
        return ChatSandboxPoolRepository.billing_month(now)

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
        return lock_capacity(db, wait=wait)

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
        return self._pool_repository().finalize_cost(row, now)

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
                    (
                        self._finalize_pool_cost(row, now)[1]
                        if row.state in {"starting", "blank_ready", "draining"}
                        else float(row.estimated_blank_cost_usd)
                    )
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
        if not self.blank_pool_enabled or not self.pool_maintenance_owner():
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
            transport = self._worker_transport()
            control = transport.blank_control(sandbox_id)
            if control is not None:
                if control.sandbox_id != sandbox_id:
                    return None
                checked_at = transport.blank_health_checked_at(sandbox_id)
                if (
                    checked_at is not None
                    and time.monotonic() - checked_at
                    <= POOL_LOCAL_HEALTH_MAX_AGE_SECONDS
                ):
                    return control.sandbox
                if await self._ping_control(control, worker_generation):
                    if transport.mark_blank_healthy(
                        sandbox_id,
                        expected=control,
                        checked_at=time.monotonic(),
                    ):
                        return control.sandbox
                    replacement = transport.blank_control(sandbox_id)
                    replacement_checked_at = transport.blank_health_checked_at(
                        sandbox_id
                    )
                    if (
                        replacement is not None
                        and replacement_checked_at is not None
                        and time.monotonic() - replacement_checked_at
                        <= POOL_LOCAL_HEALTH_MAX_AGE_SECONDS
                    ):
                        return replacement.sandbox
                return None
            provider = self._provider_adapter()
            sandbox = await provider.resolve(sandbox_id)
            if await provider.poll(sandbox) is not None:
                return None
            healthy = await provider.health(
                sandbox,
                persistent=True,
                worker_generation=worker_generation,
            )
            return sandbox if healthy else None
        except Exception:
            return None

    async def _start_persistent_control(
        self, sandbox, worker_generation: str
    ) -> SessionControl:
        return await self._worker_transport().open_persistent_control(
            sandbox, worker_generation
        )

    async def _ping_control(
        self, control: SessionControl, worker_generation: str
    ) -> bool:
        return await self._worker_transport().ping(control, worker_generation)

    async def _terminate_pool_row(
        self,
        pool_id: uuid.UUID,
        sandbox_id: str | None,
        *,
        failure_code: str | None,
    ) -> bool:
        now = datetime.now(UTC)
        claim = None
        with self.session_factory() as db, db.begin():
            claim = self._pool_repository().claim_termination(
                db,
                pool_id,
                sandbox_id,
                failure_code=failure_code,
                now=now,
                stale_draining_before=now
                - timedelta(seconds=self.pool_termination_claim_timeout_seconds),
            )
        if claim is None:
            return False
        return await self._terminate_claimed_pool_row(claim)

    async def _terminate_claimed_pool_row(
        self,
        claim: PoolTerminationClaim,
    ) -> bool:
        confirmed = True
        if claim.sandbox_id:
            self._drop_blank_control(claim.sandbox_id)
            confirmed = await self._terminate_provider_sandbox(claim.sandbox_id)
        now = datetime.now(UTC)
        with self.session_factory() as db, db.begin():
            outcome = self._pool_repository().finish_termination(
                db,
                claim,
                confirmed=confirmed,
                now=now,
            )
            if (
                outcome is PoolTerminationFinishOutcome.FINISHED
                and claim.sandbox_id
                and getattr(
                    self.settings,
                    "chat_sandbox_spend_enforcement_enabled",
                    False,
                )
            ):
                ChatSandboxSpendService(db, self.settings).terminate(
                    claim.sandbox_id,
                    claim.failure_code,
                    confirmed=confirmed,
                )
        return outcome is PoolTerminationFinishOutcome.FINISHED

    async def _terminate_claimed_pool_rows(
        self,
        claims: list[PoolTerminationClaim],
    ) -> int:
        semaphore = asyncio.Semaphore(self.pool_termination_concurrency)

        async def terminate_one(claim: PoolTerminationClaim) -> bool:
            async with semaphore:
                return await self._terminate_claimed_pool_row(claim)

        results = await asyncio.gather(*(terminate_one(claim) for claim in claims))
        return sum(results)

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
        pool = self._pool_repository()
        compatibility = pool.compatibility()
        # app_release_id is audit provenance, not worker identity. Rolling deploys
        # may reuse an unassigned blank when its immutable worker and resources
        # still match; assigned leases remain scoped to their originating chat.
        with self.session_factory() as db:
            candidates = pool.list_claim_candidates(
                db,
                compatibility,
                minimum_expires_at=minimum_expiry,
                limit=self.settings.chat_blank_pool_max,
            )
        for candidate in candidates:
            if not candidate.sandbox_id:
                await self._terminate_pool_row(
                    candidate.pool_id, None, failure_code="sandbox_lost"
                )
                continue
            sandbox = await self._pool_sandbox_health(
                candidate.sandbox_id,
                candidate.worker_generation,
            )
            if sandbox is None:
                await self._terminate_pool_row(
                    candidate.pool_id,
                    candidate.sandbox_id,
                    failure_code="sandbox_lost",
                )
                continue
            local_control = self._worker_transport().blank_control(candidate.sandbox_id)
            claim: BlankPoolClaim | None = None
            now = datetime.now(UTC)
            with self.session_factory() as db:
                spend = None
                availability_assertion = None
                if getattr(
                    self.settings, "chat_sandbox_spend_enforcement_enabled", False
                ):
                    spend = ChatSandboxSpendService(db, self.settings)

                    def availability_assertion() -> None:
                        spend.assert_available(
                            now,
                            capacity_locked=True,
                        )

                    try:
                        claim = pool.claim_blank(
                            db,
                            candidate,
                            chat_session_id,
                            compatibility,
                            minimum_expires_at=now
                            + timedelta(
                                seconds=self.settings.chat_blank_pool_min_remaining_seconds
                            ),
                            now=now,
                            availability_assertion=availability_assertion,
                        )
                    except ChatComputeDisabled as error:
                        db.commit()
                        raise SandboxError(error.code, str(error)) from error
                else:
                    claim = pool.claim_blank(
                        db,
                        candidate,
                        chat_session_id,
                        compatibility,
                        minimum_expires_at=now
                        + timedelta(
                            seconds=self.settings.chat_blank_pool_min_remaining_seconds
                        ),
                        now=now,
                    )
                if claim is not None:
                    if spend is not None:
                        spend.claim(
                            claim.sandbox_id,
                            chat_session_id,
                            now,
                        )
                db.commit()
            if claim is not None:
                if local_control is not None:
                    self._worker_transport().promote_blank_control(
                        claim.sandbox_id,
                        chat_session_id,
                        expected=local_control,
                    )
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
            and self.pool_maintenance_owner()
        ):
            return 0
        now = datetime.now(UTC)
        reservation: PoolStartReservation | None = None
        eviction: PoolEvictionRequired | None = None
        with self.session_factory() as db, db.begin():
            if not self._lock_pool_maintenance(db):
                return 0
            interval_reserver = None
            if getattr(self.settings, "chat_sandbox_spend_enforcement_enabled", False):
                spend = ChatSandboxSpendService(db, self.settings)

                def interval_reserver(worker_generation: str) -> uuid.UUID:
                    return spend.reserve_interval(
                        origin="blank_pool",
                        worker_generation=worker_generation,
                        now=now,
                        capacity_locked=True,
                    )

            try:
                outcome = self._pool_repository().reserve_starting_blank(
                    db,
                    now=now,
                    interval_reserver=interval_reserver,
                )
            except ChatComputeDisabled:
                return 0
            if isinstance(outcome, PoolStartReservation):
                reservation = outcome
            elif isinstance(outcome, PoolEvictionRequired):
                eviction = outcome
            elif isinstance(outcome, PoolReservationUnavailable):
                return 0
        if eviction is not None:
            if await self.snapshot_and_terminate(eviction.chat_session_id):
                return await self.replenish_pool()
            return 0
        if reservation is None:
            return 0
        pool_id = reservation.pool_id
        worker_generation = reservation.worker_generation
        interval_id = reservation.interval_id
        try:
            sandbox = await self._create_provider_sandbox(
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
            control = await self._start_persistent_control(sandbox, worker_generation)
            if not await self._ping_control(control, worker_generation):
                raise SandboxError(
                    "sandbox_worker_not_ready",
                    "Persistent blank worker health check failed",
                )
            self._worker_transport().register_blank_control(
                sandbox.object_id,
                control,
                checked_at=time.monotonic(),
            )
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
        now = datetime.now(UTC)
        with self.session_factory() as db, db.begin():
            landing = self._pool_repository().land_provider_creation(
                db,
                reservation,
                sandbox_id,
                now=now,
            )
            if landing is PoolLandingOutcome.LANDED and interval_id is not None:
                ChatSandboxSpendService(db, self.settings).provider_created(
                    interval_id,
                    sandbox_id,
                    now,
                )
        if landing is not PoolLandingOutcome.LANDED:
            self._drop_blank_control(sandbox_id)
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
                await self._link_provider_pool_interval(sandbox)
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

    async def _link_provider_pool_interval(self, sandbox: object) -> bool:
        """Recover a pool creation race from immutable provider tags."""

        try:
            tags = await self._provider_adapter().get_tags(sandbox)
            pool_id = uuid.UUID(str(tags["pool_id"]))
        except (AttributeError, KeyError, ModalError, TypeError, ValueError):
            return False
        with self.session_factory() as db, db.begin():
            pool = db.get(ChatSandboxPool, pool_id)
            if (
                pool is None
                or tags.get("pool") != "blank"
                or tags.get("release") != pool.app_release_id
                or tags.get("image") != pool.image_version
                or tags.get("contract") != pool.worker_contract_version
            ):
                return False
            interval = db.execute(
                select(ChatSandboxComputeInterval)
                .where(
                    ChatSandboxComputeInterval.environment == self.settings.environment,
                    ChatSandboxComputeInterval.worker_generation
                    == pool.worker_generation,
                )
                .with_for_update()
            ).scalar_one_or_none()
            if interval is None or interval.modal_sandbox_id not in {
                None,
                sandbox.object_id,
            }:
                return False
            ChatSandboxSpendService(db, self.settings).provider_created(
                interval.id,
                sandbox.object_id,
            )
            return True

    async def _listed_pool_sandboxes(self):
        async for sandbox in self._provider_adapter().iter_sandboxes(
            tags={"service": "pwc-chat", "pool": "blank"},
        ):
            yield sandbox

    async def maintain_pool(self) -> dict[str, int]:
        """Drain stale blanks, reconcile provider loss, and replenish safely."""

        if not self.pool_maintenance_owner():
            return {
                "drained": 0,
                "lost": 0,
                "orphaned": 0,
                "abandoned": 0,
                "cleaned": 0,
                "replenished": 0,
            }
        enabled = self.blank_pool_enabled
        now = datetime.now(UTC)
        drain: list[PoolTerminationClaim] = []
        health_candidates: list[tuple[uuid.UUID, str, str]] = []
        budget_blocked = not enabled
        termination_concurrency = self.pool_termination_concurrency
        with self.session_factory() as db, db.begin():
            if not self._lock_pool_maintenance(db):
                return {
                    "drained": 0,
                    "lost": 0,
                    "orphaned": 0,
                    "abandoned": 0,
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
                # Preserve a compatible unassigned worker across app-only releases.
                # Its creator release remains recorded on the pool row for audit.
                incompatible = (
                    row.image_version != self.settings.chat_modal_image_version
                    or row.worker_contract_version
                    != self.settings.chat_worker_contract_version
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
                    if len(drain) >= termination_concurrency:
                        continue
                    claim = self._pool_repository().claim_termination(
                        db,
                        row.id,
                        row.modal_sandbox_id,
                        failure_code=failure_code,
                        now=now,
                        stale_draining_before=now
                        - timedelta(
                            seconds=self.pool_termination_claim_timeout_seconds
                        ),
                        capacity_locked=True,
                    )
                    if claim is not None:
                        drain.append(claim)
                elif row.state == "blank_ready" and row.modal_sandbox_id:
                    health_candidates.append(
                        (row.id, row.modal_sandbox_id, row.worker_generation)
                    )
        drained = await self._terminate_claimed_pool_rows(drain)
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
                        ChatSandboxPool.worker_generation == worker_generation,
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
        abandoned = 0
        if self.settings.chat_sandbox_spend_enforcement_enabled:
            with self.session_factory() as db, db.begin():
                abandoned = ChatSandboxSpendService(
                    db, self.settings
                ).abort_abandoned_pool_reservations()
            if abandoned:
                logger.info(
                    "chat blank pool abandoned reservations released count=%d",
                    abandoned,
                )
        replenished = 0 if budget_blocked else await self.replenish_pool()
        return {
            "drained": drained,
            "lost": lost,
            "orphaned": orphaned,
            "abandoned": abandoned,
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
    def pool_termination_claim_timeout_seconds(self) -> float:
        return (
            self.ready_timeout_seconds
            + self.settings.chat_sandbox_termination_grace_seconds
            + 15
        )

    @property
    def pool_termination_concurrency(self) -> int:
        configured_max = self.settings.chat_blank_pool_max or 1
        return min(
            self.MAINTENANCE_CONCURRENCY,
            self.settings.chat_blank_pool_refill_concurrency,
            configured_max,
        )

    @property
    def blank_pool_enabled(self) -> bool:
        return bool(
            getattr(self.settings, "chat_blank_pool_enabled", False)
            and getattr(self.settings, "chat_sandbox_admission_enabled", True)
        )

    async def validate_image_reference(self) -> None:
        if self.settings.chat_sandbox_spend_enforcement_enabled:
            actual_environment = os.environ.get("MODAL_ENVIRONMENT", "")
            if actual_environment != self.settings.chat_sandbox_modal_environment:
                raise SandboxError(
                    "sandbox_identity_unverified",
                    "The sandbox provider Environment does not match deployment policy",
                )
            client = await _Client.from_env()
            try:
                token = await client.stub.TokenInfoGet(api_pb2.TokenInfoGetRequest())
                if self.settings.chat_sandbox_provider_mode == "starter_workspace":
                    if (
                        token.WhichOneof("identity") != "user_identity"
                        or token.workspace_name
                        != self.settings.chat_sandbox_modal_workspace
                        or token.user_identity.username
                        != self.settings.chat_sandbox_modal_owner_username
                    ):
                        raise SandboxError(
                            "sandbox_identity_unverified",
                            "The configured personal Workspace identity does not match deployment policy",
                        )
                elif token.WhichOneof("identity") != "service_user_identity":
                    raise SandboxError(
                        "sandbox_identity_unverified",
                        "A restricted Environment service identity is required",
                    )
                else:
                    service_user = token.service_user_identity.service_user_name
                    environment = modal.Environment.from_name(
                        self.settings.chat_sandbox_modal_environment
                    )
                    members = await environment.members.list.aio()
                    if members["service_users"].get(service_user) != "contributor":
                        raise SandboxError(
                            "sandbox_identity_unverified",
                            "The service identity is not scoped to the chat Environment",
                        )
                    budget = await client.stub.EnvironmentGetBudget(
                        api_pb2.EnvironmentGetBudgetRequest(
                            environment_id=environment.object_id
                        )
                    )
                    configured_budget_microusd = (
                        round(budget.cycle_budget_dollars * 1_000_000)
                        if budget.HasField("cycle_budget_dollars")
                        else None
                    )
                    if (
                        configured_budget_microusd
                        != self.settings.chat_sandbox_environment_cap_microusd
                    ):
                        raise SandboxError(
                            "sandbox_budget_unverified",
                            "The provider Environment budget does not match deployment policy",
                        )
                    other_environment = (
                        "pwc-chat-production"
                        if self.settings.environment == "staging"
                        else "pwc-chat-staging"
                    )
                    try:
                        other_members = await modal.Environment.from_name(
                            other_environment
                        ).members.list.aio()
                    except NotFoundError:
                        other_members = {"service_users": {}}
                    if service_user in other_members["service_users"]:
                        raise SandboxError(
                            "sandbox_identity_unverified",
                            "The service identity must not access the other chat Environment",
                        )
            finally:
                await client._close()
        try:
            await modal.App.lookup.aio(MODAL_APP_NAME, create_if_missing=False)
            await resolve_modal_image(self.settings.chat_modal_image_version)
        except Exception as error:
            raise SandboxError(
                "sandbox_image_unresolved",
                "The pinned sandbox image could not be resolved",
            ) from error

    def _lease(self, db: Session, chat_session_id: uuid.UUID, *, lock: bool):
        return self._state_repository().load_lease(db, chat_session_id, lock=lock)

    @staticmethod
    def _lock_start_claim(db: Session, chat_session_id: uuid.UUID) -> None:
        ChatSandboxStateRepository.lock_start_claim(db, chat_session_id)

    @staticmethod
    def _token_hash(token: str) -> str:
        return ChatSandboxStateRepository.token_hash(token)

    async def _recover_acquisition(
        self,
        chat_session_id: uuid.UUID,
        recovery: RecoveryRequired,
        sandbox: object | None = None,
    ) -> bool:
        """Terminate and account for one committed recovery claim."""

        claim = recovery.claim
        if claim.sandbox_id is None:  # pragma: no cover - recovery requires an ID
            raise LeaseDecisionChanged
        self._drop_control(chat_session_id)
        confirmed = (
            await self._terminate_provider_sandbox(claim.sandbox_id)
            if sandbox is None
            else await self._terminate_provider_sandbox(claim.sandbox_id, sandbox)
        )
        if getattr(
            self.settings,
            "chat_sandbox_spend_enforcement_enabled",
            False,
        ):
            with self.session_factory() as db, db.begin():
                ChatSandboxSpendService(db, self.settings).terminate(
                    claim.sandbox_id,
                    claim.failure_code,
                    confirmed=confirmed,
                )
        if not confirmed:
            return False
        with self.session_factory() as db, db.begin():
            self._capacity_repository().finish_recovery(
                db,
                chat_session_id,
                claim=claim,
                now=datetime.now(UTC),
            )
        return True

    async def _cleanup_failed_start(
        self,
        chat_session_id: uuid.UUID,
        claim: StartClaim,
        *,
        interval_id: uuid.UUID | None,
        sandbox: object | None,
        failure_code: str,
    ) -> None:
        """Release exactly the claimed lease, reservation, and created provider."""

        self._fail_start_claim(chat_session_id, claim, failure_code)
        if sandbox is None:
            if interval_id is not None:
                with self.session_factory() as db, db.begin():
                    ChatSandboxSpendService(db, self.settings).abort_reservation(
                        interval_id,
                        failure_code,
                    )
            return

        sandbox_id = sandbox.object_id
        confirmed = await self._terminate_provider_sandbox(sandbox_id, sandbox)
        if interval_id is not None:
            with self.session_factory() as db, db.begin():
                spend = ChatSandboxSpendService(db, self.settings)
                spend.provider_created(interval_id, sandbox_id)
                spend.terminate(
                    sandbox_id,
                    failure_code,
                    confirmed=confirmed,
                )

    async def ensure_ready(
        self,
        chat_session_id: uuid.UUID,
        *,
        allow_pool: bool = False,
        pool_miss: bool = False,
        pool_lookup_ms: int | None = None,
        budget_prechecked: bool = False,
    ) -> tuple[object, int, bool, str, int | None]:
        started = time.perf_counter()
        if not budget_prechecked and getattr(
            self.settings, "chat_sandbox_spend_enforcement_enabled", False
        ):
            with self.session_factory() as db:
                try:
                    ChatSandboxSpendService(db, self.settings).assert_available()
                except ChatComputeDisabled as error:
                    db.commit()
                    raise SandboxError(error.code, str(error)) from error
                db.commit()
        if allow_pool:
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
        while claim is None:
            creation_token = secrets.token_urlsafe(24)
            next_generation = secrets.token_hex(16)
            now = datetime.now(UTC)
            acquisition = None
            budget_rejection: ChatComputeDisabled | None = None
            try:
                with self.session_factory() as db, db.begin():
                    reserve_interval: Callable[[str], uuid.UUID] | None = None
                    if getattr(
                        self.settings,
                        "chat_sandbox_spend_enforcement_enabled",
                        False,
                    ):
                        spend = ChatSandboxSpendService(db, self.settings)

                        def reserve_direct_interval(generation: str) -> uuid.UUID:
                            return spend.reserve_interval(
                                origin="direct",
                                worker_generation=generation,
                                chat_session_id=chat_session_id,
                                now=now,
                                capacity_locked=True,
                            )

                        reserve_interval = reserve_direct_interval

                    try:
                        acquisition = self._capacity_repository().acquire(
                            db,
                            chat_session_id,
                            creation_token=creation_token,
                            worker_generation=next_generation,
                            now=now,
                            ready_timeout_seconds=self.ready_timeout_seconds,
                            reserve_interval=reserve_interval,
                        )
                    except ChatComputeDisabled as error:
                        # Committing here preserves the durable circuit trip; the
                        # repository has not changed the lease before reservation.
                        budget_rejection = error
            except LeaseDecisionChanged:
                # Any reservation and repair from this attempt rolled back with
                # the transaction. Reselect the now-current exact lease state.
                continue
            if budget_rejection is not None:
                raise SandboxError(
                    budget_rejection.code, str(budget_rejection)
                ) from budget_rejection
            assert acquisition is not None
            if isinstance(acquisition, ReuseLease):
                await self.enforce_warm_cap()
                control = self._worker_transport().session_control(chat_session_id)
                if (
                    getattr(
                        self.settings,
                        "chat_persistent_worker_enabled",
                        False,
                    )
                    and control is not None
                    and control.sandbox_id == acquisition.sandbox_id
                ):
                    return (
                        control.sandbox,
                        round((time.perf_counter() - started) * 1000),
                        False,
                        "reused_session",
                        pool_lookup_ms,
                    )

                sandbox = None
                try:
                    provider = self._provider_adapter()
                    sandbox = await provider.resolve(acquisition.sandbox_id)
                    if await provider.poll(sandbox) is None and await provider.health(
                        sandbox,
                        persistent=bool(
                            getattr(
                                self.settings,
                                "chat_persistent_worker_enabled",
                                False,
                            )
                        ),
                        worker_generation=acquisition.worker_generation,
                    ):
                        return (
                            sandbox,
                            round((time.perf_counter() - started) * 1000),
                            False,
                            "reused_session",
                            pool_lookup_ms,
                        )
                except Exception:
                    pass

                try:
                    with self.session_factory() as db, db.begin():
                        recovery = self._capacity_repository().claim_reuse_recovery(
                            db,
                            chat_session_id,
                            acquisition,
                            now=datetime.now(UTC),
                            ready_timeout_seconds=self.ready_timeout_seconds,
                        )
                except LeaseDecisionChanged:
                    continue
                if await self._recover_acquisition(
                    chat_session_id,
                    recovery,
                    sandbox,
                ):
                    continue
                while time.monotonic() < deadline:
                    await asyncio.sleep(min(0.05, max(0, deadline - time.monotonic())))
                raise SandboxError(
                    "sandbox_capacity",
                    "Secure workspace capacity is temporarily full",
                )
            if isinstance(acquisition, StartAcquired):
                claim = acquisition.claim
                interval_id = acquisition.interval_id
                break
            if isinstance(acquisition, EvictionRequired):
                if await self.snapshot_and_terminate(acquisition.chat_session_id):
                    continue
                if time.monotonic() >= deadline:
                    raise SandboxError(
                        "sandbox_capacity",
                        "Secure workspace capacity is temporarily full",
                    )
                await asyncio.sleep(0.05)
                continue
            if isinstance(acquisition, WaitForLease):
                if time.monotonic() >= deadline:
                    if acquisition.state == "terminating":
                        raise SandboxError(
                            "sandbox_capacity",
                            "Secure workspace capacity is temporarily full",
                        )
                    raise SandboxError(
                        "sandbox_timeout", "Secure workspace startup timed out"
                    )
                await asyncio.sleep(0.05)
                continue
            if isinstance(acquisition, RecoveryRequired):
                if await self._recover_acquisition(chat_session_id, acquisition):
                    continue
                while time.monotonic() < deadline:
                    await asyncio.sleep(min(0.05, max(0, deadline - time.monotonic())))
                raise SandboxError(
                    "sandbox_capacity",
                    "Secure workspace capacity is temporarily full",
                )
            if isinstance(acquisition, CapacityUnavailable):
                raise SandboxError(
                    "sandbox_capacity",
                    "Secure workspace capacity is temporarily full",
                )
            raise AssertionError("Unhandled sandbox acquisition outcome")

        assert claim is not None
        try:
            await self.enforce_warm_cap()
        except (asyncio.CancelledError, Exception):
            await self._cleanup_failed_start(
                chat_session_id,
                claim,
                interval_id=interval_id,
                sandbox=None,
                failure_code="sandbox_start_failed",
            )
            raise

        sandbox = None
        try:
            async with asyncio.timeout(self.ready_timeout_seconds):
                sandbox = await self._create_provider_sandbox(
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
                            self._state_repository().clear_start_snapshot(
                                lease, claim=claim
                            )
        except asyncio.CancelledError:
            await self._cleanup_failed_start(
                chat_session_id,
                claim,
                interval_id=interval_id,
                sandbox=sandbox,
                failure_code="sandbox_start_failed",
            )
            raise
        except TimeoutError as error:
            await self._cleanup_failed_start(
                chat_session_id,
                claim,
                interval_id=interval_id,
                sandbox=sandbox,
                failure_code="sandbox_timeout",
            )
            raise SandboxError(
                "sandbox_timeout", "Secure workspace startup timed out"
            ) from error
        except Exception as error:
            await self._cleanup_failed_start(
                chat_session_id,
                claim,
                interval_id=interval_id,
                sandbox=sandbox,
                failure_code="sandbox_start_failed",
            )
            raise SandboxError(
                "sandbox_start_failed", "Secure workspace startup failed"
            ) from error

        sandbox_id = sandbox.object_id
        landed = False
        try:
            with self.session_factory() as db, db.begin():
                lease = self._lease(db, chat_session_id, lock=True)
                landed = self._state_repository().land_start(
                    lease,
                    claim=claim,
                    sandbox_id=sandbox_id,
                    now=datetime.now(UTC),
                )
                if landed and interval_id is not None:
                    ChatSandboxSpendService(db, self.settings).provider_created(
                        interval_id,
                        sandbox_id,
                    )
        except Exception:
            await self._cleanup_failed_start(
                chat_session_id,
                claim,
                interval_id=interval_id,
                sandbox=sandbox,
                failure_code="sandbox_start_failed",
            )
            raise
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

    def _fail_start_claim(
        self, chat_session_id: uuid.UUID, claim: StartClaim, code: str
    ) -> bool:
        with self.session_factory() as db, db.begin():
            if self.blank_pool_enabled:
                self._lock_capacity(db)
            lease = self._lease(db, chat_session_id, lock=True)
            return self._state_repository().fail_start(
                lease,
                claim=claim,
                code=code,
                now=datetime.now(UTC),
            )

    def _claim_worker(self, chat_session_id: uuid.UUID, sandbox_id: str) -> WorkerClaim:
        assignment_token = secrets.token_urlsafe(24)
        with self.session_factory() as db, db.begin():
            lease = self._lease(db, chat_session_id, lock=True)
            try:
                return self._state_repository().claim_worker(
                    lease,
                    sandbox_id=sandbox_id,
                    assignment_token=assignment_token,
                    now=datetime.now(UTC),
                )
            except LeaseUnavailable as error:
                raise SandboxError(
                    "sandbox_lost", "Secure workspace is unavailable"
                ) from error
            except WorkerGenerationUnavailable as error:
                raise SandboxError(
                    "sandbox_lost", "Secure workspace generation is unavailable"
                ) from error

    def _release_worker(self, chat_session_id: uuid.UUID, claim: WorkerClaim) -> bool:
        with self.session_factory() as db, db.begin():
            lease = self._lease(db, chat_session_id, lock=True)
            return self._state_repository().release_worker(
                lease,
                claim=claim,
                now=datetime.now(UTC),
            )

    async def _terminate_worker(
        self,
        chat_session_id: uuid.UUID,
        claim: WorkerClaim,
        *,
        failure_code: str,
    ) -> bool:
        termination: TerminationClaim | None = None
        with self.session_factory() as db, db.begin():
            lease = self._lease(db, chat_session_id, lock=True)
            now = datetime.now(UTC)
            termination = self._state_repository().claim_worker_termination(
                lease,
                claim=claim,
                termination_token=secrets.token_urlsafe(24),
                failure_code=failure_code,
                expires_at=now + timedelta(seconds=self.ready_timeout_seconds + 15),
                now=now,
            )
        if termination is None:
            return False
        self._drop_control(chat_session_id)
        await self._terminate_claimed_sandbox(
            chat_session_id,
            termination,
        )
        return True

    def _drop_control(self, chat_session_id: uuid.UUID) -> None:
        self._worker_transport().drop_session_control(chat_session_id)

    def _drop_control_by_sandbox(self, sandbox_id: str) -> None:
        self._worker_transport().drop_session_controls_by_sandbox(sandbox_id)

    def _drop_blank_control(self, sandbox_id: str) -> None:
        self._worker_transport().drop_blank_control(sandbox_id)

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
        web_search_enabled: bool = False,
        fetchable_urls: list[str] | None = None,
    ) -> AsyncIterator[dict]:
        if getattr(self.settings, "chat_sandbox_spend_enforcement_enabled", False):
            with self.session_factory() as db:
                try:
                    ChatSandboxSpendService(db, self.settings).assert_available()
                except ChatComputeDisabled as error:
                    db.commit()
                    raise SandboxError(error.code, str(error)) from error
                db.commit()
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
                    web_search_enabled=web_search_enabled,
                    fetchable_urls=fetchable_urls or [],
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
        web_search_enabled: bool = False,
        fetchable_urls: list[str] | None = None,
        allow_pool: bool,
        forced_pool_miss: bool,
    ) -> AsyncIterator[dict]:
        turn_started = time.perf_counter()
        transport = self._worker_transport()
        yield {"type": "sandbox_start", "session_id": str(chat_session_id)}
        persistent = bool(
            getattr(self.settings, "chat_persistent_worker_enabled", False)
        )
        reusable_sandbox = (
            transport.reusable_sandbox(chat_session_id, resume) if persistent else None
        )
        if reusable_sandbox is not None:
            sandbox = reusable_sandbox
            cold_start_ms = 0
            created = False
            acquisition_outcome = "reused_session"
            pool_lookup_ms = None
        else:
            (
                sandbox,
                cold_start_ms,
                created,
                acquisition_outcome,
                pool_lookup_ms,
            ) = await self.ensure_ready(
                chat_session_id,
                pool_miss=forced_pool_miss,
                budget_prechecked=True,
                allow_pool=bool(
                    allow_pool
                    and persistent
                    and self.blank_pool_enabled
                    and resume is None
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
        execution: WorkerTurnExecution | None = None
        try:
            claim = self._claim_worker(chat_session_id, sandbox.object_id)
            execution = transport.create_execution(
                sandbox,
                claim,
                WorkerTurnRequest(
                    chat_session_id=chat_session_id,
                    turn_id=turn_id,
                    request_id=request_id,
                    prompt=prompt,
                    model=model,
                    resume=resume,
                    capability_token=capability.token,
                    gateway_url=self.settings.chat_gateway_url,
                    web_search_enabled=web_search_enabled,
                    fetchable_urls=tuple(fetchable_urls or ()),
                ),
                (WorkerTurnMode.PERSISTENT if persistent else WorkerTurnMode.ONE_SHOT),
                process_timeout_seconds=round(
                    self.settings.chat_agent_timeout_seconds + 15
                ),
            )
            dispatch = await execution.dispatch()
            if dispatch is WorkerTurnDispatchOutcome.CANCELLED:
                yield {"type": "_cancelled"}
                return
            yield {
                "type": "_latency",
                "phase": "capability_install_ms",
                "elapsed_ms": round((time.perf_counter() - turn_started) * 1000),
            }
            async for output in execution.events(
                timeout_seconds=self.settings.chat_agent_timeout_seconds
            ):
                if output is WorkerTurnMilestone.SDK_DISPATCHED:
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
                elif output is WorkerTurnMilestone.FIRST_DELTA:
                    yield {
                        "type": "_latency",
                        "phase": "first_worker_delta",
                        "elapsed_ms": round(
                            (time.perf_counter() - turn_started) * 1000
                        ),
                    }
                elif output is WorkerTurnMilestone.CANCELLED:
                    yield {"type": "_cancelled"}
                else:
                    yield output
        except (TimeoutError, ProtocolError, SandboxError) as error:
            if acquisition_outcome in {"pool_hit", "reused_session"} and not (
                execution is not None and execution.sdk_dispatched
            ):
                raise SandboxError(
                    "pool_assignment_failed",
                    "The secure workspace assignment failed",
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
            if acquisition_outcome in {"pool_hit", "reused_session"} and not (
                execution is not None and execution.sdk_dispatched
            ):
                raise SandboxError(
                    "pool_assignment_failed",
                    "The secure workspace assignment failed",
                    uncertain=True,
                ) from error
            raise
        finally:
            if execution is not None:
                await execution.close()
            if execution is None or not execution.terminal:
                if claim is not None:
                    await self._terminate_worker(
                        chat_session_id,
                        claim,
                        failure_code=(
                            "cancelled"
                            if execution is not None and execution.cancel_requested
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
        transport = self._worker_transport()
        outcome = await transport.cancel(
            turn_id,
            grace_seconds=self.settings.chat_cancel_grace_seconds,
        )
        if outcome.status is WorkerCancelStatus.NOT_FOUND:
            return False
        if outcome.status is WorkerCancelStatus.CONTROL_LOST:
            assert outcome.claim is not None
            await self._terminate_worker(
                chat_session_id,
                outcome.claim,
                failure_code="cancel_control_lost",
            )
            transport.complete_control_loss(outcome)
        elif outcome.status is WorkerCancelStatus.TIMED_OUT:
            assert outcome.claim is not None
            await self._terminate_worker(
                chat_session_id,
                outcome.claim,
                failure_code="cancel_timeout",
            )
        return True

    async def terminate(
        self, chat_session_id: uuid.UUID, *, failure_code: str | None = None
    ) -> None:
        claim: TerminationClaim | None = None
        with self.session_factory() as db, db.begin():
            lease = self._lease(db, chat_session_id, lock=True)
            claim = self._state_repository().claim_termination(
                lease,
                termination_token=secrets.token_urlsafe(24),
                failure_code=failure_code,
                expires_at=datetime.now(UTC)
                + timedelta(seconds=self.ready_timeout_seconds + 15),
            )
        if claim is not None:
            self._drop_control(chat_session_id)
            await self._terminate_claimed_sandbox(chat_session_id, claim)

    async def _terminate_claimed_sandbox(
        self,
        chat_session_id: uuid.UUID,
        claim: TerminationClaim,
    ) -> None:
        failure_code = claim.failure_code
        termination_confirmed: bool | None = None
        if claim.sandbox_id:
            termination_confirmed = await self._terminate_provider_sandbox(
                claim.sandbox_id
            )
            if getattr(
                self.settings,
                "chat_sandbox_spend_enforcement_enabled",
                False,
            ):
                with self.session_factory() as db, db.begin():
                    ChatSandboxSpendService(db, self.settings).terminate(
                        claim.sandbox_id,
                        claim.failure_code,
                        confirmed=termination_confirmed,
                    )
            if not termination_confirmed:
                failure_code = "termination_uncertain"
        self._finish_termination_claim(
            chat_session_id,
            claim,
            state="failed" if failure_code else "terminated",
            failure_code=failure_code,
            clear_sandbox=True,
        )

    def _finish_termination_claim(
        self,
        chat_session_id: uuid.UUID,
        claim: TerminationClaim,
        *,
        state: str,
        failure_code: str | None,
        clear_sandbox: bool,
    ) -> bool:
        with self.session_factory() as db, db.begin():
            if self.blank_pool_enabled:
                self._lock_capacity(db)
            lease = self._lease(db, chat_session_id, lock=True)
            return self._state_repository().finish_termination(
                lease,
                claim=claim,
                state=state,
                failure_code=failure_code,
                clear_sandbox=clear_sandbox,
                now=datetime.now(UTC),
            )

    async def cleanup_deleted(
        self, sandbox_id: str | None, snapshot_id: str | None
    ) -> None:
        termination_confirmed = True
        if sandbox_id:
            self._drop_control_by_sandbox(sandbox_id)
            termination_confirmed = await self._terminate_provider_sandbox(sandbox_id)
            if self.settings.chat_sandbox_spend_enforcement_enabled:
                with self.session_factory() as db, db.begin():
                    ChatSandboxSpendService(db, self.settings).terminate(
                        sandbox_id,
                        "session_deleted",
                        confirmed=termination_confirmed,
                    )
        if snapshot_id:
            await self.snapshots.delete(snapshot_id)
        if not termination_confirmed:
            raise SandboxCleanupUnverified(
                "Sandbox termination could not be confirmed after chat deletion"
            )

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
        claim: TerminationClaim | None = None
        with self.session_factory() as db, db.begin():
            lease = self._lease(db, chat_session_id, lock=True)
            claim = self._state_repository().claim_snapshot_termination(
                lease,
                termination_token=secrets.token_urlsafe(24),
                expires_at=datetime.now(UTC)
                + timedelta(seconds=self.ready_timeout_seconds + 15),
            )
        if claim is None:
            return False
        sandbox_id = claim.sandbox_id
        assert sandbox_id is not None
        if claim.should_snapshot:
            try:
                sandbox = await self._provider_adapter().resolve(sandbox_id)
                snapshot_id = await self.snapshots.save(sandbox, chat_session_id)
                with self.session_factory() as db, db.begin():
                    lease = self._lease(db, chat_session_id, lock=True)
                    self._state_repository().record_snapshot(
                        lease,
                        claim=claim,
                        snapshot_id=snapshot_id,
                        image_version=self.settings.chat_modal_image_version,
                        now=datetime.now(UTC),
                    )
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
        self._finish_termination_claim(
            chat_session_id,
            claim,
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
            transport = self._worker_transport()
            for running in transport.running_workers():
                try:
                    await transport.signal_cancel(running)
                except Exception:
                    pass
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
        protected_busy_ids: set[str] = set()
        if datetime.now(UTC) < deadline:
            with self.session_factory() as db:
                protected_busy_ids = set(
                    db.execute(
                        select(ChatSandboxLease.modal_sandbox_id).where(
                            ChatSandboxLease.state == "busy",
                            ChatSandboxLease.modal_sandbox_id.is_not(None),
                        )
                    ).scalars()
                )
        uncertain = 0
        async for sandbox in self._provider_adapter().iter_sandboxes(
            tags={"service": "pwc-chat", "environment": self.settings.environment},
        ):
            if sandbox.object_id in protected_busy_ids:
                continue
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
            unresolved_intervals = (
                db.scalar(
                    select(func.count())
                    .select_from(ChatSandboxComputeInterval)
                    .where(
                        ChatSandboxComputeInterval.environment
                        == self.settings.environment,
                        ChatSandboxComputeInterval.terminal_at.is_(None),
                    )
                )
                or 0
            )
            ChatSandboxSpendService(db, self.settings).record_kill_sweep(
                complete=(
                    uncertain == 0 and remaining_live == 0 and unresolved_intervals == 0
                )
            )
        return {"state": "tripped", "terminated": terminated, "uncertain": uncertain}

    async def deliver_spend_alerts(self) -> int:
        """Deliver bounded, content-free circuit transitions without blocking kill sweeps."""
        from backend.models.database import ChatSandboxCircuitEvent

        # Initial rollout keeps transitions durable and pending until the operator
        # provisions both alert destinations. Blank-pool activation requires them.
        if not self.settings.chat_sandbox_slack_webhook_url:
            return 0
        with self.session_factory() as db:
            now = datetime.now(UTC)
            events = list(
                db.execute(
                    select(ChatSandboxCircuitEvent)
                    .where(
                        ChatSandboxCircuitEvent.delivery_state.in_(
                            ["pending", "retry", "delivering"]
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
                now = datetime.now(UTC)
                if (
                    event is None
                    or event.delivery_state not in {"pending", "retry", "delivering"}
                    or (
                        event.next_delivery_attempt_at is not None
                        and self._as_utc(event.next_delivery_attempt_at) > now
                    )
                ):
                    continue
                event.delivery_attempts += 1
                event.delivery_state = "delivering"
                event.next_delivery_attempt_at = now + timedelta(seconds=30)
                payload = {
                    "text": (
                        f"PwC chat compute {event.severity}: {event.event_type}; "
                        f"environment={event.details.get('environment')}; cycle={event.details.get('billing_cycle')}; "
                        f"release={event.details.get('release')}; effective_microusd={event.details.get('effective_microusd')}; "
                        f"provider_floor_microusd={event.details.get('provider_floor_microusd')}; "
                        f"threshold_microusd={event.details.get('threshold_microusd')}; "
                        f"provider_reserve_microusd={event.details.get('remaining_provider_reserve_microusd')}; "
                        f"state={event.details.get('circuit_state')}; live={event.details.get('live_count')}; "
                        f"uncertain={event.details.get('uncertain_count')}; reconciliation_age_seconds={event.details.get('reconciliation_age_seconds')}; event_id={event.id}; "
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
        with self.session_factory() as db:
            now = datetime.now(UTC)
            fallback_ids = list(
                db.execute(
                    select(ChatSandboxCircuitEvent.id)
                    .where(
                        ChatSandboxCircuitEvent.delivery_state == "failed",
                        ChatSandboxCircuitEvent.fallback_delivery_state.in_(
                            ["pending", "retry", "delivering"]
                        ),
                        ChatSandboxCircuitEvent.fallback_delivery_attempts < 5,
                        (
                            ChatSandboxCircuitEvent.fallback_next_delivery_attempt_at.is_(
                                None
                            )
                            | (
                                ChatSandboxCircuitEvent.fallback_next_delivery_attempt_at
                                <= now
                            )
                        ),
                    )
                    .order_by(ChatSandboxCircuitEvent.created_at)
                    .limit(10)
                ).scalars()
            )
        for event_id in fallback_ids:
            with self.session_factory() as db, db.begin():
                event = db.execute(
                    select(ChatSandboxCircuitEvent)
                    .where(ChatSandboxCircuitEvent.id == event_id)
                    .with_for_update()
                ).scalar_one_or_none()
                now = datetime.now(UTC)
                if (
                    event is None
                    or event.delivery_state != "failed"
                    or event.fallback_delivery_state
                    not in {"pending", "retry", "delivering"}
                    or (
                        event.fallback_next_delivery_attempt_at is not None
                        and self._as_utc(event.fallback_next_delivery_attempt_at) > now
                    )
                ):
                    continue
                event.fallback_delivery_attempts += 1
                event.fallback_delivery_state = "delivering"
                event.fallback_next_delivery_attempt_at = now + timedelta(seconds=30)
                payload = {
                    "text": (
                        "PwC chat compute primary alert delivery failed; "
                        f"environment={event.details.get('environment')}; "
                        f"severity=critical; event_id={event.id}; "
                        f"runbook={self.settings.chat_sandbox_runbook_url}"
                    )
                }
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    response = await client.post(
                        self.settings.chat_sandbox_alert_fallback_webhook_url,
                        json=payload,
                    )
                    response.raise_for_status()
            except Exception as error:
                logger.critical(
                    "chat spend fallback alert delivery failed event_id=%s error=%s",
                    event_id,
                    type(error).__name__,
                )
                with self.session_factory() as db, db.begin():
                    event = db.get(ChatSandboxCircuitEvent, event_id)
                    if event:
                        event.fallback_delivery_state = (
                            "failed"
                            if event.fallback_delivery_attempts >= 5
                            else "retry"
                        )
                        event.fallback_next_delivery_attempt_at = datetime.now(
                            UTC
                        ) + timedelta(
                            seconds=min(300, 15 * (2**event.fallback_delivery_attempts))
                        )
                continue
            with self.session_factory() as db, db.begin():
                event = db.get(ChatSandboxCircuitEvent, event_id)
                if event:
                    event.fallback_delivery_state = "delivered"
                    event.fallback_next_delivery_attempt_at = None
                    event.fallback_delivered_at = datetime.now(UTC)
        return delivered

    async def reconcile_spend_provider(self) -> bool:
        """Refresh the provider floor at most hourly; local metering remains authoritative."""
        now = datetime.now(UTC)
        with self.session_factory() as db, db.begin():
            if not ChatSandboxSpendService(
                db, self.settings
            ).claim_provider_reconciliation(now):
                return False
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
                        ChatSandboxLease.lease_token_hash,
                        ChatSandboxLease.worker_generation,
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
        for (
            session_id,
            sandbox_id,
            state,
            token_hash,
            worker_generation,
        ) in stale_operations:
            expected = LeaseStateClaim(
                state=state,
                sandbox_id=sandbox_id,
                token_hash=token_hash,
                worker_generation=worker_generation,
            )
            claim: TerminationClaim | None = None
            with self.session_factory() as db, db.begin():
                lease = self._lease(db, session_id, lock=True)
                session = db.execute(
                    select(ChatSession)
                    .where(ChatSession.id == session_id)
                    .with_for_update()
                ).scalar_one_or_none()
                if session is None:
                    continue
                current = datetime.now(UTC)
                claim = self._state_repository().claim_stale_termination(
                    lease,
                    expected=expected,
                    active_turn_expires_at=session.active_turn_expires_at,
                    termination_token=secrets.token_urlsafe(24),
                    expires_at=current
                    + timedelta(seconds=self.ready_timeout_seconds + 15),
                    now=current,
                )
            if claim is None:
                continue
            self._drop_control(session_id)
            await self._terminate_claimed_sandbox(session_id, claim)
            repaired += 1

        with self.session_factory() as db:
            candidates = list(
                db.execute(
                    select(
                        ChatSandboxLease.chat_session_id,
                        ChatSandboxLease.modal_sandbox_id,
                        ChatSandboxLease.state,
                        ChatSandboxLease.lease_token_hash,
                        ChatSandboxLease.worker_generation,
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
        for session_id, sandbox_id, state, token_hash, worker_generation in candidates:
            if state == "starting":
                if token_hash:
                    claim = StartClaim(
                        token_hash=token_hash,
                        stale_sandbox_id=None,
                        snapshot_id=None,
                        worker_generation=worker_generation,
                    )
                    with self.session_factory() as db, db.begin():
                        if self.blank_pool_enabled:
                            self._lock_capacity(db)
                        lease = self._lease(db, session_id, lock=True)
                        if self._state_repository().fail_expired_start(
                            lease,
                            claim=claim,
                            code="sandbox_start_failed",
                            now=datetime.now(UTC),
                        ):
                            repaired += 1
                continue
            claim = LeaseStateClaim(
                state=state,
                sandbox_id=sandbox_id,
                token_hash=token_hash,
                worker_generation=worker_generation,
            )
            if not sandbox_id:
                with self.session_factory() as db, db.begin():
                    lease = self._lease(db, session_id, lock=True)
                    if self._state_repository().mark_lost(
                        lease,
                        claim=claim,
                        now=datetime.now(UTC),
                    ):
                        repaired += 1
                continue
            try:
                provider = self._provider_adapter()
                sandbox = await provider.resolve(sandbox_id)
                alive = await provider.poll(sandbox) is None
            except Exception:
                alive = False
            if not alive:
                with self.session_factory() as db, db.begin():
                    lease = self._lease(db, session_id, lock=True)
                    if self._state_repository().mark_lost(
                        lease,
                        claim=claim,
                        now=datetime.now(UTC),
                    ):
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
            if not snapshot_id:
                continue
            claim = SnapshotClaim(snapshot_id=snapshot_id)
            await self.snapshots.delete(snapshot_id)
            with self.session_factory() as db, db.begin():
                lease = self._lease(db, session_id, lock=True)
                if self._state_repository().clear_inactive_snapshot(lease, claim=claim):
                    expired += 1
        return expired
