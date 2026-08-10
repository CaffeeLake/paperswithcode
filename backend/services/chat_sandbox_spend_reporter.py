"""Provider boundary for authoritative chat sandbox spend reports."""

from __future__ import annotations

from datetime import datetime
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
        items = await modal.Workspace.from_context().billing.report.aio(
            start=start,
            end=end,
            resolution="h",
        )
        dollars = sum(
            item.cost
            for item in items
            if item.description == MODAL_APP_NAME
            and item.environment_name
            in {"main", self.settings.chat_sandbox_modal_environment}
        )
        return round(dollars * 1_000_000)
