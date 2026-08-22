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


def _catalog_client(monkeypatch):
    from backend.database.connection import get_database_session
    from backend.main import create_app

    app = create_app()
    app.dependency_overrides[get_database_session] = lambda: object()
    return TestClient(app)


def _evaluation_app(monkeypatch, service):
    from backend.database.connection import get_database_session
    from backend.routers import evaluations
    from backend.utils.auth import evaluation_mutation_context

    app = FastAPI()
    register_catalog_error_handlers(app)
    app.include_router(evaluations.router, prefix="/api/v1")
    app.dependency_overrides[get_database_session] = lambda: None
    app.dependency_overrides[evaluation_mutation_context] = lambda: {"actor": {}}
    monkeypatch.setattr(evaluations, "EvaluationCurationService", lambda _db: service)
    return app


@pytest.mark.parametrize(
    ("error", "status", "detail"),
    [
        (CatalogNotFoundError("Evaluation 1 not found"), 404, "Evaluation 1 not found"),
        (CatalogPersistenceError("database unavailable"), 500, "database unavailable"),
        (
            CatalogConflictError({"code": "stale_catalog_version"}),
            409,
            {"code": "stale_catalog_version"},
        ),
    ],
)
def test_evaluation_delete_route_uses_catalog_error_contract(
    monkeypatch, error, status, detail
):
    class Service:
        def delete(self, **_kwargs):
            raise error

    with TestClient(_evaluation_app(monkeypatch, Service())) as client:
        response = client.delete("/api/v1/evaluations/1")

    assert response.status_code == status
    assert response.json() == {"detail": detail}


def test_evaluation_delete_route_success(monkeypatch):
    class Service:
        def delete(self, **_kwargs):
            return None

    with TestClient(_evaluation_app(monkeypatch, Service())) as client:
        response = client.delete("/api/v1/evaluations/1")

    assert response.status_code == 204


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
    assert response.json() == {"detail": error.detail}


def test_catalog_conflict_preserves_structured_detail():
    error = CatalogConflictError(
        {"code": "stale_catalog_version", "current_version": "current"}
    )
    app = FastAPI()
    register_catalog_error_handlers(app)

    @app.get("/catalog-conflict")
    def catalog_conflict():
        raise error

    with TestClient(app) as client:
        response = client.get("/catalog-conflict")

    assert response.status_code == 409
    assert response.json() == {"detail": error.detail}


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


@pytest.mark.parametrize(
    ("path", "service", "method", "error", "status"),
    [
        (
            "/api/v1/areas/invalid",
            "backend.services.area_service.AreaService",
            "get_area_by_id",
            CatalogValidationError("Invalid area ID format"),
            400,
        ),
        (
            "/api/v1/areas/404",
            "backend.services.area_service.AreaService",
            "get_area_by_id",
            PaperNotFoundError("Area with ID 404 not found"),
            404,
        ),
        (
            "/api/v1/areas/",
            "backend.services.area_service.AreaService",
            "get_areas",
            CatalogPersistenceError("Failed to retrieve areas"),
            500,
        ),
    ],
)
def test_taxonomy_endpoint_errors_keep_detail_only_envelopes(
    monkeypatch, path, service, method, error, status
):
    module_name, class_name = service.rsplit(".", 1)
    module = __import__(module_name, fromlist=[class_name])
    monkeypatch.setattr(
        getattr(module, class_name),
        method,
        lambda *_args, **_kwargs: (_ for _ in ()).throw(error),
    )

    with _catalog_client(monkeypatch) as client:
        response = client.get(path)

    assert response.status_code == status
    assert response.json() == {"detail": str(error)}


@pytest.mark.parametrize(
    ("path", "service", "method"),
    [
        (
            "/api/v1/tasks/404",
            "backend.services.task_service.TaskService",
            "get_task_by_id",
        ),
        (
            "/api/v1/methods/404",
            "backend.services.method_service.MethodService",
            "get_method_by_id",
        ),
        (
            "/api/v1/organizations/missing",
            "backend.services.organization_service.OrganizationService",
            "get_organization",
        ),
        (
            "/api/v1/repositories/404",
            "backend.services.repository_service.RepositoryService",
            "get_repository_by_id",
        ),
        (
            "/api/v1/project-pages/404",
            "backend.services.project_page_service.ProjectPageService",
            "get_project_page_by_id",
        ),
    ],
)
def test_migrated_taxonomy_lookups_translate_legacy_service_failures(
    monkeypatch, path, service, method
):
    module_name, class_name = service.rsplit(".", 1)
    module = __import__(module_name, fromlist=[class_name])
    monkeypatch.setattr(
        getattr(module, class_name),
        method,
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            PaperNotFoundError("entity not found")
        ),
    )

    with _catalog_client(monkeypatch) as client:
        response = client.get(path)

    assert response.status_code == 404
    assert response.json() == {"detail": "entity not found"}


def test_create_task_requires_catalog_mutator_before_service_is_called(monkeypatch):
    from backend.services.task_service import TaskService

    monkeypatch.setattr(
        TaskService,
        "create_task",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("called")),
    )
    with _catalog_client(monkeypatch) as client:
        response = client.post("/api/v1/tasks/", json={"name": "Protected task"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}
