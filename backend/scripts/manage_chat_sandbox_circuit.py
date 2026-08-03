"""Audited exceptional early re-arm for the sandbox spend circuit."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime

from sqlalchemy import func, select

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.models.database import ChatSandboxCircuitEvent, ChatSandboxComputeInterval
from backend.services.chat_sandbox_spend_service import ChatSandboxSpendService


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", required=True)
    parser.add_argument("--cycle", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument(
        "--basis",
        required=True,
        choices=("accounting-correction", "reviewed-higher-caps"),
    )
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    settings = get_settings()
    expected = f"REARM_{settings.environment.upper()}_{args.cycle}"
    if args.environment != settings.environment or args.confirm != expected:
        raise SystemExit(f"confirmation must be {expected}")
    if not args.reason.strip():
        raise SystemExit("reason is required")
    now = datetime.now(UTC)
    with db_manager.session_local() as db, db.begin():
        service = ChatSandboxSpendService(db, settings)
        state = service.refresh(now)
        live = (
            db.scalar(
                select(func.count())
                .select_from(ChatSandboxComputeInterval)
                .where(ChatSandboxComputeInterval.terminal_at.is_(None))
            )
            or 0
        )
        effective = max(state.estimated_accrued_microusd, state.provider_floor_microusd)
        print(
            {
                "old_state": state.circuit_state,
                "effective_microusd": effective,
                "provider_floor_microusd": state.provider_floor_microusd,
                "remaining_microusd": state.application_cap_microusd - effective,
                "live_sandboxes": live,
                "old_policy_microusd": {
                    "warning": state.warning_microusd,
                    "application": state.application_cap_microusd,
                    "environment": state.environment_cap_microusd,
                    "workspace": state.workspace_cap_microusd,
                },
                "configured_policy_microusd": {
                    "warning": settings.chat_sandbox_warning_microusd,
                    "application": settings.chat_sandbox_application_cap_microusd,
                    "environment": settings.chat_sandbox_environment_cap_microusd,
                    "workspace": settings.chat_sandbox_workspace_cap_microusd,
                },
                "basis": args.basis,
            }
        )
        if (
            state.billing_cycle.isoformat() != args.cycle
            or live
            or state.outstanding_reservation_microusd
        ):
            raise SystemExit("cycle, live sandbox, or reservation safety check failed")
        active_cap = (
            settings.chat_sandbox_application_cap_microusd
            if args.basis == "reviewed-higher-caps"
            else state.application_cap_microusd
        )
        if args.basis == "reviewed-higher-caps" and (
            settings.chat_sandbox_budget_attestation == state.policy_attestation
            or active_cap <= state.application_cap_microusd
        ):
            raise SystemExit(
                "reviewed higher caps require a higher configured application cap and new attestation"
            )
        if state.reconciliation_state != "fresh" or effective >= active_cap:
            raise SystemExit(
                "fresh reconciliation below the active application cap is required"
            )
        if args.basis == "reviewed-higher-caps":
            state.warning_microusd = settings.chat_sandbox_warning_microusd
            state.application_cap_microusd = active_cap
            state.environment_cap_microusd = (
                settings.chat_sandbox_environment_cap_microusd
            )
            state.workspace_cap_microusd = settings.chat_sandbox_workspace_cap_microusd
            state.policy_attestation = settings.chat_sandbox_budget_attestation
        state.circuit_state = "armed"
        state.trip_reason = None
        state.tripped_at = None
        state.updated_at = now
        db.add(
            ChatSandboxCircuitEvent(
                id=__import__("uuid").uuid4(),
                budget_state_id=state.id,
                event_type="operator_rearmed",
                severity="critical",
                reason=args.reason,
                details={
                    "environment": settings.environment,
                    "billing_cycle": args.cycle,
                    "release": settings.release_id,
                    "basis": args.basis,
                    "effective_microusd": effective,
                    "provider_floor_microusd": state.provider_floor_microusd,
                },
                created_at=now,
            )
        )


if __name__ == "__main__":
    main()
