#!/usr/bin/env python3
"""
Set ICML 2026 outstanding-paper awards on paper_conferences rows.

Source:
https://blog.icml.cc/2026/07/05/announcing-the-icml-2026-awards/
"""

from __future__ import annotations

import asyncio
import sys

from backend.database.conferences_setup.import_cvpr2026 import link_conference
from backend.database.connection import db_manager
from backend.models.database import Conference, Paper, PaperConference
from backend.services.arxiv_service import ArxivService
from backend.services.paper_service import PaperService

CONFERENCE_SLUG = "icml-2026"
PROCEEDING = "ICML 2026"
AWARDS: dict[str, str] = {
    # Outstanding Paper Award
    "2601.15165": "outstanding",
    "2602.01338": "outstanding",
    # Outstanding Paper Honorable Mention
    "2602.15515": "honorable_mention",
    "2601.08828": "honorable_mention",
    "2505.24832": "honorable_mention",
    "2602.02908": "honorable_mention",
    "2601.19791": "honorable_mention",
}


async def ensure_arxiv_paper(session, arxiv_id: str) -> Paper | None:
    paper = (
        session.query(Paper)
        .filter(Paper.arxiv_id == arxiv_id, Paper.is_latest_version)
        .order_by(Paper.id.desc())
        .first()
    )
    if paper is not None:
        return paper

    metadata = await ArxivService().get_paper_metadata(arxiv_id)
    if not metadata.success:
        print(f"  failed to fetch arXiv metadata: {arxiv_id}")
        return None

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
    session.flush()
    return session.query(Paper).filter(Paper.id == paper_id).first()


async def main() -> None:
    session = db_manager.session_local()
    try:
        conference = (
            session.query(Conference).filter(Conference.slug == CONFERENCE_SLUG).first()
        )
        if conference is None:
            print(f"Conference not found: {CONFERENCE_SLUG}")
            sys.exit(1)

        updated = 0
        missing = 0
        for arxiv_id, award in AWARDS.items():
            paper = await ensure_arxiv_paper(session, arxiv_id)
            if paper is None:
                print(f"  missing paper: {arxiv_id}")
                missing += 1
                continue

            link_conference(session, paper, conference)
            session.flush()
            if not paper.proceeding or paper.proceeding == PROCEEDING:
                paper.proceeding = PROCEEDING

            link = (
                session.query(PaperConference)
                .filter(
                    PaperConference.paper_id == paper.id,
                    PaperConference.conference_id == conference.id,
                )
                .first()
            )
            if link is None:
                print(f"  missing conference link: {arxiv_id}")
                missing += 1
                continue

            link.award = award
            updated += 1
            print(f"  {arxiv_id} -> {award}")

        session.commit()
        print(f"Updated {updated} awards ({missing} missing)")
    except Exception as exc:
        session.rollback()
        print(f"Failed: {exc}")
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    asyncio.run(main())
