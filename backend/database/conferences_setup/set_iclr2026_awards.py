#!/usr/bin/env python3
"""
Set ICLR 2026 outstanding-paper awards on paper_conferences rows.

Source:
https://blog.iclr.cc/2026/04/23/announcing-the-iclr-2026-outstanding-papers/
"""

from __future__ import annotations

import sys

from backend.database.connection import db_manager
from backend.models.database import Conference, Paper, PaperConference

CONFERENCE_SLUG = "iclr-2026"
AWARDS: dict[str, str] = {
    "2510.19315": "outstanding",
    "2505.06120": "outstanding",
    "2505.16932": "honorable_mention",
}


def main() -> None:
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
            paper = (
                session.query(Paper)
                .filter(Paper.arxiv_id == arxiv_id, Paper.is_latest_version)
                .order_by(Paper.id.desc())
                .first()
            )
            if paper is None:
                print(f"  missing paper: {arxiv_id}")
                missing += 1
                continue

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
    main()
