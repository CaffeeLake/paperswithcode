"""
HTTP utilities for fetching arbitrary external pages (blog posts, technical
reports, vendor announcements) used by the external-resource ingestion path.

Kept deliberately small: we only need plain HTML text and best-effort link
extraction. Heavy parsing (LLM page understanding) lives in genai_steps.
"""

import asyncio
import logging
import re
from typing import List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup


logger = logging.getLogger(__name__)


_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; paperswithcode.co external resource indexer)"
    ),
}


async def fetch_html(
    url: str, timeout_seconds: float = 15.0, max_bytes: int = 2_000_000
) -> Optional[str]:
    """
    Fetch an HTML page. Returns the raw HTML text or ``None`` on failure.

    `max_bytes` caps how much body we read so a runaway server cannot fill
    memory; 2 MB is more than enough for any technical report or blog post.
    """
    if not url:
        return None

    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    try:

        async def _do_fetch() -> Optional[str]:
            async with aiohttp.ClientSession(
                headers=_DEFAULT_HEADERS, timeout=timeout
            ) as session:
                async with session.get(url, allow_redirects=True) as response:
                    response.raise_for_status()
                    raw = await response.content.read(max_bytes + 1)
                    if len(raw) > max_bytes:
                        logger.warning(
                            "Truncating %s: body exceeded %d bytes", url, max_bytes
                        )
                        raw = raw[:max_bytes]
                    encoding = response.charset or "utf-8"
                    return raw.decode(encoding, errors="replace")

        return await asyncio.shield(_do_fetch())
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        logger.warning("fetch_html failed for %s: %s", url, exc)
        return None
    except asyncio.CancelledError:
        logger.warning("fetch_html cancelled for %s", url)
        return None


def html_to_text(html: str, max_chars: int = 100_000) -> str:
    """
    Best-effort extraction of readable page text. Falls back to raw text on
    parse errors. The output is truncated to `max_chars` to keep prompts small.
    """
    if not html:
        return ""

    try:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "template"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
    except Exception as exc:
        logger.warning("html_to_text parse failure: %s", exc)
        text = html

    text = re.sub(r"\n{3,}", "\n\n", text)
    if len(text) > max_chars:
        text = text[:max_chars]
    return text


_GITHUB_RE = re.compile(
    r"https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", re.IGNORECASE
)
_HF_REPO_RE = re.compile(
    r"https?://huggingface\.co/(?!papers/)[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",
    re.IGNORECASE,
)


def _absolute_links_from_html(html: str, base_url: str) -> List[str]:
    """All absolute href links from anchors plus raw URLs found in text."""
    if not html:
        return []
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        soup = None

    urls: List[str] = []
    if soup is not None:
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href:
                continue
            if href.startswith(("http://", "https://")):
                urls.append(href)
            elif href.startswith("/"):
                urls.append(urljoin(base_url, href))
    # Raw URLs in the visible text catch the case where the link is not
    # wrapped in an anchor tag (common in plain-text reports).
    urls.extend(_GITHUB_RE.findall(html))
    urls.extend(_HF_REPO_RE.findall(html))
    return urls


