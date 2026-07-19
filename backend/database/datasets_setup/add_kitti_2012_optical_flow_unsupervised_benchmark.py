"""Add the KITTI 2012 unsupervised optical-flow benchmark.

Legacy PwC tracks this protocol with Average End-Point Error only. It is kept
separate from the unrestricted official hidden-test leaderboard because rows
must not use KITTI target-benchmark flow ground truth or supervised fine-tuning.

Run:
    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/add_kitti_2012_optical_flow_unsupervised_benchmark.py
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

BENCHMARK_NAME = "KITTI 2012 Optical Flow Unsupervised"
BENCHMARK_SLUG = "kitti-2012-optical-flow-unsupervised"
BENCHMARK_HOMEPAGE = (
    "https://www.cvlibs.net/datasets/kitti/eval_stereo_flow.php?benchmark=flow"
)
METRIC_NAME = "Average End-Point Error"


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


def get_metric_id(session: Session) -> int:
    row = (
        session.execute(
            text("SELECT id, direction FROM metrics WHERE name = :name"),
            {"name": METRIC_NAME},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise RuntimeError(f"Required metric {METRIC_NAME!r} not found")
    if row["direction"] != "lower_is_better":
        raise RuntimeError(
            f"{METRIC_NAME} has unexpected direction {row['direction']!r}"
        )
    return int(row["id"])


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
        "KITTI 2012 optical-flow AEE without target flow supervision or fine-tuning."
    )
    dataset.description = (
        "KITTI 2012 optical-flow evaluation restricted to unsupervised methods: "
        "the evaluated model must not use KITTI target-benchmark optical-flow "
        "ground-truth supervision or supervised KITTI fine-tuning. Legacy PwC "
        "supports comparable Average End-Point Error cells for this protocol, "
        "but does not establish a comparable unsupervised Out-Noc series, so only "
        "Average End-Point Error is ranked. This protocol is separate from the "
        "unrestricted official KITTI 2012 hidden-test leaderboard."
    )
    dataset.url = BENCHMARK_HOMEPAGE
    dataset.homepage = BENCHMARK_HOMEPAGE
    dataset.paper_url = f"https://paperswithcode.co/paper/{source_paper.id}"
    dataset.introducing_paper_id = source_paper.id
    dataset.introducing_paper_title = source_paper.title
    dataset.introduced_year = 2012
    dataset.variant_type = "variant"
    dataset.split_name = "unsupervised protocol"
    session.flush()
    return dataset


def main() -> None:
    with db_manager.session_local() as session:
        task = get_task(session)
        source_paper = get_source_paper(session)
        metric_id = get_metric_id(session)
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
        session.execute(
            text(
                """
                DELETE FROM task_dataset_metrics
                WHERE task_id = :task_id
                  AND dataset_id = :dataset_id
                  AND metric_id <> :metric_id
                """
            ),
            {
                "task_id": task.id,
                "dataset_id": dataset.id,
                "metric_id": metric_id,
            },
        )
        session.execute(
            text(
                """
                INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
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
            "%s ready: dataset_id=%s slug=%s task_id=%s metric_id=%s "
            "source_paper_id=%s paper_url=%s",
            dataset.name,
            dataset.id,
            dataset.slug,
            task.id,
            metric_id,
            source_paper.id,
            dataset.paper_url,
        )


if __name__ == "__main__":
    main()
