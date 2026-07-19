#!/usr/bin/env python3
"""Re-link papers for Motion Generation after tightening keywords."""

from __future__ import annotations

import os
import re
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor, execute_batch

from backend.utils.keyword_matching import (
    create_keyword_patterns,
    find_matching_items_simple,
)

MOTION_GENERATION_KEYWORDS = (
    "text-to-motion, text-driven human motion, text-driven motion generation, "
    "human motion generation, human motion synthesis, generating human motion, "
    "3d human motion generation, whole-body motion generation, human interaction generation, "
    "motion synthesis, motion diffusion, skeletal motion generation, video-to-motion, "
    "dance generation, music-conditioned dance, text-guided motion generation, "
    "motion inpainting, physics-based character control, open-vocabulary motion generation, "
    "motion-language"
)

# Title-level signals that the paper is not primarily motion generation, even when the
# abstract cites diffusion models or related work.
TITLE_EXCLUSION_PATTERNS: tuple[str, ...] = (
    r"motion prediction",
    r"motion forecasting",
    r"motion planning",
    r"image-to-video",
    r"text-to-video",
    r"video generation",
    r"facial animation",
    r"portrait animation",
    r"talking head",
    r"lip sync",
    r"automatic rigging",
    r"auto-rig",
    r"gaussian splat",
    r"video-to-4d",
    r"4d generation",
    r"4d content generation",
    r"neural avatar",
    r"human avatar",
    r"head avatar",
    r"image animation",
    r"character image animation",
    r"cloth dynamics",
    r"clothing dynamics",
    r"reconstructing articulated objects",
    r"robot action planning",
)

# Full-text exclusions when the paper lacks a strong generation signal in the title.
TEXT_EXCLUSION_PATTERNS: tuple[str, ...] = (
    r"motion completion for human motion prediction",
    r"controllable video generation",
    r"clothed avatar generation",
    r"skinned avatar",
    r"articulation-ready",
)

TITLE_STRONG_PATTERNS: tuple[str, ...] = (
    r"text-to-motion",
    r"human motion generation",
    r"human motion synthesis",
    r"text-driven human motion",
    r"motion diffusion model",
    r"skeletal motion",
    r"dance generation",
    r"music-conditioned dance",
    r"video-to-motion",
    r"generating human motion",
    r"3d human motion",
    r"motion inpainting",
    r"physics-based character control",
    r"open-vocabulary motion generation",
    r"motion-language",
    r"text-driven motion generation",
    r"whole-body motion generation",
    r"human interaction generation",
    r"text-guided motion",
    r"motion synthesis",
)

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "update_motion_generation_keywords.sql"
)


def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("PWC_DB_HOST", "localhost"),
        port=os.getenv("PWC_DB_PORT", "5432"),
        database=os.getenv("PWC_DB_NAME", "paperswithcode_hf"),
        user=os.getenv("PWC_DB_USER", "postgres"),
        password=os.getenv("PWC_DB_PASSWORD", "postgres"),
    )


def is_motion_generation_paper(title: str, abstract: str | None) -> bool:
    title_l = (title or "").lower()
    text_l = f"{title or ''} {abstract or ''}".lower()

    if any(re.search(p, title_l) for p in TITLE_EXCLUSION_PATTERNS):
        return False

    if any(re.search(p, text_l) for p in TEXT_EXCLUSION_PATTERNS):
        if not any(re.search(p, title_l) for p in TITLE_STRONG_PATTERNS):
            return False

    return True


def main() -> None:
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    if MIGRATION.is_file():
        cur.execute(MIGRATION.read_text())

    cur.execute("SELECT id FROM tasks WHERE slug = 'motion-generation'")
    task = cur.fetchone()
    if not task:
        raise RuntimeError("motion-generation task not found")
    task_id = task["id"]

    cur.execute(
        "UPDATE tasks SET keywords = %s WHERE id = %s",
        (MOTION_GENERATION_KEYWORDS, task_id),
    )

    cur.execute(
        "DELETE FROM paper_tasks WHERE task_id = %s AND source = 'auto'",
        (task_id,),
    )
    deleted = cur.rowcount
    print(f"Deleted {deleted:,} auto links for Motion Generation")

    task_row = {"id": task_id, "keywords": MOTION_GENERATION_KEYWORDS}
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
        if not find_matching_items_simple(text, case_sensitive, case_insensitive):
            continue
        if not is_motion_generation_paper(row["title"], row["abstract"]):
            continue
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
    print(f"Created {len(matches):,} auto links for Motion Generation")

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
