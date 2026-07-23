"""
Server-side rendered paper-page HTML with per-paper social meta tags.

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
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Path as FastApiPath, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from backend.database.connection import get_database_session
from backend.config import get_settings
from backend.services.default_og_image import get_default_og_image_bytes
from backend.services.paper_service import PaperService
from backend.services.social_meta_service import (
    build_paper_meta,
    build_request_origin,
    inject_paper_meta,
)
from backend.utils.exceptions import DatabaseError, PaperNotFoundError
from backend.utils.urls import get_paper_route_identifier

logger = logging.getLogger(__name__)


router = APIRouter()


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_RELEASE_INDEX_PATH = (
    _PROJECT_ROOT.parent / "pwc-releases" / "current" / "frontend-dist" / "index.html"
)
_DIST_INDEX_PATH = _PROJECT_ROOT / "frontend" / "dist" / "index.html"
_SRC_INDEX_PATH = _PROJECT_ROOT / "frontend" / "index.html"

_cached_index_html: Optional[str] = None
_cached_index_mtime: Optional[float] = None
_cached_index_path: Optional[Path] = None


def _load_index_html() -> Optional[str]:
    """
    Load the SPA shell HTML, preferring the active production release.

    Production nginx serves an immutable snapshot through the sibling
    ``pwc-releases/current`` symlink. Paper routes must use that same shell;
    the checkout's ``frontend/dist`` can contain an unrelated development
    build whose hashed chunks are not publicly available. In dev and tests,
    where the release link is absent, fall back to the checkout build and
    then the Vite source shell.
    """
    global _cached_index_html, _cached_index_mtime, _cached_index_path

    settings = get_settings()
    if settings.is_deployed:
        paths = (settings.frontend_dist_path / "index.html",)
    else:
        paths = (_RELEASE_INDEX_PATH, _DIST_INDEX_PATH, _SRC_INDEX_PATH)

    for path in paths:
        if not path.exists():
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if (
            _cached_index_html is not None
            and _cached_index_mtime == mtime
            and _cached_index_path == path
        ):
            return _cached_index_html
        try:
            _cached_index_html = path.read_text(encoding="utf-8")
            _cached_index_mtime = mtime
            _cached_index_path = path
            return _cached_index_html
        except OSError as exc:
            logger.warning("Failed to read SPA index from %s: %s", path, exc)
            continue

    return None


def _origin_from_request(request: Request) -> str:
    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host") or request.headers.get(
        "host"
    )
    return build_request_origin(forwarded_proto or request.url.scheme, forwarded_host)


def _render_paper_html(
    paper_id: str,
    request: Request,
    db: Session,
    is_legacy_path: bool,
) -> Response:
    index_html = _load_index_html()
    if index_html is None:
        return HTMLResponse(
            "<!doctype html><title>Papers with Code</title>"
            "<p>Frontend bundle is not available.</p>",
            status_code=500,
        )

    try:
        paper = PaperService(db).get_paper_by_id_or_arxiv(paper_id)
    except PaperNotFoundError:
        return HTMLResponse(
            content=index_html,
            status_code=404,
            headers={"Cache-Control": "no-store"},
        )
    except DatabaseError as exc:
        logger.warning("Database error rendering /paper/%s: %s", paper_id, exc)
        return HTMLResponse(
            content=index_html,
            status_code=200,
            headers={"Cache-Control": "no-store"},
        )

    origin = _origin_from_request(request)
    route_identifier = get_paper_route_identifier(
        paper.source, paper.arxiv_id, int(paper.id)
    )
    meta = build_paper_meta(paper, route_identifier=route_identifier, origin=origin)
    rendered = inject_paper_meta(index_html, meta)

    headers = {
        "Cache-Control": "public, max-age=300, stale-while-revalidate=3600",
    }
    if is_legacy_path:
        headers["Link"] = f'<{meta.canonical_url}>; rel="canonical"'

    return HTMLResponse(content=rendered, status_code=200, headers=headers)


@router.get("/paper/{paper_id}", response_class=HTMLResponse, include_in_schema=False)
def get_paper_page(
    request: Request,
    paper_id: str = FastApiPath(..., description="ArXiv ID or internal paper ID"),
    db: Session = Depends(get_database_session),
) -> Response:
    """Serve the SPA shell with paper-specific social meta tags."""
    return _render_paper_html(paper_id, request, db, is_legacy_path=False)


@router.get("/papers/{paper_id}", response_class=HTMLResponse, include_in_schema=False)
def get_paper_page_legacy(
    request: Request,
    paper_id: str = FastApiPath(..., description="ArXiv ID or internal paper ID"),
    db: Session = Depends(get_database_session),
) -> Response:
    """
    Legacy alias for ``/paper/{id}`` (singular is canonical).

    The React app already redirects ``/papers/:id`` to ``/paper/:id``
    client-side. Mirroring that here means crawlers and direct shares
    of the legacy URL still get a fully populated social card.
    """
    return _render_paper_html(paper_id, request, db, is_legacy_path=True)


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
