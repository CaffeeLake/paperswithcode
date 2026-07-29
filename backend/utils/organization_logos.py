"""Stable, extension-bearing URLs for cached organization logos."""

LOGO_EXTENSIONS = {
    "image/gif": "gif",
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


def organization_logo_extension(mime_type: str | None) -> str | None:
    return LOGO_EXTENSIONS.get(mime_type or "")


def organization_logo_path(
    slug: str,
    mime_type: str | None,
    sha256: str | None = None,
) -> str | None:
    extension = organization_logo_extension(mime_type)
    if not extension:
        return None
    if sha256:
        return f"/api/v1/organizations/{slug}/logo/{sha256}.{extension}"
    return f"/api/v1/organizations/{slug}/logo.{extension}"
