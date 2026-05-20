"""
Tests for the per-paper social meta-tag injection used by `/paper/{id}` and
the legacy `/papers/{id}` route.

These tests focus on:
  - Resolving the social image URL from an existing paper thumbnail.
  - Falling back to the static default image when no thumbnail is on disk.
  - Injecting properly escaped meta tags into the SPA shell HTML.
  - The end-to-end response surface of the FastAPI routes, including a
    smoke check that the default OG image endpoint returns a PNG payload.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pytest
from fastapi.testclient import TestClient

from backend.database.connection import get_database_session
from backend.main import create_app
from backend.models.api import Paper
from backend.routers import paper_pages as paper_pages_module
from backend.services import default_og_image, social_meta_service
from backend.services.paper_service import PaperService
from backend.services.social_meta_service import (
    PRODUCTION_ORIGIN,
    build_paper_meta,
    build_request_origin,
    inject_paper_meta,
    resolve_social_image_url,
)
from backend.utils.exceptions import PaperNotFoundError


class _FakeThumbnailService:
    """In-memory ThumbnailService stand-in for resolve_social_image_url tests."""

    def __init__(
        self, present: Optional[set[str]] = None, custom: Optional[set[str]] = None
    ):
        self._present = present or set()
        self._custom = custom or set()

    def get_local_thumbnail_path(self, filename: str) -> Optional[Path]:
        if filename in self._present:
            return Path("/tmp") / filename
        return None

    def get_existing_custom_thumbnail_path(self, filename: str) -> Optional[Path]:
        if filename in self._custom:
            return Path("/tmp") / filename
        return None

    def get_local_custom_thumbnail_path(self, filename: str) -> Optional[Path]:
        return self.get_existing_custom_thumbnail_path(filename)


def _make_paper(**overrides) -> Paper:
    base = dict(
        id="1234",
        arxiv_id="2504.12516",
        source="arxiv",
        url_abs="https://arxiv.org/abs/2504.12516",
        url_pdf="https://arxiv.org/pdf/2504.12516.pdf",
        thumbnail_url="/api/thumbnails/2504_12516_v1.jpg?fit=fit2",
        title="A <Great> Paper & Friends",
        abstract="We propose a clever method.  " * 10,
        authors=["Alice Author", "Bob Builder", "Carla Coder"],
        version="v1",
        is_latest_version=True,
        citation_count=42,
    )
    base.update(overrides)
    return Paper(**base)


@pytest.fixture(autouse=True)
def _reset_default_og_cache():
    default_og_image._cached_png = None
    yield
    default_og_image._cached_png = None


@pytest.fixture(autouse=True)
def _reset_index_cache():
    paper_pages_module._cached_index_html = None
    paper_pages_module._cached_index_mtime = None
    yield
    paper_pages_module._cached_index_html = None
    paper_pages_module._cached_index_mtime = None


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


def test_build_request_origin_uses_forwarded_headers():
    assert (
        build_request_origin("https", "paperswithcode.co")
        == "https://paperswithcode.co"
    )


def test_build_request_origin_falls_back_to_production_when_host_missing():
    assert build_request_origin(None, None) == PRODUCTION_ORIGIN


def test_build_request_origin_normalises_scheme():
    assert build_request_origin("javascript", "example.test") == "https://example.test"


def test_resolve_social_image_uses_existing_arxiv_thumbnail():
    paper = _make_paper()
    fake = _FakeThumbnailService(present={"2504_12516_v1.jpg"})

    result = resolve_social_image_url(
        paper, "https://paperswithcode.co", thumbnail_service=fake
    )

    assert result.is_fallback is False
    assert result.absolute_url == (
        "https://paperswithcode.co/api/thumbnails/2504_12516_v1.jpg?fit=fit2"
    )


def test_resolve_social_image_falls_back_when_thumbnail_missing():
    paper = _make_paper()
    fake = _FakeThumbnailService(present=set())

    result = resolve_social_image_url(
        paper, "https://paperswithcode.co", thumbnail_service=fake
    )

    assert result.is_fallback is True
    assert result.absolute_url == ("https://paperswithcode.co/api/og/default.png")


def test_resolve_social_image_uses_existing_custom_thumbnail():
    paper = _make_paper(
        source="external",
        arxiv_id=None,
        thumbnail_url="/api/thumbnails/custom/external_1234.jpg?fit=fit2",
    )
    fake = _FakeThumbnailService(custom={"external_1234.jpg"})

    result = resolve_social_image_url(
        paper, "https://paperswithcode.co", thumbnail_service=fake
    )

    assert result.is_fallback is False
    assert result.absolute_url.endswith(
        "/api/thumbnails/custom/external_1234.jpg?fit=fit2"
    )


def test_resolve_social_image_accepts_absolute_url_without_disk_check():
    paper = _make_paper(thumbnail_url="https://example.com/preview.jpg")
    fake = _FakeThumbnailService(present=set())

    result = resolve_social_image_url(
        paper, "https://paperswithcode.co", thumbnail_service=fake
    )

    assert result.is_fallback is False
    assert result.absolute_url == "https://example.com/preview.jpg"


def test_inject_paper_meta_escapes_user_supplied_strings():
    paper = _make_paper()
    fake = _FakeThumbnailService(present={"2504_12516_v1.jpg"})

    meta = build_paper_meta(
        paper,
        route_identifier=paper.arxiv_id or paper.id,
        origin="https://paperswithcode.co",
        thumbnail_service=fake,
    )
    html = inject_paper_meta(
        "<!doctype html><html><head><title>Papers with Code</title>"
        '<meta name="description" content="default" />'
        '<meta property="og:title" content="default" />'
        '<meta property="og:description" content="default" />'
        '<meta property="og:type" content="website" />'
        '<meta name="twitter:card" content="summary" />'
        "</head><body></body></html>",
        meta,
    )

    # The user-supplied title was `A <Great> Paper & Friends` and must be
    # HTML-escaped in every place we render it.
    assert "A &lt;Great&gt; Paper &amp; Friends | Papers with Code" in html
    # Old, generic tags must be replaced (no duplicate `Papers with Code`
    # title or generic `og:type=website`).
    assert html.count("<title>") == 1
    assert 'og:type" content="website"' not in html
    assert 'og:type" content="article"' in html
    assert 'twitter:card" content="summary"' not in html
    assert 'twitter:card" content="summary_large_image"' in html
    # Canonical URL points at the singular `/paper/{id}` shape.
    assert (
        '<link rel="canonical" href="https://paperswithcode.co/paper/2504.12516" />'
        in html
    )
    # Real thumbnail URL is absolute.
    assert (
        'og:image" content="https://paperswithcode.co/api/thumbnails/'
        '2504_12516_v1.jpg?fit=fit2"'
    ) in html
    assert (
        'twitter:image" content="https://paperswithcode.co/api/thumbnails/'
        '2504_12516_v1.jpg?fit=fit2"'
    ) in html


def test_inject_paper_meta_uses_fallback_image_when_disk_misses():
    paper = _make_paper()
    fake = _FakeThumbnailService(present=set())

    meta = build_paper_meta(
        paper,
        route_identifier=paper.arxiv_id or paper.id,
        origin="https://paperswithcode.co",
        thumbnail_service=fake,
    )
    html = inject_paper_meta("<html><head></head><body></body></html>", meta)

    assert 'og:image" content="https://paperswithcode.co/api/og/default.png"' in html
    # Fallback image carries explicit dimensions so summary_large_image
    # cards render cleanly even before the platform has scraped the asset.
    assert 'og:image:width" content="1200"' in html
    assert 'og:image:height" content="630"' in html


def test_inject_paper_meta_uses_authors_when_abstract_empty():
    paper = _make_paper(abstract="")
    fake = _FakeThumbnailService(present={"2504_12516_v1.jpg"})

    meta = build_paper_meta(
        paper,
        route_identifier=paper.arxiv_id or paper.id,
        origin="https://paperswithcode.co",
        thumbnail_service=fake,
    )

    assert meta.description.startswith("By Alice Author")


# ---------------------------------------------------------------------------
# Default OG image endpoint
# ---------------------------------------------------------------------------


def test_default_og_image_is_a_png():
    payload = default_og_image.get_default_og_image_bytes()
    # PNG magic header.
    assert payload[:8] == b"\x89PNG\r\n\x1a\n"
    # Cached on second call.
    assert default_og_image.get_default_og_image_bytes() is payload


# ---------------------------------------------------------------------------
# Route integration tests
# ---------------------------------------------------------------------------


@pytest.fixture
def client(monkeypatch):
    app = create_app()

    def override_get_database_session():
        yield object()

    app.dependency_overrides[get_database_session] = override_get_database_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _stub_paper_lookup(monkeypatch, paper: Paper):
    def fake(self, identifier, include_resources=False):
        return paper

    monkeypatch.setattr(PaperService, "get_paper_by_id_or_arxiv", fake)


def _stub_paper_lookup_missing(monkeypatch):
    def fake(self, identifier, include_resources=False):
        raise PaperNotFoundError(identifier)

    monkeypatch.setattr(PaperService, "get_paper_by_id_or_arxiv", fake)


def _stub_thumbnail_present(monkeypatch, filenames: set[str]):
    fake = _FakeThumbnailService(present=filenames)
    monkeypatch.setattr(
        social_meta_service,
        "ThumbnailService",
        lambda: fake,
    )


def test_paper_route_returns_html_with_paper_specific_meta(client, monkeypatch):
    paper = _make_paper()
    _stub_paper_lookup(monkeypatch, paper)
    _stub_thumbnail_present(monkeypatch, {"2504_12516_v1.jpg"})

    response = client.get(
        "/paper/2504.12516",
        headers={"X-Forwarded-Proto": "https", "Host": "paperswithcode.co"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    body = response.text
    assert "A &lt;Great&gt; Paper &amp; Friends | Papers with Code" in body
    assert 'og:url" content="https://paperswithcode.co/paper/2504.12516"' in body
    assert (
        'twitter:image" content="https://paperswithcode.co/api/thumbnails/'
        '2504_12516_v1.jpg?fit=fit2"'
    ) in body


def test_paper_route_returns_404_when_paper_missing(client, monkeypatch):
    _stub_paper_lookup_missing(monkeypatch)

    response = client.get("/paper/9999.99999")

    assert response.status_code == 404
    # The shell HTML is still returned so the SPA can render its NotFound view
    # for normal browser visitors.
    assert '<div id="root">' in response.text


def test_legacy_papers_route_renders_canonical_link_header(client, monkeypatch):
    paper = _make_paper()
    _stub_paper_lookup(monkeypatch, paper)
    _stub_thumbnail_present(monkeypatch, set())  # force fallback image

    response = client.get(
        "/papers/2504.12516",
        headers={"X-Forwarded-Proto": "https", "Host": "paperswithcode.co"},
    )

    assert response.status_code == 200
    assert (
        response.headers.get("link")
        == '<https://paperswithcode.co/paper/2504.12516>; rel="canonical"'
    )
    body = response.text
    assert 'og:image" content="https://paperswithcode.co/api/og/default.png"' in body


def test_default_og_image_endpoint_returns_png(client):
    response = client.get("/api/og/default.png")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content[:8] == b"\x89PNG\r\n\x1a\n"