def extract_github_urls(html: str, base_url: str = "") -> List[str]:
    """Unique-by-(owner, name) GitHub repository URLs found on a page."""
    seen: set = set()
    out: List[str] = []
    for url in _absolute_links_from_html(html, base_url):
        match = _GITHUB_RE.search(url)
        if not match:
            continue
        candidate = match.group(0).rstrip("/")
        parts = urlparse(candidate).path.strip("/").split("/")
        if len(parts) < 2:
            continue
        # Drop trailing path segments (e.g. /tree/main/...).
        owner = parts[0]
        name = parts[1].rstrip(".git")
        key = (owner.lower(), name.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(f"https://github.com/{owner}/{name}")
    return out


def extract_hf_repo_urls(html: str, base_url: str = "") -> List[str]:
    """Unique HF model/dataset/space URLs (owner/name shape) found on a page."""
    seen: set = set()
    out: List[str] = []
    for url in _absolute_links_from_html(html, base_url):
        match = _HF_REPO_RE.search(url)
        if not match:
            continue
        candidate = match.group(0).rstrip("/")
        # Strip query/fragment
        candidate = candidate.split("?")[0].split("#")[0]
        # Skip non-repo HF paths like /docs, /pricing, /papers, etc.
        path = urlparse(candidate).path.strip("/")
        parts = path.split("/")
        if len(parts) < 2:
            continue
        first = parts[0].lower()
        if first in {"docs", "pricing", "blog", "join", "login", "papers"}:
            continue
        # Normalize to "owner/name" for typical HF paths and "datasets/owner/name"
        # or "spaces/owner/name" for datasets/spaces.
        if first in {"datasets", "spaces"} and len(parts) >= 3:
            normalized = f"https://huggingface.co/{parts[0]}/{parts[1]}/{parts[2]}"
        else:
            normalized = f"https://huggingface.co/{parts[0]}/{parts[1]}"
        if normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


_FRAMER_SEARCH_INDEX_RE = re.compile(
    r'name="framer-search-index"\s+content="([^"]+)"', re.IGNORECASE
)


async def _framer_search_index_text(html: str, page_url: str) -> Optional[str]:
    """
    Extract content from a Framer-hosted page via its search index JSON.

    Framer (the SPA builder used by some vendor sites such as zyphra.com)
    renders the body client-side, so the raw HTML returned by `fetch_html`
    is essentially empty. The page advertises a `framer-search-index`
    metadata URL whose JSON contains the prerendered text for every page on
    the site keyed by path. This function pulls the entry for the requested
    URL and concatenates its visible text.

    Returns ``None`` when the page is not a Framer SPA or when the index
    cannot be fetched/parsed.
    """
    match = _FRAMER_SEARCH_INDEX_RE.search(html)
    if not match:
        return None

    index_url = match.group(1)
    try:
        timeout = aiohttp.ClientTimeout(total=15.0)
        async with aiohttp.ClientSession(
            headers=_DEFAULT_HEADERS, timeout=timeout
        ) as session:
            async with session.get(index_url, allow_redirects=True) as response:
                response.raise_for_status()
                payload = await response.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        logger.warning("framer index fetch failed for %s: %s", index_url, exc)
        return None
    except asyncio.CancelledError:
        return None

    if not isinstance(payload, dict):
        return None

    def _entry_text(entry: dict) -> str:
        chunks: List[str] = []
        title = entry.get("title")
        if title:
            chunks.append(str(title))
        for key in ("h1", "h2", "h3", "h4", "h5", "h6", "p", "codeblock"):
            values = entry.get(key) or []
            if isinstance(values, list):
                for v in values:
                    if v:
                        chunks.append(str(v))
        return "\n".join(chunks).strip()

    def _entry_has_body(entry: dict) -> bool:
        """True iff the entry has at least one heading or paragraph."""
        for key in ("h1", "h2", "h3", "h4", "h5", "h6", "p", "codeblock"):
            values = entry.get(key) or []
            if isinstance(values, list) and any(v for v in values):
                return True
        return False

    path = urlparse(page_url).path or "/"
    entry = payload.get(path) or payload.get(path.rstrip("/"))

    # Some pages (e.g. PDF-hosting "technical report" pages) exist in the
    # index with only a site-level title and no body. Fall back to a related
    # companion post whose slug shares a stem with this URL after stripping
    # common suffixes.
    if not isinstance(entry, dict) or not _entry_has_body(entry):
        slug = path.strip("/").split("/")[-1].lower()
        suffix_words = ("-technical-report", "-paper", "-report", "-blog")
        stem = slug
        for suffix in suffix_words:
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
                break

        candidates = []
        for cand_path, cand in payload.items():
            if not isinstance(cand, dict):
                continue
            cand_slug = cand_path.strip("/").split("/")[-1].lower()
            if not cand_slug:
                continue
            score = 0
            if cand_slug == stem:
                score = 100
            elif stem and cand_slug.startswith(stem + "-"):
                score = 80
            elif stem and stem.startswith(cand_slug + "-"):
                score = 70
            elif stem and stem in cand_slug:
                score = 50
            if score and _entry_has_body(cand):
                candidates.append((score, cand_path, cand))

        if candidates:
            # Prefer /post/... entries (announcement bodies) over /models/...
            candidates.sort(
                key=lambda item: (
                    item[0],
                    1 if item[1].startswith("/post/") else 0,
                ),
                reverse=True,
            )
            entry = candidates[0][2]

    if not isinstance(entry, dict):
        return None

    text = _entry_text(entry)
    return text or None


async def fetch_html_and_text(
    url: str, max_text_chars: int = 60_000
) -> Tuple[Optional[str], Optional[str]]:
    """
    Convenience: fetch a URL and return (raw_html, plain_text). Either tuple
    element may be None if fetching fails.

    Falls back to the Framer search index when the rendered body is empty so
    that JS-only pages (e.g. zyphra.com) still yield usable text for the LLM.
    """
    html = await fetch_html(url)
    if html is None:
        return None, None

    text = html_to_text(html, max_chars=max_text_chars)
    if len(text) < 200:
        framer_text = await _framer_search_index_text(html, url)
        if framer_text:
            text = framer_text[:max_text_chars]

    return html, text
