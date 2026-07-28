from __future__ import annotations

import base64
from urllib.parse import parse_qs, urlparse

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from starlette.requests import Request

from backend.config import Settings
from backend.routers import auth


def _key_values() -> tuple[str, str]:
    private_key = Ed25519PrivateKey.from_private_bytes(b"\x02" * 32)
    private_value = base64.urlsafe_b64encode(b"\x02" * 32).rstrip(b"=").decode()
    public_value = (
        base64.urlsafe_b64encode(
            private_key.public_key().public_bytes(
                serialization.Encoding.Raw,
                serialization.PublicFormat.Raw,
            )
        )
        .rstrip(b"=")
        .decode()
    )
    return private_value, public_value


def _settings(*, production: bool) -> Settings:
    private_value, public_value = _key_values()
    return Settings(
        environment="production" if production else "staging",
        jwt_secret="production-legacy" if production else "staging-legacy",
        session_cookie_name="pwc_session" if production else "pwc_staging_session",
        shared_session_cookie_name="pwc_shared_session",
        shared_session_cookie_domain=".paperswithcode.co",
        session_signing_private_key=private_value if production else "",
        session_verification_public_key=public_value,
        auth_authority_origin="https://paperswithcode.co",
        auth_return_origins=(
            "https://paperswithcode.co,https://staging.paperswithcode.co"
        ),
        admin_hf_usernames="alice",
        hf_oauth_client_id="client",
    )


def _request(host: str, cookie: str = "") -> Request:
    headers = [(b"host", host.encode()), (b"x-forwarded-proto", b"https")]
    if cookie:
        headers.append((b"cookie", cookie.encode()))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "scheme": "http",
            "headers": headers,
        }
    )


def test_production_session_is_verified_on_staging(monkeypatch):
    current = _settings(production=True)
    monkeypatch.setattr(auth, "get_settings", lambda: current)
    token = auth._encode_session(
        {"sub": "hf-123", "username": "Alice", "name": "Alice"}
    )

    current = _settings(production=False)
    payload = auth.decode_request_session(
        _request("staging.paperswithcode.co", f"pwc_shared_session={token}")
    )

    assert payload is not None
    assert payload["sub"] == "hf-123"
    assert payload["username"] == "Alice"


def test_staging_legacy_token_cannot_impersonate_shared_session(monkeypatch):
    settings = _settings(production=False)
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    token = jwt.encode(
        {"sub": "forged", "username": "Alice"},
        settings.jwt_secret,
        algorithm="HS256",
    )

    assert (
        auth.decode_request_session(
            _request("staging.paperswithcode.co", f"pwc_shared_session={token}")
        )
        is None
    )


def test_staging_login_redirects_to_production_authority(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: _settings(production=False))

    response = auth.hf_login(
        _request("staging.paperswithcode.co"),
        return_to="/chat?paper=123",
    )

    location = response.headers["location"]
    parsed = urlparse(location)
    assert f"{parsed.scheme}://{parsed.netloc}" == "https://paperswithcode.co"
    assert parsed.path == "/api/v1/auth/hf/login"
    assert parse_qs(parsed.query)["return_to"] == [
        "https://staging.paperswithcode.co/chat?paper=123"
    ]


def test_absolute_return_destinations_are_allowlisted(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: _settings(production=True))

    assert (
        auth._safe_return_to("https://staging.paperswithcode.co/chat")
        == "https://staging.paperswithcode.co/chat"
    )
    assert auth._safe_return_to("https://evil.example/chat") == "/"
