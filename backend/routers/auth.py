"""
Hugging Face OAuth authentication for the PapersWithCode API.

Implements the "Sign in with Hugging Face" flow described at
https://huggingface.co/docs/hub/oauth :

  * `GET  /auth/hf/login`     — redirects the browser to HF authorize URL.
  * `GET  /auth/hf/callback`  — exchanges the auth code for an access token,
                                fetches the userinfo, sets a signed session
                                cookie and redirects back to `return_to`.
  * `POST /auth/logout`       — clears the session cookie.
  * `GET  /auth/me`           — returns the signed-in user (or 401).

The session cookie is a JWT (HS256) signed with `PWC_JWT_SECRET`.  It is the
sole source of truth for "is this request from an admin?" — see
`backend.utils.auth.require_admin`.
"""

from __future__ import annotations

import secrets
import time
from typing import Optional
from urllib.parse import urlencode, urlparse

import httpx
import jwt
from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from backend.config import get_settings


router = APIRouter()


HF_AUTHORIZE_URL = "https://huggingface.co/oauth/authorize"
HF_TOKEN_URL = "https://huggingface.co/oauth/token"
HF_USERINFO_URL = "https://huggingface.co/oauth/userinfo"

SESSION_COOKIE_NAME = "pwc_session"
SESSION_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days
STATE_TTL_SECONDS = 5 * 60  # 5 minutes


class AuthMe(BaseModel):
    username: str
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    is_admin: bool


def _origin_from_request(request: Request) -> str:
    """Best-effort origin (scheme + host) for the incoming request.

    Honours `X-Forwarded-Proto`/`Host` because we sit behind nginx in prod.
    """

    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if not host:
        host = request.url.netloc
    return f"{proto}://{host}"


def _redirect_uri(request: Request) -> str:
    """Compute the absolute redirect URI registered with the HF OAuth app."""

    return f"{_origin_from_request(request)}/api/v1/auth/hf/callback"


def _safe_return_to(value: Optional[str]) -> str:
    """Restrict `return_to` to same-origin paths to prevent open redirects."""

    if not value:
        return "/"
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc:
        return "/"
    if not value.startswith("/"):
        return "/"
    return value


def _is_admin(username: str) -> bool:
    settings = get_settings()
    return username.lower() in settings.admin_hf_username_set


def _encode_state(return_to: str, host: str) -> str:
    settings = get_settings()
    payload = {
        "nonce": secrets.token_urlsafe(16),
        "host": host,
        "return_to": return_to,
        "exp": int(time.time()) + STATE_TTL_SECONDS,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def _decode_state(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])


def _encode_session(user: dict) -> str:
    settings = get_settings()
    payload = {
        "sub": user["sub"],
        "username": user["username"],
        "name": user.get("name"),
        "avatar_url": user.get("avatar_url"),
        "is_admin": _is_admin(user["username"]),
        "exp": int(time.time()) + SESSION_TTL_SECONDS,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_session_cookie(token: str) -> Optional[dict]:
    """Decode + validate the session JWT.  Returns None on any failure."""

    settings = get_settings()
    if not settings.jwt_secret or not token:
        return None
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def _set_session_cookie(response: Response, token: str, secure: bool) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )


def _clear_session_cookie(response: Response, secure: bool) -> None:
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=secure,
        samesite="lax",
    )


def _is_secure_origin(request: Request) -> bool:
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    return proto == "https"


@router.get("/auth/hf/login")
async def hf_login(
    request: Request,
    return_to: Optional[str] = Query(default=None),
):
    """Kick off the HF OAuth authorization-code flow."""

    settings = get_settings()
    if not settings.hf_oauth_client_id or not settings.jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Hugging Face OAuth is not configured on this server",
        )

    safe_return = _safe_return_to(return_to)
    state = _encode_state(safe_return, request.headers.get("host", ""))
    params = {
        "client_id": settings.hf_oauth_client_id,
        "redirect_uri": _redirect_uri(request),
        "scope": "openid profile",
        "response_type": "code",
        "state": state,
    }
    return RedirectResponse(
        url=f"{HF_AUTHORIZE_URL}?{urlencode(params)}",
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/auth/hf/callback")
async def hf_callback(
    request: Request,
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
):
    """Complete the OAuth flow: trade the code for a token, set cookie."""

    settings = get_settings()
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Hugging Face returned an error: {error}",
        )
    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing code or state",
        )
    if not settings.hf_oauth_client_id or not settings.hf_oauth_client_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Hugging Face OAuth is not configured on this server",
        )

    try:
        state_payload = _decode_state(state)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OAuth state",
        ) from exc

    expected_host = state_payload.get("host")
    actual_host = request.headers.get("host", "")
    if expected_host and expected_host != actual_host:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state host mismatch",
        )

    return_to = _safe_return_to(state_payload.get("return_to"))

    async with httpx.AsyncClient(timeout=15.0) as client:
        token_response = await client.post(
            HF_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": _redirect_uri(request),
            },
            auth=(settings.hf_oauth_client_id, settings.hf_oauth_client_secret),
            headers={"Accept": "application/json"},
        )
        if token_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to exchange code for token: {token_response.text}",
            )
        token_payload = token_response.json()
        access_token = token_payload.get("access_token")
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Hugging Face did not return an access token",
            )

        userinfo_response = await client.get(
            HF_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if userinfo_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to fetch HF userinfo: {userinfo_response.text}",
            )
        userinfo = userinfo_response.json()

    username = userinfo.get("preferred_username") or userinfo.get("name")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="HF userinfo did not include a username",
        )

    session_token = _encode_session(
        {
            "sub": userinfo.get("sub", username),
            "username": username,
            "name": userinfo.get("name"),
            "avatar_url": userinfo.get("picture"),
        }
    )

    response = RedirectResponse(url=return_to, status_code=status.HTTP_302_FOUND)
    _set_session_cookie(response, session_token, secure=_is_secure_origin(request))
    return response


@router.post("/auth/logout")
async def logout(request: Request):
    response = JSONResponse({"ok": True})
    _clear_session_cookie(response, secure=_is_secure_origin(request))
    return response


@router.get("/auth/me", response_model=AuthMe)
async def me(request: Request):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    payload = decode_session_cookie(token or "")
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return AuthMe(
        username=payload["username"],
        name=payload.get("name"),
        avatar_url=payload.get("avatar_url"),
        is_admin=_is_admin(payload["username"]),
    )
