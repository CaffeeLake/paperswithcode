"""XML sitemap and crawlable, user-facing paper archive routes."""

from __future__ import annotations

import html
import re
from datetime import date
from typing import Iterator, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from sqlalchemy.orm import Session

from backend.database.connection import get_database_session
from backend.services.sitemap_service import (
    PRODUCTION_ORIGIN,
    SitemapService,
    SitemapShard,
)


router = APIRouter()
SITEMAP_HEADERS = {
    "Cache-Control": "public, max-age=3600, stale-while-revalidate=86400"
}
ARCHIVE_HEADERS = {"Cache-Control": "public, max-age=300, stale-while-revalidate=3600"}
_SHARD_RE = re.compile(r"^(?P<year>\d{4})-(?P<bucket>\d+)$")


def _xml_response(content: Iterator[str] | str) -> Response:
    if isinstance(content, str):
        return Response(
            content=content,
            media_type="application/xml",
            headers=SITEMAP_HEADERS,
        )
    return StreamingResponse(
        content,
        media_type="application/xml",
        headers=SITEMAP_HEADERS,
    )


@router.api_route("/sitemap.xml", methods=["GET", "HEAD"], include_in_schema=False)
def sitemap_index(db: Session = Depends(get_database_session)) -> Response:
    service = SitemapService(db)
    entries = [f"<sitemap><loc>{PRODUCTION_ORIGIN}/sitemaps/static.xml</loc></sitemap>"]
    entries.extend(
        f"<sitemap><loc>{PRODUCTION_ORIGIN}/sitemaps/{kind}.xml</loc></sitemap>"
        for kind in (
            "tasks",
            "methods",
            "benchmarks",
            "conferences",
            "organizations",
        )
    )
    entries.extend(
        f"<sitemap><loc>{PRODUCTION_ORIGIN}/sitemaps/authors-{bucket}.xml</loc></sitemap>"
        for bucket in service.list_author_shards()
    )
    entries.extend(
        "<sitemap><loc>"
        f"{PRODUCTION_ORIGIN}/sitemaps/papers-{shard.name}.xml"
        "</loc></sitemap>"
        for shard in service.list_shards()
    )
    return _xml_response(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(entries)
        + "</sitemapindex>"
    )


@router.api_route(
    "/sitemaps/static.xml", methods=["GET", "HEAD"], include_in_schema=False
)
def static_sitemap() -> Response:
    paths = ("/", "/papers/recent", "/papers/archive")
    urls = "".join(f"<url><loc>{PRODUCTION_ORIGIN}{path}</loc></url>" for path in paths)
    return _xml_response(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{urls}</urlset>"
    )


def _paper_sitemap_xml(service: SitemapService, shard: SitemapShard) -> Iterator[str]:
    yield (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    )
    for paper in service.iter_shard(shard):
        location = html.escape(
            f"{PRODUCTION_ORIGIN}/paper/{paper.route_identifier}", quote=True
        )
        yield (
            f"<url><loc>{location}</loc>"
            f"<lastmod>{paper.lastmod.isoformat()}</lastmod></url>"
        )
    yield "</urlset>"


def _entity_sitemap_xml(entities) -> Iterator[str]:
    yield (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    )
    for entity in entities:
        location = html.escape(f"{PRODUCTION_ORIGIN}{entity.path}", quote=True)
        yield (
            f"<url><loc>{location}</loc>"
            f"<lastmod>{entity.lastmod.isoformat()}</lastmod></url>"
        )
    yield "</urlset>"


@router.api_route(
    "/sitemaps/papers-{shard_name}.xml",
    methods=["GET", "HEAD"],
    include_in_schema=False,
)
def paper_sitemap(
    shard_name: str,
    db: Session = Depends(get_database_session),
) -> Response:
    match = _SHARD_RE.fullmatch(shard_name)
    if not match:
        return Response(status_code=404)
    shard = SitemapShard(
        year=int(match.group("year")), bucket=int(match.group("bucket"))
    )
    return _xml_response(_paper_sitemap_xml(SitemapService(db), shard))


@router.api_route(
    "/sitemaps/{kind}.xml", methods=["GET", "HEAD"], include_in_schema=False
)
def entity_sitemap(kind: str, db: Session = Depends(get_database_session)) -> Response:
    author_match = re.fullmatch(r"authors-(\d+)", kind)
    if author_match:
        return _xml_response(
            _entity_sitemap_xml(
                SitemapService(db).iter_author_shard(int(author_match.group(1)))
            )
        )
    if kind not in {"tasks", "methods", "benchmarks", "conferences", "organizations"}:
        return Response(status_code=404)
    return _xml_response(_entity_sitemap_xml(SitemapService(db).iter_entities(kind)))


