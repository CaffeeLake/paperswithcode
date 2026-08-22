"""HTTP translation contracts for catalog domain errors."""

import asyncio
import json

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from backend.routers.catalog_error_handlers import register_catalog_error_handlers
from backend.services.catalog_errors import (
    CatalogConflictError,
    CatalogNotFoundError,
    CatalogPersistenceError,
    CatalogValidationError,
)
from backend.utils.exceptions import DatabaseError, PaperNotFoundError


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (CatalogNotFoundError("Paper with ID 1 not found"), 404),
        (CatalogConflictError("A paper with this ID already exists"), 409),
        (CatalogValidationError("arxiv_id is required"), 400),
        (CatalogPersistenceError("Failed to save paper"), 500),
    ],
)
def test_catalog_domain_errors_have_stable_http_translation(error, status_code):
    app = FastAPI()
    register_catalog_error_handlers(app)

    @app.get("/catalog-error")
    def catalog_error():
        raise error

    with TestClient(app) as client:
        response = client.get("/catalog-error")

    assert response.status_code == status_code
    assert response.json() == {"detail": str(error)}


def test_legacy_catalog_errors_remain_compatible_with_new_error_categories():
    assert isinstance(PaperNotFoundError("missing"), CatalogNotFoundError)
    assert isinstance(DatabaseError("unavailable"), CatalogPersistenceError)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            PaperNotFoundError("Paper with ID 1 not found"),
            (404, {"error": "Paper not found", "detail": "Paper with ID 1 not found"}),
        ),
        (
            DatabaseError("Failed to save paper"),
            (500, {"error": "Database error", "detail": "Failed to save paper"}),
        ),
    ],
)
def test_unmigrated_catalog_errors_keep_their_legacy_response_contract(error, expected):
    from backend.main import create_app

    app = create_app()
    request = Request({"type": "http", "method": "GET", "path": "/"})
    response = asyncio.run(app.exception_handlers[type(error)](request, error))

    assert (response.status_code, json.loads(response.body)) == expected
