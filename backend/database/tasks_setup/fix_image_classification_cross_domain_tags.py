"""Remove mistaken image-classification auto tags on audio-domain papers.

Audio papers frequently cite ViT, ImageNet, ResNet, or VGG as cross-modal
pretraining baselines. Those citations should not tag the paper with
image-classification unless the abstract also names an IC benchmark/task.

Run:
    uv run --env-file backend/keys.env \
        python backend/database/tasks_setup/fix_image_classification_cross_domain_tags.py
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.utils.keyword_matching import has_strong_image_classification_signal

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATION = (
    REPO_ROOT / "backend/database/migrations/update_image_classification_keywords.sql"
)


def apply_migration() -> None:
    sql = MIGRATION.read_text()
    with db_manager.engine.begin() as conn:
        conn.execute(text(sql))
    logger.info("Applied %s", MIGRATION.name)


def cleanup_false_positive_tags() -> int:
    with db_manager.engine.begin() as conn:
        image_task_id = conn.execute(
            text("SELECT id FROM tasks WHERE slug = 'image-classification'")
        ).scalar_one()
        audio_task_id = conn.execute(
            text("SELECT id FROM tasks WHERE slug = 'audio-classification'")
        ).scalar_one()

        rows = (
            conn.execute(
                text(
                    """
                SELECT p.id, p.arxiv_id, p.title, p.abstract
                FROM papers p
                JOIN paper_tasks pt_ic
                  ON pt_ic.paper_id = p.id
                 AND pt_ic.task_id = :image_task_id
                 AND pt_ic.source = 'auto'
                JOIN paper_tasks pt_audio
                  ON pt_audio.paper_id = p.id
                 AND pt_audio.task_id = :audio_task_id
                WHERE p.is_latest_version
                """
                ),
                {"image_task_id": image_task_id, "audio_task_id": audio_task_id},
            )
            .mappings()
            .all()
        )

        to_delete: list[int] = []
        for row in rows:
            blob = f"{row['title'] or ''} {row['abstract'] or ''}".strip()
            if not has_strong_image_classification_signal(blob):
                to_delete.append(row["id"])
                logger.info(
                    "Removing auto image-classification tag from %s (%s)",
                    row["arxiv_id"],
                    (row["title"] or "")[:70],
                )

        if not to_delete:
            return 0

        conn.execute(
            text(
                """
                DELETE FROM paper_tasks
                WHERE task_id = :image_task_id
                  AND source = 'auto'
                  AND paper_id = ANY(:paper_ids)
                """
            ),
            {"image_task_id": image_task_id, "paper_ids": to_delete},
        )
        return len(to_delete)


def main() -> None:
    apply_migration()
    removed = cleanup_false_positive_tags()
    logger.info("Removed %s auto image-classification tag(s)", removed)


if __name__ == "__main__":
    main()
