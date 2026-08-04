"""Capability-scoped, catalog-authorized web fetching for the chat worker."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from backend.models.database import (
    Paper,
    PaperProjectPage,
    PaperRepository,
    ProjectPage,
    Repository,
)
from backend.services.safe_outbound_http_service import (
    SafeOutboundHttpError,
    fetch_public_resource,
    resolve_public_addresses,
)

MAX_WEB_FETCH_BYTES = 10 * 1024 * 1024
WEB_FETCH_TIMEOUT_SECONDS = 60
_ARXIV_HOST = "arxiv.org"
_HOST = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)
_ALLOWED_CONTENT_TYPES = frozenset(
    {
        "application/pdf",
        "application/xhtml+xml",
        "text/html",
        "text/markdown",
        "text/plain",
        "text/x-markdown",
    }
)


class ChatWebFetchError(RuntimeError):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class WebFetchResult:
    status_code: int
    content_type: str
    body: bytes


def canonical_fetch_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        if (
            parsed.scheme.lower() != "https"
            or not host
            or not host.isascii()
            or _HOST.fullmatch(host.lower().rstrip(".")) is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in {None, 443}
        ):
            raise ValueError
    except ValueError:
        raise ChatWebFetchError(422, "WebFetch requires a public HTTPS URL") from None

    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit(("https", host.lower().rstrip("."), path, parsed.query, ""))


def _arxiv_identifier(url: str) -> str | None:
    parsed = urlsplit(url)
    if parsed.hostname != _ARXIV_HOST or parsed.query:
        return None
    parts = parsed.path.strip("/").split("/")
    if len(parts) != 2 or parts[0] not in {"abs", "pdf"}:
        return None
    identifier = parts[1]
    identifier = identifier.removesuffix(".pdf")
    base, marker, version = identifier.partition("v")
    if marker and (not version.isdigit() or not version):
        return None
    year_month, dot, number = base.partition(".")
    if (
        not dot
        or len(year_month) != 4
        or len(number) not in {4, 5}
        or not year_month.isdigit()
        or not number.isdigit()
    ):
        return None
    return base


def authorize_catalog_url(db: Session, value: str) -> str:
    url = canonical_fetch_url(value)
    if identifier := _arxiv_identifier(url):
        found = db.execute(
            select(exists().where(Paper.arxiv_id == identifier))
        ).scalar_one()
        if found:
            return url
        raise ChatWebFetchError(403, "The ArXiv URL is not linked to a PwC paper")

    candidates = {url}
    if urlsplit(url).path != "/":
        candidates.add(f"{url}/")
    repository_exists = exists(
        select(Repository.id)
        .join(PaperRepository, PaperRepository.repository_id == Repository.id)
        .where(Repository.url.in_(candidates))
    )
    if db.execute(select(repository_exists)).scalar_one():
        return url
    project_exists = exists(
        select(ProjectPage.id)
        .join(
            PaperProjectPage,
            PaperProjectPage.project_page_id == ProjectPage.id,
        )
        .where(ProjectPage.url.in_(candidates))
    )
    if db.execute(select(project_exists)).scalar_one():
        return url
    raise ChatWebFetchError(403, "The URL is not attached to a PwC paper")


async def _public_addresses(host: str) -> tuple[str, ...]:
    """Compatibility wrapper for the shared pinned-fetch validation."""

    try:
        return await resolve_public_addresses(host, 443)
    except SafeOutboundHttpError as exc:
        raise ChatWebFetchError(exc.status_code, str(exc)) from exc


def _validate_origin_metadata(status_code: int, content_type: str) -> str:
    if 300 <= status_code < 400:
        raise ChatWebFetchError(409, "WebFetch redirects are not allowed")
    if not 200 <= status_code < 300:
        raise ChatWebFetchError(502, "WebFetch origin returned an error")
    normalized = content_type.split(";", 1)[0].lower()
    if normalized not in _ALLOWED_CONTENT_TYPES:
        raise ChatWebFetchError(415, "Unsupported WebFetch content type")
    return normalized


def _validate_body_size(body: bytes) -> bytes:
    if len(body) > MAX_WEB_FETCH_BYTES:
        raise ChatWebFetchError(413, "The WebFetch response is too large")
    return body


async def fetch_catalog_url(db: Session, value: str) -> WebFetchResult:
    url = authorize_catalog_url(db, value)
    try:
        result = await fetch_public_resource(
            url,
            allowed_content_types=_ALLOWED_CONTENT_TYPES,
            max_bytes=MAX_WEB_FETCH_BYTES,
            timeout_seconds=WEB_FETCH_TIMEOUT_SECONDS,
            max_redirects=0,
        )
    except SafeOutboundHttpError as exc:
        raise ChatWebFetchError(exc.status_code, str(exc)) from exc
    return WebFetchResult(result.status_code, result.content_type, result.body)
