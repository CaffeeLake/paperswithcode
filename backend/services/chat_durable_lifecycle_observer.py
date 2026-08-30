"""Bounded content-free telemetry for durable chat lifecycle operations."""

from __future__ import annotations

import logging
from typing import Any

from backend.config import Settings
from backend.services.chat_tracing_service import configured_chat_client

logger = logging.getLogger(__name__)

EVENTS = frozenset(
    {
        "turn_state",
        "typed_failure",
        "journal_events",
        "journal_bytes",
        "journal_cleanup",
        "worker_reconnect",
        "executor_recovery",
        "workspace_state",
        "turn_replay",
        "ttft_ms",
        "terminal_latency_ms",
    }
)
CODES = frozenset(
    {
        "admitted",
        "leased",
        "running",
        "waiting_model",
        "waiting_tool",
        "cancelling",
        "completed",
        "failed",
        "interrupted",
        "cancelled",
        "cancel_control_missing",
        "dispatch_failed",
        "external_worker_lost",
        "execution_lost",
        "event_journal_exhausted",
        "projection_mismatch",
        "created",
        "reused",
        "released",
        "invalidated",
        "accepted",
        "succeeded",
    }
)
MAX_VALUE = 16 * 1024 * 1024


class DurableLifecycleObserver:
    def __init__(self, settings: Settings, *, client: Any = None) -> None:
        self.settings = settings
        self.client = client if client is not None else configured_chat_client(settings)

    def __call__(self, event: str, code: str | None, value: int) -> None:
        if (
            event not in EVENTS
            or (code is not None and code not in CODES)
            or not isinstance(value, int)
            or isinstance(value, bool)
            or not 0 <= value <= MAX_VALUE
        ):
            raise ValueError("Durable lifecycle observation is invalid")
        logger.info(
            "chat durable lifecycle event=%s code=%s value=%d",
            event,
            code or "none",
            value,
        )
        if self.client is None or event not in {"turn_state", "typed_failure"}:
            return
        try:
            self.client.start_observation(
                name="durable-chat-lifecycle",
                as_type="span",
                metadata={"event": event, "code": code or "none", "value": value},
            ).end()
        except Exception:
            logger.warning("chat durable lifecycle Langfuse emission failed")


def durable_lifecycle_observer(settings: Settings) -> DurableLifecycleObserver:
    return DurableLifecycleObserver(settings)
