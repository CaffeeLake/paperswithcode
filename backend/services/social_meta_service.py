"""
Per-paper social preview (Open Graph / Twitter) meta tag injection.

Paper pages are normally rendered by the React SPA from `frontend/dist/
index.html`, which carries only generic site-wide social tags. Crawlers like
Twitterbot, Slackbot and Discord don't execute JavaScript, so they always see
the same generic preview for every paper URL.

This module returns a per-paper variant of the SPA HTML with paper-specific
`<title>`, `description`, `og:*` and `twitter:*` tags injected, including
an absolute image URL pointing at the paper's existing thumbnail when the
image is already on disk. When no thumbnail is available we point at a
shared static fallback that always exists.

Nothing here touches the React bundle or runtime behaviour. The injected
HTML still references the same Vite-built `index.html`, and React takes over
once it boots.
"""

from __future__ import annotations

import html as html_lib
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

from backend.models.api import Paper
from backend.services.thumbnail_service import ThumbnailService
from backend.utils.latex_text import latex_to_plain_text

logger = logging.getLogger(__name__)


PRODUCTION_ORIGIN = "https://paperswithcode.co"
FALLBACK_IMAGE_PATH = "/api/og/default.png"
MAX_DESCRIPTION_CHARS = 280


@dataclass(frozen=True)
class _ResolvedImage:
    """Outcome of resolving the social image URL for a paper."""

    absolute_url: str
    is_fallback: bool


def build_request_origin(
    scheme: Optional[str],
    host: Optional[str],
) -> str:
    """
    Build the public origin (``scheme://host``) for absolute URLs in meta tags.

    Falls back to the production origin when the request did not carry
    trustworthy forwarded headers (the typical case when curling the
    backend directly without a host header).
    """
    safe_scheme = (scheme or "https").lower()
    if safe_scheme not in {"http", "https"}:
        safe_scheme = "https"
    safe_host = (host or "").strip()
    if not safe_host:
        return PRODUCTION_ORIGIN
    return f"{safe_scheme}://{safe_host}"


def _truncate_description(text: str, limit: int = MAX_DESCRIPTION_CHARS) -> str:
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    truncated = cleaned[: limit - 1].rstrip()
    return truncated + "\u2026"


def _absolutize(url: str, origin: str) -> str:
    parts = urlsplit(url)
    if parts.scheme and parts.netloc:
        return url
    return origin.rstrip("/") + "/" + url.lstrip("/")


def _is_arxiv_thumbnail_url(path: str) -> bool:
    return path.startswith("/api/thumbnails/") and not path.startswith(
        "/api/thumbnails/custom/"
    )


def _is_custom_thumbnail_url(path: str) -> bool:
    return path.startswith("/api/thumbnails/custom/")


def _extract_thumbnail_filename(thumbnail_path: str) -> Optional[str]:
    """Pull the JPEG filename out of an internal /api/thumbnails/... URL."""
    parts = urlsplit(thumbnail_path)
    leaf = parts.path.rsplit("/", 1)[-1]
    if not leaf or "." not in leaf:
        return None
    return leaf


