"""Authenticated, bounded GitHub repository metadata for chat link previews."""

from __future__ import annotations

import time
from dataclasses import dataclass
from urllib.parse import quote

import httpx

from backend.config import Settings

_CACHE_TTL_SECONDS = 60 * 60
_CACHE_MAX_ENTRIES = 512
_CACHE: dict[str, tuple[float, "GithubRepositoryPreview"]] = {}


class GithubPreviewError(RuntimeError):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class GithubRepositoryPreview:
    description: str | None
    stars: int
    forks: int
    language: str | None
    archived: bool
    avatar_url: str | None


def _cached(key: str) -> GithubRepositoryPreview | None:
    cached = _CACHE.get(key)
    if cached is None:
        return None
    expires_at, preview = cached
    if expires_at <= time.monotonic():
        _CACHE.pop(key, None)
        return None
    return preview


def _remember(key: str, preview: GithubRepositoryPreview) -> None:
    if len(_CACHE) >= _CACHE_MAX_ENTRIES:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = (time.monotonic() + _CACHE_TTL_SECONDS, preview)


def _count(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


async def get_github_repository_preview(
    owner: str,
    repository: str,
    settings: Settings,
    *,
    client: httpx.AsyncClient | None = None,
) -> GithubRepositoryPreview:
    key = f"{owner}/{repository}".lower()
    if preview := _cached(key):
        return preview
    if not settings.github_token:
        raise GithubPreviewError(503, "GitHub previews are unavailable")

    encoded = "/".join(quote(part, safe="") for part in (owner, repository))
    active_client = client or httpx.AsyncClient(timeout=3, follow_redirects=False)
    try:
        response = await active_client.get(
            f"https://api.github.com/repos/{encoded}",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {settings.github_token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
    except httpx.TransportError:
        raise GithubPreviewError(502, "GitHub preview lookup failed") from None
    finally:
        if client is None:
            await active_client.aclose()

    if response.status_code == 404:
        raise GithubPreviewError(404, "GitHub repository not found")
    if response.status_code != 200:
        raise GithubPreviewError(502, "GitHub preview lookup failed")
    try:
        payload = response.json()
    except ValueError:
        raise GithubPreviewError(502, "GitHub preview lookup failed") from None
    if not isinstance(payload, dict):
        raise GithubPreviewError(502, "GitHub preview lookup failed")
    account = payload.get("owner")
    avatar_url = account.get("avatar_url") if isinstance(account, dict) else None
    preview = GithubRepositoryPreview(
        description=(
            str(payload["description"])[:500]
            if isinstance(payload.get("description"), str)
            else None
        ),
        stars=max(0, _count(payload.get("stargazers_count"))),
        forks=max(0, _count(payload.get("forks_count"))),
        language=(
            str(payload["language"])[:100]
            if isinstance(payload.get("language"), str)
            else None
        ),
        archived=payload.get("archived") is True,
        avatar_url=(
            str(avatar_url)[:1000]
            if isinstance(avatar_url, str) and avatar_url.startswith("https://")
            else None
        ),
    )
    _remember(key, preview)
    return preview
