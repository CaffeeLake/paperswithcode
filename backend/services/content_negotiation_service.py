"""HTTP content negotiation helpers for canonical public pages."""

from __future__ import annotations

import re
from collections.abc import MutableMapping

_MEDIA_RANGE_RE = re.compile(
    r"^(?:[!#$%&'*+.^_`|~0-9a-z-]+|\*)/"
    r"(?:[!#$%&'*+.^_`|~0-9a-z-]+|\*)$"
)


def _quality(parameters: list[str]) -> float | None:
    quality = 1.0
    for parameter in parameters:
        name, separator, value = parameter.strip().partition("=")
        if not separator or name.lower() != "q":
            continue
        try:
            quality = float(value.strip().strip('"'))
        except ValueError:
            return None
        if not 0 <= quality <= 1:
            return None
    return quality


def _media_ranges(accept_header: str) -> list[tuple[str, float, int]]:
    ranges: list[tuple[str, float, int]] = []
    for position, item in enumerate(accept_header.split(",")):
        media_type, *parameters = item.split(";")
        media_type = media_type.strip().lower()
        if not _MEDIA_RANGE_RE.fullmatch(media_type):
            continue
        major, minor = media_type.split("/", 1)
        if major == "*" and minor != "*":
            continue
        quality = _quality(parameters)
        if quality is not None:
            ranges.append((media_type, quality, position))
    return ranges


def _effective_quality(
    ranges: list[tuple[str, float, int]], media_type: str
) -> tuple[float, int] | None:
    major, _ = media_type.split("/", 1)
    matches = [
        (range_type.count("*"), position, quality)
        for range_type, quality, position in ranges
        if range_type in {media_type, f"{major}/*", "*/*"}
    ]
    if not matches:
        return None
    _, position, quality = min(matches, key=lambda item: (item[0], item[1]))
    return quality, position


def prefers_markdown(accept_header: str | None) -> bool:
    """Return whether an Accept header gives Markdown priority over HTML."""
    if not accept_header:
        return False
    ranges = _media_ranges(accept_header)
    markdown = _effective_quality(ranges, "text/markdown")
    if markdown is None or markdown[0] == 0:
        return False
    html = _effective_quality(ranges, "text/html")
    if html is None:
        return True
    if markdown[0] != html[0]:
        return markdown[0] > html[0]
    return markdown[1] < html[1]


def merge_vary(headers: MutableMapping[str, str], value: str) -> None:
    """Merge a case-insensitive value into a response's Vary header."""
    existing_key = next((key for key in headers if key.lower() == "vary"), "Vary")
    values = [
        item.strip()
        for item in headers.get(existing_key, "").split(",")
        if item.strip()
    ]
    if value.lower() not in {item.lower() for item in values}:
        values.append(value)
    headers[existing_key] = ", ".join(values)


def public_page_headers(
    canonical_url: str,
    *,
    cache_control: str = "public, max-age=300, stale-while-revalidate=3600",
) -> dict[str, str]:
    headers = {
        "Cache-Control": cache_control,
        "Link": f'<{canonical_url}>; rel="canonical"',
    }
    merge_vary(headers, "Accept")
    return headers
