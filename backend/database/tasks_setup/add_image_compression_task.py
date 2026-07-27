#!/usr/bin/env python3
"""Import the seed paper and conservatively tag Image Compression papers."""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select, text

from backend.database.connection import db_manager
from backend.models.database import Author, Paper, PaperAuthor
from backend.services.arxiv_service import ArxivService
from backend.services.paper_service import PaperService
from backend.utils.keyword_matching import (
    create_keyword_patterns,
    find_matching_items_simple,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TASK_SLUG = "image-compression"
SEED_ARXIV_ID = "2111.06707"


async def ensure_arxiv_paper(session, arxiv_id: str) -> Paper:
    paper = session.scalar(
        select(Paper).where(
            Paper.arxiv_id == arxiv_id,
            Paper.is_latest_version.is_(True),
        )
    )
    if paper:
        return paper

    metadata = await ArxivService().get_paper_metadata(arxiv_id)
    if not metadata.success:
        raise RuntimeError(
            f"Failed to fetch arXiv metadata for {arxiv_id}: {metadata.error_message}"
        )

    paper_id = PaperService(session).add_paper(
        {
            "arxiv_id": metadata.arxiv_id,
            "title": metadata.title,
            "abstract": metadata.abstract,
            "version": metadata.version,
            "date_published": metadata.published.date() if metadata.published else None,
            "primary_category": metadata.primary_category,
            "all_categories": metadata.categories,
            "is_latest_version": True,
        }
    )
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise RuntimeError(f"Paper import returned no row for {arxiv_id}")

    for order, author_name in enumerate(metadata.authors or [], start=1):
        author = session.scalar(select(Author).where(Author.name == author_name))
        if author is None:
            author = Author(name=author_name)
            session.add(author)
            session.flush()
        session.add(
            PaperAuthor(
                paper_id=paper.id,
                author_id=author.id,
                author_order=order,
            )
        )
    session.flush()
    logger.info("Imported seed paper %s (id=%s)", arxiv_id, paper.id)
    return paper


def link_keyword_candidates(session, task_id: int, keywords: str) -> list[Paper]:
    """Tag only explicit title matches; abstracts create incidental false positives."""
    sensitive, insensitive = create_keyword_patterns(
        [{"id": task_id, "keywords": keywords}]
    )
    candidates = session.scalars(
        select(Paper).where(Paper.is_latest_version.is_(True))
    ).all()
    matches = [
        paper
        for paper in candidates
        if task_id in find_matching_items_simple(paper.title, sensitive, insensitive)
    ]
    for paper in matches:
        session.execute(
            text(
                """
                INSERT INTO paper_tasks (paper_id, task_id, source)
                VALUES (:paper_id, :task_id, 'auto')
                ON CONFLICT (paper_id, task_id) DO NOTHING
                """
            ),
            {"paper_id": paper.id, "task_id": task_id},
        )
    return matches


async def run() -> None:
    session = db_manager.session_local()
    try:
        task = (
            session.execute(
                text("SELECT id, keywords FROM tasks WHERE slug = :slug"),
                {"slug": TASK_SLUG},
            )
            .mappings()
            .one()
        )
        seed = await ensure_arxiv_paper(session, SEED_ARXIV_ID)
        matches = link_keyword_candidates(session, int(task["id"]), task["keywords"])

        # Preserve the user-requested seed link across future auto-tag rebuilds.
        session.execute(
            text(
                """
                INSERT INTO paper_tasks (paper_id, task_id, source)
                VALUES (:paper_id, :task_id, 'manual')
                ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'
                """
            ),
            {"paper_id": seed.id, "task_id": task["id"]},
        )
        session.commit()
        logger.info(
            "Tagged %s keyword-title matches; seed paper %s is pinned as manual",
            len(matches),
            SEED_ARXIV_ID,
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
