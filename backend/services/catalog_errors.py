"""Typed domain failures shared by catalog services.

These errors deliberately carry only the public detail string.  HTTP adapters
translate that detail centrally, keeping catalog services independent of
FastAPI while preserving the API's established error payload shape.
"""


class CatalogError(Exception):
    """Base class for failures from catalog domain operations."""

    def __init__(self, detail: str | dict):
        self.detail = detail
        super().__init__(detail)


class CatalogNotFoundError(CatalogError):
    """Raised when a catalog entity cannot be found."""


class CatalogConflictError(CatalogError, ValueError):
    """Raised when a catalog operation conflicts with current state."""


class CatalogValidationError(CatalogError, ValueError):
    """Raised when catalog operation input is invalid."""


class CatalogPersistenceError(CatalogError):
    """Raised when catalog persistence cannot complete."""


def raise_as_catalog_error(error: Exception) -> None:
    """Re-raise legacy catalog failures as their public typed equivalents."""
    from backend.utils.exceptions import DatabaseError, PaperNotFoundError

    if isinstance(error, PaperNotFoundError):
        raise CatalogNotFoundError(str(error)) from error
    if isinstance(error, DatabaseError):
        raise CatalogPersistenceError(str(error)) from error
    raise error
