"""Bounded content-free telemetry for durable chat lifecycle operations."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

from backend.config import Settings
from backend.services.chat_tracing_service import configured_chat_client
from backend.services.chat_turn_lifecycle import LIFECYCLE_CODES

logger = logging.getLogger(__name__)

EVENTS = frozenset(
    {
        "turn_state",
        "typed_failure",
        "journal_events",
        "journal_bytes",
        "journal_cleanup",
        "worker_reconnect",
        "capacity_saturation",
        "executor_recovery",
        "workspace_state",
        "workspace_active_ms",
        "turn_replay",
        "ttft_ms",
        "terminal_latency_ms",
        "stale_fence_rejection",
        "expired_turn_lease",
    }
)
CODES = LIFECYCLE_CODES | {"reconnecting"}
MAX_VALUE = 16 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ApplicationModalLifecycleSnapshot:
    captured_at_ms: int
    creates: int
    reuses: int
    evictions: int
    active_duration_ms: int
    source: str = "application_modal_lifecycle"


class _ApplicationModalLifecycleCounter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._creates = 0
        self._reuses = 0
        self._evictions = 0
        self._active_duration_ms = 0

    def observe(self, event: str, code: str | None, value: int) -> None:
        with self._lock:
            if event == "workspace_state" and code == "created":
                self._creates += value
            elif event == "workspace_state" and code == "reused":
                self._reuses += value
            elif event == "workspace_state" and code == "invalidated":
                self._evictions += value
            elif event == "workspace_active_ms" and code is None:
                self._active_duration_ms += value

    def snapshot(self) -> ApplicationModalLifecycleSnapshot:
        with self._lock:
            return ApplicationModalLifecycleSnapshot(
                captured_at_ms=round(time.monotonic() * 1_000),
                creates=self._creates,
                reuses=self._reuses,
                evictions=self._evictions,
                active_duration_ms=self._active_duration_ms,
            )


_application_modal_lifecycle = _ApplicationModalLifecycleCounter()


def application_modal_lifecycle_snapshot() -> ApplicationModalLifecycleSnapshot:
    return _application_modal_lifecycle.snapshot()


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
        _application_modal_lifecycle.observe(event, code, value)
        logger.info(
            "chat durable lifecycle event=%s code=%s value=%d",
            event,
            code or "none",
            value,
        )
        if self.client is None:
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
