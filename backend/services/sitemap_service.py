"""Bounded canonical sitemap queries shared with crawlable paper archives."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterator, Optional

from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Query, Session

from backend.models.database import Paper as DBPaper
from backend.utils.urls import get_paper_route_identifier


PRODUCTION_ORIGIN = "https://paperswithcode.co"
SITEMAP_BUCKET_SIZE = 50_000
SITEMAP_BATCH_SIZE = 1_000
ARCHIVE_PAGE_SIZE = 100


@dataclass(frozen=True)
class SitemapShard:
    year: int
    bucket: int

    @property
    def name(self) -> str:
        return f"{self.year:04d}-{self.bucket}"


@dataclass(frozen=True)
class SitemapPaper:
    route_identifier: str
    lastmod: datetime


@dataclass(frozen=True)
class ArchivePaper:
    route_identifier: str
    title: str
    published: Optional[date]


def eligible_paper_filter():
    """One public-eligibility predicate for sitemaps, archives, and reports."""
    return and_(
        DBPaper.is_latest_version,
        func.length(func.trim(DBPaper.title)) > 0,
        func.length(func.trim(func.coalesce(DBPaper.abstract, ""))) > 0,
        or_(
            and_(
                DBPaper.source == "arxiv",
                DBPaper.arxiv_id.is_not(None),
            ),
            and_(
                DBPaper.source == "external",
                DBPaper.source_url.is_not(None),
            ),
        ),
    )


def _year_expression():
    return case(
        (DBPaper.date_published.is_(None), 0),
        else_=func.extract("year", DBPaper.date_published),
    )


class SitemapService:
    def __init__(self, db: Session):
        self.db = db

    def list_shards(self) -> list[SitemapShard]:
        year = _year_expression().label("year")
        bucket = func.floor(DBPaper.id / SITEMAP_BUCKET_SIZE).label("bucket")
        rows = (
            self.db.query(year, bucket)
            .filter(eligible_paper_filter())
            .distinct()
            .order_by(year, bucket)
            .all()
        )
        return [SitemapShard(int(row.year), int(row.bucket)) for row in rows]

    def iter_shard(self, shard: SitemapShard) -> Iterator[SitemapPaper]:
        lower = shard.bucket * SITEMAP_BUCKET_SIZE
        upper = lower + SITEMAP_BUCKET_SIZE
        query = (
            self.db.query(DBPaper)
            .filter(
                eligible_paper_filter(),
                DBPaper.id >= lower,
                DBPaper.id < upper,
            )
            .order_by(DBPaper.id)
            .yield_per(SITEMAP_BATCH_SIZE)
        )
        if shard.year:
            query = query.filter(
                DBPaper.date_published >= date(shard.year, 1, 1),
                DBPaper.date_published < date(shard.year + 1, 1, 1),
            )
        else:
            query = query.filter(DBPaper.date_published.is_(None))

        for paper in query:
            published_at = (
                datetime.combine(paper.date_published, time.min, tzinfo=timezone.utc)
                if paper.date_published
                else None
            )
            created_at = paper.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            lastmod = max(value for value in (published_at, created_at) if value)
            yield SitemapPaper(
                route_identifier=get_paper_route_identifier(
                    paper.source, paper.arxiv_id, paper.id
                ),
                lastmod=lastmod,
            )

    def archive_years(self) -> list[tuple[int, int]]:
        year = func.extract("year", DBPaper.date_published).label("year")
        return [
            (int(row.year), int(row.count))
            for row in (
                self.db.query(year, func.count(DBPaper.id).label("count"))
                .filter(
                    eligible_paper_filter(),
                    DBPaper.date_published.is_not(None),
                )
                .group_by(year)
                .order_by(year.desc())
                .all()
            )
        ]

    def archive_query(
        self,
        *,
        recent: bool = False,
        year: Optional[int] = None,
        month: Optional[int] = None,
    ) -> Query:
        query = self.db.query(DBPaper).filter(eligible_paper_filter())
        if recent:
            cutoff = datetime.now(timezone.utc) - timedelta(days=14)
            query = query.filter(
                or_(
                    DBPaper.date_published >= cutoff.date(),
                    DBPaper.created_at >= cutoff,
                )
            )
        elif year is not None:
            start = date(year, month or 1, 1)
            if month == 12:
                end = date(year + 1, 1, 1)
            elif month:
                end = date(year, month + 1, 1)
            else:
                end = date(year + 1, 1, 1)
            query = query.filter(
                DBPaper.date_published >= start,
                DBPaper.date_published < end,
            )
        return query.order_by(
            DBPaper.date_published.desc().nullslast(), DBPaper.id.desc()
        )

    def archive_page(
        self,
        *,
        page: int,
        recent: bool = False,
        year: Optional[int] = None,
        month: Optional[int] = None,
    ) -> tuple[list[ArchivePaper], bool]:
        rows = (
            self.archive_query(recent=recent, year=year, month=month)
            .offset((page - 1) * ARCHIVE_PAGE_SIZE)
            .limit(ARCHIVE_PAGE_SIZE + 1)
            .all()
        )
        items = [
            ArchivePaper(
                route_identifier=get_paper_route_identifier(
                    paper.source, paper.arxiv_id, paper.id
                ),
                title=paper.title,
                published=paper.date_published,
            )
            for paper in rows[:ARCHIVE_PAGE_SIZE]
        ]
        return items, len(rows) > ARCHIVE_PAGE_SIZE
