from __future__ import annotations

import asyncio

import httpx
import pytest

from backend.config import Settings
from backend.services import hf_inference_billing_service as billing


def _settings() -> Settings:
    return Settings(jwt_secret="x" * 32)


def test_inference_token_round_trip_is_bound_to_hf_subject():
    encrypted = billing.encrypt_token("hf_secret", "hf-user-1", _settings())

    assert billing.decrypt_token(encrypted, "hf-user-1", _settings()) == "hf_secret"
    assert billing.decrypt_token(encrypted, "hf-user-2", _settings()) is None
    assert "hf_secret" not in encrypted


def test_verify_token_detects_pro_account(monkeypatch):
    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, headers):
            assert url == billing.HF_WHOAMI_URL
            assert headers["Authorization"] == "Bearer hf_test"
            return httpx.Response(
                200,
                json={"id": "hf-user-1", "name": "alice", "isPro": True},
            )

    monkeypatch.setattr(billing.httpx, "AsyncClient", lambda **_kwargs: FakeClient())

    account = asyncio.run(billing.verify_token("hf_test", "hf-user-1"))

    assert account.username == "alice"
    assert account.is_pro is True


def test_verify_token_rejects_a_different_account(monkeypatch):
    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, *_args, **_kwargs):
            return httpx.Response(
                200,
                json={"id": "someone-else", "name": "mallory", "isPro": False},
            )

    monkeypatch.setattr(billing.httpx, "AsyncClient", lambda **_kwargs: FakeClient())

    with pytest.raises(
        billing.HfInferenceCredentialError,
        match="different Hugging Face account",
    ):
        asyncio.run(billing.verify_token("hf_test", "hf-user-1"))
