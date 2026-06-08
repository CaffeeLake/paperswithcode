#!/usr/bin/env python3
"""Re-link papers for Anomaly Detection after tightening keywords."""

from __future__ import annotations

import os

import psycopg2
from psycopg2.extras import RealDictCursor, execute_batch

from backend.utils.keyword_matching import (
    create_keyword_patterns,
    find_matching_items_simple,
)

ANOMALY_KEYWORDS = (
    "anomaly detection, industrial anomaly, out-of-distribution detection, "
    "OOD detection, unsupervised anomaly detection, anomaly localization, "
    "zero-shot anomaly detection, video anomaly detection, anomaly segmentation"
)


def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("PWC_DB_HOST", "localhost"),
        port=os.getenv("PWC_DB_PORT", "5432"),
        database=os.getenv("PWC_DB_NAME", "paperswithcode_hf"),
        user=os.getenv("PWC_DB_USER", "postgres"),
        password=os.getenv("PWC_DB_PASSWORD", "postgres"),
    )


def main() -> None:
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("SELECT id FROM tasks WHERE slug = 'anomaly-detection'")
    task = cur.fetchone()
    if not task:
        raise RuntimeError("anomaly-detection task not found")
    task_id = task["id"]

    cur.execute(
        "UPDATE tasks SET keywords = %s WHERE id = %s",
        (ANOMALY_KEYWORDS, task_id),
    )

    cur.execute(
        "DELETE FROM paper_tasks WHERE task_id = %s AND source = 'auto'",
        (task_id,),
    )
    deleted = cur.rowcount
    print(f"Deleted {deleted:,} auto links for Anomaly Detection")

    task_row = {"id": task_id, "keywords": ANOMALY_KEYWORDS}
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
    processed = 0
    for row in cur:
        processed += 1
        text = f"{row['title']} {row['abstract'] or ''}"
        if find_matching_items_simple(text, case_sensitive, case_insensitive):
            matches.append((row["id"], task_id))

    if matches:
        execute_batch(
            cur,
            """
            INSERT INTO paper_tasks (paper_id, task_id, source)
            VALUES (%s, %s, 'auto')
            ON CONFLICT DO NOTHING
            """,
            matches,
            page_size=1000,
        )

    conn.commit()
    print(f"Processed {processed:,} papers")
    print(f"Created {len(matches):,} auto links for Anomaly Detection")

    cur.execute(
        """
        SELECT count(*)
        FROM paper_tasks
        WHERE task_id = %s
        """,
        (task_id,),
    )
    total = cur.fetchone()["count"]
    print(f"Total links (auto + manual): {total:,}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
