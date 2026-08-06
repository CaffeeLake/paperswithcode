"""Content-free operational alerts for production chat health."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import ChatMessageRecord

PROVIDER_ERROR_CODES = frozenset(
    {
        "provider_error",
        "provider_invalid_request",
        "provider_rate_limit",
        "provider_timeout",
        "provider_unavailable",
    }
)

# These strings are emitted without prompts, answers, capabilities, or credentials.
# Provider failures are excluded because they use the sustained database signal below.
RUNTIME_FAILURE_PATTERNS = {
    "pool_replenishment_failure": "chat blank pool replenishment failed",
    "pool_budget_block": "chat blank pool budget blocked",
    "turn_cleanup_failure": "chat cleanup failed",
    "edit_cleanup_failure": "chat edit preparation cleanup failed",
    "background_task_failure": "chat background task failed",
    "stream_persistence_failure": "chat stream persistence failed",
    "transcript_mirror_failure": "chat transcript mirror failed",
    "transcript_reconciliation_failure": "chat transcript reconciliation failed",
    "latency_finalize_failure": "chat latency finalize failed",
    "latency_phase_failure": "chat latency phase failed",
    "stale_turn_reconciliation": "chat stale turns reconciled",
    "langfuse_initialization_failure": "chat Langfuse trace initialization failed",
    "langfuse_finalization_failure": "chat Langfuse trace finalization failed",
    "langfuse_client_failure": "chat Langfuse client initialization failed",
}


@dataclass(frozen=True)
class ProviderHealth:
    total_turns: int
    failed_turns: int
    window_start: datetime
    window_end: datetime

    @property
    def failure_percent(self) -> int:
        if not self.total_turns:
            return 0
        return round(self.failed_turns * 100 / self.total_turns)


def provider_health(db: Session, settings: Settings, now: datetime) -> ProviderHealth:
    """Count terminal DeepSeek turns without reading transcript content."""

    start = now - timedelta(seconds=settings.chat_provider_alert_window_seconds)
    terminal = ChatMessageRecord.status.in_(("complete", "error", "interrupted"))
    scope = (
        ChatMessageRecord.role == "user",
        ChatMessageRecord.model_route == settings.chat_deepseek_v4_flash_route,
        ChatMessageRecord.created_at >= start,
        ChatMessageRecord.created_at <= now,
        terminal,
    )
    total = int(
        db.scalar(select(func.count()).select_from(ChatMessageRecord).where(*scope))
        or 0
    )
    failed = int(
        db.scalar(
            select(func.count())
            .select_from(ChatMessageRecord)
            .where(*scope, ChatMessageRecord.error_code.in_(PROVIDER_ERROR_CODES))
        )
        or 0
    )
    return ProviderHealth(total, failed, start, now)


def provider_transition(
    *, active: bool, health: ProviderHealth, settings: Settings
) -> str | None:
    """Return only incident-entry or full-window-recovery transitions."""

    sustained = (
        health.failed_turns >= settings.chat_provider_alert_min_failures
        and health.failure_percent >= settings.chat_provider_alert_failure_percent
    )
    if not active and sustained:
        return "hf_provider_sustained_failure"
    if active and health.failed_turns == 0:
        return "hf_provider_recovered"
    return None


def runtime_failure_counts(messages: list[str]) -> dict[str, int]:
    """Classify raw journal lines, returning only content-free aggregate counts."""

    counts = {
        name: sum(pattern in message for message in messages)
        for name, pattern in RUNTIME_FAILURE_PATTERNS.items()
    }
    counts["session_store_forbidden"] = sum(
        "POST /api/internal/chat-gateway/session-store" in message
        and "403 Forbidden" in message
        for message in messages
    )
    return {name: count for name, count in counts.items() if count}


def operational_alert_payload(
    event: dict[str, Any], settings: Settings
) -> dict[str, str]:
    """Render a content-free payload shared by primary and fallback delivery."""

    classifications = ",".join(sorted(event.get("classifications", {}))) or "none"
    return {
        "text": (
            f"PwC chat operational alert; signal={event['signal']}; "
            f"severity={event['severity']}; environment={settings.environment}; "
            f"release={settings.release_id}; count={event['count']}; "
            f"classifications={classifications}; window_start={event['window_start']}; "
            f"window_end={event['window_end']}; event_id={event['id']}; "
            f"runbook={settings.chat_sandbox_runbook_url}"
        )
    }


async def post_operational_alert(
    url: str,
    event: dict[str, Any],
    settings: Settings,
) -> None:
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.post(
            url, json=operational_alert_payload(event, settings)
        )
        response.raise_for_status()
