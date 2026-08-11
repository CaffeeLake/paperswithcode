"""Shared runtime policy for blank sandbox pool coordination."""

from __future__ import annotations

from dataclasses import dataclass

from backend.config import Settings

POOL_TERMINATION_MAX_CONCURRENCY = 8


@dataclass(frozen=True)
class ChatSandboxPoolPolicy:
    """Interpret pool feature gates and timing settings in one place."""

    settings: Settings

    @property
    def enabled(self) -> bool:
        return bool(
            getattr(self.settings, "chat_blank_pool_enabled", False)
            and getattr(self.settings, "chat_sandbox_admission_enabled", True)
        )

    @property
    def refill_enabled(self) -> bool:
        return bool(
            self.enabled
            and getattr(self.settings, "chat_persistent_worker_enabled", False)
            and self.settings.chat_blank_pool_min > 0
        )

    @property
    def spend_enforced(self) -> bool:
        return bool(
            getattr(
                self.settings,
                "chat_sandbox_spend_enforcement_enabled",
                False,
            )
        )

    @property
    def ready_timeout_seconds(self) -> float:
        if getattr(self.settings, "chat_persistent_worker_enabled", False):
            return getattr(
                self.settings,
                "chat_worker_ready_timeout_seconds",
                self.settings.chat_sandbox_ready_timeout_seconds,
            )
        return self.settings.chat_sandbox_ready_timeout_seconds

    @property
    def termination_claim_timeout_seconds(self) -> float:
        return (
            self.ready_timeout_seconds
            + self.settings.chat_sandbox_termination_grace_seconds
            + 15
        )

    @property
    def termination_concurrency(self) -> int:
        configured_max = self.settings.chat_blank_pool_max or 1
        return min(
            POOL_TERMINATION_MAX_CONCURRENCY,
            self.settings.chat_blank_pool_refill_concurrency,
            configured_max,
        )
