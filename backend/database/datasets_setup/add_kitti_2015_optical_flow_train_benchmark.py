"""Add the public KITTI 2015 optical-flow training-split benchmark.

This leaderboard is for paper-reported evaluation on the public KITTI 2015
training split. It is deliberately separate from the official hidden-test
server leaderboard and from unsupervised-only protocol leaderboards.

Run:
    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/add_kitti_2015_optical_flow_train_benchmark.py
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import (
    Dataset as DBDataset,
    Paper as DBPaper,
    Task as DBTask,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

TASK_ID = 323
TASK_SLUG = "optical-flow"
SOURCE_PAPER_ID = 98365

BENCHMARK_NAME = "KITTI 2015 Optical Flow Train"
BENCHMARK_SLUG = "kitti-2015-optical-flow-train"
BENCHMARK_HOMEPAGE = (
    "https://www.cvlibs.net/datasets/kitti/eval_scene_flow.php?benchmark=flow"
)

METRICS = {
    "EPE": {
        "full_name": "Average Endpoint Error",
        "direction": "lower_is_better",
        "scale": "pixels",
        "description": (
            "Mean Euclidean endpoint error between predicted and ground-truth "
            "optical-flow vectors, in pixels; lower is better."
        ),
    },
    "F1-all": {
        "full_name": "Percentage of All Optical Flow Outliers",
        "direction": "lower_is_better",
        "scale": "percent",
        "description": (
            "KITTI optical-flow outlier percentage over all evaluated pixels; a "
            "pixel is an outlier when endpoint error exceeds both 3 px and 5% "
            "of ground-truth flow. Lower is better."
        ),
    },
}


def get_task(session: Session) -> DBTask:
    task = session.query(DBTask).filter(DBTask.id == TASK_ID).one_or_none()
    if task is None or task.slug != TASK_SLUG:
        raise RuntimeError(
            f"Expected task id={TASK_ID}, slug={TASK_SLUG!r}; got {task!r}"
        )
    return task


def get_source_paper(session: Session) -> DBPaper:
    paper = session.query(DBPaper).filter(DBPaper.id == SOURCE_PAPER_ID).one_or_none()
    if paper is None:
        raise RuntimeError(f"Source paper id={SOURCE_PAPER_ID} not found")
    return paper


def ensure_metrics(session: Session) -> dict[str, int]:
    metric_ids: dict[str, int] = {}
    for name, spec in METRICS.items():
        metric_id = session.execute(
            text("SELECT id FROM metrics WHERE name = :name"), {"name": name}
        ).scalar_one_or_none()
        if metric_id is None:
            metric_id = session.execute(
                text(
                    """
                    INSERT INTO metrics
                        (name, full_name, direction, scale, description)
                    VALUES
                        (:name, :full_name, :direction, :scale, :description)
                    RETURNING id
                    """
                ),
                {"name": name, **spec},
            ).scalar_one()
            logger.info("Created metric %s (id=%s)", name, metric_id)
        else:
            session.execute(
                text(
                    """
                    UPDATE metrics
                    SET full_name = :full_name,
                        direction = :direction,
                        scale = :scale,
                        description = :description,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :metric_id
                    """
                ),
                {"metric_id": metric_id, **spec},
            )
        metric_ids[name] = int(metric_id)
    return metric_ids


def ensure_dataset(session: Session, source_paper: DBPaper) -> DBDataset:
    dataset = (
        session.query(DBDataset).filter(DBDataset.slug == BENCHMARK_SLUG).one_or_none()
    )
    if dataset is None:
        dataset = DBDataset(name=BENCHMARK_NAME, slug=BENCHMARK_SLUG)
        session.add(dataset)
        session.flush()
        logger.info("Created dataset %s (id=%s)", BENCHMARK_NAME, dataset.id)

    dataset.name = BENCHMARK_NAME
    dataset.full_name = BENCHMARK_NAME
    dataset.short_description = (
        "Public KITTI 2015 optical-flow training split (EPE and F1-all)."
    )
    dataset.description = (
        "Paper-reported evaluation on the public KITTI 2015 optical-flow "
        "training split using average endpoint error (EPE, pixels) and F1-all "
        "(outlier percentage). Hidden-test-server Fl-all scores and "
        "unsupervised-only protocols are intentionally excluded."
    )
    dataset.url = BENCHMARK_HOMEPAGE
    dataset.homepage = BENCHMARK_HOMEPAGE
    dataset.paper_url = f"https://paperswithcode.co/paper/{source_paper.id}"
    dataset.introducing_paper_id = source_paper.id
    dataset.introducing_paper_title = source_paper.title
    dataset.introduced_year = 2015
    dataset.variant_type = "split"
    dataset.split_name = "train"
    session.flush()
    return dataset


def main() -> None:
    with db_manager.session_local() as session:
        task = get_task(session)
        source_paper = get_source_paper(session)
        metric_ids = ensure_metrics(session)
        dataset = ensure_dataset(session, source_paper)

        session.execute(
            text(
                """
                INSERT INTO paper_tasks (paper_id, task_id, source)
                VALUES (:paper_id, :task_id, 'manual')
                ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'
                """
            ),
            {"paper_id": source_paper.id, "task_id": task.id},
        )
        session.execute(
            text(
                """
                INSERT INTO task_datasets
                    (task_id, dataset_id, supports_harness, featured_rank)
                VALUES (:task_id, :dataset_id, FALSE, NULL)
                ON CONFLICT (task_id, dataset_id) DO UPDATE
                SET supports_harness = FALSE, featured_rank = NULL,
                    updated_at = CURRENT_TIMESTAMP
                """
            ),
            {"task_id": task.id, "dataset_id": dataset.id},
        )

        # Enforce the public-training protocol if this script is rerun after
        # accidental test-server or unsupervised metric wiring.
        session.execute(
            text(
                """
                DELETE FROM task_dataset_metrics
                WHERE task_id = :task_id
                  AND dataset_id = :dataset_id
                  AND metric_id <> ALL(:metric_ids)
                """
            ),
            {
                "task_id": task.id,
                "dataset_id": dataset.id,
                "metric_ids": list(metric_ids.values()),
            },
        )
        for metric_id in metric_ids.values():
            session.execute(
                text(
                    """
                    INSERT INTO task_dataset_metrics
                        (task_id, dataset_id, metric_id)
                    VALUES (:task_id, :dataset_id, :metric_id)
                    ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING
                    """
                ),
                {
                    "task_id": task.id,
                    "dataset_id": dataset.id,
                    "metric_id": metric_id,
                },
            )
        session.commit()

        logger.info(
            "%s ready: dataset_id=%s slug=%s task_id=%s metrics=%s "
            "source_paper_id=%s paper_url=%s",
            dataset.name,
            dataset.id,
            dataset.slug,
            task.id,
            metric_ids,
            source_paper.id,
            dataset.paper_url,
        )


if __name__ == "__main__":
    main()