def _archive_html(
    *,
    title: str,
    description: str,
    canonical_path: str,
    papers,
    page: int,
    has_next: bool,
    navigation: str = "",
) -> str:
    canonical = PRODUCTION_ORIGIN + canonical_path
    page_suffix = f"?page={page}" if page > 1 else ""
    links = []
    if page > 1:
        previous = page - 1
        href = canonical_path + (f"?page={previous}" if previous > 1 else "")
        links.append(f'<a rel="prev" href="{href}">Newer papers</a>')
    if has_next:
        links.append(
            f'<a rel="next" href="{canonical_path}?page={page + 1}">Older papers</a>'
        )
    items = "".join(
        "<li>"
        f'<a href="/paper/{html.escape(paper.route_identifier, quote=True)}">'
        f"{html.escape(paper.title)}</a>"
        + (
            f' <time datetime="{paper.published.isoformat()}">'
            f"{paper.published.strftime('%-d %B %Y')}</time>"
            if paper.published
            else ""
        )
        + "</li>"
        for paper in papers
    )
    empty = (
        "<p>No eligible papers were published in this period.</p>" if not papers else ""
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(title)}</title>"
        f'<meta name="description" content="{html.escape(description, quote=True)}">'
        f'<link rel="canonical" href="{canonical}{page_suffix}">'
        "<style>body{max-width:920px;margin:auto;padding:24px;font:16px/1.55 system-ui,sans-serif}"
        "li{margin:.65rem 0}time{color:#666;font-size:.9rem}nav{display:flex;gap:1rem;flex-wrap:wrap}"
        '</style></head><body><header><a href="/">Papers with Code</a>'
        f"<h1>{html.escape(title.split(' | ')[0])}</h1><p>{html.escape(description)}</p>"
        f"</header>{navigation}<main><ol>{items}</ol>{empty}</main>"
        f'<nav aria-label="Pagination">{" ".join(links)}</nav>'
        '<footer><p><a href="/papers/recent">Recent papers</a> · '
        '<a href="/papers/archive">Paper archive</a></p></footer></body></html>'
    )


def _page_number(page: int) -> Optional[Response]:
    if page < 1 or page > 10_000:
        return HTMLResponse("Not found", status_code=404)
    return None


@router.api_route("/papers/recent", methods=["GET", "HEAD"], include_in_schema=False)
def recent_papers(
    page: int = Query(1),
    db: Session = Depends(get_database_session),
) -> Response:
    invalid = _page_number(page)
    if invalid:
        return invalid
    papers, has_next = SitemapService(db).archive_page(page=page, recent=True)
    return HTMLResponse(
        _archive_html(
            title="Recent AI research papers | Papers with Code",
            description="Canonical AI research papers added or published in the last fourteen days.",
            canonical_path="/papers/recent",
            papers=papers,
            page=page,
            has_next=has_next,
        ),
        headers=ARCHIVE_HEADERS,
    )


@router.api_route("/papers/archive", methods=["GET", "HEAD"], include_in_schema=False)
def paper_archive(db: Session = Depends(get_database_session)) -> Response:
    years = SitemapService(db).archive_years()
    navigation = (
        "<main><ul>"
        + "".join(
            f'<li><a href="/papers/archive/{year}">{year}</a> ({count:,} papers)</li>'
            for year, count in years
        )
        + "</ul></main>"
    )
    return HTMLResponse(
        _archive_html(
            title="AI research paper archive | Papers with Code",
            description="Browse canonical AI research papers by publication year.",
            canonical_path="/papers/archive",
            papers=[],
            page=1,
            has_next=False,
            navigation=navigation,
        ).replace("<p>No eligible papers were published in this period.</p>", ""),
        headers=ARCHIVE_HEADERS,
    )


def _valid_period(year: int, month: Optional[int] = None) -> bool:
    current_year = date.today().year
    return 1990 <= year <= current_year + 1 and (month is None or 1 <= month <= 12)


@router.api_route(
    "/papers/archive/{year}", methods=["GET", "HEAD"], include_in_schema=False
)
def paper_archive_year(
    year: int,
    page: int = Query(1),
    db: Session = Depends(get_database_session),
) -> Response:
    if not _valid_period(year):
        return HTMLResponse("Not found", status_code=404)
    invalid = _page_number(page)
    if invalid:
        return invalid
    service = SitemapService(db)
    papers, has_next = service.archive_page(page=page, year=year)
    months = " ".join(
        f'<a href="/papers/archive/{year}/{month:02d}">{date(year, month, 1).strftime("%B")}</a>'
        for month in range(1, 13)
    )
    return HTMLResponse(
        _archive_html(
            title=f"AI research papers published in {year} | Papers with Code",
            description=f"Browse canonical AI research papers published in {year}.",
            canonical_path=f"/papers/archive/{year}",
            papers=papers,
            page=page,
            has_next=has_next,
            navigation=f'<nav aria-label="Months">{months}</nav>',
        ),
        headers=ARCHIVE_HEADERS,
    )


@router.api_route(
    "/papers/archive/{year}/{month}",
    methods=["GET", "HEAD"],
    include_in_schema=False,
)
def paper_archive_month(
    year: int,
    month: str,
    page: int = Query(1),
    db: Session = Depends(get_database_session),
) -> Response:
    if not re.fullmatch(r"(0[1-9]|1[0-2])", month):
        return HTMLResponse("Not found", status_code=404)
    month_number = int(month)
    if not _valid_period(year, month_number):
        return HTMLResponse("Not found", status_code=404)
    invalid = _page_number(page)
    if invalid:
        return invalid
    papers, has_next = SitemapService(db).archive_page(
        page=page, year=year, month=month_number
    )
    month_name = date(year, month_number, 1).strftime("%B")
    return HTMLResponse(
        _archive_html(
            title=f"AI research papers published in {month_name} {year} | Papers with Code",
            description=f"Browse canonical AI research papers published in {month_name} {year}.",
            canonical_path=f"/papers/archive/{year}/{month}",
            papers=papers,
            page=page,
            has_next=has_next,
            navigation=f'<nav><a href="/papers/archive/{year}">All {year} papers</a></nav>',
        ),
        headers=ARCHIVE_HEADERS,
    )
