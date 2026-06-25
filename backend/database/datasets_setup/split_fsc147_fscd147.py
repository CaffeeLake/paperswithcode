#!/usr/bin/env python3
"""Split FSC-147 counting-only evals off FSCD-147 detection benchmark."""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.database.datasets_setup.add_object_counting_benchmarks import (
    ensure_dataset,
    ensure_source_paper,
    ensure_task,
)
from backend.services.evaluation_service import EvaluationService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

FSC147_SPEC = {
    "name": "FSC-147",
    "full_name": "Few-Shot Counting 147",
    "description": (
        "FSC-147 is a dataset of 147 object categories with over 6000 images for "
        "few-shot open-world object counting. Each instance is annotated with a dot "
        "at its center; three exemplar instances per image also have bounding boxes."
    ),
    "short_description": "Few-shot open-world object counting benchmark.",
    "homepage": "https://github.com/cvlab-stonybrook/LearningToCountEverything",
    "introduced_date": date(2021, 4, 16),
    "source_key": "fsc147",
    "metrics": [6, 8],
}


def move_counting_only_evals(
    session, task_id: int, fsc147_id: int, fscd147_id: int
) -> int:
    result = session.execute(
        text(
            """
            UPDATE evaluations e
            SET dataset_id = :fsc147_id
            WHERE e.task_id = :task_id
              AND e.dataset_id = :fscd147_id
              AND NOT EXISTS (
                SELECT 1
                FROM evaluations e2
                WHERE e2.task_id = e.task_id
                  AND e2.dataset_id = e.dataset_id
                  AND e2.paper_id = e.paper_id
                  AND e2.model_name = e.model_name
                  AND COALESCE(e2.harness, '') = COALESCE(e.harness, '')
                  AND e2.best_metric IN ('AP', 'AP50')
              )
            RETURNING e.id, e.model_name, e.best_metric
            """
        ),
        {
            "task_id": task_id,
            "fsc147_id": fsc147_id,
            "fscd147_id": fscd147_id,
        },
    )
    moved = result.fetchall()
    for row in moved:
        logger.info("Moved eval id=%s model=%s metric=%s", row[0], row[1], row[2])
    return len(moved)


def recalculate_leaderboards(session, task_id: int, dataset_id: int) -> None:
    svc = EvaluationService(session)
    for metric in ("MAE", "RMSE", "AP", "AP50"):
        svc.recalculate_ranks(task_id, dataset_id, metric_name=metric)


def main() -> None:
    session = db_manager.session_local()
    try:
        task_id = ensure_task(session)
        source_paper = ensure_source_paper(session, "fsc147")
        fsc147_id = ensure_dataset(session, FSC147_SPEC, task_id, source_paper)

        fscd147_id = session.execute(
            text("SELECT id FROM datasets WHERE slug = 'fscd-147'")
        ).scalar_one()

        moved = move_counting_only_evals(session, task_id, fsc147_id, fscd147_id)
        recalculate_leaderboards(session, task_id, fsc147_id)
        recalculate_leaderboards(session, task_id, fscd147_id)

        session.commit()
        logger.info(
            "FSC-147 id=%s: moved %s counting-only evals from FSCD-147 id=%s",
            fsc147_id,
            moved,
            fscd147_id,
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
