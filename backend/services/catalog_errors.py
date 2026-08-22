"""Typed domain failures shared by catalog services.

These errors deliberately carry only the public detail string.  HTTP adapters
translate that detail centrally, keeping catalog services independent of
FastAPI while preserving the API's established error payload shape.
"""


class CatalogError(Exception):
    """Base class for failures from catalog domain operations."""


class CatalogNotFoundError(CatalogError):
    """Raised when a catalog entity cannot be found."""


class CatalogConflictError(CatalogError, ValueError):
    """Raised when a catalog operation conflicts with current state."""


class CatalogValidationError(CatalogError, ValueError):
    """Raised when catalog operation input is invalid."""


class CatalogPersistenceError(CatalogError):
    """Raised when catalog persistence cannot complete."""
