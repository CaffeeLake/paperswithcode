"""Validation for public links persisted in catalog and submission records."""

from __future__ import annotations

import re
from urllib.parse import SplitResult, urlsplit, urlunsplit

MAX_PUBLIC_URL_LENGTH = 2048
_CONTROL_OR_WHITESPACE = re.compile(r"[\x00-\x20\x7f]")


class PublicUrlValidationError(ValueError):
    pass


def normalize_public_url(value: str) -> str:
    if not isinstance(value, str):
        raise PublicUrlValidationError("URL must be a string")
    normalized = value.strip()
    if not normalized or len(normalized) > MAX_PUBLIC_URL_LENGTH:
        raise PublicUrlValidationError(
            f"URL must be between 1 and {MAX_PUBLIC_URL_LENGTH} characters"
        )
    if _CONTROL_OR_WHITESPACE.search(normalized):
        raise PublicUrlValidationError("URL must not contain whitespace or controls")
    try:
        parsed = urlsplit(normalized)
        port = parsed.port
    except ValueError as exc:
        raise PublicUrlValidationError("URL is malformed") from exc
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.hostname:
        raise PublicUrlValidationError("URL must be an absolute HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise PublicUrlValidationError("URL must not contain credentials")
    try:
        ascii_host = parsed.hostname.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise PublicUrlValidationError("URL hostname is malformed") from exc
    if not ascii_host:
        raise PublicUrlValidationError("URL hostname is required")
    rendered_host = f"[{ascii_host}]" if ":" in ascii_host else ascii_host
    netloc = rendered_host if port is None else f"{rendered_host}:{port}"
    return urlunsplit(
        SplitResult(scheme, netloc, parsed.path or "", parsed.query, parsed.fragment)
    )


def normalize_optional_public_url(value: str | None) -> str | None:
    return None if value is None else normalize_public_url(value)
