"""Server-rendered initial documents for public browse/entity routes."""

from __future__ import annotations

from dataclasses import replace

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.database.connection import get_database_session
from backend.services.discovery_html_service import render_discovery_shell
from backend.services.discovery_page_service import DiscoveryPage, DiscoveryPageService
from backend.services.spa_shell_service import load_index_html

router = APIRouter()

RESERVED_TOP_LEVEL_PREFIXES = frozenset(
    {
        "api",
        "assets",
        "images",
        "thumbnails",
        "paper",
        "papers",
        "tasks",
        "task",
        "methods",
        "benchmark",
        "conferences",
        "organizations",
        "authors",
        "frameworks",
        "trends",
        "chat",
        "submit",
        "saved",
        "settings",
        "admin-dashboard",
        "cron-dashboard",
        "submissions",
        "ai-deadlines",
        "sitemaps",
        "health",
        "docs",
        "redoc",
        "openapi.json",
    }
)
KNOWN_CLIENT_TOP_LEVEL_PREFIXES = frozenset(
    {
        "papers",
        "tasks",
        "methods",
        "conferences",
        "organizations",
        "frameworks",
        "trends",
        "chat",
        "submit",
        "saved",
        "settings",
        "admin-dashboard",
        "cron-dashboard",
        "submissions",
        "ai-deadlines",
    }
)


def _not_found() -> HTMLResponse:
    return HTMLResponse(
        '<!doctype html><html lang="en"><head><meta name="robots" content="noindex">'
        "<title>Page not found | Papers with Code</title></head>"
        '<body><main><h1>Page not found</h1><p><a href="/">Browse research</a></p>'
        "</main></body></html>",
        status_code=404,
        headers={"Cache-Control": "no-store"},
    )


def _spa_document() -> HTMLResponse:
    shell = load_index_html()
    if shell is None:
        return HTMLResponse("Frontend bundle is not available.", status_code=500)
    headers = {"Cache-Control": "no-store"}
    if get_settings().environment.lower() == "staging":
        headers["X-Robots-Tag"] = "noindex, nofollow"
    return HTMLResponse(shell, headers=headers)


def _render(page: DiscoveryPage | None, request: Request) -> Response:
    if page is None:
        return _not_found()
    settings = get_settings()
    if settings.environment.lower() == "staging":
        page = replace(page, robots="noindex,nofollow")
    elif request.query_params:
        page = replace(page, robots="noindex,follow")
    shell = load_index_html()
    if shell is None:
        return HTMLResponse(
            "<!doctype html><title>Papers with Code</title>"
            "<p>Frontend bundle is not available.</p>",
            status_code=500,
            headers={"Cache-Control": "no-store"},
        )
    try:
        content = render_discovery_shell(shell, page)
    except ValueError:
        return HTMLResponse(
            "<!doctype html><title>Papers with Code</title>"
            "<p>Frontend bundle is not available.</p>",
            status_code=500,
            headers={"Cache-Control": "no-store"},
        )
    headers = {
        "Cache-Control": "public, max-age=300, stale-while-revalidate=3600",
        "Link": f'<{page.canonical_url}>; rel="canonical"',
    }
    if settings.environment.lower() == "staging":
        headers["X-Robots-Tag"] = "noindex, nofollow"
    return HTMLResponse(content, headers=headers)


@router.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
def homepage(request: Request, db: Session = Depends(get_database_session)) -> Response:
    return _render(DiscoveryPageService(db).homepage(), request)


@router.api_route("/tasks/{slug}", methods=["GET", "HEAD"], include_in_schema=False)
def task_page(
    slug: str, request: Request, db: Session = Depends(get_database_session)
) -> Response:
    return _render(DiscoveryPageService(db).task(slug), request)


@router.api_route("/task/{slug}", methods=["GET", "HEAD"], include_in_schema=False)
def legacy_task_page(slug: str) -> RedirectResponse:
    return RedirectResponse(f"/tasks/{slug}", status_code=301)


@router.api_route("/methods/{slug}", methods=["GET", "HEAD"], include_in_schema=False)
def method_page(
    slug: str, request: Request, db: Session = Depends(get_database_session)
) -> Response:
    return _render(DiscoveryPageService(db).method(slug), request)


@router.api_route("/benchmark/{slug}", methods=["GET", "HEAD"], include_in_schema=False)
def benchmark_page(
    slug: str, request: Request, db: Session = Depends(get_database_session)
) -> Response:
    return _render(
        DiscoveryPageService(db).benchmark(slug, request.query_params.get("task")),
        request,
    )


@router.api_route(
    "/conferences/{slug}", methods=["GET", "HEAD"], include_in_schema=False
)
def conference_page(
    slug: str, request: Request, db: Session = Depends(get_database_session)
) -> Response:
    return _render(DiscoveryPageService(db).conference(slug), request)


@router.api_route(
    "/conferences/{slug}/{task_slug}", methods=["GET", "HEAD"], include_in_schema=False
)
def conference_task_page(
    slug: str,
    task_slug: str,
    request: Request,
    db: Session = Depends(get_database_session),
) -> Response:
    return _render(DiscoveryPageService(db).conference_task(slug, task_slug), request)


@router.api_route(
    "/authors/{author_id}", methods=["GET", "HEAD"], include_in_schema=False
)
def author_page(
    author_id: int, request: Request, db: Session = Depends(get_database_session)
) -> Response:
    return _render(DiscoveryPageService(db).author(author_id), request)


@router.api_route(
    "/organizations/{slug}", methods=["GET", "HEAD"], include_in_schema=False
)
def organization_alias(slug: str) -> RedirectResponse:
    return RedirectResponse(f"/{slug}", status_code=301)


@router.api_route(
    "/organizations/{slug}/{task_slug}",
    methods=["GET", "HEAD"],
    include_in_schema=False,
)
def organization_task_alias(slug: str, task_slug: str) -> RedirectResponse:
    return RedirectResponse(f"/{slug}/{task_slug}", status_code=301)


@router.api_route("/{slug}", methods=["GET", "HEAD"], include_in_schema=False)
def organization_page(
    slug: str, request: Request, db: Session = Depends(get_database_session)
) -> Response:
    if slug in RESERVED_TOP_LEVEL_PREFIXES or "." in slug:
        if slug in KNOWN_CLIENT_TOP_LEVEL_PREFIXES:
            return _spa_document()
        return _not_found()
    return _render(DiscoveryPageService(db).organization(slug), request)


@router.api_route(
    "/{slug}/{task_slug}", methods=["GET", "HEAD"], include_in_schema=False
)
def organization_task_page(
    slug: str,
    task_slug: str,
    request: Request,
    db: Session = Depends(get_database_session),
) -> Response:
    if slug in RESERVED_TOP_LEVEL_PREFIXES:
        if slug in KNOWN_CLIENT_TOP_LEVEL_PREFIXES:
            return _spa_document()
        return _not_found()
    return _render(DiscoveryPageService(db).organization_task(slug, task_slug), request)
