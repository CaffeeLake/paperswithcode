"""Authentication helpers for protecting administrative endpoints."""

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

from backend.config import get_settings


admin_token_header = APIKeyHeader(name="X-Admin-Token", auto_error=False)


def require_admin_token(token: str = Depends(admin_token_header)) -> None:
    """Ensure that an admin token is present and matches configuration."""

    settings = get_settings()

    if not settings.admin_api_token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Admin token is not configured",
        )

    if token != settings.admin_api_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )

    # Returning None is sufficient for dependency success
