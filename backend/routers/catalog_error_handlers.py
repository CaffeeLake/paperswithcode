"""Central HTTP translation for typed catalog domain failures."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.types import ExceptionHandler

from backend.services.catalog_errors import (
    CatalogConflictError,
    CatalogNotFoundError,
    CatalogPersistenceError,
    CatalogValidationError,
)


def _catalog_error_response(status_code: int) -> ExceptionHandler:
    async def handler(_request: Request, error: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=status_code,
            content={"detail": getattr(error, "detail", str(error))},
        )

    return handler


def register_catalog_error_handlers(app: FastAPI) -> None:
    """Register the public HTTP contracts for catalog domain errors."""
    app.add_exception_handler(
        CatalogNotFoundError, _catalog_error_response(status_code=404)
    )
    app.add_exception_handler(
        CatalogConflictError, _catalog_error_response(status_code=409)
    )
    app.add_exception_handler(
        CatalogValidationError, _catalog_error_response(status_code=400)
    )
    app.add_exception_handler(
        CatalogPersistenceError, _catalog_error_response(status_code=500)
    )
