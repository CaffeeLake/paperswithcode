"""Cross-device OpenRouter BYOK storage, consent, and online revocation."""

from __future__ import annotations

import base64
import json
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import (
    ChatOpenRouterCredential,
    ChatOpenRouterCredentialAudit,
)
from backend.services.openrouter_user_budget_service import opaque_owner

logger = logging.getLogger(__name__)
OPENROUTER_CURRENT_KEY_URL = "https://openrouter.ai/api/v1/key"


class OpenRouterCredentialError(ValueError):
    pass


class OpenRouterCredentialUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class OpenRouterCredentialStatus:
    connected: bool
    verified_at: datetime | None = None
    fallback_enabled: bool = False

    def public_dict(self) -> dict[str, object]:
        return {
            "connected": self.connected,
            "verified_at": self.verified_at,
            "fallback_enabled": self.fallback_enabled,
        }


@dataclass(frozen=True)
class SelectedOpenRouterCredential:
    token: str
    revision: uuid.UUID


def _decode_key(value: str) -> bytes:
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError) as error:
        raise OpenRouterCredentialUnavailable(
            "Credential keyring is invalid"
        ) from error
    if len(raw) != 32:
        raise OpenRouterCredentialUnavailable(
            "Credential keyring must contain AES-256 keys"
        )
    return raw


