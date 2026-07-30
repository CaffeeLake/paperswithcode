"""Content-free persistence for staging chat latency measurements."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from math import isfinite
from typing import Any

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import (
    ChatSession,
    ChatTurnLatency,
)

RETENTION_DAYS = 30
MAX_DURATION_MS = 3_600_000
DEFAULT_CLEANUP_BATCH_SIZE = 500
MAX_CLEANUP_BATCH_SIZE = 5_000
MODAL_CPU_USD_PER_CORE_SECOND = 0.00003942
MODAL_MEMORY_USD_PER_GIB_SECOND = 0.00000672
ACTIVE_SPEND_ALERT_FLOOR_USD = 50.0
ACTIVE_SPEND_LOOKBACK_DAYS = 7
ACTIVE_SPEND_BASELINE_DAYS = 30
ACTIVE_SPEND_ALERT_MULTIPLIER = 2.0
MIN_ACTIVE_SPEND_OBSERVATION_SECONDS = 60.0

PHASE_COLUMNS = {
    "sandbox_acquisition_started": "acquisition_started_ms",
    "sandbox_acquisition_ms": "acquisition_started_ms",
    "pool_lookup_completed": "pool_lookup_completed_ms",
    "modal_sandbox_created": "modal_sandbox_created_ms",
    "modal_create_ms": "modal_sandbox_created_ms",
    "worker_control_ready": "worker_control_ready_ms",
    "worker_ready_ms": "worker_control_ready_ms",
    "session_assignment_completed": "session_assignment_completed_ms",
    "broker_capability_installed": "broker_capability_installed_ms",
    "capability_install_ms": "broker_capability_installed_ms",
    "sdk_query_dispatched": "sdk_query_dispatched_ms",
    "sdk_dispatch_ms": "sdk_query_dispatched_ms",
    "provider_gateway_received": "provider_gateway_received_ms",
    "upstream_response_headers": "upstream_response_headers_ms",
    "upstream_first_body_byte": "upstream_first_body_byte_ms",
    "first_worker_delta": "first_worker_delta_ms",
    "first_application_sse_delta": "first_application_sse_delta_ms",
}
ACQUISITION_OUTCOMES = {
    "pending",
    "created",
    "reused_session",
    "pool_hit",
    "pool_miss",
}
TERMINAL_STATUSES = {"complete", "stopped", "error", "interrupted"}
BROWSER_TERMINAL_CLASSIFICATIONS = {
    "complete",
    "stopped",
    "error",
    "network_error",
    "aborted",
}


def _bounded_duration(value: Any, name: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
    ):
        raise ValueError(f"{name} must be a finite number")
    if not 0 <= value <= MAX_DURATION_MS:
        raise ValueError(f"{name} is out of range")
    return round(value)


def _payload_value(payload: object, name: str) -> Any:
    if isinstance(payload, dict):
        return payload.get(name)
    return getattr(payload, name, None)


class ChatLatencyService:
    """Write one sanitized latency record per admitted chat turn."""

    def __init__(self, db: Session):
        self.db = db

    def admit(
        self,
        *,
        turn_id: uuid.UUID,
        session_id: uuid.UUID,
        request_id: str,
        settings: Settings,
        model_route: str,
        execution_backend: str,
        is_new_chat: bool,
    ) -> ChatTurnLatency:
        if execution_backend not in {"local_mcp", "modal_cli"}:
            raise ValueError("Unsupported chat execution backend")
        try:
            request_uuid = uuid.UUID(request_id)
        except ValueError:
            raise ValueError("request_id must be a UUID") from None
        existing = self.db.execute(
            select(ChatTurnLatency).where(ChatTurnLatency.request_id == request_uuid)
        ).scalar_one_or_none()
        if existing is not None:
            if existing.chat_session_id != session_id or existing.turn_id != turn_id:
                raise ValueError("Request reference is already bound to another turn")
            return existing

        row = ChatTurnLatency(
            turn_id=turn_id,
            request_id=request_uuid,
            chat_session_id=session_id,
            traffic_class="new_chat" if is_new_chat else "followup",
            execution_backend=execution_backend,
            model_route=model_route,
            app_release_id=settings.release_id,
            sandbox_image_version=settings.chat_modal_image_version or None,
            worker_contract_version=settings.chat_worker_contract_version or None,
            pwc_cli_version=settings.chat_pwc_cli_version or None,
            system_prompt_sha256=settings.chat_system_prompt_sha256 or None,
            sandbox_cpu_request=(
                settings.chat_sandbox_cpu if execution_backend == "modal_cli" else None
            ),
            sandbox_memory_request_mib=(
                settings.chat_sandbox_memory_mib
                if execution_backend == "modal_cli"
                else None
            ),
            acquisition_outcome="pending",
            terminal_status="running",
        )
        self.db.add(row)
        self.db.flush()
        return row

    def record_phase(
        self,
        request_id: str,
        phase: str,
        elapsed_ms: int,
        *,
        acquisition_outcome: str | None = None,
    ) -> bool:
        column_name = PHASE_COLUMNS.get(phase)
        if column_name is None:
            raise ValueError(f"Unsupported latency phase: {phase}")
        elapsed_ms = _bounded_duration(elapsed_ms, "elapsed_ms")
        values: dict[str, Any] = {
            column_name: elapsed_ms,
            "updated_at": datetime.now(UTC),
        }
        if acquisition_outcome is not None:
            if acquisition_outcome not in ACQUISITION_OUTCOMES - {"pending"}:
                raise ValueError("Unsupported sandbox acquisition outcome")
            values["acquisition_outcome"] = acquisition_outcome
        result = self.db.execute(
            update(ChatTurnLatency)
            .where(
                ChatTurnLatency.request_id == uuid.UUID(request_id),
                getattr(ChatTurnLatency, column_name).is_(None),
                ChatTurnLatency.terminal_status == "running",
            )
            .values(**values)
        )
        return bool(result.rowcount)

    def record_phase_for_turn(
        self,
        turn_id: uuid.UUID,
        phase: str,
        elapsed_ms: int,
    ) -> bool:
        column_name = PHASE_COLUMNS.get(phase)
        if column_name is None:
            raise ValueError(f"Unsupported latency phase: {phase}")
        elapsed_ms = _bounded_duration(elapsed_ms, "elapsed_ms")
        result = self.db.execute(
            update(ChatTurnLatency)
            .where(
                ChatTurnLatency.turn_id == turn_id,
                getattr(ChatTurnLatency, column_name).is_(None),
                ChatTurnLatency.terminal_status == "running",
            )
            .values(**{column_name: elapsed_ms, "updated_at": datetime.now(UTC)})
        )
        return bool(result.rowcount)

    def record_gateway_received(
        self,
        turn_id: uuid.UUID,
        received_at: datetime,
    ) -> bool:
        if received_at.tzinfo is None:
            raise ValueError("received_at must be timezone-aware")
        admitted_at = self.db.execute(
            select(ChatTurnLatency.admitted_at).where(
                ChatTurnLatency.turn_id == turn_id
            )
        ).scalar_one_or_none()
        if admitted_at is None:
            return False
        if admitted_at.tzinfo is None:
            admitted_at = admitted_at.replace(tzinfo=UTC)
        elapsed_ms = round((received_at - admitted_at).total_seconds() * 1000)
        return self.record_phase_for_turn(
            turn_id, "provider_gateway_received", elapsed_ms
        )

    def finalize(self, request_id: str, status: str, total_ms: int) -> bool:
        if status not in TERMINAL_STATUSES:
            raise ValueError("Unsupported terminal latency status")
        total_ms = _bounded_duration(total_ms, "total_ms")
        now = datetime.now(UTC)
        row = self.db.execute(
            select(
                ChatTurnLatency.execution_backend,
                ChatTurnLatency.sandbox_cpu_request,
                ChatTurnLatency.sandbox_memory_request_mib,
            ).where(ChatTurnLatency.request_id == uuid.UUID(request_id))
        ).one_or_none()
        estimated_active_cost_usd = None
        if (
            row is not None
            and row.execution_backend == "modal_cli"
            and row.sandbox_cpu_request is not None
            and row.sandbox_memory_request_mib is not None
        ):
            seconds = total_ms / 1000
            estimated_active_cost_usd = seconds * (
                float(row.sandbox_cpu_request) * MODAL_CPU_USD_PER_CORE_SECOND
                + (row.sandbox_memory_request_mib / 1024)
                * MODAL_MEMORY_USD_PER_GIB_SECOND
            )
        result = self.db.execute(
            update(ChatTurnLatency)
            .where(
                ChatTurnLatency.request_id == uuid.UUID(request_id),
                ChatTurnLatency.terminal_status == "running",
                ChatTurnLatency.total_ms.is_(None),
            )
            .values(
                terminal_status=status,
                total_ms=total_ms,
                estimated_active_cost_usd=estimated_active_cost_usd,
                completed_at=now,
                updated_at=now,
            )
        )
        return bool(result.rowcount)

    def update_browser(
        self,
        owner_id: str,
        request_id: str,
        payload: object,
    ) -> bool:
        try:
            request_uuid = uuid.UUID(request_id)
        except ValueError:
            raise ValueError("request_id must be a UUID") from None
        latency = self.db.execute(
            select(ChatTurnLatency)
            .join(ChatSession, ChatSession.id == ChatTurnLatency.chat_session_id)
            .where(
                ChatTurnLatency.request_id == request_uuid,
                ChatSession.hf_user_id == owner_id,
            )
        ).scalar_one_or_none()
        if latency is None:
            return False

        supplied = {
            "browser_stream_start_ms": _payload_value(
                payload, "submission_to_stream_start_ms"
            ),
            "browser_first_visible_delta_ms": _payload_value(
                payload, "submission_to_first_visible_delta_ms"
            ),
            "browser_terminal_classification": _payload_value(
                payload, "terminal_classification"
            ),
        }
        values: dict[str, Any] = {"updated_at": datetime.now(UTC)}
        null_conditions = []
        for column_name, value in supplied.items():
            if value is None:
                continue
            if column_name == "browser_terminal_classification":
                if value not in BROWSER_TERMINAL_CLASSIFICATIONS:
                    raise ValueError("Unsupported browser terminal classification")
            else:
                value = _bounded_duration(value, column_name)
            column = getattr(ChatTurnLatency, column_name)
            values[column_name] = func.coalesce(column, value)
            null_conditions.append(column.is_(None))
        if not null_conditions:
            raise ValueError("Browser timing update is empty")

        self.db.execute(
            update(ChatTurnLatency)
            .where(
                ChatTurnLatency.request_id == request_uuid,
                ChatTurnLatency.chat_session_id == latency.chat_session_id,
                or_(*null_conditions),
            )
            .values(**values)
        )
        # An authenticated duplicate is still a successful idempotent update;
        # COALESCE above preserves the first value for each timing class.
        return True

    def active_spend_status(self, *, now: datetime | None = None) -> dict[str, Any]:
        """Return content-free active-compute spend and alert projections."""
        observed_at = now or datetime.now(UTC)
        if observed_at.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        observed_at = observed_at.astimezone(UTC)
        month_start = observed_at.replace(
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        next_month = (
            month_start.replace(year=month_start.year + 1, month=1)
            if month_start.month == 12
            else month_start.replace(month=month_start.month + 1)
        )
        cost = ChatTurnLatency.estimated_active_cost_usd
        cost_recorded = cost.is_not(None)
        in_month = (ChatTurnLatency.completed_at >= month_start) & (
            ChatTurnLatency.completed_at <= observed_at
        )
        trailing_start = observed_at - timedelta(days=ACTIVE_SPEND_LOOKBACK_DAYS)

        month_cost, first_observation = self.db.execute(
            select(
                func.coalesce(func.sum(cost), 0),
                func.min(ChatTurnLatency.completed_at),
            ).where(cost_recorded, in_month)
        ).one()
        completed_turns = int(
            self.db.scalar(
                select(func.count())
                .select_from(ChatTurnLatency)
                .where(
                    cost_recorded,
                    in_month,
                    ChatTurnLatency.terminal_status == "complete",
                )
            )
            or 0
        )
        trailing_cost = float(
            self.db.scalar(
                select(func.coalesce(func.sum(cost), 0)).where(
                    cost_recorded,
                    ChatTurnLatency.completed_at >= trailing_start,
                    ChatTurnLatency.completed_at <= observed_at,
                )
            )
            or 0
        )
        month_cost = float(month_cost or 0)
        cost_per_completed_turn = (
            month_cost / completed_turns if completed_turns else 0.0
        )

        projected_monthly_cost = 0.0
        if first_observation is not None and month_cost:
            if first_observation.tzinfo is None:
                first_observation = first_observation.replace(tzinfo=UTC)
            observation_seconds = max(
                (observed_at - first_observation).total_seconds(),
                MIN_ACTIVE_SPEND_OBSERVATION_SECONDS,
            )
            projected_monthly_cost = (
                month_cost
                / observation_seconds
                * (next_month - month_start).total_seconds()
            )

        trailing_daily_average = trailing_cost / ACTIVE_SPEND_LOOKBACK_DAYS
        trailing_30_day_projection = trailing_daily_average * ACTIVE_SPEND_BASELINE_DAYS
        alert_threshold = max(
            ACTIVE_SPEND_ALERT_FLOOR_USD,
            ACTIVE_SPEND_ALERT_MULTIPLIER * trailing_30_day_projection,
        )
        return {
            "month_to_date_cost_usd": month_cost,
            "completed_turns": completed_turns,
            "cost_per_completed_turn_usd": cost_per_completed_turn,
            "projected_monthly_cost_usd": projected_monthly_cost,
            "trailing_seven_day_cost_usd": trailing_cost,
            "trailing_daily_average_usd": trailing_daily_average,
            "trailing_30_day_projection_usd": trailing_30_day_projection,
            "alert_threshold_usd": alert_threshold,
            "should_alert": projected_monthly_cost > alert_threshold,
        }

    def cleanup(
        self,
        batch_size: int = DEFAULT_CLEANUP_BATCH_SIZE,
        *,
        now: datetime | None = None,
    ) -> int:
        if not 1 <= batch_size <= MAX_CLEANUP_BATCH_SIZE:
            raise ValueError("cleanup batch_size is out of range")
        cutoff = (now or datetime.now(UTC)) - timedelta(days=RETENTION_DAYS)
        ids = list(
            self.db.execute(
                select(ChatTurnLatency.turn_id)
                .where(ChatTurnLatency.admitted_at < cutoff)
                .order_by(ChatTurnLatency.admitted_at, ChatTurnLatency.turn_id)
                .limit(batch_size)
            ).scalars()
        )
        if not ids:
            return 0
        result = self.db.execute(
            delete(ChatTurnLatency).where(ChatTurnLatency.turn_id.in_(ids))
        )
        return max(result.rowcount or 0, 0)
