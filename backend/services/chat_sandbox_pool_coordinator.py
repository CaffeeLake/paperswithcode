"""Blank sandbox pool health, claiming, and termination orchestration."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.services.chat_sandbox_pool_repository import (
    BlankPoolClaim,
    ChatSandboxPoolRepository,
    PoolEvictionRequired,
    PoolLandingDurability,
    PoolLandingOutcome,
    PoolReservationUnavailable,
    PoolStartReservation,
    PoolTerminationClaim,
    PoolTerminationFinishOutcome,
)
from backend.services.chat_sandbox_provider import (
    SandboxError,
    SandboxProvider,
)
from backend.services.chat_sandbox_spend_service import (
    ChatComputeDisabled,
    ChatSandboxSpendService,
)
from backend.services.chat_sandbox_worker_transport import (
    ChatSandboxWorkerTransport,
    SessionControl,
)

logger = logging.getLogger(__name__)

POOL_MAINTENANCE_LOCK_NAME = "chat-sandbox-pool-maintenance-v1"
POOL_LOCAL_HEALTH_MAX_AGE_SECONDS = 15
POOL_TERMINATION_MAX_CONCURRENCY = 8

SessionFactory = Callable[[], Session]
SpendFactory = Callable[[Session], ChatSandboxSpendService]
UtcClock = Callable[[], datetime]
MonotonicClock = Callable[[], float]
MaintenanceOwner = Callable[[], bool]
MaintenanceLocker = Callable[[Session], bool]
AssignedLeaseEvictor = Callable[[uuid.UUID], Awaitable[bool]]


def lock_pool_maintenance(db: Session) -> bool:
    """Take the pool transaction lock; test backends use a no-op success."""

    if db.get_bind().dialect.name != "postgresql":
        return True
    return bool(
        db.scalar(
            select(
                func.pg_try_advisory_xact_lock(
                    func.hashtextextended(POOL_MAINTENANCE_LOCK_NAME, 0)
                )
            )
        )
    )


class ChatSandboxPoolCoordinator:
    """Compose pool persistence, provider I/O, transport, and spend hooks."""

    def __init__(
        self,
        settings: Settings,
        *,
        session_factory: SessionFactory,
        repository: ChatSandboxPoolRepository,
        provider: SandboxProvider,
        transport: ChatSandboxWorkerTransport,
        maintenance_owner: MaintenanceOwner,
        evict_assigned_lease: AssignedLeaseEvictor,
        maintenance_locker: MaintenanceLocker = lock_pool_maintenance,
        spend_factory: SpendFactory | None = None,
        utcnow: UtcClock | None = None,
        monotonic: MonotonicClock = time.monotonic,
    ):
        if transport.provider is not provider:
            raise ValueError("Pool coordinator provider and transport must be shared")
        self.settings = settings
        self.session_factory = session_factory
        self.repository = repository
        self.provider = provider
        self.transport = transport
        self.maintenance_owner = maintenance_owner
        self.evict_assigned_lease = evict_assigned_lease
        self.maintenance_locker = maintenance_locker
        self.spend_factory = spend_factory or (
            lambda db: ChatSandboxSpendService(db, settings)
        )
        self.utcnow = utcnow or (lambda: datetime.now(UTC))
        self.monotonic = monotonic
        self._refill_semaphore = asyncio.Semaphore(
            settings.chat_blank_pool_refill_concurrency
        )
        self._refill_tasks: set[asyncio.Task[int]] = set()

    @property
    def termination_claim_timeout_seconds(self) -> float:
        ready_timeout = (
            getattr(
                self.settings,
                "chat_worker_ready_timeout_seconds",
                self.settings.chat_sandbox_ready_timeout_seconds,
            )
            if getattr(self.settings, "chat_persistent_worker_enabled", False)
            else self.settings.chat_sandbox_ready_timeout_seconds
        )
        return ready_timeout + self.settings.chat_sandbox_termination_grace_seconds + 15

    @property
    def termination_concurrency(self) -> int:
        configured_max = self.settings.chat_blank_pool_max or 1
        return min(
            POOL_TERMINATION_MAX_CONCURRENCY,
            self.settings.chat_blank_pool_refill_concurrency,
            configured_max,
        )

    def spawn_replenishment(self) -> None:
        if (
            not self._refill_enabled
            or not self.maintenance_owner()
            or len(self._refill_tasks)
            >= self.settings.chat_blank_pool_refill_concurrency
        ):
            return
        task = asyncio.create_task(self.replenish_pool())
        self._refill_tasks.add(task)

        def finished(completed: asyncio.Task[int]) -> None:
            self._refill_tasks.discard(completed)
            if completed.cancelled():
                return
            error = completed.exception()
            if error is not None:
                logger.warning(
                    "chat blank pool replenishment failed error=%s",
                    type(error).__name__,
                )

        task.add_done_callback(finished)

    async def pool_sandbox_health(
        self,
        sandbox_id: str,
        worker_generation: str,
    ) -> object | None:
        try:
            control = self.transport.blank_control(sandbox_id)
            if control is not None:
                if control.sandbox_id != sandbox_id:
                    return None
                checked_at = self.transport.blank_health_checked_at(sandbox_id)
                if (
                    checked_at is not None
                    and self.monotonic() - checked_at
                    <= POOL_LOCAL_HEALTH_MAX_AGE_SECONDS
                ):
                    return control.sandbox
                if await self.transport.ping(control, worker_generation):
                    if self.transport.mark_blank_healthy(
                        sandbox_id,
                        expected=control,
                        checked_at=self.monotonic(),
                    ):
                        return control.sandbox
                    replacement = self.transport.blank_control(sandbox_id)
                    replacement_checked_at = self.transport.blank_health_checked_at(
                        sandbox_id
                    )
                    if (
                        replacement is not None
                        and replacement_checked_at is not None
                        and self.monotonic() - replacement_checked_at
                        <= POOL_LOCAL_HEALTH_MAX_AGE_SECONDS
                    ):
                        return replacement.sandbox
                return None
            sandbox = await self.provider.resolve(sandbox_id)
            if await self.provider.poll(sandbox) is not None:
                return None
            healthy = await self.provider.health(
                sandbox,
                persistent=True,
                worker_generation=worker_generation,
            )
            return sandbox if healthy else None
        except Exception:
            return None

    async def claim_blank(
        self,
        chat_session_id: uuid.UUID,
    ) -> tuple[object, int] | None:
        """Health-check and atomically bind one compatible blank worker."""

        if not (self._enabled and self.settings.chat_persistent_worker_enabled):
            return None
        started = self.monotonic()
        now = self.utcnow()
        minimum_expiry = now + timedelta(
            seconds=self.settings.chat_blank_pool_min_remaining_seconds
        )
        compatibility = self.repository.compatibility()
        # Release identifies the creator for audit; immutable worker and resource
        # compatibility determines whether an unassigned blank can be reused.
        with self.session_factory() as db:
            candidates = self.repository.list_claim_candidates(
                db,
                compatibility,
                minimum_expires_at=minimum_expiry,
                limit=self.settings.chat_blank_pool_max,
            )
        for candidate in candidates:
            if not candidate.sandbox_id:
                await self.terminate_pool_row(
                    candidate.pool_id,
                    None,
                    failure_code="sandbox_lost",
                )
                continue
            sandbox = await self.pool_sandbox_health(
                candidate.sandbox_id,
                candidate.worker_generation,
            )
            if sandbox is None:
                await self.terminate_pool_row(
                    candidate.pool_id,
                    candidate.sandbox_id,
                    failure_code="sandbox_lost",
                )
                continue
            local_control = self.transport.blank_control(candidate.sandbox_id)
            claim: BlankPoolClaim | None = None
            now = self.utcnow()
            with self.session_factory() as db:
                spend = None
                availability_assertion = None
                if getattr(
                    self.settings,
                    "chat_sandbox_spend_enforcement_enabled",
                    False,
                ):
                    spend = self.spend_factory(db)

                    def availability_assertion(
                        *,
                        spend_service: ChatSandboxSpendService = spend,
                        checked_at: datetime = now,
                    ) -> None:
                        spend_service.assert_available(
                            checked_at,
                            capacity_locked=True,
                        )

                    try:
                        claim = self.repository.claim_blank(
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
                    claim = self.repository.claim_blank(
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
                if claim is not None and spend is not None:
                    spend.claim(
                        claim.sandbox_id,
                        chat_session_id,
                        now,
                    )
                db.commit()
            if claim is not None:
                if local_control is not None:
                    self.transport.promote_blank_control(
                        claim.sandbox_id,
                        chat_session_id,
                        expected=local_control,
                    )
                self.spawn_replenishment()
                return sandbox, round((self.monotonic() - started) * 1000)
        return None

    async def replenish_pool(self) -> int:
        """Reserve and initialize at most one blank worker per invocation."""

        if not self._refill_enabled or not self.maintenance_owner():
            return 0
        async with self._refill_semaphore:
            if not self._refill_enabled or not self.maintenance_owner():
                return 0
            return await self._replenish_one()

    async def _replenish_one(self) -> int:
        refill_started = self.monotonic()
        for reservation_attempt in range(2):
            now = self.utcnow()
            reservation: PoolStartReservation | None = None
            eviction: PoolEvictionRequired | None = None
            with self.session_factory() as db, db.begin():
                if not self.maintenance_locker(db):
                    return 0
                interval_reserver = None
                if getattr(
                    self.settings,
                    "chat_sandbox_spend_enforcement_enabled",
                    False,
                ):
                    spend = self.spend_factory(db)

                    def interval_reserver(
                        worker_generation: str,
                        *,
                        spend_service: ChatSandboxSpendService = spend,
                        reserved_at: datetime = now,
                    ) -> uuid.UUID:
                        return spend_service.reserve_interval(
                            origin="blank_pool",
                            worker_generation=worker_generation,
                            now=reserved_at,
                            capacity_locked=True,
                        )

                try:
                    outcome = self.repository.reserve_starting_blank(
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
            if eviction is None:
                break
            if reservation_attempt == 1:
                return 0
            if not await self.evict_assigned_lease(eviction.chat_session_id):
                return 0
            if not self._refill_enabled or not self.maintenance_owner():
                return 0

        if reservation is None:
            return 0
        sandbox = None
        control: SessionControl | None = None
        try:
            sandbox = await self.provider.create(
                name=f"chat-blank-{reservation.pool_id}",
                tags={
                    "service": "pwc-chat",
                    "environment": getattr(
                        self.settings,
                        "environment",
                        "staging",
                    ),
                    "pool": "blank",
                    "pool_id": str(reservation.pool_id),
                    "release": self.settings.release_id,
                    "image": self.settings.chat_modal_image_version,
                    "contract": self.settings.chat_worker_contract_version,
                },
                worker_generation=reservation.worker_generation,
            )
            control = await self.transport.open_persistent_control(
                sandbox,
                reservation.worker_generation,
            )
            if not await self.transport.ping(control, reservation.worker_generation):
                raise SandboxError(
                    "sandbox_worker_not_ready",
                    "Persistent blank worker health check failed",
                )
            self.transport.register_blank_control(
                sandbox.object_id,
                control,
                checked_at=self.monotonic(),
            )
        except asyncio.CancelledError:
            try:
                await self._complete_cleanup(
                    self._compensate_start(
                        reservation,
                        sandbox=sandbox,
                        control=control,
                        failure_code="sandbox_start_failed",
                    )
                )
            except Exception as error:
                logger.warning(
                    "cancelled blank pool start cleanup failed error=%s",
                    type(error).__name__,
                )
            raise
        except Exception:
            await self._complete_cleanup(
                self._compensate_start(
                    reservation,
                    sandbox=sandbox,
                    control=control,
                    failure_code="sandbox_start_failed",
                )
            )
            return 0

        sandbox_id = sandbox.object_id
        try:
            with self.session_factory() as db, db.begin():
                landing = self.repository.land_provider_creation(
                    db,
                    reservation,
                    sandbox_id,
                    now=self.utcnow(),
                )
                if (
                    landing is PoolLandingOutcome.LANDED
                    and reservation.interval_id is not None
                ):
                    self.spend_factory(db).provider_created(
                        reservation.interval_id,
                        sandbox_id,
                        self.utcnow(),
                    )
            # Deliver cancellation requested during the synchronous landing commit.
            await asyncio.sleep(0)
        except asyncio.CancelledError as cancellation:
            try:
                durability = self._landing_durability(reservation, sandbox_id)
            except Exception as error:
                self._drop_registered_start_control(sandbox_id, control)
                logger.warning(
                    "cancelled blank landing durability check failed error=%s",
                    type(error).__name__,
                )
                raise cancellation
            if durability is PoolLandingDurability.OWNERSHIP_MOVED:
                self._drop_registered_start_control(sandbox_id, control)
            elif durability is PoolLandingDurability.NOT_DURABLE:
                try:
                    await self._complete_cleanup(
                        self._compensate_start(
                            reservation,
                            sandbox=sandbox,
                            control=control,
                            failure_code="sandbox_start_failed",
                        )
                    )
                except Exception as error:
                    logger.warning(
                        "cancelled blank landing cleanup failed error=%s",
                        type(error).__name__,
                    )
            raise
        except Exception as landing_error:
            try:
                durability = self._landing_durability(reservation, sandbox_id)
            except Exception:
                self._drop_registered_start_control(sandbox_id, control)
                raise landing_error
            if durability is PoolLandingDurability.BLANK_READY:
                landing = PoolLandingOutcome.LANDED
            elif durability is PoolLandingDurability.OWNERSHIP_MOVED:
                self._drop_registered_start_control(sandbox_id, control)
                return 0
            else:
                try:
                    await self._complete_cleanup(
                        self._compensate_start(
                            reservation,
                            sandbox=sandbox,
                            control=control,
                            failure_code="sandbox_start_failed",
                        )
                    )
                except Exception as cleanup_error:
                    logger.warning(
                        "blank landing cleanup failed error=%s",
                        type(cleanup_error).__name__,
                    )
                raise

        if landing is not PoolLandingOutcome.LANDED:
            await self._complete_cleanup(
                self._settle_ownership_changed(
                    reservation,
                    sandbox=sandbox,
                    control=control,
                )
            )
            return 0
        logger.info(
            "chat blank pool refill ready pool_id=%s sandbox_id=%s refill_ms=%d",
            reservation.pool_id,
            sandbox_id,
            round((self.monotonic() - refill_started) * 1000),
        )
        return 1

    def _landing_durability(
        self,
        reservation: PoolStartReservation,
        sandbox_id: str,
    ) -> PoolLandingDurability:
        with self.session_factory() as db:
            return self.repository.provider_landing_durability(
                db,
                reservation,
                sandbox_id,
            )

    async def _complete_cleanup(self, cleanup: Awaitable[None]) -> None:
        task = asyncio.create_task(cleanup)
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await asyncio.shield(task)
            raise

    async def _compensate_start(
        self,
        reservation: PoolStartReservation,
        *,
        sandbox: object | None,
        control: SessionControl | None,
        failure_code: str,
    ) -> None:
        sandbox_id = getattr(sandbox, "object_id", None)
        now = self.utcnow()
        with self.session_factory() as db, db.begin():
            claim = self.repository.claim_start_termination(
                db,
                reservation,
                None,
                failure_code=failure_code,
                now=now,
            )
        self._close_failed_start_control(sandbox_id, control)
        confirmed = True
        if sandbox_id is not None:
            try:
                confirmed = await self.provider.terminate(sandbox_id, sandbox)
            except Exception:
                confirmed = False
        self._finish_failed_start(
            reservation,
            claim=claim,
            sandbox_id=sandbox_id,
            failure_code=failure_code,
            confirmed=confirmed,
        )

    async def _settle_ownership_changed(
        self,
        reservation: PoolStartReservation,
        *,
        sandbox: object,
        control: SessionControl,
    ) -> None:
        sandbox_id = sandbox.object_id
        self._close_failed_start_control(sandbox_id, control)
        try:
            confirmed = await self.provider.terminate(sandbox_id, sandbox)
        except Exception:
            confirmed = False
        self._finish_failed_start(
            reservation,
            claim=None,
            sandbox_id=sandbox_id,
            failure_code="ownership_changed",
            confirmed=confirmed,
        )

    def _finish_failed_start(
        self,
        reservation: PoolStartReservation,
        *,
        claim: PoolTerminationClaim | None,
        sandbox_id: str | None,
        failure_code: str,
        confirmed: bool,
    ) -> None:
        if claim is None and reservation.interval_id is None:
            return
        now = self.utcnow()
        with self.session_factory() as db, db.begin():
            if claim is not None:
                finish = self.repository.finish_termination(
                    db,
                    claim,
                    confirmed=confirmed,
                    now=now,
                )
                if finish is not PoolTerminationFinishOutcome.FINISHED:
                    return
            if reservation.interval_id is None:
                return
            spend = self.spend_factory(db)
            if sandbox_id is None:
                spend.abort_reservation(
                    reservation.interval_id,
                    failure_code,
                    now,
                )
            else:
                spend.provider_created(reservation.interval_id, sandbox_id, now)
                spend.terminate(
                    sandbox_id,
                    failure_code,
                    confirmed=confirmed,
                    now=now,
                )

    def _close_failed_start_control(
        self,
        sandbox_id: str | None,
        control: SessionControl | None,
    ) -> None:
        if control is None:
            return
        if (
            sandbox_id is not None
            and self.transport.drop_blank_control(
                sandbox_id,
                expected=control,
            )
            is not None
        ):
            return
        self.transport.schedule_close(control)

    def _drop_registered_start_control(
        self,
        sandbox_id: str,
        control: SessionControl,
    ) -> None:
        self.transport.drop_blank_control(sandbox_id, expected=control)

    async def terminate_pool_row(
        self,
        pool_id: uuid.UUID,
        sandbox_id: str | None,
        *,
        failure_code: str | None,
    ) -> bool:
        now = self.utcnow()
        with self.session_factory() as db, db.begin():
            claim = self.repository.claim_termination(
                db,
                pool_id,
                sandbox_id,
                failure_code=failure_code,
                now=now,
                stale_draining_before=now
                - timedelta(seconds=self.termination_claim_timeout_seconds),
            )
        if claim is None:
            return False
        return await self.terminate_claimed_pool_row(claim)

    async def terminate_claimed_pool_row(
        self,
        claim: PoolTerminationClaim,
    ) -> bool:
        confirmed = True
        if claim.sandbox_id:
            self.transport.drop_blank_control(claim.sandbox_id)
            confirmed = await self.provider.terminate(claim.sandbox_id)
        now = self.utcnow()
        with self.session_factory() as db, db.begin():
            outcome = self.repository.finish_termination(
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
                self.spend_factory(db).terminate(
                    claim.sandbox_id,
                    claim.failure_code,
                    confirmed=confirmed,
                )
        return outcome is PoolTerminationFinishOutcome.FINISHED

    async def terminate_claimed_pool_rows(
        self,
        claims: list[PoolTerminationClaim],
    ) -> int:
        semaphore = asyncio.Semaphore(self.termination_concurrency)

        async def terminate_one(claim: PoolTerminationClaim) -> bool:
            async with semaphore:
                return await self.terminate_claimed_pool_row(claim)

        results = await asyncio.gather(*(terminate_one(claim) for claim in claims))
        return sum(results)

    @property
    def _enabled(self) -> bool:
        return bool(
            getattr(self.settings, "chat_blank_pool_enabled", False)
            and getattr(self.settings, "chat_sandbox_admission_enabled", True)
        )

    @property
    def _refill_enabled(self) -> bool:
        return bool(
            self._enabled
            and getattr(self.settings, "chat_persistent_worker_enabled", False)
            and self.settings.chat_blank_pool_min > 0
        )
