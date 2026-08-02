"""Fail-closed spend guard for the optional server-funded OpenRouter preview."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import httpx

from backend.config import Settings

OPENROUTER_KEY_STATUS_URL = "https://openrouter.ai/api/v1/key"


class OpenRouterBudgetUnavailable(RuntimeError):
    """The provider could not prove that shared spend remains within budget."""


class OpenRouterBudgetExceeded(RuntimeError):
    """The configured or provider-enforced shared spend reserve was reached."""


@dataclass(frozen=True)
class OpenRouterBudgetStatus:
    enabled: bool
    usage_monthly_usd: float
    budget_usd: float
    reserve_usd: float
    remaining_usd: float
    provider_limit_usd: float | None
    provider_limit_remaining_usd: float | None
    within_budget: bool

    def sanitized(self) -> dict[str, bool | float | None]:
        return asdict(self)


def _number(value: Any, name: str, *, optional: bool = False) -> float | None:
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OpenRouterBudgetUnavailable(f"OpenRouter omitted numeric {name}")
    result = float(value)
    if result < 0:
        raise OpenRouterBudgetUnavailable(f"OpenRouter returned negative {name}")
    return result


async def openrouter_budget_status(
    settings: Settings,
    *,
    client: httpx.AsyncClient | None = None,
) -> OpenRouterBudgetStatus:
    """Read provider-authoritative key usage without exposing the credential."""

    budget = float(settings.chat_openrouter_monthly_budget_usd)
    reserve = float(settings.chat_openrouter_budget_reserve_usd)
    if not settings.chat_openrouter_server_funded_enabled:
        return OpenRouterBudgetStatus(
            enabled=False,
            usage_monthly_usd=0,
            budget_usd=budget,
            reserve_usd=reserve,
            remaining_usd=budget,
            provider_limit_usd=None,
            provider_limit_remaining_usd=None,
            within_budget=True,
        )
    if not settings.chat_openrouter_api_key:
        raise OpenRouterBudgetUnavailable("OpenRouter credential is not configured")

    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=3, follow_redirects=False)
    try:
        response = await active_client.get(
            OPENROUTER_KEY_STATUS_URL,
            headers={"Authorization": f"Bearer {settings.chat_openrouter_api_key}"},
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError, TypeError) as error:
        raise OpenRouterBudgetUnavailable(
            "OpenRouter budget status could not be verified"
        ) from error
    finally:
        if owns_client:
            await active_client.aclose()

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise OpenRouterBudgetUnavailable("OpenRouter budget response is invalid")
    usage = _number(data.get("usage_monthly"), "usage_monthly")
    provider_limit = _number(data.get("limit"), "limit", optional=True)
    provider_remaining = _number(
        data.get("limit_remaining"),
        "limit_remaining",
        optional=True,
    )
    assert usage is not None
    application_remaining = max(0.0, budget - usage)
    remaining = application_remaining
    if provider_remaining is not None:
        remaining = min(remaining, provider_remaining)
    within_budget = remaining > reserve
    return OpenRouterBudgetStatus(
        enabled=True,
        usage_monthly_usd=usage,
        budget_usd=budget,
        reserve_usd=reserve,
        remaining_usd=remaining,
        provider_limit_usd=provider_limit,
        provider_limit_remaining_usd=provider_remaining,
        within_budget=within_budget,
    )


async def require_openrouter_budget(settings: Settings) -> OpenRouterBudgetStatus:
    status = await openrouter_budget_status(settings)
    if not status.within_budget:
        raise OpenRouterBudgetExceeded(
            "The shared OpenRouter preview reached its spend reserve"
        )
    return status
