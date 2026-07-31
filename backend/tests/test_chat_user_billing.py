from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.chat_gateway_app import _provider_headers, _user_provider_token
from backend.config import Settings
from backend.services.chat_gateway_service import ChatGatewayService
from backend.services.hf_inference_billing_service import encrypt_token


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


def test_gateway_fails_closed_instead_of_using_shared_token():
    settings = Settings(_env_file=None, jwt_secret="x" * 32, hf_token="nielsr-token")
    row = SimpleNamespace(owner_hash="a" * 64, provider_token_encrypted=None)

    with pytest.raises(HTTPException) as error:
        _user_provider_token(row, settings)

    assert error.value.status_code == 402
    assert error.value.detail == "Connect Hugging Face billing"


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
