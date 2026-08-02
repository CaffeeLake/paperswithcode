from __future__ import annotations

import asyncio

import httpx
import pytest

from backend.config import Settings
from backend.routers import chat as chat_router
from backend.services.chat_session_service import ChatServiceError
from backend.services.openrouter_budget_service import (
    OpenRouterBudgetExceeded,
    OpenRouterBudgetUnavailable,
    openrouter_budget_status,
    require_openrouter_budget,
)


def _settings(**overrides) -> Settings:
    values = {
        "environment": "staging",
        "release_id": "release-a",
        "chat_openrouter_api_key": "secret",
        "chat_openrouter_server_funded_enabled": True,
        "chat_openrouter_monthly_user_budget_usd": 1,
        "chat_openrouter_workspace_monthly_budget_usd": 5,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _client(payload: dict, *, status_code: int = 200) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer secret"
        return httpx.Response(status_code, json=payload)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_deployed_model_registry_hides_disabled_shared_provider():
    settings = _settings(chat_openrouter_server_funded_enabled=False)

    assert "deepseek-ai/DeepSeek-V4-Flash-0731" not in {
        choice["id"] for choice in settings.chat_model_choices
    }
    assert "deepseek-ai/DeepSeek-V4-Flash-0731" not in settings.chat_model_routes
    assert (
        settings.chat_model_providers["deepseek-ai/DeepSeek-V4-Flash-0731"]
        == "openrouter"
    )


def test_staging_exposes_explicitly_enabled_shared_provider():
    settings = _settings(chat_openrouter_server_funded_enabled=True)

    assert "deepseek-ai/DeepSeek-V4-Flash-0731" in {
        choice["id"] for choice in settings.chat_model_choices
    }


def test_development_keeps_model_available_for_explicit_local_testing():
    settings = Settings(_env_file=None)

    assert "deepseek-ai/DeepSeek-V4-Flash-0731" in {
        choice["id"] for choice in settings.chat_model_choices
    }


def test_disabled_shared_provider_is_safe_without_network():
    status = asyncio.run(
        openrouter_budget_status(_settings(chat_openrouter_server_funded_enabled=False))
    )

    assert status.enabled is False
    assert status.within_budget is True
    assert status.remaining_usd == 5


def test_provider_reported_monthly_usage_preserves_reserve():
    async def run():
        async with _client(
            {
                "data": {
                    "usage_monthly": 1.25,
                    "limit": 5,
                    "limit_remaining": 3.75,
                    "limit_reset": "monthly",
                }
            }
        ) as client:
            return await openrouter_budget_status(_settings(), client=client)

    status = asyncio.run(run())

    assert status.enabled is True
    assert status.usage_monthly_usd == 1.25
    assert status.remaining_usd == 3.75
    assert status.within_budget is True
    assert "secret" not in str(status.sanitized())


def test_provider_limit_must_match_configured_hard_guardrail():
    async def run():
        async with _client(
            {
                "data": {
                    "usage_monthly": 1,
                    "limit": 2,
                    "limit_remaining": 0.25,
                    "limit_reset": "monthly",
                }
            }
        ) as client:
            return await openrouter_budget_status(_settings(), client=client)

    with pytest.raises(OpenRouterBudgetUnavailable):
        asyncio.run(run())


def test_budget_guard_fails_closed_at_reserve(monkeypatch: pytest.MonkeyPatch):
    async def exhausted(_settings):
        async with _client(
            {
                "data": {
                    "usage_monthly": 5,
                    "limit": 5,
                    "limit_remaining": 0,
                    "limit_reset": "monthly",
                }
            }
        ) as client:
            return await openrouter_budget_status(_settings, client=client)

    monkeypatch.setattr(
        "backend.services.openrouter_budget_service.openrouter_budget_status",
        exhausted,
    )

    with pytest.raises(OpenRouterBudgetExceeded):
        asyncio.run(require_openrouter_budget(_settings()))


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"data": {}},
        {"data": {"usage_monthly": "1", "limit": None}},
    ],
)
def test_budget_guard_rejects_unverifiable_provider_data(payload: dict):
    async def run():
        async with _client(payload) as client:
            return await openrouter_budget_status(_settings(), client=client)

    with pytest.raises(OpenRouterBudgetUnavailable):
        asyncio.run(run())


def test_chat_admission_rejects_disabled_shared_provider():
    with pytest.raises(ChatServiceError) as error:
        asyncio.run(
            chat_router._authorize_openrouter(
                _settings(chat_openrouter_server_funded_enabled=False),
            )
        )

    assert error.value.code == "openrouter_unavailable"
    assert error.value.status_code == 503


@pytest.mark.parametrize(
    ("budget_error", "expected_code"),
    [
        (OpenRouterBudgetExceeded("exhausted"), "openrouter_unavailable"),
        (OpenRouterBudgetUnavailable("unavailable"), "openrouter_unavailable"),
    ],
)
def test_chat_admission_maps_budget_failure_without_leaking_detail(
    monkeypatch: pytest.MonkeyPatch,
    budget_error: RuntimeError,
    expected_code: str,
):
    async def fail(_settings):
        raise budget_error

    monkeypatch.setattr(chat_router, "require_openrouter_budget", fail)
    with pytest.raises(ChatServiceError) as error:
        asyncio.run(chat_router._authorize_openrouter(_settings()))

    assert error.value.code == expected_code
    assert "exhausted" not in str(error.value)
    assert str(error.value) == chat_router.OPENROUTER_UNAVAILABLE_MESSAGE


def test_chat_admission_has_no_process_local_request_quota(
    monkeypatch: pytest.MonkeyPatch,
):
    async def allow(_settings):
        return None

    monkeypatch.setattr(chat_router, "require_openrouter_budget", allow)
    asyncio.run(chat_router._authorize_openrouter(_settings()))
    asyncio.run(chat_router._authorize_openrouter(_settings()))
