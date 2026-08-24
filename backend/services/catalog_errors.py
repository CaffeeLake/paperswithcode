"""Typed domain failures shared by catalog services.

These errors deliberately carry only a JSON-compatible public detail. HTTP adapters
translate that detail centrally, keeping catalog services independent of
FastAPI while preserving the API's established error payload shape.
"""

from functools import wraps


JSONDetail = (
    str | int | float | bool | None | list["JSONDetail"] | dict[str, "JSONDetail"]
)


class CatalogError(Exception):
    """Base class for failures from catalog domain operations."""

    def __init__(self, detail: JSONDetail):
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


def catalog_operation(operation):
    """Expose a domain operation with typed catalog failures.

    Modern ``CatalogError`` subclasses pass through unchanged. Legacy
    ``PaperNotFoundError`` and ``DatabaseError`` are compatibility subclasses
    that are normalized to the base not-found and persistence categories.
    """

    @wraps(operation)
    def wrapped(*args, **kwargs):
        from backend.utils.exceptions import DatabaseError, PaperNotFoundError

        try:
            return operation(*args, **kwargs)
        except PaperNotFoundError as error:
            raise CatalogNotFoundError(str(error)) from error
        except DatabaseError as error:
            raise CatalogPersistenceError(str(error)) from error

    return wrapped
