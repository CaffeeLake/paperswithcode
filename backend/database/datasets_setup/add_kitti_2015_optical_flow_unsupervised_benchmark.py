"""Add the KITTI 2015 unsupervised optical-flow test benchmark.

The legacy leaderboard reports official KITTI 2015 test-server Fl-all for
methods trained without KITTI target-benchmark flow ground truth or supervised
KITTI fine-tuning. It must remain separate from the unrestricted hidden-test
leaderboard and the public training-split leaderboard.

Run:
    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/add_kitti_2015_optical_flow_unsupervised_benchmark.py
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

BENCHMARK_NAME = "KITTI 2015 Optical Flow Unsupervised"
BENCHMARK_SLUG = "kitti-2015-optical-flow-unsupervised"
BENCHMARK_HOMEPAGE = (
    "https://www.cvlibs.net/datasets/kitti/eval_scene_flow.php?benchmark=flow"
)
METRIC_NAME = "Fl-all"


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
        raise RuntimeError(
            "Fl-all must be created by the KITTI 2015 hidden-test benchmark setup"
        )
    if row["direction"] != "lower_is_better":
        raise RuntimeError(f"Fl-all has unexpected direction {row['direction']!r}")
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
        "KITTI 2015 hidden-test Fl-all for methods without target flow supervision."
    )
    dataset.description = (
        "Official KITTI 2015 hidden optical-flow test-server evaluation restricted "
        "to unsupervised methods: the model is trained without KITTI target-"
        "benchmark optical-flow ground-truth supervision or supervised KITTI "
        "fine-tuning. The score is Fl-all, the percentage of all test pixels whose "
        "endpoint error exceeds both 3 pixels and 5% of ground-truth flow. This "
        "protocol is separate from the unrestricted hidden-test leaderboard and "
        "from paper-reported evaluation on the public training split."
    )
    dataset.url = BENCHMARK_HOMEPAGE
    dataset.homepage = BENCHMARK_HOMEPAGE
    dataset.paper_url = f"https://paperswithcode.co/paper/{source_paper.id}"
    dataset.introducing_paper_id = source_paper.id
    dataset.introducing_paper_title = source_paper.title
    dataset.introduced_year = 2015
    dataset.variant_type = "variant"
    dataset.split_name = "test (unsupervised)"
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
