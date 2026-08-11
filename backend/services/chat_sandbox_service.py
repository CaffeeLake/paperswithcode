"""Durable Modal sandbox lifecycle and framed worker transport."""

from __future__ import annotations

import os
import secrets
import time
import uuid
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import cast

import modal
from modal.client import _Client
from modal.exception import NotFoundError
from modal_proto import api_pb2
from sqlalchemy.orm import Session
from websockets.asyncio.client import connect as websocket_connect

from backend.chat_sandbox_worker.contract import MODAL_APP_NAME
from backend.chat_sandbox_worker.protocol import ProtocolError
from backend.config import Settings
from backend.database.connection import db_manager
from backend.services.chat_capability_service import IssuedCapability
from backend.services.chat_sandbox_acquisition_coordinator import (
    ChatSandboxAcquisitionCoordinator,
    LegacyEnsureReadyResult,
    legacy_ensure_ready_result,
)
from backend.services.chat_sandbox_capacity_repository import (
    ChatSandboxCapacityRepository,
)
from backend.services.chat_sandbox_lease_eviction_coordinator import (
    ChatSandboxLeaseEvictionCoordinator,
)
from backend.services.chat_sandbox_lease_lifecycle_coordinator import (
    ChatSandboxLeaseLifecycleCoordinator,
)
from backend.services.chat_sandbox_lease_lifecycle_coordinator import (
    SandboxCleanupUnverified as SandboxCleanupUnverified,  # noqa: PLC0414
)
from backend.services.chat_sandbox_lease_maintenance_coordinator import (
    ChatSandboxLeaseMaintenanceCoordinator,
)
from backend.services.chat_sandbox_pool_coordinator import (
    ChatSandboxPoolCoordinator,
    PoolMaintenanceResult,
    lock_pool_maintenance,
)
from backend.services.chat_sandbox_pool_repository import ChatSandboxPoolRepository
from backend.services.chat_sandbox_provider import (
    ModalSandboxProviderAdapter,
    SandboxError,
    SandboxProvider,
)
from backend.services.chat_sandbox_provider import (
    resolve_modal_image as _resolve_modal_image,
)
from backend.services.chat_sandbox_provider import (
    sandbox_environment as _sandbox_environment,
)
from backend.services.chat_sandbox_spend_alert_dispatcher import (
    ChatSandboxSpendAlertDispatcher,
)
from backend.services.chat_sandbox_spend_cap_coordinator import (
    ChatSandboxSpendCapCoordinator,
    SpendCapPublicResult,
)
from backend.services.chat_sandbox_spend_reconciler import (
    ChatSandboxSpendReconciler,
    PoolBudgetStatus,
    ProviderReconciliationOutcome,
)
from backend.services.chat_sandbox_spend_reporter import (
    ModalProviderSpendReporter,
    ProviderSpendReporter,
)
from backend.services.chat_sandbox_spend_service import (
    ChatComputeDisabled,
    ChatSandboxSpendService,
)
from backend.services.chat_sandbox_state_repository import (
    ChatSandboxStateRepository,
    LeaseUnavailable,
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
        lease_eviction_coordinator: ChatSandboxLeaseEvictionCoordinator | None = None,
        lease_lifecycle_coordinator: ChatSandboxLeaseLifecycleCoordinator | None = None,
        lease_maintenance_coordinator: ChatSandboxLeaseMaintenanceCoordinator
        | None = None,
        spend_alert_dispatcher: ChatSandboxSpendAlertDispatcher | None = None,
        spend_reporter: ProviderSpendReporter | None = None,
        spend_reconciler: ChatSandboxSpendReconciler | None = None,
    ):
        self.settings = settings
        self.session_factory = session_factory or db_manager.session_local
        if pool_repository is not None and pool_repository.settings is not settings:
            raise ValueError("Pool repository settings must be shared")
        if spend_alert_dispatcher is not None:
            if spend_alert_dispatcher.settings is not settings:
                raise ValueError("Spend alert dispatcher settings must be shared")
            if spend_alert_dispatcher.session_factory is not self.session_factory:
                raise ValueError("Spend alert dispatcher sessions must be shared")
        if spend_reporter is not None and spend_reporter.settings is not settings:
            raise ValueError("Spend reporter settings must be shared")
        if spend_reconciler is not None:
            if spend_reconciler.settings is not settings:
                raise ValueError("Spend reconciler settings must be shared")
            if spend_reconciler.session_factory is not self.session_factory:
                raise ValueError("Spend reconciler sessions must be shared")
            if (
                spend_reporter is not None
                and spend_reconciler.reporter is not spend_reporter
            ):
                raise ValueError("Spend reconciler reporter must be shared")
            if (
                pool_repository is not None
                and spend_reconciler.pool_repository is not pool_repository
            ):
                raise ValueError("Spend reconciler pool repository must be shared")
            spend_reporter = spend_reconciler.reporter
            pool_repository = spend_reconciler.pool_repository
        self._sandbox_provider = sandbox_provider
        self._sandbox_state = state_repository
        self._sandbox_capacity = capacity_repository
        self._sandbox_pool = pool_repository
        self._sandbox_pool_coordinator = None
        self._sandbox_lease_eviction = lease_eviction_coordinator
        self._sandbox_lease_lifecycle = lease_lifecycle_coordinator
        self._sandbox_lease_maintenance = lease_maintenance_coordinator
        self._sandbox_spend_alerts = spend_alert_dispatcher
        self._sandbox_spend_reporter = spend_reporter
        self._sandbox_spend_reconciler = spend_reconciler
        self._sandbox_spend_cap = None
        self._sandbox_acquisition = None
        self.pool_maintenance_owner = pool_maintenance_owner or (lambda: True)
        self.snapshots = snapshot_provider or WorkspaceSnapshotProvider(
            ttl_days=settings.chat_workspace_snapshot_inactivity_days
        )
        self._worker_transport_state = ChatSandboxWorkerTransport(
            self._provider_adapter()
        )
        if settings.chat_workspace_snapshots_enabled and not self.snapshots.supported:
            raise SandboxError(
                "snapshot_unsupported",
                "Configured workspace snapshots require a Directory Snapshot provider",
            )

    def _provider_adapter(self) -> SandboxProvider:
        provider = getattr(self, "_sandbox_provider", None)
        if provider is not None:
            return provider
        provider = ModalSandboxProviderAdapter(
            self.settings,
            image_resolver=resolve_modal_image,
            websocket_connector=_connect_provider_websocket,
        )
        self._sandbox_provider = provider
        return provider

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
            state_repository = self._state_repository()
            repository = ChatSandboxCapacityRepository(
                self.settings,
                state_repository,
            )
            self._sandbox_capacity = repository
        return repository

    def _pool_repository(self) -> ChatSandboxPoolRepository:
        repository = getattr(self, "_sandbox_pool", None)
        if repository is None:
            repository = ChatSandboxPoolRepository(
                self.settings,
                capacity_locker=self._capacity_repository().capacity_locker,
            )
            self._sandbox_pool = repository
        return repository

    def _lease_eviction_coordinator(self) -> ChatSandboxLeaseEvictionCoordinator:
        coordinator = getattr(self, "_sandbox_lease_eviction", None)
        if coordinator is None:
            transport = self._worker_transport()
            coordinator = ChatSandboxLeaseEvictionCoordinator(
                self.settings,
                session_factory=self.session_factory,
                repository=self._state_repository(),
                provider=cast(SandboxProvider, transport.provider),
                transport=transport,
                snapshots=self.snapshots,
                capacity_locker=self._capacity_repository().capacity_locker,
            )
            self._sandbox_lease_eviction = coordinator
        return coordinator

    def _pool_coordinator(self) -> ChatSandboxPoolCoordinator:
        coordinator = getattr(self, "_sandbox_pool_coordinator", None)
        if coordinator is None:
            transport = self._worker_transport()
            coordinator = ChatSandboxPoolCoordinator(
                self.settings,
                session_factory=self.session_factory,
                repository=self._pool_repository(),
                provider=cast(SandboxProvider, transport.provider),
                transport=transport,
                maintenance_owner=self.pool_maintenance_owner,
                maintenance_locker=lock_pool_maintenance,
                lease_eviction=self._lease_eviction_coordinator(),
            )
            self._sandbox_pool_coordinator = coordinator
        return coordinator

    def _lease_lifecycle_coordinator(self) -> ChatSandboxLeaseLifecycleCoordinator:
        coordinator = getattr(self, "_sandbox_lease_lifecycle", None)
        if coordinator is None:
            transport = self._worker_transport()
            coordinator = ChatSandboxLeaseLifecycleCoordinator(
                self.settings,
                session_factory=self.session_factory,
                repository=self._state_repository(),
                provider=cast(SandboxProvider, transport.provider),
                transport=transport,
                snapshots=self.snapshots,
                idle_eviction=self._lease_eviction_coordinator(),
                capacity_locker=self._capacity_repository().capacity_locker,
                termination_concurrency=self.MAINTENANCE_CONCURRENCY,
            )
            self._sandbox_lease_lifecycle = coordinator
        return coordinator

    def _lease_maintenance_coordinator(
        self,
    ) -> ChatSandboxLeaseMaintenanceCoordinator:
        coordinator = getattr(self, "_sandbox_lease_maintenance", None)
        if coordinator is None:
            transport = self._worker_transport()
            lifecycle = self._lease_lifecycle_coordinator()
            coordinator = ChatSandboxLeaseMaintenanceCoordinator(
                self.settings,
                session_factory=self.session_factory,
                repository=self._state_repository(),
                provider=cast(SandboxProvider, transport.provider),
                lifecycle=lifecycle,
                snapshots=self.snapshots,
                capacity_locker=lifecycle.capacity_locker,
            )
            self._sandbox_lease_maintenance = coordinator
        return coordinator

    def _spend_alert_dispatcher(self) -> ChatSandboxSpendAlertDispatcher:
        dispatcher = getattr(self, "_sandbox_spend_alerts", None)
        if dispatcher is None:
            dispatcher = ChatSandboxSpendAlertDispatcher(
                self.settings,
                session_factory=self.session_factory,
            )
            self._sandbox_spend_alerts = dispatcher
        return dispatcher

    def _spend_reporter(self) -> ProviderSpendReporter:
        reporter = getattr(self, "_sandbox_spend_reporter", None)
        if reporter is None:
            reporter = ModalProviderSpendReporter(self.settings)
            self._sandbox_spend_reporter = reporter
        return reporter

    def _spend_reconciler(self) -> ChatSandboxSpendReconciler:
        reconciler = getattr(self, "_sandbox_spend_reconciler", None)
        if reconciler is None:
            reconciler = ChatSandboxSpendReconciler(
                self.settings,
                session_factory=self.session_factory,
                reporter=self._spend_reporter(),
                pool_repository=self._pool_repository(),
            )
            self._sandbox_spend_reconciler = reconciler
        return reconciler

    def _spend_cap_coordinator(self) -> ChatSandboxSpendCapCoordinator:
        coordinator = getattr(self, "_sandbox_spend_cap", None)
        if coordinator is None:
            transport = self._worker_transport()
            coordinator = ChatSandboxSpendCapCoordinator(
                self.settings,
                session_factory=self.session_factory,
                lifecycle=self._lease_lifecycle_coordinator(),
                pool=self._pool_coordinator(),
                transport=transport,
                provider=cast(SandboxProvider, transport.provider),
                termination_concurrency=self.MAINTENANCE_CONCURRENCY,
            )
            self._sandbox_spend_cap = coordinator
        return coordinator

    def _acquisition_coordinator(self) -> ChatSandboxAcquisitionCoordinator:
        coordinator = getattr(self, "_sandbox_acquisition", None)
        if coordinator is None:
            transport = self._worker_transport()
            coordinator = ChatSandboxAcquisitionCoordinator(
                self.settings,
                session_factory=self.session_factory,
                state_repository=self._state_repository(),
                capacity_repository=self._capacity_repository(),
                pool=self._pool_coordinator(),
                provider=cast(SandboxProvider, transport.provider),
                transport=transport,
                snapshots=self.snapshots,
                lease_maintenance=self._lease_maintenance_coordinator(),
            )
            self._sandbox_acquisition = coordinator
        return coordinator

    def pool_budget_status(self) -> PoolBudgetStatus:
        return self._spend_reconciler().pool_budget_status()

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

    async def claim_blank(
        self, chat_session_id: uuid.UUID
    ) -> tuple[object, int] | None:
        return await self._pool_coordinator().claim_blank(chat_session_id)

    async def replenish_pool(self) -> int:
        return await self._pool_coordinator().replenish_pool()

    async def reconcile_pool_orphans(self) -> int:
        return await self._pool_coordinator().reconcile_pool_orphans()

    async def maintain_pool(self) -> dict[str, int]:
        result: PoolMaintenanceResult = await self._pool_coordinator().maintain_pool()
        return {
            "drained": result.drained,
            "lost": result.lost,
            "orphaned": result.orphaned,
            "abandoned": result.abandoned,
            "cleaned": result.cleaned,
            "replenished": result.replenished,
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

    async def ensure_ready(
        self,
        chat_session_id: uuid.UUID,
        *,
        allow_pool: bool = False,
        pool_miss: bool = False,
        pool_lookup_ms: int | None = None,
        budget_prechecked: bool = False,
    ) -> LegacyEnsureReadyResult:
        return legacy_ensure_ready_result(
            await self._acquisition_coordinator().acquire(
                chat_session_id,
                allow_pool=allow_pool,
                pool_miss=pool_miss,
                pool_lookup_ms=pool_lookup_ms,
                budget_prechecked=budget_prechecked,
            )
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
        outcome = await self._lease_lifecycle_coordinator().terminate_worker(
            chat_session_id,
            claim,
            failure_code=failure_code,
        )
        return outcome.acquired

    def _drop_control(self, chat_session_id: uuid.UUID) -> None:
        self._worker_transport().drop_session_control(chat_session_id)

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
        await self._lease_lifecycle_coordinator().terminate(
            chat_session_id,
            failure_code=failure_code,
        )

    async def cleanup_deleted(
        self, sandbox_id: str | None, snapshot_id: str | None
    ) -> None:
        await self._lease_lifecycle_coordinator().cleanup_deleted(
            sandbox_id,
            snapshot_id,
        )

    async def reap_idle(self) -> int:
        return await self._lease_maintenance_coordinator().reap_idle()

    async def snapshot_and_terminate(self, chat_session_id: uuid.UUID) -> bool:
        outcome = await self._lease_eviction_coordinator().evict_idle(chat_session_id)
        return outcome.acquired

    async def enforce_warm_cap(self) -> int:
        return await self._lease_maintenance_coordinator().enforce_warm_cap()

    async def enforce_spend_cap(self) -> SpendCapPublicResult:
        result = await self._spend_cap_coordinator().enforce()
        return {
            "state": result.state,
            "terminated": result.terminated,
            "uncertain": result.uncertain,
        }

    async def deliver_spend_alerts(self) -> int:
        return await self._spend_alert_dispatcher().deliver_pending()

    async def reconcile_spend_provider(self) -> bool:
        outcome = await self._spend_reconciler().reconcile_provider()
        return outcome is ProviderReconciliationOutcome.RECONCILED

    async def reconcile(self) -> int:
        """Converge expired creations and provider-lost sandbox leases."""
        return await self._lease_maintenance_coordinator().reconcile()

    async def expire_inactive_snapshots(self) -> int:
        return await self._lease_maintenance_coordinator().expire_inactive_snapshots()
