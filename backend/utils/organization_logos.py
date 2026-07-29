"""Stable, extension-bearing URLs for cached organization logos."""

from typing import Optional


LOGO_EXTENSIONS = {
    "image/gif": "gif",
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


def organization_logo_extension(mime_type: Optional[str]) -> Optional[str]:
    return LOGO_EXTENSIONS.get(mime_type or "")


def organization_logo_path(slug: str, mime_type: Optional[str]) -> Optional[str]:
    extension = organization_logo_extension(mime_type)
    if not extension:
        return None
    return f"/api/v1/organizations/{slug}/logo.{extension}"
