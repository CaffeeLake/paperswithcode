"""Conservative lifecycle metering and durable Modal-chat circuit breaker."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_CEILING, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.chat_sandbox_worker.contract import MODAL_APP_NAME
from backend.config import Settings
from backend.models.database import (
    ChatSandboxBudgetState,
    ChatSandboxCircuitEvent,
    ChatSandboxComputeInterval,
    ChatSandboxLease,
    ChatSandboxPool,
)

CAPACITY_LOCK_NAME = "chat-sandbox-capacity-v1"
CPU_MICROUSD_PER_CORE_SECOND = Decimal("39.42")
MEMORY_MICROUSD_PER_GIB_SECOND = Decimal("6.72")


class ChatComputeDisabled(RuntimeError):
    code = "chat_temporarily_disabled"


def billing_cycle(now: datetime) -> date:
    if now.tzinfo is None:
        raise ValueError("billing-cycle timestamps must be timezone aware")
    return now.astimezone(UTC).date().replace(day=1)


def cycle_end(cycle: date) -> datetime:
    return datetime(
        cycle.year + (cycle.month == 12), cycle.month % 12 + 1, 1, tzinfo=UTC
    )


class ChatSandboxSpendService:
    """All money is integer microdollars; the provider floor can only raise spend."""

    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings

    def _lock(self) -> None:
        if self.db.get_bind().dialect.name != "postgresql":
            return
        self.db.scalar(
            select(
                func.pg_advisory_xact_lock(func.hashtextextended(CAPACITY_LOCK_NAME, 0))
            )
        )

    def _policy(self) -> tuple[int, int, int, int]:
        return (
            self.settings.chat_sandbox_warning_microusd,
            self.settings.chat_sandbox_application_cap_microusd,
            self.settings.chat_sandbox_environment_cap_microusd,
            self.settings.chat_sandbox_workspace_cap_microusd,
        )

    def _state(
        self,
        now: datetime,
        *,
        lock: bool = True,
        provider_cycle_confirmed: bool = False,
    ) -> ChatSandboxBudgetState:
        cycle = billing_cycle(now)
        query = select(ChatSandboxBudgetState).where(
            ChatSandboxBudgetState.environment == self.settings.environment,
            ChatSandboxBudgetState.billing_cycle == cycle,
        )
        if lock:
            query = query.with_for_update()
        state = self.db.execute(query).scalar_one_or_none()
        if state is None:
            previous = self.db.execute(
                select(ChatSandboxBudgetState)
                .where(ChatSandboxBudgetState.environment == self.settings.environment)
                .order_by(ChatSandboxBudgetState.billing_cycle.desc())
                .limit(1)
                .with_for_update()
            ).scalar_one_or_none()
            if previous is not None and previous.circuit_state == "tripped":
                unresolved = (
                    self.db.scalar(
                        select(func.count())
                        .select_from(ChatSandboxComputeInterval)
                        .where(
                            ChatSandboxComputeInterval.environment
                            == self.settings.environment,
                            (ChatSandboxComputeInterval.terminal_at.is_(None))
                            | (ChatSandboxComputeInterval.reserved_microusd > 0),
                        )
                    )
                    or 0
                )
                safe_spend_trip = previous.trip_reason in {
                    "application_cap",
                    "safety_reserve",
                    "provider_budget",
                }
                if not (
                    safe_spend_trip
                    and provider_cycle_confirmed
                    and unresolved == 0
                    and previous.policy_attestation
                    == self.settings.chat_sandbox_budget_attestation
                ):
                    raise ChatComputeDisabled("Chat is temporarily disabled")
            warning, application, environment, workspace = self._policy()
            state = ChatSandboxBudgetState(
                id=uuid.uuid4(),
                environment=self.settings.environment,
                billing_cycle=cycle,
                cycle_end_at=cycle_end(cycle),
                warning_microusd=warning,
                application_cap_microusd=application,
                environment_cap_microusd=environment,
                workspace_cap_microusd=workspace,
                policy_attestation=self.settings.chat_sandbox_budget_attestation,
            )
            self.db.add(state)
            self.db.flush()
            if previous is not None:
                self._event(state, "cycle_rearmed", "recovery", None, now)
        return state

    def cost_per_second(self) -> int:
        cpu = Decimal(
            str(self.settings.chat_sandbox_cpu_limit or self.settings.chat_sandbox_cpu)
        )
        memory = Decimal(
            self.settings.chat_sandbox_memory_limit_mib
            or self.settings.chat_sandbox_memory_mib
        ) / Decimal(1024)
        return int(
            (
                cpu * CPU_MICROUSD_PER_CORE_SECOND
                + memory * MEMORY_MICROUSD_PER_GIB_SECOND
            ).to_integral_value(rounding=ROUND_CEILING)
        )

    def reservation_amount(self) -> int:
        seconds = (
            self.settings.chat_sandbox_watchdog_seconds
            + self.settings.chat_sandbox_drain_grace_seconds
            + self.settings.chat_sandbox_termination_grace_seconds
        )
        return (
            self.cost_per_second() * seconds
            + self.settings.chat_sandbox_reconciliation_allowance_microusd
        )

    def refresh(self, now: datetime) -> ChatSandboxBudgetState:
        self._lock()
        state = self._state(now)
        intervals = list(
            self.db.execute(
                select(ChatSandboxComputeInterval)
                .where(
                    ChatSandboxComputeInterval.environment == self.settings.environment,
                    ChatSandboxComputeInterval.billing_cycle == state.billing_cycle,
                )
                .with_for_update()
            ).scalars()
        )
        accrued = 0
        reserved = 0
        for interval in intervals:
            end = interval.terminal_at or now
            if end.tzinfo is None:
                end = end.replace(tzinfo=UTC)
            start = interval.reserved_at
            if start.tzinfo is None:
                start = start.replace(tzinfo=UTC)
            seconds = max(0, int((end - start).total_seconds()))
            # Each interval preserves its resource limits so policy changes cannot rewrite history.
            rate = int(
                (
                    Decimal(interval.cpu_limit_millicores)
                    / Decimal(1000)
                    * CPU_MICROUSD_PER_CORE_SECOND
                    + Decimal(interval.memory_limit_mib)
                    / Decimal(1024)
                    * MEMORY_MICROUSD_PER_GIB_SECOND
                ).to_integral_value(rounding=ROUND_CEILING)
            )
            interval.accrued_microusd = max(interval.accrued_microusd, seconds * rate)
            interval.updated_at = now
            accrued += interval.accrued_microusd
            if interval.terminal_at is None:
                reserved += interval.reserved_microusd
        state.estimated_accrued_microusd = accrued
        state.outstanding_reservation_microusd = reserved
        configured_floor = self.settings.chat_sandbox_provider_floor_microusd
        state.provider_floor_microusd = max(
            state.provider_floor_microusd, configured_floor
        )
        if self.settings.chat_sandbox_provider_reported_at:
            reported_at = datetime.fromisoformat(
                self.settings.chat_sandbox_provider_reported_at
            )
            if reported_at.tzinfo is None:
                raise ValueError("provider report timestamp must be timezone aware")
            if billing_cycle(reported_at) == state.billing_cycle:
                state.last_reconciled_at = reported_at.astimezone(UTC)
                state.reconciliation_state = "fresh"
        state.last_metered_at = now
        state.updated_at = now
        self._evaluate(state, now)
        if state.provider_floor_microusd > state.estimated_accrued_microusd:
            self._event(
                state, "provider_above_estimate", "critical", "provider_budget", now
            )
        return state

    def _event(
        self,
        state: ChatSandboxBudgetState,
        event_type: str,
        severity: str,
        reason: str | None,
        now: datetime,
        *,
        deduplicate: bool = True,
    ) -> None:
        duplicate = None
        if deduplicate:
            duplicate = self.db.execute(
                select(ChatSandboxCircuitEvent.id)
                .where(
                    ChatSandboxCircuitEvent.budget_state_id == state.id,
                    ChatSandboxCircuitEvent.event_type == event_type,
                )
                .limit(1)
            ).scalar_one_or_none()
        if duplicate is None:
            live_count = (
                self.db.scalar(
                    select(func.count())
                    .select_from(ChatSandboxComputeInterval)
                    .where(
                        ChatSandboxComputeInterval.environment == state.environment,
                        ChatSandboxComputeInterval.terminal_at.is_(None),
                    )
                )
                or 0
            )
            uncertain_count = (
                self.db.scalar(
                    select(func.count())
                    .select_from(ChatSandboxComputeInterval)
                    .where(
                        ChatSandboxComputeInterval.environment == state.environment,
                        ChatSandboxComputeInterval.terminal_at.is_(None),
                        ChatSandboxComputeInterval.reconciliation_state
                        == "termination_uncertain",
                    )
                )
                or 0
            )
            effective = max(
                state.estimated_accrued_microusd, state.provider_floor_microusd
            )
            self.db.add(
                ChatSandboxCircuitEvent(
                    id=uuid.uuid4(),
                    budget_state_id=state.id,
                    event_type=event_type,
                    severity=severity,
                    reason=reason,
                    details={
                        "environment": state.environment,
                        "billing_cycle": state.billing_cycle.isoformat(),
                        "release": self.settings.release_id,
                        "effective_microusd": effective,
                        "provider_floor_microusd": state.provider_floor_microusd,
                        "threshold_microusd": state.application_cap_microusd,
                        "remaining_provider_reserve_microusd": max(
                            0, state.environment_cap_microusd - effective
                        ),
                        "circuit_state": state.circuit_state,
                        "live_count": live_count,
                        "uncertain_count": uncertain_count,
                    },
                    created_at=now,
                )
            )

    def _evaluate(self, state: ChatSandboxBudgetState, now: datetime) -> None:
        effective = max(state.estimated_accrued_microusd, state.provider_floor_microusd)
        projected = effective + state.outstanding_reservation_microusd
        if (
            state.circuit_state != "tripped"
            and projected >= state.application_cap_microusd
        ):
            state.circuit_state = "tripped"
            state.trip_reason = "application_cap"
            state.tripped_at = now
            self._event(state, "circuit_tripped", "critical", state.trip_reason, now)
        elif state.circuit_state == "armed" and effective >= state.warning_microusd:
            state.circuit_state = "warning"
            self._event(state, "warning_entered", "warning", None, now)

    def assert_available(self, now: datetime | None = None) -> ChatSandboxBudgetState:
        state = self.refresh(now or datetime.now(UTC))
        if state.circuit_state == "tripped":
            raise ChatComputeDisabled("Chat is temporarily disabled")
        return state

    def reserve_interval(
        self,
        *,
        origin: str,
        worker_generation: str,
        chat_session_id: uuid.UUID | None = None,
        now: datetime | None = None,
    ) -> uuid.UUID:
        now = now or datetime.now(UTC)
        state = self.assert_available(now)
        reservation = self.reservation_amount()
        effective = max(state.estimated_accrued_microusd, state.provider_floor_microusd)
        if (
            effective + state.outstanding_reservation_microusd + reservation
            >= state.application_cap_microusd
        ):
            state.circuit_state = "tripped"
            state.trip_reason = "safety_reserve"
            state.tripped_at = now
            self._event(state, "circuit_tripped", "critical", state.trip_reason, now)
            raise ChatComputeDisabled("Chat is temporarily disabled")
        interval_id = uuid.uuid4()
        self.db.add(
            ChatSandboxComputeInterval(
                id=interval_id,
                environment=self.settings.environment,
                modal_app=MODAL_APP_NAME,
                app_release_id=self.settings.release_id,
                image_version=self.settings.chat_modal_image_version,
                worker_generation=worker_generation,
                origin=origin,
                chat_session_id=chat_session_id,
                cpu_request_millicores=round(self.settings.chat_sandbox_cpu * 1000),
                cpu_limit_millicores=round(
                    (
                        self.settings.chat_sandbox_cpu_limit
                        or self.settings.chat_sandbox_cpu
                    )
                    * 1000
                ),
                memory_request_mib=self.settings.chat_sandbox_memory_mib,
                memory_limit_mib=self.settings.chat_sandbox_memory_limit_mib
                or self.settings.chat_sandbox_memory_mib,
                reserved_at=now,
                billing_cycle=state.billing_cycle,
                reserved_microusd=reservation,
                updated_at=now,
            )
        )
        self.db.flush()
        return interval_id

    def provider_created(
        self, interval_id: uuid.UUID, sandbox_id: str, now: datetime | None = None
    ) -> None:
        row = self.db.get(ChatSandboxComputeInterval, interval_id)
        if row:
            row.modal_sandbox_id = sandbox_id
            row.provider_created_at = now or datetime.now(UTC)
            row.updated_at = now or datetime.now(UTC)

    def abort_reservation(
        self, interval_id: uuid.UUID, reason: str, now: datetime | None = None
    ) -> None:
        now = now or datetime.now(UTC)
        row = self.db.get(ChatSandboxComputeInterval, interval_id)
        if row and row.terminal_at is None:
            row.terminal_at = now
            row.terminal_reason = reason
            row.reserved_microusd = 0
            row.reconciliation_state = "creation_failed"
            row.updated_at = now

    def claim(
        self, sandbox_id: str, chat_session_id: uuid.UUID, now: datetime | None = None
    ) -> None:
        row = self.db.execute(
            select(ChatSandboxComputeInterval)
            .where(ChatSandboxComputeInterval.modal_sandbox_id == sandbox_id)
            .with_for_update()
        ).scalar_one_or_none()
        if row:
            row.chat_session_id = chat_session_id
            row.claimed_at = row.claimed_at or now or datetime.now(UTC)
            row.updated_at = now or datetime.now(UTC)

    def terminate(
        self,
        sandbox_id: str,
        reason: str | None,
        *,
        confirmed: bool,
        now: datetime | None = None,
    ) -> None:
        now = now or datetime.now(UTC)
        row = self.db.execute(
            select(ChatSandboxComputeInterval)
            .where(ChatSandboxComputeInterval.modal_sandbox_id == sandbox_id)
            .with_for_update()
        ).scalar_one_or_none()
        if row is None:
            cycle = billing_cycle(now)
            cycle_start = datetime(cycle.year, cycle.month, 1, tzinfo=UTC)
            row = ChatSandboxComputeInterval(
                id=uuid.uuid4(),
                modal_sandbox_id=sandbox_id,
                environment=self.settings.environment,
                modal_app=MODAL_APP_NAME,
                app_release_id=self.settings.release_id,
                image_version=self.settings.chat_modal_image_version,
                worker_generation="reconciled-orphan",
                origin="reconciled_orphan",
                cpu_request_millicores=round(self.settings.chat_sandbox_cpu * 1000),
                cpu_limit_millicores=round(
                    (
                        self.settings.chat_sandbox_cpu_limit
                        or self.settings.chat_sandbox_cpu
                    )
                    * 1000
                ),
                memory_request_mib=self.settings.chat_sandbox_memory_mib,
                memory_limit_mib=self.settings.chat_sandbox_memory_limit_mib
                or self.settings.chat_sandbox_memory_mib,
                reserved_at=max(
                    cycle_start,
                    now
                    - timedelta(
                        seconds=self.settings.chat_persistent_sandbox_lifetime_seconds
                    ),
                ),
                provider_created_at=None,
                billing_cycle=cycle,
                reserved_microusd=0 if confirmed else self.reservation_amount(),
                updated_at=now,
            )
            self.db.add(row)
        row.termination_requested_at = row.termination_requested_at or now
        row.terminal_reason = reason
        if confirmed:
            row.terminal_at = now
            row.reserved_microusd = 0
            row.reconciliation_state = "confirmed"
        else:
            row.reconciliation_state = "termination_uncertain"
        row.updated_at = now

    def reconcile_provider_floor(
        self, floor_microusd: int, reported_at: datetime
    ) -> ChatSandboxBudgetState:
        self._lock()
        self._state(reported_at, provider_cycle_confirmed=True)
        state = self.refresh(reported_at)
        was_degraded = state.reconciliation_state != "fresh"
        state.provider_floor_microusd = max(
            state.provider_floor_microusd, floor_microusd
        )
        state.last_reconciled_at = reported_at
        state.reconciliation_state = "fresh"
        state.updated_at = reported_at
        self._evaluate(state, reported_at)
        if was_degraded:
            self._event(
                state,
                "reconciliation_recovered",
                "recovery",
                None,
                reported_at,
                deduplicate=False,
            )
        return state

    def reconciliation_unavailable(
        self, now: datetime | None = None
    ) -> ChatSandboxBudgetState:
        now = now or datetime.now(UTC)
        state = self.refresh(now)
        was_unavailable = state.reconciliation_state == "unavailable"
        state.reconciliation_state = "unavailable"
        state.updated_at = now
        if not was_unavailable:
            self._event(
                state,
                "reconciliation_unavailable",
                "warning",
                "provider_budget",
                now,
                deduplicate=False,
            )
        return state

    def record_kill_sweep(
        self, *, complete: bool, now: datetime | None = None
    ) -> ChatSandboxBudgetState:
        now = now or datetime.now(UTC)
        state = self.refresh(now)
        self._event(
            state,
            "kill_sweep_complete" if complete else "kill_sweep_incomplete",
            "recovery" if complete else "critical",
            None if complete else "termination_uncertain",
            now,
        )
        return state

    def status(self, now: datetime | None = None) -> dict:
        now = now or datetime.now(UTC)
        state = self.refresh(now)
        effective = max(state.estimated_accrued_microusd, state.provider_floor_microusd)
        live = (
            self.db.execute(
                select(ChatSandboxComputeInterval).where(
                    ChatSandboxComputeInterval.environment == state.environment,
                    ChatSandboxComputeInterval.terminal_at.is_(None),
                )
            )
            .scalars()
            .all()
        )
        leases = self.db.execute(
            select(ChatSandboxLease.state, func.count()).group_by(
                ChatSandboxLease.state
            )
        ).all()
        pools = self.db.execute(
            select(ChatSandboxPool.state, func.count()).group_by(ChatSandboxPool.state)
        ).all()
        live_states = {
            "starting": 0,
            "blank": 0,
            "busy": 0,
            "idle": 0,
            "draining": 0,
            "termination_uncertain": 0,
        }
        for lifecycle_state, count in leases:
            key = "draining" if lifecycle_state == "terminating" else lifecycle_state
            if key in live_states:
                live_states[key] += count
        for lifecycle_state, count in pools:
            key = {"blank_ready": "blank", "draining": "draining"}.get(
                lifecycle_state, lifecycle_state
            )
            if key in live_states:
                live_states[key] += count
        live_states["termination_uncertain"] = sum(
            row.reconciliation_state == "termination_uncertain" for row in live
        )
        daily: dict[str, dict[str, int]] = {}
        cycle_rows = (
            self.db.execute(
                select(ChatSandboxComputeInterval).where(
                    ChatSandboxComputeInterval.environment == state.environment,
                    ChatSandboxComputeInterval.billing_cycle == state.billing_cycle,
                )
            )
            .scalars()
            .all()
        )
        for row in cycle_rows:
            day = row.reserved_at.date().isoformat()
            bucket = daily.setdefault(
                day, {"blank_pool_microusd": 0, "assigned_microusd": 0}
            )
            bucket[
                "blank_pool_microusd"
                if row.origin == "blank_pool" and row.claimed_at is None
                else "assigned_microusd"
            ] += row.accrued_microusd
        events = (
            self.db.execute(
                select(ChatSandboxCircuitEvent)
                .where(ChatSandboxCircuitEvent.budget_state_id == state.id)
                .order_by(ChatSandboxCircuitEvent.created_at.desc())
                .limit(20)
            )
            .scalars()
            .all()
        )
        reconciled_at = state.last_reconciled_at
        if reconciled_at is not None and reconciled_at.tzinfo is None:
            reconciled_at = reconciled_at.replace(tzinfo=UTC)
        age = (
            None
            if reconciled_at is None
            else int((now - reconciled_at).total_seconds())
        )
        reconciliation = (
            "unavailable"
            if age is None or state.reconciliation_state == "unavailable"
            else (
                "stale"
                if age > self.settings.chat_sandbox_reconciliation_stale_seconds
                else "fresh"
            )
        )
        if reconciliation == "stale" and state.reconciliation_state != "stale":
            state.reconciliation_state = "stale"
            self._event(
                state,
                "reconciliation_stale",
                "warning",
                "provider_budget",
                now,
                deduplicate=False,
            )
        return {
            "environment": state.environment,
            "billing_cycle": state.billing_cycle.isoformat(),
            "cycle_end_at": state.cycle_end_at,
            "circuit_state": state.circuit_state,
            "trip_reason": state.trip_reason,
            "tripped_at": state.tripped_at,
            "estimated_microusd": state.estimated_accrued_microusd,
            "provider_floor_microusd": state.provider_floor_microusd,
            "effective_microusd": effective,
            "warning_microusd": state.warning_microusd,
            "application_cap_microusd": state.application_cap_microusd,
            "environment_cap_microusd": state.environment_cap_microusd,
            "workspace_cap_microusd": state.workspace_cap_microusd,
            "remaining_microusd": max(
                0,
                state.application_cap_microusd
                - effective
                - state.outstanding_reservation_microusd,
            ),
            "outstanding_reservation_microusd": state.outstanding_reservation_microusd,
            "last_metered_at": state.last_metered_at,
            "last_reconciled_at": state.last_reconciled_at,
            "next_reconciliation_at": (
                None if reconciled_at is None else reconciled_at + timedelta(hours=1)
            ),
            "reconciliation_state": reconciliation,
            "live_count": len(live),
            "termination_uncertain_count": sum(
                row.reconciliation_state == "termination_uncertain" for row in live
            ),
            "live_states": live_states,
            "oldest_live_at": min((row.reserved_at for row in live), default=None),
            "burn_rate_microusd_per_hour": None,
            "projected_cap_hit_at": None,
            "daily_spend": [
                {"date": day, **values} for day, values in sorted(daily.items())
            ],
            "events": [
                {
                    "id": str(event.id),
                    "type": event.event_type,
                    "severity": event.severity,
                    "reason": event.reason,
                    "created_at": event.created_at,
                }
                for event in events
            ],
        }
