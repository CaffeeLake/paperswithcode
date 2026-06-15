"""Retag image-matting papers and introduce video-matting.

1. Apply keyword + video-matting migrations
2. Remove mistaken manual tag on arXiv 1706.03137 (quantum paper)
3. Clear auto image-matting tags and re-run keyword linker
4. Drop known false positives that only cite matting as related work

Run:
    uv run --env-file backend/keys.env \
        python backend/database/tasks_setup/fix_image_matting_keyword_tags.py
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from sqlalchemy import text

from backend.database.connection import db_manager

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]

# Papers that mention image matting in related work but are not matting papers.
FALSE_POSITIVE_ARXIV_IDS = (
    "2511.16249",  # layer decomposition
    "2601.03362",  # 3D depth / view synthesis (HairGuard)
    "2508.01098",  # transparent image inpainting
    "2204.10648",  # exposure correction; cites portrait matting as downstream eval
)

MIGRATIONS = (
    "backend/database/migrations/update_image_matting_keywords.sql",
    "backend/database/migrations/add_video_matting_task.sql",
)


def apply_migrations() -> None:
    for rel in MIGRATIONS:
        sql = (REPO_ROOT / rel).read_text()
        with db_manager.engine.begin() as conn:
            conn.execute(text(sql))
        logger.info("Applied %s", rel)


def cleanup_and_prepare() -> None:
    with db_manager.engine.begin() as conn:
        image_task_id = conn.execute(
            text("SELECT id FROM tasks WHERE slug = 'image-matting'")
        ).scalar_one()

        removed_wrong_manual = conn.execute(
            text(
                """
                DELETE FROM paper_tasks pt
                USING papers p
                WHERE pt.paper_id = p.id
                  AND pt.task_id = :task_id
                  AND pt.source = 'manual'
                  AND p.arxiv_id = '1706.03137'
                """
            ),
            {"task_id": image_task_id},
        ).rowcount
        logger.info(
            "Removed %s mistaken manual tag(s) for arXiv 1706.03137",
            removed_wrong_manual,
        )

        removed_auto = conn.execute(
            text(
                """
                DELETE FROM paper_tasks
                WHERE task_id = :task_id AND source = 'auto'
                """
            ),
            {"task_id": image_task_id},
        ).rowcount
        logger.info("Removed %s auto image-matting tag(s)", removed_auto)


def run_keyword_linker() -> None:
    cmd = [
        "uv",
        "run",
        "--env-file",
        "backend/keys.env",
        "backend/database/tasks_setup/link_papers_by_task_keywords.py",
    ]
    logger.info("Running keyword linker: %s", " ".join(cmd))
    subprocess.run(cmd, cwd=REPO_ROOT, check=True)


def remove_false_positives() -> None:
    with db_manager.engine.begin() as conn:
        image_task_id = conn.execute(
            text("SELECT id FROM tasks WHERE slug = 'image-matting'")
        ).scalar_one()
        removed = conn.execute(
            text(
                """
                DELETE FROM paper_tasks pt
                USING papers p
                WHERE pt.paper_id = p.id
                  AND pt.task_id = :task_id
                  AND p.arxiv_id = ANY(:arxiv_ids)
                """
            ),
            {
                "task_id": image_task_id,
                "arxiv_ids": list(FALSE_POSITIVE_ARXIV_IDS),
            },
        ).rowcount
        logger.info("Removed %s curated false-positive image-matting tag(s)", removed)


def report_counts() -> None:
    with db_manager.engine.connect() as conn:
        for slug in ("image-matting", "video-matting"):
            row = conn.execute(
                text(
                    """
                    SELECT COUNT(*) AS n,
                           COUNT(*) FILTER (WHERE pt.source = 'auto') AS auto_n,
                           COUNT(*) FILTER (WHERE pt.source = 'manual') AS manual_n
                    FROM paper_tasks pt
                    JOIN tasks t ON t.id = pt.task_id
                    JOIN papers p ON p.id = pt.paper_id
                    WHERE t.slug = :slug AND p.is_latest_version
                    """
                ),
                {"slug": slug},
            ).one()
            logger.info(
                "%s: %s papers (auto=%s, manual=%s)",
                slug,
                row.n,
                row.auto_n,
                row.manual_n,
            )

        video_on_image = conn.execute(
            text(
                """
                SELECT p.arxiv_id, p.title
                FROM paper_tasks pt_vid
                JOIN paper_tasks pt_img
                  ON pt_img.paper_id = pt_vid.paper_id
                JOIN tasks t_vid ON t_vid.id = pt_vid.task_id
                JOIN tasks t_img ON t_img.id = pt_img.task_id
                JOIN papers p ON p.id = pt_vid.paper_id
                WHERE t_vid.slug = 'video-matting'
                  AND t_img.slug = 'image-matting'
                  AND p.is_latest_version
                ORDER BY p.title
                """
            )
        ).fetchall()
        if video_on_image:
            logger.warning(
                "Papers still tagged with BOTH tasks (%s):", len(video_on_image)
            )
            for r in video_on_image:
                logger.warning("  %s | %s", r.arxiv_id or "?", r.title[:80])
        else:
            logger.info("No papers carry both image-matting and video-matting tags")


def main() -> None:
    apply_migrations()
    cleanup_and_prepare()
    run_keyword_linker()
    remove_false_positives()
    report_counts()


if __name__ == "__main__":
    main()