def _strip_thumbnail_query_for_external_check(url: str) -> str:
    """Return ``url`` with query/fragment removed for filesystem lookups."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def resolve_social_image_url(
    paper: Paper,
    origin: str,
    thumbnail_service: Optional[ThumbnailService] = None,
) -> _ResolvedImage:
    """
    Pick an absolute image URL for ``og:image`` / ``twitter:image``.

    Prefers the paper's existing thumbnail (the same JPEG the site already
    displays in feed cards). If that file is not yet on disk locally we use
    the shared default image so crawlers always receive a working URL.
    """
    raw_thumb = (paper.thumbnail_url or "").strip()
    if not raw_thumb:
        return _ResolvedImage(
            _absolutize(FALLBACK_IMAGE_PATH, origin), is_fallback=True
        )

    if raw_thumb.startswith(("http://", "https://")):
        return _ResolvedImage(raw_thumb, is_fallback=False)

    if not raw_thumb.startswith("/"):
        return _ResolvedImage(
            _absolutize(FALLBACK_IMAGE_PATH, origin), is_fallback=True
        )

    if _is_arxiv_thumbnail_url(raw_thumb) or _is_custom_thumbnail_url(raw_thumb):
        path_only = _strip_thumbnail_query_for_external_check(raw_thumb)
        filename = _extract_thumbnail_filename(path_only)
        if filename:
            service = thumbnail_service or ThumbnailService()
            on_disk = _check_thumbnail_on_disk(
                service, filename, _is_custom_thumbnail_url(raw_thumb)
            )
            if on_disk:
                return _ResolvedImage(_absolutize(raw_thumb, origin), is_fallback=False)

    return _ResolvedImage(_absolutize(FALLBACK_IMAGE_PATH, origin), is_fallback=True)


def _check_thumbnail_on_disk(
    service: ThumbnailService, filename: str, is_custom: bool
) -> bool:
    """
    Check whether the thumbnail JPEG is materialised on the local mirror.

    ``get_local_thumbnail_path`` already filters out missing files, so we
    only need to check that it returned a path. Custom thumbnails go
    through the same disk-only path to avoid per-request HF bucket
    round-trips on the public preview hot path.
    """
    try:
        if is_custom:
            path: Optional[Path] = service.get_local_custom_thumbnail_path(filename)
        else:
            path = service.get_local_thumbnail_path(filename)
    except Exception as exc:
        logger.debug("Thumbnail existence check failed for %s: %s", filename, exc)
        return False
    return path is not None


def _authors_line(authors: list[str], max_authors: int = 5) -> str:
    cleaned = [a for a in (authors or []) if a]
    if not cleaned:
        return ""
    if len(cleaned) <= max_authors:
        return ", ".join(cleaned)
    head = ", ".join(cleaned[:max_authors])
    return f"{head} et al."


def _build_description(paper: Paper) -> str:
    """Pick a sensible description string from abstract + author line."""
    abstract = (paper.abstract or "").strip()
    if abstract:
        return _truncate_description(abstract)

    authors = _authors_line(paper.authors or [])
    if authors:
        return _truncate_description(f"By {authors}.")

    return "Trending AI research papers with code, datasets, methods, and evaluation leaderboards."


def _build_title(paper: Paper) -> str:
    paper_title = latex_to_plain_text((paper.title or "").strip()) or "Paper"
    return f"{paper_title} | Papers with Code"


def _build_canonical_url(origin: str, route_identifier: str) -> str:
    return f"{origin.rstrip('/')}/paper/{route_identifier}"


@dataclass(frozen=True)
class PaperMetaTags:
    """The set of meta tag values rendered into a paper-page HTML response."""

    title: str
    description: str
    canonical_url: str
    image_url: str
    is_fallback_image: bool


def build_paper_meta(
    paper: Paper,
    *,
    route_identifier: str,
    origin: str,
    thumbnail_service: Optional[ThumbnailService] = None,
) -> PaperMetaTags:
    image = resolve_social_image_url(paper, origin, thumbnail_service=thumbnail_service)
    return PaperMetaTags(
        title=_build_title(paper),
        description=_build_description(paper),
        canonical_url=_build_canonical_url(origin, route_identifier),
        image_url=image.absolute_url,
        is_fallback_image=image.is_fallback,
    )


# --- HTML injection ----------------------------------------------------------


_HEAD_CLOSE_RE = re.compile(r"</head\s*>", re.IGNORECASE)
_TITLE_TAG_RE = re.compile(r"<title>.*?</title>", re.IGNORECASE | re.DOTALL)
_META_NAME_RE_TEMPLATE = r'<meta\s+name=["\']{name}["\'][^>]*/?>'
_META_PROPERTY_RE_TEMPLATE = r'<meta\s+property=["\']{prop}["\'][^>]*/?>'


def _escape(value: str) -> str:
    return html_lib.escape(value, quote=True)


def _replace_or_remove(html: str, pattern: re.Pattern[str]) -> str:
    return pattern.sub("", html, count=1)


def inject_paper_meta(html: str, meta: PaperMetaTags) -> str:
    """
    Return ``html`` with paper-specific meta tags replacing the static ones.

    The strategy is:
      1. Strip the static meta tags that the production ``index.html`` ships
         with so crawlers don't see conflicting values.
      2. Insert a paper-specific block right before ``</head>`` containing
         the canonical title, description, and Open Graph / Twitter tags.

    String-based rewriting is intentional: the SPA's ``index.html`` is a tiny
    static template, and we want to avoid pulling in an HTML parser dependency
    just for this hot, per-request path.
    """
    rewritten = _TITLE_TAG_RE.sub("", html, count=1)
    for name in ("description", "twitter:card"):
        pattern = re.compile(_META_NAME_RE_TEMPLATE.format(name=name), re.IGNORECASE)
        rewritten = _replace_or_remove(rewritten, pattern)
    for prop in ("og:title", "og:description", "og:type"):
        pattern = re.compile(
            _META_PROPERTY_RE_TEMPLATE.format(prop=prop), re.IGNORECASE
        )
        rewritten = _replace_or_remove(rewritten, pattern)

    block = _render_meta_block(meta)

    match = _HEAD_CLOSE_RE.search(rewritten)
    if match:
        insert_at = match.start()
        return rewritten[:insert_at] + block + rewritten[insert_at:]

    return rewritten + block


def _render_meta_block(meta: PaperMetaTags) -> str:
    title = _escape(meta.title)
    description = _escape(meta.description)
    canonical = _escape(meta.canonical_url)
    image = _escape(meta.image_url)

    lines = [
        f"    <title>{title}</title>",
        f'    <meta name="description" content="{description}" />',
        f'    <link rel="canonical" href="{canonical}" />',
        f'    <meta property="og:title" content="{title}" />',
        f'    <meta property="og:description" content="{description}" />',
        '    <meta property="og:type" content="article" />',
        f'    <meta property="og:url" content="{canonical}" />',
        f'    <meta property="og:image" content="{image}" />',
        '    <meta property="og:site_name" content="Papers with Code" />',
        '    <meta name="twitter:card" content="summary_large_image" />',
        f'    <meta name="twitter:title" content="{title}" />',
        f'    <meta name="twitter:description" content="{description}" />',
        f'    <meta name="twitter:image" content="{image}" />',
    ]
    if meta.is_fallback_image:
        lines.extend(
            [
                '    <meta property="og:image:width" content="1200" />',
                '    <meta property="og:image:height" content="630" />',
            ]
        )

    return "\n" + "\n".join(lines) + "\n  "
