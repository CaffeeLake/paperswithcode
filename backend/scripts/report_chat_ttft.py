#!/usr/bin/env python3
"""Report content-free TTFT release gates for one exact chat release/image."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from backend.database.connection import db_manager
from backend.models.database import (
    ChatOpenRouterProviderCall,
    ChatSandboxPool,
    ChatTurnLatency,
)
from backend.services.chat_latency_service import (
    MODAL_CPU_USD_PER_CORE_SECOND,
    MODAL_MEMORY_USD_PER_GIB_SECOND,
)


def percentile(values: list[int], quantile: float) -> int:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * quantile) - 1)]


def distribution(values: list[int]) -> dict[str, int] | None:
    if not values:
        return None
    return {
        "count": len(values),
        "min": min(values),
        "p50": round(statistics.median(values)),
        "p75": percentile(values, 0.75),
        "p90": percentile(values, 0.90),
        "p99": percentile(values, 0.99),
        "max": max(values),
    }


def metric(rows: list[ChatTurnLatency], name: str) -> dict[str, int] | None:
    return distribution(
        [int(value) for row in rows if (value := getattr(row, name)) is not None]
    )


def component_metric(rows: list[ChatTurnLatency]) -> dict[str, int] | None:
    return distribution(
        [
            row.sdk_query_dispatched_ms - row.session_assignment_completed_ms
            for row in rows
            if row.sdk_query_dispatched_ms is not None
            and row.session_assignment_completed_ms is not None
        ]
    )


def passes(value: dict[str, int] | None, *, count: int, p50: int, p90: int) -> bool:
    return bool(
        value
        and value["count"] >= count
        and value["p50"] <= p50
        and value["p90"] <= p90
    )


def report(args: argparse.Namespace) -> dict[str, Any]:
    with db_manager.session_local() as db:
        query = select(ChatTurnLatency).where(
            ChatTurnLatency.app_release_id == args.release_id,
            ChatTurnLatency.sandbox_image_version == args.image_id,
            ChatTurnLatency.admitted_at >= args.after,
        )
        if args.run_id:
            query = query.where(ChatTurnLatency.qualification_run_id == args.run_id)
        rows = list(db.scalars(query.order_by(ChatTurnLatency.admitted_at)))
        pool_rows = list(
            db.scalars(
                select(ChatSandboxPool)
                .where(
                    ChatSandboxPool.app_release_id == args.release_id,
                    ChatSandboxPool.image_version == args.image_id,
                    ChatSandboxPool.created_at >= args.after,
                )
                .order_by(ChatSandboxPool.created_at)
            )
        )
        turn_ids = [row.turn_id for row in rows]
        provider_calls = (
            list(
                db.scalars(
                    select(ChatOpenRouterProviderCall).where(
                        ChatOpenRouterProviderCall.turn_id.in_(turn_ids)
                    )
                )
            )
            if turn_ids
            else []
        )

    pool_hits = [
        row
        for row in rows
        if row.traffic_class == "new_chat"
        and row.acquisition_outcome == "pool_hit"
        and row.agent_harness == "pi"
    ]
    eligible = [
        row
        for row in rows
        if row.traffic_class == "new_chat"
        and row.agent_harness == "pi"
        and row.model_route == args.model
    ]
    reused = [
        row
        for row in rows
        if row.traffic_class == "followup"
        and row.acquisition_outcome == "reused_session"
    ]
    followups = [row for row in rows if row.traffic_class == "followup"]
    component = component_metric(pool_hits)
    pool_browser = metric(pool_hits, "browser_first_reasoning_delta_ms")
    reused_browser = metric(reused, "browser_first_reasoning_delta_ms")
    model_to_application = distribution(
        [
            row.first_semantic_event_ms - row.sdk_query_dispatched_ms
            for row in rows
            if row.first_semantic_event_ms is not None
            and row.sdk_query_dispatched_ms is not None
        ]
    )
    hit_rate = len(pool_hits) / len(eligible) if eligible else 0
    seconds_per_month = 365.25 / 12 * 24 * 3600
    monthly_idle_cost = (
        args.pool_target
        * seconds_per_month
        * (
            args.cpu * MODAL_CPU_USD_PER_CORE_SECOND
            + args.memory_mib / 1024 * MODAL_MEMORY_USD_PER_GIB_SECOND
        )
    )
    unknown_calls = sum(call.state == "cost_unknown" for call in provider_calls)
    reliability = (
        sum(row.terminal_status == "complete" for row in rows) / len(rows)
        if rows
        else 0
    )
    gates = {
        "component": passes(component, count=50, p50=1500, p90=3000),
        "model_to_application": passes(
            model_to_application, count=50, p50=1500, p90=3500
        ),
        "pool_browser": passes(pool_browser, count=50, p50=4000, p90=8000),
        "reused_browser": passes(reused_browser, count=50, p50=3000, p90=6000),
        "hit_rate": len(eligible) >= 200 and hit_rate >= 0.95,
        "reliability": bool(rows) and reliability >= args.minimum_reliability,
        "accounting": bool(provider_calls) and unknown_calls == 0,
    }
    return {
        "status": "passed" if all(gates.values()) else "failed",
        "release_id": args.release_id,
        "image_id": args.image_id,
        "model": args.model,
        "observation_window": {
            "after": args.after.isoformat(),
            "first": rows[0].admitted_at.isoformat() if rows else None,
            "last": rows[-1].admitted_at.isoformat() if rows else None,
        },
        "sample_sizes": {
            "all": len(rows),
            "eligible_new": len(eligible),
            "pool_hits": len(pool_hits),
            "reused": len(reused),
            "provider_calls": len(provider_calls),
            "pool_starts": len(pool_rows),
        },
        "latency_ms": {
            "assignment_to_dispatch": component,
            "pool_hit_browser_reasoning": pool_browser,
            "pool_hit_browser_tool_first": metric(
                pool_hits, "browser_first_tool_call_ms"
            ),
            "pool_hit_browser_answer_first": metric(
                pool_hits, "browser_first_answer_delta_ms"
            ),
            "reused_browser_reasoning": reused_browser,
            "reused_browser_tool_first": metric(reused, "browser_first_tool_call_ms"),
            "reused_browser_answer_first": metric(
                reused, "browser_first_answer_delta_ms"
            ),
            "dispatch_to_application_semantic": model_to_application,
            "phases": {
                name: metric(rows, name)
                for name in (
                    "control_connection_ms",
                    "agent_spawn_ms",
                    "agent_startup_ready_ms",
                    "session_bind_restore_ms",
                    "resource_loading_ms",
                    "agent_session_ready_ms",
                    "provider_gateway_received_ms",
                    "upstream_response_headers_ms",
                    "upstream_first_body_byte_ms",
                    "first_application_sse_delta_ms",
                )
            },
            "pool_startup": {
                name: distribution(
                    [
                        int(value)
                        for row in pool_rows
                        if (value := getattr(row, name)) is not None
                    ]
                )
                for name in (
                    "provider_create_ms",
                    "backend_control_connect_ms",
                    "broker_ready_ms",
                    "control_ready_ms",
                    "agent_spawn_ms",
                    "agent_startup_ready_ms",
                )
            },
            "provider_ttft": distribution(
                [
                    call.provider_ttft_ms
                    for call in provider_calls
                    if call.provider_ttft_ms
                ]
            ),
        },
        "semantic_classes": dict(
            Counter(row.first_semantic_event_class or "missing" for row in rows)
        ),
        "cohorts": {
            "traffic": dict(Counter(row.traffic_class for row in rows)),
            "harness": dict(Counter(row.agent_harness for row in rows)),
            "model": dict(Counter(row.model_route for row in rows)),
            "acquisition": dict(Counter(row.acquisition_outcome for row in rows)),
            "effort": dict(Counter(call.reasoning_effort for call in provider_calls)),
        },
        "acquisition": {
            "hit_rate": round(hit_rate, 4),
            "outcomes": dict(Counter(row.acquisition_outcome for row in eligible)),
            "miss_reasons": dict(
                Counter(
                    row.pool_miss_reason or "unclassified"
                    for row in eligible
                    if row.acquisition_outcome == "pool_miss"
                )
            ),
        },
        "reuse_cohorts": dict(
            Counter(row.session_reuse_cohort or "unclassified" for row in followups)
        ),
        "reliability": {
            "completion_rate": round(reliability, 4),
            "terminal_statuses": dict(Counter(row.terminal_status for row in rows)),
        },
        "accounting": {
            "states": dict(Counter(call.state for call in provider_calls)),
            "unknown_cost_calls": unknown_calls,
            "routing": dict(Counter(call.routing_policy for call in provider_calls)),
            "providers": dict(
                Counter(call.upstream_provider or "missing" for call in provider_calls)
            ),
            "fallbacks": sum(call.fallback_count for call in provider_calls),
            "tokens": {
                name: distribution(
                    [
                        int(value)
                        for call in provider_calls
                        if (value := getattr(call, name)) is not None
                    ]
                )
                for name in (
                    "prompt_tokens",
                    "completion_tokens",
                    "cache_read_tokens",
                    "cache_creation_tokens",
                )
            },
            "request_bytes": distribution(
                [
                    call.request_bytes
                    for call in provider_calls
                    if call.request_bytes is not None
                ]
            ),
            "provider_cost_usd": {
                "actual": round(
                    sum((call.actual_microusd or 0) for call in provider_calls)
                    / 1_000_000,
                    6,
                ),
                "reserved": round(
                    sum(call.reserved_microusd for call in provider_calls) / 1_000_000,
                    6,
                ),
            },
            "payload_token_buckets": {
                "system": distribution(
                    [
                        call.system_token_bucket
                        for call in provider_calls
                        if call.system_token_bucket is not None
                    ]
                ),
                "tools": distribution(
                    [
                        call.tool_token_bucket
                        for call in provider_calls
                        if call.tool_token_bucket is not None
                    ]
                ),
                "conversation": distribution(
                    [
                        call.conversation_token_bucket
                        for call in provider_calls
                        if call.conversation_token_bucket is not None
                    ]
                ),
            },
        },
        "cost": {
            "pool_target": args.pool_target,
            "cpu": args.cpu,
            "memory_mib": args.memory_mib,
            "projected_monthly_idle_usd": round(monthly_idle_cost, 2),
            "observed_active_usd": round(
                sum(float(row.estimated_active_cost_usd or 0) for row in rows), 6
            ),
        },
        "gates": gates,
        "isolation": {
            "status": "requires qualification artifact",
            "note": "Latency rows contain no prompts, credentials, transcripts, or tool output.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--image-id", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--after", type=datetime.fromisoformat, required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--pool-target", type=int, required=True)
    parser.add_argument("--cpu", type=float, required=True)
    parser.add_argument("--memory-mib", type=int, required=True)
    parser.add_argument("--minimum-reliability", type=float, default=0.99)
    args = parser.parse_args()
    if args.after.tzinfo is None:
        args.after = args.after.replace(tzinfo=UTC)
    result = report(args)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
