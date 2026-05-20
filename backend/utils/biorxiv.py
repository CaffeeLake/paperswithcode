"""
bioRxiv / medRxiv metadata adapter.

The HTML pages on https://www.biorxiv.org and https://www.medrxiv.org are
served behind Cloudflare's bot challenge and return HTTP 403 to every
server-side request regardless of user agent. To support user submissions of
bio/medRxiv papers we instead pull metadata from the public bioRxiv API
(https://api.biorxiv.org), which is not behind the challenge.

This module is intentionally tiny: just URL detection + a single GET against
the details endpoint, returning a normalized dataclass that the
external-resource ingestion path can consume.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional
from urllib.parse import urlparse

import aiohttp


logger = logging.getLogger(__name__)

# The bioRxiv API rate-limits requests that use aiohttp's default user agent
# (HTTP 429), so identify ourselves explicitly.
_API_HEADERS = {
    "User-Agent": (
        "paperswithcode.co external resource indexer (+https://paperswithcode.co)"
    ),
    "Accept": "application/json",
}


# Both bioRxiv and medRxiv use the same `10.1101/<suffix>` DOI prefix.
_DOI_IN_URL_RE = re.compile(
    r"(10\.1101/[A-Za-z0-9._\-]+?)(?:v\d+)?(?:\.full(?:\.pdf)?)?(?:[/?#]|$)"
)

# Fallback for the "early" URL form:
# https://www.biorxiv.org/content/early/2025/05/18/2025.05.14.654049v1
_EARLY_DOI_TAIL_RE = re.compile(r"^(\d{4}\.\d{2}\.\d{2}\.\d+)(?:v\d+)?(?:\.full)?$")

_PREPRINT_SERVERS = {
    "www.biorxiv.org": "biorxiv",
    "biorxiv.org": "biorxiv",
    "www.medrxiv.org": "medrxiv",
    "medrxiv.org": "medrxiv",
}


@dataclass
class BioRxivMetadata:
    """Normalized subset of the bioRxiv API response used for ingestion."""

    title: str
    abstract: Optional[str] = None
    authors: List[str] = field(default_factory=list)
    date_published: Optional[date] = None
    doi: Optional[str] = None


def parse_biorxiv_doi(url: str) -> Optional[tuple[str, str]]:
    """
    Extract ``(server, doi)`` from a bio/medRxiv URL.

    Returns ``None`` if the URL is not a recognized bio/medRxiv link.
    ``server`` is the bioRxiv API server segment (``"biorxiv"`` or
    ``"medrxiv"``). ``doi`` is the canonical DOI without version suffix
    (e.g. ``"10.1101/2025.05.14.654049"``).
    """
    if not url:
        return None

    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    server = _PREPRINT_SERVERS.get(host)
    if not server:
        return None

    match = _DOI_IN_URL_RE.search(parsed.path)
    if match:
        return server, match.group(1)

    # Fallback for /content/early/YYYY/MM/DD/<suffix>vN forms that omit the
    # `10.1101/` segment from the path.
    tail = parsed.path.rstrip("/").rsplit("/", 1)[-1]
    early_match = _EARLY_DOI_TAIL_RE.match(tail)
    if early_match:
        return server, f"10.1101/{early_match.group(1)}"

    return None


def _split_author_string(raw: str) -> List[str]:
    """Convert the bioRxiv "Last, F.; ..." author string to ``["First Last", ...]``."""
    if not raw:
        return []

    out: List[str] = []
    for entry in raw.split(";"):
        name = entry.strip()
        if not name:
            continue
        if "," in name:
            last, _, first = name.partition(",")
            last = last.strip()
            first = first.strip()
            display = f"{first} {last}".strip() if first else last
        else:
            display = name
        if display:
            out.append(display)
    return out


async def fetch_biorxiv_metadata(
    url: str, timeout_seconds: float = 12.0
) -> Optional[BioRxivMetadata]:
    """
    Fetch metadata for a bio/medRxiv URL via the public API.

    Returns ``None`` if the URL is not a bio/medRxiv link or the API call
    fails. Raised exceptions are swallowed and logged: callers should treat a
    ``None`` return as "fall back to generic extraction".
    """
    parsed = parse_biorxiv_doi(url)
    if parsed is None:
        return None

    server, doi = parsed
    api_url = f"https://api.biorxiv.org/details/{server}/{doi}"

    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    try:
        async with aiohttp.ClientSession(
            headers=_API_HEADERS, timeout=timeout
        ) as session:
            async with session.get(api_url, allow_redirects=True) as response:
                response.raise_for_status()
                payload = await response.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        logger.warning("biorxiv api fetch failed for %s: %s", api_url, exc)
        return None
    except asyncio.CancelledError:
        return None

    collection = (payload or {}).get("collection") or []
    if not isinstance(collection, list) or not collection:
        return None

    # Pick the latest version by `version` if present.
    def _version_key(item: dict) -> int:
        try:
            return int(str(item.get("version") or "1"))
        except (TypeError, ValueError):
            return 1

    entry = max(
        (e for e in collection if isinstance(e, dict)),
        key=_version_key,
        default=None,
    )
    if entry is None:
        return None

    title = (entry.get("title") or "").strip()
    if not title:
        return None

    abstract = (entry.get("abstract") or "").strip() or None
    authors = _split_author_string(entry.get("authors") or "")

    date_str = entry.get("date")
    parsed_date: Optional[date] = None
    if isinstance(date_str, str) and date_str:
        try:
            parsed_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            logger.warning("biorxiv api returned unparseable date %r", date_str)

    return BioRxivMetadata(
        title=title,
        abstract=abstract,
        authors=authors,
        date_published=parsed_date,
        doi=str(entry.get("doi") or doi),
    )
