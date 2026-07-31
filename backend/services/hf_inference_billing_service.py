"""Per-user Hugging Face Inference Providers credentials.

The long-lived credential is kept only in an encrypted, HTTP-only cookie.
Short-lived chat capabilities carry a separately encrypted copy so the private
gateway can bill model calls to the user without exposing the token to the
sandbox.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass

import httpx
from cryptography.fernet import Fernet, InvalidToken

from backend.config import Settings

HF_WHOAMI_URL = "https://huggingface.co/api/whoami-v2"
HF_INFERENCE_SETTINGS_URL = "https://huggingface.co/settings/inference-providers"
HF_TOKEN_SETTINGS_URL = (
    "https://huggingface.co/settings/tokens/new?tokenType=fineGrained"
)
COOKIE_NAME = "pwc_hf_inference"


class HfInferenceCredentialError(ValueError):
    pass


@dataclass(frozen=True)
class HfInferenceAccount:
    subject: str
    username: str
    is_pro: bool


def _fernet(settings: Settings) -> Fernet:
    if not settings.jwt_secret:
        raise HfInferenceCredentialError("Credential encryption is not configured")
    digest = hashlib.sha256(
        f"pwc-hf-inference-v1:{settings.jwt_secret}".encode()
    ).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_token(token: str, subject: str, settings: Settings) -> str:
    payload = json.dumps(
        {"token": token, "sub": subject},
        separators=(",", ":"),
    ).encode()
    return _fernet(settings).encrypt(payload).decode()


def decrypt_token(value: str, subject: str, settings: Settings) -> str | None:
    try:
        payload = json.loads(_fernet(settings).decrypt(value.encode()))
    except (InvalidToken, ValueError, TypeError, json.JSONDecodeError):
        return None
    token = payload.get("token")
    if payload.get("sub") != subject or not isinstance(token, str) or not token:
        return None
    return token


async def verify_token(token: str, expected_subject: str) -> HfInferenceAccount:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            HF_WHOAMI_URL,
            headers={"Authorization": f"Bearer {token}"},
        )
    if response.status_code != 200:
        raise HfInferenceCredentialError(
            "Hugging Face rejected this token. Use a token with Inference "
            "Providers permission."
        )
    payload = response.json()
    subject = payload.get("id")
    username = payload.get("name")
    if subject != expected_subject:
        raise HfInferenceCredentialError(
            "This token belongs to a different Hugging Face account."
        )
    if not isinstance(username, str) or not username:
        raise HfInferenceCredentialError("Hugging Face returned an invalid account")
    return HfInferenceAccount(
        subject=subject,
        username=username,
        is_pro=payload.get("isPro") is True,
    )
