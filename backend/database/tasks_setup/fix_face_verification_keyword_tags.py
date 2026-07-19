"""Retag face-verification after removing tar/far keyword false positives.

Run:
    uv run --env-file backend/keys.env \\
        python backend/database/tasks_setup/fix_face_verification_keyword_tags.py
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor, execute_batch
from sqlalchemy import text

from backend.database.connection import db_manager
from backend.utils.keyword_matching import (
    create_keyword_patterns,
    find_matching_items_simple,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATION = "backend/database/migrations/fix_face_verification_keywords.sql"

FACE_VERIFICATION_KEYWORDS = "face verification,face recognition,lfw,ijb"


def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("PWC_DB_HOST", "localhost"),
        port=os.getenv("PWC_DB_PORT", "5432"),
        database=os.getenv("PWC_DB_NAME", "paperswithcode_hf"),
        user=os.getenv("PWC_DB_USER", "postgres"),
        password=os.getenv("PWC_DB_PASSWORD", "postgres"),
    )


def apply_migration() -> None:
    sql = (REPO_ROOT / MIGRATION).read_text()
    with db_manager.engine.begin() as conn:
        conn.execute(text(sql))
    logger.info("Applied %s", MIGRATION)


def relink_face_verification() -> None:
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("SELECT id FROM tasks WHERE slug = 'face-verification'")
    task = cur.fetchone()
    if not task:
        raise RuntimeError("face-verification task not found")
    task_id = task["id"]

    cur.execute(
        "DELETE FROM paper_tasks WHERE task_id = %s AND source = 'auto'",
        (task_id,),
    )
    deleted = cur.rowcount
    logger.info("Removed %s auto face-verification tag(s)", deleted)

    task_row = {"id": task_id, "keywords": FACE_VERIFICATION_KEYWORDS}
    case_sensitive, case_insensitive = create_keyword_patterns([task_row])

    cur.execute(
        """
        SELECT id, title, abstract
        FROM papers
        WHERE is_latest_version
        ORDER BY id
        """
    )

    matches: list[tuple[int, int]] = []
    for row in cur:
        paper_text = f"{row['title']} {row['abstract'] or ''}"
        if find_matching_items_simple(paper_text, case_sensitive, case_insensitive):
            matches.append((row["id"], task_id))

    if matches:
        execute_batch(
            cur,
            """
            INSERT INTO paper_tasks (paper_id, task_id, source)
            VALUES (%s, %s, 'auto')
            ON CONFLICT (paper_id, task_id) DO NOTHING
            """,
            matches,
            page_size=1000,
        )
    logger.info("Re-linked %s face-verification paper(s)", len(matches))

    conn.commit()
    cur.close()
    conn.close()


def main() -> None:
    apply_migration()
    relink_face_verification()


if __name__ == "__main__":
    main()
