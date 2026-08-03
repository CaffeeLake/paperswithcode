"""Exercise spend thresholds without creating or purchasing provider compute."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from sqlalchemy import select

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.models.database import ChatSandboxBudgetState, ChatSandboxCircuitEvent
from backend.services.chat_sandbox_service import SandboxSessionManager
from backend.services.chat_sandbox_spend_service import (
    ChatComputeDisabled,
    ChatSandboxSpendService,
    cycle_end,
)

CONFIRMATION = "QUALIFY_STAGING_CHAT_SPEND"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qualification-id", required=True)
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    if args.confirm != CONFIRMATION:
        parser.error(f"--confirm must be {CONFIRMATION}")
    if not re.fullmatch(r"[a-z0-9]{4,12}", args.qualification_id):
        parser.error("--qualification-id must be 4-12 lowercase letters or digits")
    base = get_settings()
    if base.environment != "staging" or not base.chat_sandbox_spend_enforcement_enabled:
        parser.error("qualification requires deployed staging spend enforcement")
    environment = f"staging-q-{args.qualification_id}"
    settings = base.model_copy(update={"environment": environment})
    now = datetime.now(UTC)
    samples = (
        (74_990_000, "armed"),
        (75_000_000, "warning"),
        (99_990_000, "warning"),
        (100_000_000, "tripped"),
    )
    observed = []
    with db_manager.session_local() as db, db.begin():
        existing = db.execute(
            select(ChatSandboxBudgetState.id).where(
                ChatSandboxBudgetState.environment == environment
            )
        ).first()
        if existing is not None:
            parser.error("qualification ID has already been used; choose a new ID")
        service = ChatSandboxSpendService(db, settings)
        for floor, expected in samples:
            state = service.reconcile_provider_floor(floor, now)
            if state.circuit_state != expected:
                raise RuntimeError(
                    f"threshold {floor} produced {state.circuit_state}, expected {expected}"
                )
            observed.append(
                {"effective_microusd": floor, "circuit_state": state.circuit_state}
            )
        service.record_kill_sweep(complete=True, now=now)
    reservation_environment = f"{environment}-r"
    with db_manager.session_local() as db:
        reservation = ChatSandboxSpendService(db, settings).reservation_amount()
    reservation_settings = settings.model_copy(
        update={
            "environment": reservation_environment,
            "chat_sandbox_warning_microusd": 1,
            "chat_sandbox_application_cap_microusd": reservation * 3 + 1,
            "chat_sandbox_environment_cap_microusd": reservation * 4 + 1,
            "chat_sandbox_workspace_cap_microusd": reservation * 5 + 1,
            "chat_sandbox_budget_attestation": "synthetic-concurrency-v1",
        }
    )

    def reserve(index: int) -> str | None:
        with db_manager.session_local() as db, db.begin():
            try:
                return str(
                    ChatSandboxSpendService(db, reservation_settings).reserve_interval(
                        origin="qualification",
                        worker_generation=f"qualification-{index}",
                        now=now,
                    )
                )
            except ChatComputeDisabled:
                return None

    with ThreadPoolExecutor(max_workers=8) as executor:
        reservations = list(executor.map(reserve, range(8)))
    accepted_reservations = [value for value in reservations if value is not None]
    if len(accepted_reservations) != 3:
        raise RuntimeError(
            "atomic reservation qualification did not admit exactly three reservations"
        )
    with db_manager.session_local() as db, db.begin():
        restarted = ChatSandboxSpendService(db, settings).status(now)
        if restarted["circuit_state"] != "tripped":
            raise RuntimeError("trip did not survive a fresh service instance")
        next_cycle = restarted["cycle_end_at"]
        rearmed = ChatSandboxSpendService(db, settings).reconcile_provider_floor(
            0, next_cycle
        )
        if rearmed.circuit_state != "armed":
            raise RuntimeError("synthetic next-cycle re-arm failed")
    delivered = asyncio.run(SandboxSessionManager(settings).deliver_spend_alerts())
    with db_manager.session_local() as db:
        events = list(
            db.execute(
                select(
                    ChatSandboxCircuitEvent.event_type,
                    ChatSandboxCircuitEvent.delivery_state,
                )
                .join(
                    ChatSandboxBudgetState,
                    ChatSandboxBudgetState.id
                    == ChatSandboxCircuitEvent.budget_state_id,
                )
                .where(ChatSandboxBudgetState.environment == environment)
            ).all()
        )
    required_events = {"warning_entered", "circuit_tripped", "cycle_rearmed"}
    observed_events = {event_type for event_type, _state in events}
    if not required_events <= observed_events:
        raise RuntimeError(
            "required warning, trip, and recovery events were not emitted"
        )
    if any(state != "delivered" for _event_type, state in events):
        raise RuntimeError("one or more synthetic alert transitions were not delivered")
    report = {
        "environment": environment,
        "samples": observed,
        "restart_persisted": True,
        "next_cycle": cycle_end(now.date().replace(day=1)).isoformat(),
        "next_cycle_rearmed": True,
        "alerts_delivered": delivered,
        "event_types": sorted(observed_events),
        "concurrent_reservations": {
            "attempted": 8,
            "accepted": len(accepted_reservations),
            "rejected": 8 - len(accepted_reservations),
        },
        "admin_path": f"/api/v1/chat/admin/sandbox-spend?environment={environment}",
        "provider_compute_created": 0,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
