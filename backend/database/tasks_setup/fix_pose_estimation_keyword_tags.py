"""Retag pose-estimation after tightening keywords (drop bare "keypoints").

Run:
    uv run --env-file backend/keys.env \\
        python backend/database/tasks_setup/fix_pose_estimation_keyword_tags.py
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

MIGRATION = "backend/database/migrations/update_pose_estimation_keywords.sql"


def apply_migration() -> None:
    sql = (REPO_ROOT / MIGRATION).read_text()
    with db_manager.engine.begin() as conn:
        conn.execute(text(sql))
    logger.info("Applied %s", MIGRATION)


def retag_pose_estimation() -> None:
    with db_manager.engine.begin() as conn:
        pose_task_id = conn.execute(
            text("SELECT id FROM tasks WHERE slug = 'pose-estimation'")
        ).scalar_one()
        removed = conn.execute(
            text(
                """
                DELETE FROM paper_tasks
                WHERE task_id = :task_id AND source = 'auto'
                """
            ),
            {"task_id": pose_task_id},
        ).rowcount
        logger.info("Removed %s auto pose-estimation tag(s)", removed)

    subprocess.run(
        [
            "uv",
            "run",
            "--env-file",
            "backend/keys.env",
            "backend/database/tasks_setup/link_papers_by_task_keywords.py",
        ],
        cwd=REPO_ROOT,
        check=True,
    )


def main() -> None:
    apply_migration()
    retag_pose_estimation()


if __name__ == "__main__":
    main()
