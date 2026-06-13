#!/usr/bin/env python3
"""Revert UVIS task: move evals back to Video segmentation and delete the task.

Undoes add_unsupervised_video_instance_segmentation_task.py. Migrates zero-shot
VideoCutLER evaluations back to the shared Video segmentation task, recalculates
ranks, then deletes the UVIS task (CASCADE removes task_datasets, metrics, paper_tasks).

Run with:

    uv run --env-file backend/keys.env \\
        python backend/database/datasets_setup/revert_unsupervised_video_instance_segmentation_task.py
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.services.evaluation_service import EvaluationService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

VIDEO_SEGMENTATION_TASK_ID = 262
TASK_SLUG = "unsupervised-video-instance-segmentation"

YOUTUBE_VIS_2019_DATASET_ID = 606
YOUTUBE_VIS_2021_DATASET_ID = 607
DAVIS_DATASET_ID = 263

VIDEOCUTLER_PAPER_ID = 19871

ZERO_SHOT_EVAL_IDS = [9080, 9081, 9082]


def _migrate_evaluations_back(session: Session) -> None:
    service = EvaluationService(session)

    for eval_id in ZERO_SHOT_EVAL_IDS:
        row = (
            session.execute(
                text(
                    "SELECT task_id, dataset_id, best_metric FROM evaluations WHERE id = :id"
                ),
                {"id": eval_id},
            )
            .mappings()
            .one()
        )
        service.update_evaluation(
            evaluation_id=eval_id, task_id=VIDEO_SEGMENTATION_TASK_ID
        )
        logger.info(
            "Moved evaluation %s -> task %s (dataset %s, metric %s)",
            eval_id,
            VIDEO_SEGMENTATION_TASK_ID,
            row["dataset_id"],
            row["best_metric"],
        )

    for dataset_id, metric_name in [
        (YOUTUBE_VIS_2019_DATASET_ID, "AP"),
        (YOUTUBE_VIS_2021_DATASET_ID, "AP"),
        (DAVIS_DATASET_ID, "J&F"),
    ]:
        service.recalculate_ranks(
            VIDEO_SEGMENTATION_TASK_ID, dataset_id, metric_name=metric_name
        )


def _delete_uvis_task(session: Session) -> None:
    row = (
        session.execute(
            text("SELECT id, name FROM tasks WHERE slug = :slug"),
            {"slug": TASK_SLUG},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        logger.info("UVIS task %r not found — already reverted?", TASK_SLUG)
        return

    task_id = row["id"]
    logger.info("Deleting task %r (id=%s)", row["name"], task_id)
    session.execute(text("DELETE FROM tasks WHERE id = :id"), {"id": task_id})


def main() -> None:
    session = db_manager.session_local()
    try:
        _migrate_evaluations_back(session)
        session.commit()

        _delete_uvis_task(session)
        session.commit()

        davis_tasks = (
            session.execute(
                text(
                    """
                SELECT t.slug, t.name
                FROM task_datasets td
                JOIN tasks t ON t.id = td.task_id
                WHERE td.dataset_id = :dataset_id
                ORDER BY t.name
                """
                ),
                {"dataset_id": DAVIS_DATASET_ID},
            )
            .mappings()
            .all()
        )
        logger.info("DAVIS linked tasks after revert:")
        for row in davis_tasks:
            logger.info("  %s (%s)", row["name"], row["slug"])

        moved = (
            session.execute(
                text(
                    """
                SELECT e.id, e.model_name, d.name AS dataset, e.best_metric,
                       e.metrics, t.slug AS task_slug
                FROM evaluations e
                JOIN datasets d ON d.id = e.dataset_id
                JOIN tasks t ON t.id = e.task_id
                WHERE e.paper_id = :paper_id
                ORDER BY t.slug, d.name, e.model_name
                """
                ),
                {"paper_id": VIDEOCUTLER_PAPER_ID},
            )
            .mappings()
            .all()
        )
        logger.info("VideoCutLER evaluations after revert:")
        for row in moved:
            logger.info("  %s", dict(row))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
