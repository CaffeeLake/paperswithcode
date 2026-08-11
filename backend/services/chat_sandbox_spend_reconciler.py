"""Coordinate durable provider-spend claims around provider I/O."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import ChatSandboxPool
from backend.services.chat_sandbox_capacity_repository import lock_capacity
from backend.services.chat_sandbox_pool_repository import (
    MODAL_CPU_USD_PER_CORE_SECOND,
    MODAL_MEMORY_USD_PER_GIB_SECOND,
    ChatSandboxPoolRepository,
)
from backend.services.chat_sandbox_spend_reporter import ProviderSpendReporter
from backend.services.chat_sandbox_spend_service import ChatSandboxSpendService

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]
UtcClock = Callable[[], datetime]


class ProviderReconciliationOutcome(StrEnum):
    SKIPPED = "skipped"
    RECONCILED = "reconciled"
    UNAVAILABLE = "unavailable"


class PoolBudgetStatus(TypedDict):
    billing_month: str
    accrued_usd: float
    reported_usd: float
    effective_accrued_usd: float
    projected_usd: float
    budget_usd: float
    within_budget: bool


class ChatSandboxSpendReconciler:
    """Claim, report, and exactly finalize provider spend."""

    def __init__(
        self,
        settings: Settings,
        *,
        session_factory: SessionFactory,
        reporter: ProviderSpendReporter,
        pool_repository: ChatSandboxPoolRepository | None = None,
        utcnow: UtcClock | None = None,
    ) -> None:
        if reporter.settings is not settings:
            raise ValueError("Spend reporter settings must be shared")
        if pool_repository is not None and pool_repository.settings is not settings:
            raise ValueError("Spend pool repository settings must be shared")
        self.settings = settings
        self.session_factory = session_factory
        self.reporter = reporter
        self.pool_repository = (
            pool_repository
            if pool_repository is not None
            else ChatSandboxPoolRepository(
                settings,
                capacity_locker=lock_capacity,
            )
        )
        self.utcnow = utcnow or (lambda: datetime.now(UTC))

    def pool_budget_status(self) -> PoolBudgetStatus:
        """Project the established blank-pool or enforced spend budget status."""

        now = self.utcnow()
        if not getattr(
            self.settings,
            "chat_sandbox_spend_enforcement_enabled",
            False,
        ):
            billing_month = self.pool_repository.billing_month(now)
            with self.session_factory() as db, db.begin():
                rows = list(
                    db.execute(
                        select(ChatSandboxPool).where(
                            ChatSandboxPool.billing_month == billing_month
                        )
                    ).scalars()
                )
                accrued = sum(
                    (
                        self.pool_repository.finalize_cost(row, now)[1]
                        if row.state in {"starting", "blank_ready", "draining"}
                        else float(row.estimated_blank_cost_usd)
                    )
                    for row in rows
                )
            reported = float(self.settings.chat_blank_pool_reported_month_to_date_usd)
            effective = max(accrued, reported)
            projected = (
                effective
                + max(0, (self._next_month(now) - now).total_seconds())
                * self._pool_cost_per_second()
                * self.settings.chat_blank_pool_min
            )
            budget = float(self.settings.chat_blank_pool_monthly_budget_usd)
            return {
                "billing_month": billing_month.isoformat(),
                "accrued_usd": accrued,
                "reported_usd": reported,
                "effective_accrued_usd": effective,
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

    @staticmethod
    def _next_month(now: datetime) -> datetime:
        if now.month == 12:
            return datetime(now.year + 1, 1, 1, tzinfo=UTC)
        return datetime(now.year, now.month + 1, 1, tzinfo=UTC)

    def _pool_cost_per_second(self) -> float:
        return (
            float(self.settings.chat_sandbox_cpu) * MODAL_CPU_USD_PER_CORE_SECOND
            + float(self.settings.chat_sandbox_memory_mib)
            / 1024
            * MODAL_MEMORY_USD_PER_GIB_SECOND
        )

    async def reconcile_provider(self) -> ProviderReconciliationOutcome:
        now = self.utcnow()
        with self.session_factory() as db, db.begin():
            claim = ChatSandboxSpendService(
                db,
                self.settings,
            ).claim_provider_reconciliation_exact(now)
        if claim is None:
            return ProviderReconciliationOutcome.SKIPPED

        cycle = claim.billing_cycle
        start = datetime(cycle.year, cycle.month, 1, tzinfo=UTC)
        try:
            floor_microusd = await self.reporter.month_to_date_microusd(
                start=start,
                end=claim.attempted_at,
            )
        except Exception as error:
            logger.error(
                "chat spend provider reconciliation unavailable error=%s",
                type(error).__name__,
            )
            with self.session_factory() as db, db.begin():
                finalized = ChatSandboxSpendService(
                    db,
                    self.settings,
                ).reconciliation_unavailable_for_claim(claim)
            return (
                ProviderReconciliationOutcome.UNAVAILABLE
                if finalized is not None
                else ProviderReconciliationOutcome.SKIPPED
            )

        with self.session_factory() as db, db.begin():
            reconciled = ChatSandboxSpendService(
                db,
                self.settings,
            ).reconcile_provider_floor_for_claim(claim, floor_microusd)
        return (
            ProviderReconciliationOutcome.RECONCILED
            if reconciled is not None
            else ProviderReconciliationOutcome.SKIPPED
        )
