"""Shared typed-failure boundary for taxonomy domain services."""

from __future__ import annotations

from functools import wraps
from typing import Callable, TypeVar

from backend.services.catalog_errors import (
    CatalogConflictError,
    CatalogNotFoundError,
    CatalogPersistenceError,
    CatalogValidationError,
)
from backend.utils.exceptions import DatabaseError, PaperNotFoundError


F = TypeVar("F", bound=Callable)


def taxonomy_operation(operation: F) -> F:
    """Translate legacy storage errors at a taxonomy service boundary.

    The legacy exceptions retain their existing uses outside this boundary,
    while taxonomy routes receive only the explicit catalog vocabulary.
    """

    @wraps(operation)
    def typed_operation(*args, **kwargs):
        try:
            return operation(*args, **kwargs)
        except PaperNotFoundError as error:
            raise CatalogNotFoundError(str(error)) from error
        except DatabaseError as error:
            raise CatalogPersistenceError(str(error)) from error
        except ValueError as error:
            if "already exists" in str(error):
                raise CatalogConflictError(str(error)) from error
            raise CatalogValidationError(str(error)) from error

    return typed_operation  # type: ignore[return-value]


def taxonomy_service(cls):
    """Make every public operation on a taxonomy service typed."""
    for name, value in vars(cls).items():
        if (
            not name.startswith("_")
            and not isinstance(value, (staticmethod, classmethod))
            and callable(value)
        ):
            setattr(cls, name, taxonomy_operation(value))
    return cls
