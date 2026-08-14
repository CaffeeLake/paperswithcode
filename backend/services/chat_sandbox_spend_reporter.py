"""Provider boundary for authoritative chat sandbox spend reports."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol

import modal

from backend.chat_sandbox_worker.contract import MODAL_APP_NAME
from backend.config import Settings


class ProviderSpendReporter(Protocol):
    settings: Settings

    async def month_to_date_microusd(
        self,
        *,
        start: datetime,
        end: datetime,
    ) -> int: ...


class ModalProviderSpendReporter:
    """Read the exact Modal app/environment spend owned by this service."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def month_to_date_microusd(
        self,
        *,
        start: datetime,
        end: datetime,
    ) -> int:
        if self.settings.chat_sandbox_provider_mode == "team_environments":
            report = modal.Environment.from_name(
                self.settings.chat_sandbox_modal_environment
            ).billing.report
        else:
            report = modal.Workspace.from_context().billing.report
        items = []
        chunk_start = start
        while chunk_start < end:
            chunk_end = min(chunk_start + timedelta(days=7), end)
            items.extend(
                await report.aio(
                    start=chunk_start,
                    end=chunk_end,
                    resolution="h",
                )
            )
            chunk_start = chunk_end
        dollars = sum(
            item.cost
            for item in items
            if item.description == MODAL_APP_NAME
            and (
                self.settings.chat_sandbox_provider_mode == "team_environments"
                or item.environment_name
                in {"main", self.settings.chat_sandbox_modal_environment}
            )
        )
        return round(dollars * 1_000_000)