def credential_keyring(settings: Settings) -> dict[int, bytes]:
    try:
        payload = json.loads(settings.chat_openrouter_credential_keyring)
        result = {
            int(version): _decode_key(value) for version, value in payload.items()
        }
    except (AttributeError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise OpenRouterCredentialUnavailable(
            "Credential keyring is invalid"
        ) from error
    if settings.chat_openrouter_credential_active_key_version not in result:
        raise OpenRouterCredentialUnavailable("Active credential key is absent")
    return result


def _aad(owner_id: str) -> bytes:
    return f"paperswithcode:openrouter:{owner_id}:v1".encode()


def encrypt_openrouter_key(
    token: str, owner_id: str, settings: Settings
) -> tuple[bytes, bytes, int]:
    keyring = credential_keyring(settings)
    version = settings.chat_openrouter_credential_active_key_version
    nonce = os.urandom(12)
    ciphertext = AESGCM(keyring[version]).encrypt(nonce, token.encode(), _aad(owner_id))
    return ciphertext, nonce, version


def decrypt_openrouter_key(row: ChatOpenRouterCredential, settings: Settings) -> str:
    key = credential_keyring(settings).get(row.encryption_key_version)
    if key is None:
        raise OpenRouterCredentialUnavailable("Credential encryption key is absent")
    try:
        raw = AESGCM(key).decrypt(row.nonce, row.ciphertext, _aad(row.hf_user_id))
        value = raw.decode()
    except (ValueError, UnicodeDecodeError) as error:
        raise OpenRouterCredentialUnavailable(
            "OpenRouter credential could not decrypt"
        ) from error
    if not value:
        raise OpenRouterCredentialUnavailable("OpenRouter credential is empty")
    return value


async def verify_openrouter_inference_key(
    token: str, *, client: httpx.AsyncClient | None = None
) -> None:
    value = token.strip()
    if not value.startswith("sk-or-") or len(value) > 512:
        raise OpenRouterCredentialError("Enter a valid OpenRouter inference API key.")
    owns_client = client is None
    active = client or httpx.AsyncClient(timeout=10, follow_redirects=False)
    try:
        response = await active.get(
            OPENROUTER_CURRENT_KEY_URL,
            headers={"Authorization": f"Bearer {value}"},
        )
        if response.status_code != 200:
            raise OpenRouterCredentialError(
                "OpenRouter rejected this API key. Create an inference key and try again."
            )
        payload = response.json()
    except httpx.HTTPError as error:
        raise OpenRouterCredentialUnavailable(
            "OpenRouter key verification is temporarily unavailable"
        ) from error
    except OpenRouterCredentialError:
        raise
    except (TypeError, ValueError) as error:
        raise OpenRouterCredentialUnavailable(
            "OpenRouter returned an invalid key status"
        ) from error
    finally:
        if owns_client:
            await active.aclose()
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise OpenRouterCredentialUnavailable(
            "OpenRouter returned an invalid key status"
        )
    if (
        data.get("is_management_key") is not False
        or data.get("is_provisioning_key") is not False
    ):
        raise OpenRouterCredentialError(
            "Use an OpenRouter inference key, not a management or provisioning key."
        )


class OpenRouterBYOKService:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings

    def _row(self, owner_id: str, *, lock: bool = False):
        query = select(ChatOpenRouterCredential).where(
            ChatOpenRouterCredential.hf_user_id == owner_id
        )
        if lock:
            query = query.with_for_update()
        return self.db.execute(query).scalar_one_or_none()

    def _audit(self, owner_id: str, action: str, now: datetime) -> None:
        self.db.add(
            ChatOpenRouterCredentialAudit(
                owner_hash=opaque_owner(owner_id, self.settings),
                action=action,
                created_at=now,
            )
        )

    def status(self, owner_id: str) -> OpenRouterCredentialStatus:
        row = self._row(owner_id)
        if row is None:
            return OpenRouterCredentialStatus(connected=False)
        return OpenRouterCredentialStatus(
            connected=True,
            verified_at=row.verified_at,
            fallback_enabled=row.fallback_enabled,
        )

    async def connect(
        self, owner_id: str, token: str, now: datetime | None = None
    ) -> OpenRouterCredentialStatus:
        await verify_openrouter_inference_key(token)
        current = (now or datetime.now(UTC)).astimezone(UTC)
        ciphertext, nonce, version = encrypt_openrouter_key(
            token.strip(), owner_id, self.settings
        )
        row = self._row(owner_id, lock=True)
        replacement = row is not None
        if row is None:
            row = ChatOpenRouterCredential(
                hf_user_id=owner_id,
                ciphertext=ciphertext,
                nonce=nonce,
                encryption_key_version=version,
                verified_at=current,
                fallback_enabled=False,
                credential_revision=uuid.uuid4(),
                created_at=current,
                updated_at=current,
            )
            self.db.add(row)
        else:
            row.ciphertext = ciphertext
            row.nonce = nonce
            row.encryption_key_version = version
            row.verified_at = current
            row.fallback_enabled = False
            row.credential_revision = uuid.uuid4()
            row.updated_at = current
        self._audit(owner_id, "replaced" if replacement else "connected", current)
        self.db.flush()
        logger.info(
            "openrouter credential connected owner=%s replacement=%s",
            opaque_owner(owner_id, self.settings)[:16],
            replacement,
        )
        return self.status(owner_id)

    def set_fallback_enabled(
        self, owner_id: str, enabled: bool, now: datetime | None = None
    ) -> OpenRouterCredentialStatus:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        row = self._row(owner_id, lock=True)
        if row is None:
            raise OpenRouterCredentialError("Connect an OpenRouter API key first.")
        if row.fallback_enabled == enabled:
            return self.status(owner_id)
        row.fallback_enabled = enabled
        row.credential_revision = uuid.uuid4()
        row.updated_at = current
        self._audit(
            owner_id, "fallback_enabled" if enabled else "fallback_disabled", current
        )
        self.db.flush()
        return self.status(owner_id)

    def selected(self, owner_id: str) -> SelectedOpenRouterCredential | None:
        row = self._row(owner_id)
        if row is None or not row.fallback_enabled:
            return None
        return SelectedOpenRouterCredential(
            token=decrypt_openrouter_key(row, self.settings),
            revision=row.credential_revision,
        )

    def validate_dispatch(
        self, owner_id: str, revision: uuid.UUID
    ) -> SelectedOpenRouterCredential:
        row = self._row(owner_id)
        if (
            row is None
            or not row.fallback_enabled
            or row.credential_revision != revision
        ):
            raise OpenRouterCredentialUnavailable(
                "OpenRouter credential was disconnected or changed"
            )
        return SelectedOpenRouterCredential(
            token=decrypt_openrouter_key(row, self.settings), revision=revision
        )

    def invalidate_auth_failure(
        self, owner_id: str, now: datetime | None = None
    ) -> None:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        row = self._row(owner_id, lock=True)
        if row is None:
            return
        row.fallback_enabled = False
        row.credential_revision = uuid.uuid4()
        row.updated_at = current
        self._audit(owner_id, "invalidated", current)
        self.db.flush()

    def disconnect(
        self,
        owner_id: str,
        *,
        account_deleted: bool = False,
        now: datetime | None = None,
    ) -> None:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        row = self._row(owner_id, lock=True)
        if row is not None:
            self.db.delete(row)
        self._audit(
            owner_id, "account_deleted" if account_deleted else "disconnected", current
        )
        self.db.flush()

    def rotate_to_active_key(self, batch_size: int = 100) -> int:
        active = self.settings.chat_openrouter_credential_active_key_version
        rows = list(
            self.db.execute(
                select(ChatOpenRouterCredential)
                .where(ChatOpenRouterCredential.encryption_key_version != active)
                .order_by(ChatOpenRouterCredential.hf_user_id)
                .limit(max(1, min(batch_size, 500)))
                .with_for_update(skip_locked=True)
            ).scalars()
        )
        for row in rows:
            token = decrypt_openrouter_key(row, self.settings)
            ciphertext, nonce, version = encrypt_openrouter_key(
                token, row.hf_user_id, self.settings
            )
            row.ciphertext = ciphertext
            row.nonce = nonce
            row.encryption_key_version = version
            row.updated_at = datetime.now(UTC)
        self.db.flush()
        return len(rows)

    def purge_audit_for_owner_is_forbidden(self, _owner_id: str) -> None:
        """Audit rows intentionally have no reversible owner identifier."""

        raise OpenRouterCredentialError("Credential audit is retention-managed")
