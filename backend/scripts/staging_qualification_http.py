"""HTTP client helpers for staging qualification through the active slot."""

from __future__ import annotations

import os
from pathlib import Path

import httpx

DEFAULT_ACTIVE_SOCKET = Path(
    "/srv/paperswithcode/environments/staging/active/backend.sock"
)


def active_socket() -> Path:
    return Path(os.environ.get("PWC_STAGING_ACTIVE_SOCKET", str(DEFAULT_ACTIVE_SOCKET)))


def client(
    *,
    timeout: float,
    cookies: dict[str, str],
) -> httpx.AsyncClient:
    socket_path = active_socket()
    if not socket_path.exists():
        raise RuntimeError(f"staging active socket is unavailable: {socket_path}")
    return httpx.AsyncClient(
        base_url="http://staging-active",
        transport=httpx.AsyncHTTPTransport(uds=str(socket_path)),
        timeout=timeout,
        cookies=cookies,
    )
