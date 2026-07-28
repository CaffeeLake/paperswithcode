"""
Server-rendered paper-page HTML with crawlable content and scholarly metadata.

Paper detail pages are otherwise a pure React SPA, which means crawlers
that don't execute JavaScript (Twitterbot, Slackbot, Discord, etc.) see
the same generic Open Graph card on every URL. The routes in this module
sit in front of the SPA: they return the same Vite-built ``index.html``
but with paper-specific ``<title>``, ``description``, ``og:*`` and
``twitter:*`` tags injected, including an absolute image URL that points
at the paper's existing thumbnail when it is already on disk.

Nginx is responsible for forwarding ``/paper/{id}`` and the legacy
``/papers/{id}`` shape to the backend; all other static fall-through is
unchanged.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Path as FastApiPath
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from backend.database.connection import get_database_session
from backend.services.default_og_image import get_default_og_image_bytes
from backend.services.paper_service import PaperService
from backend.services.paper_seo_service import (
    PRODUCTION_ORIGIN,
    build_paper_seo_document,
    inject_initial_document,
    render_initial_paper_document,
)
from backend.services.social_meta_service import (
    build_paper_meta,
    inject_paper_meta,
)
from backend.services.spa_shell_service import load_index_html
from backend.utils.exceptions import DatabaseError, PaperNotFoundError
from backend.utils.urls import get_paper_route_identifier

logger = logging.getLogger(__name__)


router = APIRouter()


def _render_paper_html(
    paper_id: str,
    db: Session,
    is_legacy_path: bool,
) -> Response:
    try:
        paper = PaperService(db).get_paper_by_id_or_arxiv(
            paper_id, include_resources=True
        )
    except PaperNotFoundError:
        return HTMLResponse(
            content=(
                '<!doctype html><html lang="en"><head>'
                '<meta charset="utf-8"><meta name="robots" content="noindex">'
                "<title>Paper not found | Papers with Code</title></head>"
                "<body><main><h1>Paper not found</h1>"
                "<p>The requested paper is not available.</p>"
                '<p><a href="/papers/recent">Browse recent papers</a></p>'
                "</main></body></html>"
            ),
            status_code=404,
            headers={"Cache-Control": "no-store"},
        )
    except DatabaseError as exc:
        logger.warning("Database error rendering /paper/%s: %s", paper_id, exc)
        return HTMLResponse(
            content=(
                '<!doctype html><html lang="en"><head>'
                '<meta charset="utf-8"><meta name="robots" content="noindex">'
                "<title>Paper temporarily unavailable | Papers with Code</title>"
                "</head><body><main><h1>Paper temporarily unavailable</h1>"
                "<p>Please try again shortly.</p></main></body></html>"
            ),
            status_code=503,
            headers={"Cache-Control": "no-store", "Retry-After": "60"},
        )

    route_identifier = get_paper_route_identifier(
        paper.source, paper.arxiv_id, int(paper.id)
    )
    canonical_path = f"/paper/{route_identifier}"
    if is_legacy_path or paper_id != route_identifier:
        return RedirectResponse(
            url=canonical_path,
            status_code=301,
            headers={"Cache-Control": "public, max-age=3600"},
        )

    index_html = load_index_html()
    if index_html is None:
        return HTMLResponse(
            "<!doctype html><title>Papers with Code</title>"
            "<p>Frontend bundle is not available.</p>",
            status_code=500,
            headers={"Cache-Control": "no-store"},
        )

    document = build_paper_seo_document(paper, route_identifier)
    meta = build_paper_meta(
        paper, route_identifier=route_identifier, origin=PRODUCTION_ORIGIN
    )
    try:
        rendered = inject_paper_meta(index_html, meta, document)
        rendered = inject_initial_document(
            rendered, render_initial_paper_document(document)
        )
    except ValueError as exc:
        logger.error("Paper shell contract failed: %s", exc)
        return HTMLResponse(
            "<!doctype html><title>Papers with Code</title>"
            "<p>Frontend bundle is not available.</p>",
            status_code=500,
            headers={"Cache-Control": "no-store"},
        )

    headers = {
        "Cache-Control": "public, max-age=300, stale-while-revalidate=3600",
        "Link": f'<{document.canonical_url}>; rel="canonical"',
    }

    return HTMLResponse(content=rendered, status_code=200, headers=headers)


@router.api_route(
    "/paper/{paper_id}",
    methods=["GET", "HEAD"],
    response_class=HTMLResponse,
    include_in_schema=False,
)
def get_paper_page(
    paper_id: str = FastApiPath(..., description="ArXiv ID or internal paper ID"),
    db: Session = Depends(get_database_session),
) -> Response:
    """Serve the SPA shell with paper-specific social meta tags."""
    return _render_paper_html(paper_id, db, is_legacy_path=False)


@router.api_route(
    "/papers/{paper_id}",
    methods=["GET", "HEAD"],
    response_class=HTMLResponse,
    include_in_schema=False,
)
def get_paper_page_legacy(
    paper_id: str = FastApiPath(..., description="ArXiv ID or internal paper ID"),
    db: Session = Depends(get_database_session),
) -> Response:
    """
    Redirect the legacy plural shape directly to the resolved canonical route.
    """
    return _render_paper_html(paper_id, db, is_legacy_path=True)


@router.get(
    "/api/og/default.png",
    include_in_schema=False,
)
def get_default_og_image() -> Response:
    """
    Serve the static fallback Open Graph image used when a paper has no
    thumbnail on disk yet.

    The bytes are generated once at first request and cached in process
    memory, so crawler fetches stay cheap.
    """
    return Response(
        content=get_default_og_image_bytes(),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )
