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
    organizations: tuple[HfInferenceOrganization, ...]


@dataclass(frozen=True)
class HfInferenceOrganization:
    name: str
    display_name: str


@dataclass(frozen=True)
class HfInferenceCredential:
    token: str
    bill_to: str | None = None


def _fernet(settings: Settings) -> Fernet:
    if not settings.jwt_secret:
        raise HfInferenceCredentialError("Credential encryption is not configured")
    digest = hashlib.sha256(
        f"pwc-hf-inference-v1:{settings.jwt_secret}".encode()
    ).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_credential(
    credential: HfInferenceCredential, subject: str, settings: Settings
) -> str:
    payload = json.dumps(
        {
            "token": credential.token,
            "sub": subject,
            "bill_to": credential.bill_to,
        },
        separators=(",", ":"),
    ).encode()
    return _fernet(settings).encrypt(payload).decode()


def encrypt_token(token: str, subject: str, settings: Settings) -> str:
    return encrypt_credential(HfInferenceCredential(token), subject, settings)


def decrypt_credential(
    value: str, subject: str, settings: Settings
) -> HfInferenceCredential | None:
    try:
        payload = json.loads(_fernet(settings).decrypt(value.encode()))
    except (InvalidToken, ValueError, TypeError, json.JSONDecodeError):
        return None
    token = payload.get("token")
    if payload.get("sub") != subject or not isinstance(token, str) or not token:
        return None
    bill_to = payload.get("bill_to")
    if bill_to is not None and (not isinstance(bill_to, str) or not bill_to):
        return None
    return HfInferenceCredential(token=token, bill_to=bill_to)


def decrypt_token(value: str, subject: str, settings: Settings) -> str | None:
    credential = decrypt_credential(value, subject, settings)
    return credential.token if credential else None


def _organizations(payload: dict) -> tuple[HfInferenceOrganization, ...]:
    organizations: dict[str, HfInferenceOrganization] = {}
    for raw in payload.get("orgs") or []:
        if not isinstance(raw, dict):
            continue
        name = raw.get("name")
        if not isinstance(name, str) or not name:
            continue
        display_name = raw.get("fullname")
        organizations[name] = HfInferenceOrganization(
            name=name,
            display_name=(
                display_name if isinstance(display_name, str) and display_name else name
            ),
        )
    return tuple(sorted(organizations.values(), key=lambda org: org.name.lower()))


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
        organizations=_organizations(payload),
    )


def validate_bill_to(account: HfInferenceAccount, bill_to: str | None) -> None:
    if bill_to is None:
        return
    if bill_to not in {organization.name for organization in account.organizations}:
        raise HfInferenceCredentialError(
            "Choose an organization associated with this Hugging Face token."
        )
