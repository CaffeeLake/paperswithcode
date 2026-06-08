#!/usr/bin/env python3
"""Keep ScanNet-1500 on 3D understanding only (option 2).

Moves AUC@5 leaderboard rows from image-matching to 3d-understanding,
deletes duplicate image-matching rows that already exist on 3d-understanding,
and removes the image-matching task link for ScanNet-1500.

Run with:

    uv run --env-file backend/keys.env \\
        python backend/database/datasets_setup/unlink_scannet1500_from_image_matching.py
"""

from __future__ import annotations

import logging

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.services.evaluation_service import EvaluationService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DATASET_SLUG = "scannet-1500"
IMAGE_MATCHING_SLUG = "image-matching"
THREE_D_UNDERSTANDING_SLUG = "3d-understanding"
METRICS = ["AUC@5", "AUC@10", "AUC@20"]


def main() -> None:
    session = db_manager.session_local()
    eval_service = EvaluationService(session)
    try:
        image_matching_id = session.execute(
            text("SELECT id FROM tasks WHERE slug = :slug"),
            {"slug": IMAGE_MATCHING_SLUG},
        ).scalar_one()
        three_d_id = session.execute(
            text("SELECT id FROM tasks WHERE slug = :slug"),
            {"slug": THREE_D_UNDERSTANDING_SLUG},
        ).scalar_one()
        dataset_id = session.execute(
            text("SELECT id FROM datasets WHERE slug = :slug"),
            {"slug": DATASET_SLUG},
        ).scalar_one()

        moved = session.execute(
            text(
                """
                UPDATE evaluations
                SET task_id = :new_task_id, updated_at = NOW()
                WHERE task_id = :old_task_id
                  AND dataset_id = :dataset_id
                  AND best_metric = 'AUC@5'
                RETURNING id
                """
            ),
            {
                "new_task_id": three_d_id,
                "old_task_id": image_matching_id,
                "dataset_id": dataset_id,
            },
        ).fetchall()
        logger.info("Moved %s AUC@5 evaluations to 3d-understanding", len(moved))

        deleted = session.execute(
            text(
                """
                DELETE FROM evaluations
                WHERE task_id = :task_id
                  AND dataset_id = :dataset_id
                  AND best_metric IN ('AUC@10', 'AUC@20')
                RETURNING id
                """
            ),
            {"task_id": image_matching_id, "dataset_id": dataset_id},
        ).fetchall()
        logger.info(
            "Deleted %s duplicate image-matching evaluations on ScanNet-1500",
            len(deleted),
        )

        metric_ids = {}
        for metric_name in METRICS:
            metric_id = session.execute(
                text("SELECT id FROM metrics WHERE name = :name"),
                {"name": metric_name},
            ).scalar_one()
            metric_ids[metric_name] = int(metric_id)
            session.execute(
                text(
                    """
                    INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
                    VALUES (:task_id, :dataset_id, :metric_id)
                    ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING
                    """
                ),
                {
                    "task_id": three_d_id,
                    "dataset_id": dataset_id,
                    "metric_id": metric_id,
                },
            )

        removed_metrics = session.execute(
            text(
                """
                DELETE FROM task_dataset_metrics
                WHERE task_id = :task_id AND dataset_id = :dataset_id
                RETURNING metric_id
                """
            ),
            {"task_id": image_matching_id, "dataset_id": dataset_id},
        ).fetchall()
        logger.info(
            "Removed %s image-matching metric links for ScanNet-1500",
            len(removed_metrics),
        )

        removed_link = session.execute(
            text(
                """
                DELETE FROM task_datasets
                WHERE task_id = :task_id AND dataset_id = :dataset_id
                RETURNING task_id
                """
            ),
            {"task_id": image_matching_id, "dataset_id": dataset_id},
        ).fetchone()
        if removed_link:
            logger.info("Removed ScanNet-1500 from image-matching task_datasets")

        for metric_name in METRICS:
            eval_service.recalculate_ranks(
                three_d_id, dataset_id, metric_name=metric_name
            )
            logger.info(
                "Recalculated ranks for 3d-understanding / ScanNet-1500 / %s",
                metric_name,
            )

        remaining = session.execute(
            text(
                """
                SELECT COUNT(*) FROM evaluations
                WHERE task_id = :task_id AND dataset_id = :dataset_id
                """
            ),
            {"task_id": image_matching_id, "dataset_id": dataset_id},
        ).scalar_one()
        if remaining:
            raise RuntimeError(
                f"Expected 0 image-matching ScanNet-1500 evals, found {remaining}"
            )

        session.commit()
        logger.info("ScanNet-1500 is now 3d-understanding only.")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
