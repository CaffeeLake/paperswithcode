"""Blank sandbox pool health, claiming, and termination orchestration."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from backend.config import Settings
from backend.services.chat_sandbox_pool_repository import (
    BlankPoolClaim,
    ChatSandboxPoolRepository,
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
)

POOL_LOCAL_HEALTH_MAX_AGE_SECONDS = 15
POOL_TERMINATION_MAX_CONCURRENCY = 8

SessionFactory = Callable[[], Session]
SpendFactory = Callable[[Session], ChatSandboxSpendService]
UtcClock = Callable[[], datetime]
MonotonicClock = Callable[[], float]


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
        self.spend_factory = spend_factory or (
            lambda db: ChatSandboxSpendService(db, settings)
        )
        self.utcnow = utcnow or (lambda: datetime.now(UTC))
        self.monotonic = monotonic

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

                    def availability_assertion() -> None:
                        spend.assert_available(now, capacity_locked=True)

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
                return sandbox, round((self.monotonic() - started) * 1000)
        return None

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
