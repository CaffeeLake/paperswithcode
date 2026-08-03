#!/usr/bin/env python3
"""Content-free, release-scoped audit for the staging chat soak."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, or_, select

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.models.database import (
    ChatMessageRecord,
    ChatSandboxLease,
    ChatSandboxPool,
    ChatSession,
    ChatTurnLatency,
)
from backend.scripts.qualify_chat_sandbox import settings_for_release
from backend.services.chat_latency_service import ChatLatencyService
from backend.services.chat_sandbox_service import SandboxSessionManager
from backend.services.chat_sandbox_spend_service import ChatSandboxSpendService
from backend.services.openrouter_budget_service import (
    OpenRouterBudgetUnavailable,
    openrouter_budget_status,
)

CONFIRMATION = "AUDIT_STAGING_CHAT_SOAK"
SOAK_DURATION = timedelta(days=7)
MINIMUM_SLO_SAMPLES = 25
JOURNAL_UNITS = (
    "paperswithcode-backend@staging",
    "paperswithcode-staging-backend@blue",
    "paperswithcode-staging-backend@green",
)
JOURNAL_FAILURE_PATTERNS = {
    "pool_replenishment_failure": "chat blank pool replenishment failed",
    "pool_budget_block": "chat blank pool budget blocked",
    "turn_cleanup_failure": "chat cleanup failed",
    "edit_cleanup_failure": "chat edit preparation cleanup failed",
    "background_task_failure": "chat background task failed",
    "stream_persistence_failure": "chat stream persistence failed",
    "research_producer_failure": "chat research producer failed",
    "transcript_mirror_failure": "chat transcript mirror failed",
    "transcript_reconciliation_failure": "chat transcript reconciliation failed",
    "latency_finalize_failure": "chat latency finalize failed",
    "latency_phase_failure": "chat latency phase failed",
    "stale_turn_reconciliation": "chat stale turns reconciled",
    "langfuse_initialization_failure": "chat Langfuse trace initialization failed",
    "langfuse_finalization_failure": "chat Langfuse trace finalization failed",
    "langfuse_client_failure": "chat Langfuse client initialization failed",
}


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("The soak start must include a timezone")
    return parsed.astimezone(UTC)


def _count(db, *predicates) -> int:
    return int(
        db.scalar(select(func.count()).select_from(ChatTurnLatency).where(*predicates))
        or 0
    )


def _percentile(db, column, *predicates) -> dict[str, int] | None:
    row = db.execute(
        select(
            func.count(column),
            func.percentile_cont(0.5).within_group(column),
            func.percentile_cont(0.95).within_group(column),
            func.percentile_cont(0.99).within_group(column),
            func.max(column),
        )
        .select_from(ChatTurnLatency)
        .join(ChatSession, ChatSession.id == ChatTurnLatency.chat_session_id)
        .where(*predicates, column.is_not(None))
    ).one()
    if not row[0]:
        return None
    return {
        "count": int(row[0]),
        "p50": round(float(row[1])),
        "p95": round(float(row[2])),
        "p99": round(float(row[3])),
        "max": int(row[4]),
    }


def _journal_counts(start: datetime) -> dict[str, int]:
    command = ["journalctl"]
    for unit in JOURNAL_UNITS:
        command.extend(["-u", unit])
    command.extend(
        [
            "--since",
            start.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "--no-pager",
            "--output=cat",
        ]
    )
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )
    lines = result.stdout.splitlines()
    counts = {
        name: sum(pattern in line for line in lines)
        for name, pattern in JOURNAL_FAILURE_PATTERNS.items()
    }
    counts["langfuse_trace_complete"] = sum(
        "chat Langfuse trace complete" in line for line in lines
    )
    counts["session_store_forbidden"] = sum(
        "POST /api/internal/chat-gateway/session-store" in line
        and "403 Forbidden" in line
        for line in lines
    )
    return counts


def _status(
    *,
    now: datetime,
    finish: datetime,
    sample_gates: dict[str, bool],
    health_gates: dict[str, bool],
) -> str:
    if not all(health_gates.values()):
        return "failed"
    if now < finish:
        return "soaking"
    if not all(sample_gates.values()):
        return "insufficient_samples"
    return "telemetry_ready"


def audit(start: datetime, release_dir: Path) -> tuple[dict, bool]:
    now = datetime.now(UTC)
    finish = start + SOAK_DURATION
    environment = get_settings()
    release = settings_for_release(release_dir)
    if environment.environment != "staging":
        raise ValueError("The soak audit requires the staging environment")
    active_release = Path("/srv/paperswithcode/environments/staging/current").resolve()
    if active_release.exists() and release_dir.resolve() != active_release:
        raise ValueError("The audited release is not the active staging release")

    with db_manager.session_local() as db:
        candidate = ChatTurnLatency.app_release_id == release.release_id
        in_window = ChatTurnLatency.admitted_at >= start
        scope = (candidate, in_window)
        complete = ChatTurnLatency.terminal_status == "complete"
        new_chat = ChatTurnLatency.traffic_class == "new_chat"
        followup = ChatTurnLatency.traffic_class == "followup"
        slo_traffic = or_(
            ChatTurnLatency.qualification_scenario.is_(None),
            ChatTurnLatency.qualification_scenario == "focused_latency",
        )
        new_total = _count(db, *scope, new_chat)
        pool_hits = _count(
            db,
            *scope,
            new_chat,
            ChatTurnLatency.acquisition_outcome == "pool_hit",
        )
        pool_misses = _count(
            db,
            *scope,
            new_chat,
            ChatTurnLatency.acquisition_outcome == "pool_miss",
        )
        followup_complete = _count(db, *scope, followup, complete)
        durable_stops = _count(
            db,
            *scope,
            ChatTurnLatency.terminal_status == "stopped",
            ChatTurnLatency.qualification_scenario == "clean_cancel",
        )
        expected_errors = _count(
            db,
            *scope,
            ChatTurnLatency.terminal_status == "error",
            ChatTurnLatency.qualification_scenario == "forced_failure",
        )
        unexpected_errors = _count(
            db,
            *scope,
            ChatTurnLatency.terminal_status == "error",
            or_(
                ChatTurnLatency.qualification_scenario.is_(None),
                ChatTurnLatency.qualification_scenario != "forced_failure",
            ),
        )
        stale_turns = int(
            db.scalar(
                select(func.count())
                .select_from(ChatTurnLatency)
                .join(ChatSession, ChatSession.id == ChatTurnLatency.chat_session_id)
                .where(
                    *scope,
                    ChatTurnLatency.terminal_status == "running",
                    or_(
                        ChatSession.active_turn_id.is_(None),
                        ChatSession.active_turn_id != ChatTurnLatency.turn_id,
                        ChatSession.active_turn_expires_at.is_(None),
                        ChatSession.active_turn_expires_at <= now,
                    ),
                )
            )
            or 0
        )
        degraded_transcripts = int(
            db.scalar(
                select(func.count(func.distinct(ChatSession.id)))
                .select_from(ChatSession)
                .join(
                    ChatTurnLatency,
                    ChatTurnLatency.chat_session_id == ChatSession.id,
                )
                .where(
                    *scope,
                    ChatSession.transcript_status == "degraded",
                )
            )
            or 0
        )
        error_codes = {
            str(code or "unclassified"): int(count)
            for code, count in db.execute(
                select(ChatMessageRecord.error_code, func.count())
                .select_from(ChatTurnLatency)
                .join(
                    ChatMessageRecord,
                    (ChatMessageRecord.session_id == ChatTurnLatency.chat_session_id)
                    & (ChatMessageRecord.turn_id == ChatTurnLatency.turn_id),
                )
                .where(
                    *scope,
                    ChatTurnLatency.terminal_status == "error",
                )
                .group_by(ChatMessageRecord.error_code)
            ).all()
        }
        new_chat_pre_provider = _percentile(
            db,
            ChatTurnLatency.provider_gateway_received_ms,
            *scope,
            new_chat,
            complete,
            slo_traffic,
        )
        pool_hit_pre_provider = _percentile(
            db,
            ChatTurnLatency.provider_gateway_received_ms,
            *scope,
            new_chat,
            complete,
            slo_traffic,
            ChatTurnLatency.acquisition_outcome == "pool_hit",
        )
        followup_pre_provider = _percentile(
            db,
            ChatTurnLatency.provider_gateway_received_ms,
            *scope,
            followup,
            complete,
            slo_traffic,
            ChatTurnLatency.acquisition_outcome == "reused_session",
        )
        active_spend = ChatLatencyService(db).active_spend_status(now=now)
        sandbox_spend = ChatSandboxSpendService(db, environment).status(now=now)
        live_pool = list(
            db.execute(
                select(
                    ChatSandboxPool.worker_contract_version,
                    ChatSandboxPool.image_version,
                    ChatSandboxPool.state,
                    func.count(),
                )
                .where(
                    ChatSandboxPool.state.in_(["starting", "blank_ready", "draining"])
                )
                .group_by(
                    ChatSandboxPool.worker_contract_version,
                    ChatSandboxPool.image_version,
                    ChatSandboxPool.state,
                )
            ).all()
        )
        live_leases = list(
            db.execute(
                select(
                    ChatSandboxLease.worker_contract_version,
                    ChatSandboxLease.image_version,
                    ChatSandboxLease.state,
                    func.count(),
                )
                .where(
                    ChatSandboxLease.state.in_(["starting", "ready", "busy", "idle"])
                )
                .group_by(
                    ChatSandboxLease.worker_contract_version,
                    ChatSandboxLease.image_version,
                    ChatSandboxLease.state,
                )
            ).all()
        )

    journal = _journal_counts(start)
    journal_critical = (
        sum(journal[name] for name in JOURNAL_FAILURE_PATTERNS)
        + journal["session_store_forbidden"]
    )
    live_rows = [*live_pool, *live_leases]
    live_count = sum(int(row[3]) for row in live_rows)
    compatible = all(
        row[0] == release.chat_worker_contract_version
        and row[1] == release.chat_modal_image_version
        for row in live_rows
    )
    pool_budget = SandboxSessionManager(environment).pool_budget_status()
    try:
        openrouter_budget = asyncio.run(
            openrouter_budget_status(environment)
        ).sanitized()
    except OpenRouterBudgetUnavailable:
        openrouter_budget = {
            "enabled": environment.chat_openrouter_server_funded_enabled,
            "within_budget": False,
            "status": "unavailable",
        }
    sample_gates = {
        "new_chat_acquisitions": new_total >= 100,
        "pool_hits_and_misses": pool_hits > 0 and pool_misses > 0,
        "followups": followup_complete >= 50,
        "durable_stops": durable_stops >= 20,
        "forced_failures": expected_errors >= 10,
        "new_chat_latency_samples": bool(
            new_chat_pre_provider
            and new_chat_pre_provider["count"] >= MINIMUM_SLO_SAMPLES
        ),
        "pool_hit_latency_samples": bool(
            pool_hit_pre_provider
            and pool_hit_pre_provider["count"] >= MINIMUM_SLO_SAMPLES
        ),
        "followup_latency_samples": bool(
            followup_pre_provider
            and followup_pre_provider["count"] >= MINIMUM_SLO_SAMPLES
        ),
    }
    health_gates = {
        "tracing_enabled": environment.chat_langfuse_enabled,
        "compatible_live_workers": compatible,
        "bounded_live_workers": live_count <= environment.chat_sandbox_total_live_cap,
        "minimum_blank_present": sum(int(row[3]) for row in live_pool)
        >= environment.chat_blank_pool_min,
        "unexpected_errors_zero": unexpected_errors == 0,
        "stale_turns_zero": stale_turns == 0,
        "degraded_transcripts_zero": degraded_transcripts == 0,
        "journal_critical_failures_zero": journal_critical == 0,
        "all_new_chat_p95_below_2500_ms": bool(
            not new_chat_pre_provider
            or new_chat_pre_provider["count"] < MINIMUM_SLO_SAMPLES
            or new_chat_pre_provider["p95"] < 2_500
        ),
        "pool_hit_p95_below_1000_ms": bool(
            not pool_hit_pre_provider
            or pool_hit_pre_provider["count"] < MINIMUM_SLO_SAMPLES
            or pool_hit_pre_provider["p95"] < 1_000
        ),
        "followup_p95_below_500_ms": bool(
            not followup_pre_provider
            or followup_pre_provider["count"] < MINIMUM_SLO_SAMPLES
            or followup_pre_provider["p95"] < 500
        ),
        "blank_pool_within_budget": bool(pool_budget["within_budget"]),
        "openrouter_within_budget": bool(openrouter_budget["within_budget"]),
    }
    status = _status(
        now=now,
        finish=finish,
        sample_gates=sample_gates,
        health_gates=health_gates,
    )
    report = {
        "status": status,
        "observed_at": now.isoformat(),
        "soak_start": start.isoformat(),
        "soak_finish": finish.isoformat(),
        "remaining_seconds": max(0, round((finish - now).total_seconds())),
        "release": {
            "release_id": release.release_id,
            "worker_contract_version": release.chat_worker_contract_version,
            "image_id": release.chat_modal_image_version,
        },
        "counts": {
            "new_chat_acquisitions": new_total,
            "pool_hits": pool_hits,
            "pool_misses": pool_misses,
            "complete_followups": followup_complete,
            "durable_stops": durable_stops,
            "expected_forced_errors": expected_errors,
            "unexpected_errors": unexpected_errors,
            "stale_turns": stale_turns,
            "degraded_transcripts": degraded_transcripts,
        },
        "error_codes": error_codes,
        "latency_ms": {
            "all_new_chat_pre_provider": new_chat_pre_provider,
            "pool_hit_pre_provider": pool_hit_pre_provider,
            "reused_followup_pre_provider": followup_pre_provider,
        },
        "journal": {**journal, "critical_total": journal_critical},
        "cost": {
            "active": active_spend,
            "blank_pool": pool_budget,
            "openrouter": openrouter_budget,
            "sandbox_compute": {
                "circuit_state": sandbox_spend["circuit_state"],
                "provider_floor_microusd": sandbox_spend["provider_floor_microusd"],
                "remaining_headroom_microusd": sandbox_spend["remaining_microusd"],
                "oldest_live_interval_at": sandbox_spend["oldest_live_at"],
                "last_watchdog_success_at": sandbox_spend["last_metered_at"],
                "kill_sweep": {
                    "complete": sandbox_spend["live_count"] == 0,
                    "live_count": sandbox_spend["live_count"],
                    "termination_uncertain_count": sandbox_spend[
                        "termination_uncertain_count"
                    ],
                },
            },
        },
        "capacity": {
            "live_count": live_count,
            "live_cap": environment.chat_sandbox_total_live_cap,
            "compatible": compatible,
        },
        "sample_gates": sample_gates,
        "health_gates": health_gates,
        "elapsed_gate": now >= finish,
    }
    return report, status in {"soaking", "telemetry_ready"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--started-at", required=True)
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    if args.confirm != CONFIRMATION:
        raise SystemExit(f"--confirm must be {CONFIRMATION}")
    report, healthy = audit(_parse_time(args.started_at), args.release_dir)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
