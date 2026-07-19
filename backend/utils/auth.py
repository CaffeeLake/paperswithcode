"""Authentication helpers for protecting administrative endpoints.

Most admin endpoints accept either an HF OAuth session cookie or the legacy
``X-Admin-Token`` header for CLI/cron workflows. User-facing paper-page edits
on paper metadata use :func:`require_hf_admin` so only allowlisted HF accounts
can mutate them; evaluation CRUD uses :func:`require_admin` so scripts can
import rows with ``X-Admin-Token``.
"""

from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader

from backend.config import get_settings


admin_token_header = APIKeyHeader(name="X-Admin-Token", auto_error=False)


def require_admin(
    request: Request,
    admin_token: Optional[str] = Depends(admin_token_header),
) -> dict:
    """Allow the request iff the caller is a configured admin.

    Cookie path is preferred; the ``X-Admin-Token`` header is a fallback for
    scripts and curl-driven workflows.  Returns a small dict describing the
    caller; raises 401 otherwise.
    """

    settings = get_settings()

    # 1) Session cookie set by the HF OAuth callback.
    from backend.routers.auth import SESSION_COOKIE_NAME, decode_session_cookie

    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie:
        payload = decode_session_cookie(cookie)
        if payload and payload.get("is_admin"):
            return {
                "source": "cookie",
                "username": payload.get("username"),
            }

    # 2) X-Admin-Token header fallback (CLI / cron tooling).
    if (
        settings.admin_api_token
        and admin_token
        and admin_token == settings.admin_api_token
    ):
        return {"source": "header", "username": None}

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized",
    )


def require_hf_admin(request: Request) -> dict:
    """Allow the request only for an allowlisted Hugging Face session."""

    from backend.routers.auth import SESSION_COOKIE_NAME, decode_session_cookie

    settings = get_settings()
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    payload = decode_session_cookie(cookie or "")
    username = (payload or {}).get("username")
    if username and username.lower() in settings.admin_hf_username_set:
        return {
            "source": "cookie",
            "username": username,
        }

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sign in with an authorized Hugging Face account to edit this paper",
    )


def require_user(request: Request) -> dict:
    """Allow any signed-in HF user.

    Mirrors :func:`require_hf_admin` without the admin-allowlist check; used by
    user-scoped endpoints such as the bookmark API. Returns a small dict with
    the canonical HF ``username`` (lowercased) pulled from the session JWT.
    """

    from backend.routers.auth import SESSION_COOKIE_NAME, decode_session_cookie

    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    payload = decode_session_cookie(cookie or "")
    username = (payload or {}).get("username")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in with Hugging Face to use this feature",
        )
    return {
        "source": "cookie",
        "username": username.lower(),
    }
