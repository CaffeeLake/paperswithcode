from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.chat_gateway_app import (
    _provider_headers,
    _provider_target,
    _user_provider_credential,
    _user_provider_token,
)
from backend.config import Settings
from backend.services.chat_gateway_service import ChatGatewayService
from backend.services.hf_inference_billing_service import (
    HfInferenceCredential,
    encrypt_credential,
    encrypt_token,
)


def _request(*headers: tuple[bytes, bytes]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/messages",
            "headers": list(headers),
        }
    )


def test_gateway_uses_connected_user_token_without_bill_to_header():
    settings = Settings(_env_file=None, jwt_secret="x" * 32, hf_token="nielsr-token")
    owner_hash = "a" * 64
    row = SimpleNamespace(
        owner_hash=owner_hash,
        provider_token_encrypted=encrypt_token(
            "connected-user-token", owner_hash, settings
        ),
    )

    token = _user_provider_token(row, settings)
    headers = _provider_headers(
        token,
        _request(
            (b"accept", b"text/event-stream"),
            (b"anthropic-beta", b"test-beta"),
        ),
    )

    assert headers["Authorization"] == "Bearer connected-user-token"
    assert headers["Accept"] == "text/event-stream"
    assert headers["Anthropic-Beta"] == "test-beta"
    assert "nielsr-token" not in headers.values()
    assert "X-HF-Bill-To" not in headers


def test_gateway_forwards_validated_organization_billing_target():
    settings = Settings(_env_file=None, jwt_secret="x" * 32)
    owner_hash = "a" * 64
    row = SimpleNamespace(
        owner_hash=owner_hash,
        provider_token_encrypted=encrypt_credential(
            HfInferenceCredential("connected-user-token", "huggingface"),
            owner_hash,
            settings,
        ),
    )

    credential = _user_provider_credential(row, settings)
    headers = _provider_headers(
        credential.token,
        _request((b"accept", b"text/event-stream")),
        bill_to=credential.bill_to,
    )

    assert headers["X-HF-Bill-To"] == "huggingface"


def test_gateway_fails_closed_instead_of_using_shared_token():
    settings = Settings(_env_file=None, jwt_secret="x" * 32, hf_token="nielsr-token")
    row = SimpleNamespace(owner_hash="a" * 64, provider_token_encrypted=None)

    with pytest.raises(HTTPException) as error:
        _user_provider_token(row, settings)

    assert error.value.status_code == 402
    assert error.value.detail == "Authorize Hugging Face inference"


def test_gateway_routes_luna_to_server_funded_openrouter():
    settings = Settings(
        _env_file=None,
        chat_openrouter_api_key="openrouter-token",
        chat_openrouter_server_funded_enabled=True,
    )
    row = SimpleNamespace(
        model=settings.chat_luna_route,
        owner_hash="a" * 64,
        provider_token_encrypted=None,
    )

    assert _provider_target(row, settings) == (
        "https://openrouter.ai/api/v1/messages",
        "openrouter-token",
        None,
    )


def test_gateway_rejects_shared_openrouter_when_preview_is_disabled():
    settings = Settings(
        _env_file=None,
        chat_openrouter_api_key="openrouter-token",
        chat_openrouter_server_funded_enabled=False,
    )
    row = SimpleNamespace(
        model=settings.chat_luna_route,
        owner_hash="a" * 64,
        provider_token_encrypted=None,
    )

    with pytest.raises(HTTPException) as error:
        _provider_target(row, settings)

    assert error.value.status_code == 503


def test_gateway_keeps_hugging_face_models_on_user_billing():
    settings = Settings(_env_file=None, jwt_secret="x" * 32)
    owner_hash = "a" * 64
    row = SimpleNamespace(
        model=settings.chat_glm_route,
        owner_hash=owner_hash,
        provider_token_encrypted=encrypt_credential(
            HfInferenceCredential("connected-user-token", "huggingface"),
            owner_hash,
            settings,
        ),
    )

    assert _provider_target(row, settings) == (
        "https://router.huggingface.co/v1/messages",
        "connected-user-token",
        "huggingface",
    )


def test_chat_search_never_calls_shared_query_embedding_endpoint(monkeypatch):
    calls = []

    class PaperService:
        def __init__(self, _db):
            pass

        def search_papers_page(self, query, page, limit, *, mode):
            calls.append((query, page, limit, mode))
            return {"results": []}

    from backend.services import chat_gateway_service

    monkeypatch.setattr(chat_gateway_service, "PaperService", PaperService)
    result = ChatGatewayService(object(), Settings(_env_file=None)).catalog(
        "search",
        {"query": "vision transformers", "mode": "hybrid", "limit": 5},
    )

    assert result == {"results": []}
    assert calls == [("vision transformers", 1, 5, "keyword")]
