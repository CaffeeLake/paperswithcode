"""Capability-scoped, catalog-authorized web fetching for the chat worker."""

from __future__ import annotations

import asyncio
import re
import socket
from dataclasses import dataclass
from ipaddress import ip_address
from urllib.parse import urlsplit, urlunsplit

import aiohttp
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from backend.models.database import (
    Paper,
    PaperProjectPage,
    PaperRepository,
    ProjectPage,
    Repository,
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
    try:
        records = await asyncio.get_running_loop().getaddrinfo(
            host,
            443,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    except socket.gaierror:
        raise ChatWebFetchError(
            502, "The WebFetch hostname could not be resolved"
        ) from None
    addresses = tuple(dict.fromkeys(record[4][0] for record in records))
    if not addresses or any(not ip_address(value).is_global for value in addresses):
        raise ChatWebFetchError(403, "WebFetch cannot access a private network address")
    return addresses


class _PinnedResolver(aiohttp.abc.AbstractResolver):
    def __init__(self, host: str, addresses: tuple[str, ...]):
        self.host = host
        self.addresses = addresses

    async def resolve(self, host: str, port: int = 0, family: int = socket.AF_INET):
        if host != self.host:
            raise OSError("Unexpected WebFetch hostname")
        return [
            {
                "hostname": host,
                "host": address,
                "port": port,
                "family": socket.AF_INET6 if ":" in address else socket.AF_INET,
                "proto": socket.IPPROTO_TCP,
                "flags": socket.AI_NUMERICHOST,
            }
            for address in self.addresses
        ]

    async def close(self) -> None:
        return None


def _validate_origin_metadata(status_code: int, content_type: str) -> str:
    if 300 <= status_code < 400:
        raise ChatWebFetchError(409, "WebFetch redirects are not allowed")
    if status_code < 200 or status_code >= 300:
        raise ChatWebFetchError(502, f"WebFetch origin returned HTTP {status_code}")
    normalized = content_type.split(";", 1)[0].lower()
    if normalized not in _ALLOWED_CONTENT_TYPES:
        raise ChatWebFetchError(
            415, f"Unsupported WebFetch content type: {normalized or 'unknown'}"
        )
    return normalized


def _validate_body_size(body: bytes) -> bytes:
    if len(body) > MAX_WEB_FETCH_BYTES:
        raise ChatWebFetchError(413, "The WebFetch response is too large")
    return body


async def fetch_catalog_url(db: Session, value: str) -> WebFetchResult:
    url = authorize_catalog_url(db, value)
    host = urlsplit(url).hostname
    assert host is not None
    addresses = await _public_addresses(host)
    timeout = aiohttp.ClientTimeout(total=WEB_FETCH_TIMEOUT_SECONDS)
    connector = aiohttp.TCPConnector(
        resolver=_PinnedResolver(host, addresses),
        ttl_dns_cache=0,
        use_dns_cache=False,
    )
    headers = {
        "Accept": "text/markdown, text/html, text/plain, application/pdf",
        "User-Agent": "PapersWithCode-Research-WebFetch/1.0",
    }
    try:
        async with (
            aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                auto_decompress=True,
                headers=headers,
            ) as client,
            client.get(url, allow_redirects=False) as response,
        ):
            content_type = _validate_origin_metadata(
                response.status, response.headers.get("Content-Type", "")
            )
            body = await response.content.read(MAX_WEB_FETCH_BYTES + 1)
    except ChatWebFetchError:
        raise
    except (TimeoutError, aiohttp.ClientError):
        raise ChatWebFetchError(502, "The WebFetch origin request failed") from None
    return WebFetchResult(200, content_type, _validate_body_size(body))
