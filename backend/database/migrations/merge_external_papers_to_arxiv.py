#!/usr/bin/env python3
"""
Merge external paper rows into matching ArXiv rows (same title).

ArXiv is always preferred: linked evaluations, repos, tasks, bookmarks, and
other associations move onto the ArXiv row and the external duplicate is deleted.
"""

from __future__ import annotations

import sys

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.database.paper_merge import merge_external_paper_into_arxiv


def find_external_arxiv_title_pairs() -> list[tuple[int, int, str]]:
    session = db_manager.session_local()
    try:
        rows = session.execute(
            text(
                """
                SELECT
                    MIN(p.id) FILTER (WHERE p.source = 'external') AS external_id,
                    MIN(p.id) FILTER (WHERE p.source = 'arxiv') AS arxiv_id,
                    MIN(p.title) AS title
                FROM papers p
                WHERE p.is_latest_version = true
                GROUP BY LOWER(TRIM(p.title))
                HAVING COUNT(*) FILTER (WHERE p.source = 'external') >= 1
                   AND COUNT(*) FILTER (WHERE p.source = 'arxiv') >= 1
                ORDER BY MIN(p.id)
                """
            )
        ).fetchall()
        return [(row.external_id, row.arxiv_id, row.title) for row in rows]
    finally:
        session.close()


def main() -> int:
    pairs = find_external_arxiv_title_pairs()
    if not pairs:
        print("No external/ArXiv title duplicates found.")
        return 0

    print(f"Found {len(pairs)} external/ArXiv duplicate group(s).")
    session = db_manager.session_local()
    try:
        for external_id, arxiv_id, title in pairs:
            print(f"\nMerging external {external_id} -> arxiv paper {arxiv_id}")
            print(f"  Title: {title}")
            stats = merge_external_paper_into_arxiv(session, external_id, arxiv_id)
            session.commit()
            print(f"  Done: {stats}")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    remaining = find_external_arxiv_title_pairs()
    if remaining:
        print(f"\nWarning: {len(remaining)} duplicate group(s) still remain.")
        return 1

    print("\nAll external/ArXiv title duplicates merged.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
