"""Add the standard class-separated, normal-only BTAD benchmark.

The board is restricted to the conventional BTAD protocol: one model per
product category, trained only on normal images and evaluated on the standard
test split. Unified, zero/few-shot, and synthetic-training results are not
comparable and belong on separate boards.

Run:
    uv run --env-file backend/keys.env python \
        backend/database/datasets_setup/add_btad_class_separated_benchmark.py
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import Dataset as DBDataset
from backend.models.database import Paper as DBPaper
from backend.models.database import Task as DBTask

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

TASK_ID = 317
TASK_SLUG = "anomaly-detection"
SOURCE_PAPER_ID = 5544
SOURCE_ARXIV_ID = "2104.10036"
SOURCE_TITLE = (
    "VT-ADL: A Vision Transformer Network for Image Anomaly Detection and Localization"
)

DATASET_NAME = "BTAD (Class-Separated Normal-Only)"
DATASET_SLUG = "btad-class-separated-normal-only"
DATASET_HOMEPAGE = "https://github.com/pankajmishra000/VT-ADL"
DATASET_SHORT_DESCRIPTION = (
    "Standard BTAD evaluation with a separate normal-only model for each "
    "product category."
)
DATASET_DESCRIPTION = (
    "Class-separated anomaly detection and localization on the standard BTAD "
    "test split. Eligible results train one model independently for each of "
    "the three product categories using only that category's normal training "
    "images, then report scores aggregated across categories. Unified "
    "multi-class, zero-shot, few-shot, and synthetic-training protocols are "
    "not comparable and must not be added to this board."
)
METRICS = (
    "Detection AUROC",
    "Segmentation AUROC",
    "Segmentation AUPRO@30% FPR",
)


def get_task(session: Session) -> DBTask:
    task = session.query(DBTask).filter(DBTask.slug == TASK_SLUG).one_or_none()
    if task is None:
        raise RuntimeError(f"Task slug={TASK_SLUG!r} not found")
    if task.id != TASK_ID:
        raise RuntimeError(f"Expected task id={TASK_ID}, found id={task.id}")
    return task


def get_source_paper(session: Session) -> DBPaper:
    paper = session.get(DBPaper, SOURCE_PAPER_ID)
    if paper is None:
        raise RuntimeError(f"Source paper id={SOURCE_PAPER_ID} not found")
    if paper.arxiv_id != SOURCE_ARXIV_ID or paper.title != SOURCE_TITLE:
        raise RuntimeError(
            f"Source paper mismatch: id={paper.id}, arxiv={paper.arxiv_id!r}, "
            f"title={paper.title!r}"
        )
    return paper


def get_metrics(session: Session) -> dict[str, int]:
    rows = session.execute(
        text(
            """
            SELECT id, name, direction
            FROM metrics
            WHERE name = ANY(:names)
            """
        ),
        {"names": list(METRICS)},
    ).all()
    by_name = {str(row.name): row for row in rows}
    missing = set(METRICS) - by_name.keys()
    if missing:
        raise RuntimeError(f"Missing metrics: {sorted(missing)}")
    wrong_direction = sorted(
        name for name, row in by_name.items() if row.direction != "higher_is_better"
    )
    if wrong_direction:
        raise RuntimeError(f"Metrics are not higher-is-better: {wrong_direction}")
    return {name: int(by_name[name].id) for name in METRICS}


def ensure_dataset(session: Session, source_paper: DBPaper) -> DBDataset:
    dataset = (
        session.query(DBDataset).filter(DBDataset.slug == DATASET_SLUG).one_or_none()
    )
    if dataset is None:
        dataset = DBDataset(slug=DATASET_SLUG)
        session.add(dataset)

    dataset.name = DATASET_NAME
    dataset.full_name = DATASET_NAME
    dataset.description = DATASET_DESCRIPTION
    dataset.short_description = DATASET_SHORT_DESCRIPTION
    dataset.url = DATASET_HOMEPAGE
    dataset.homepage = DATASET_HOMEPAGE
    dataset.variant_type = "variant"
    dataset.split_name = "Class-separated; normal-only train; standard test"
    dataset.introducing_paper_id = source_paper.id
    dataset.introducing_paper_title = source_paper.title
    dataset.introduced_year = 2021
    dataset.introduced_date = source_paper.date_published
    dataset.paper_url = f"https://paperswithcode.co/paper/{SOURCE_ARXIV_ID}"
    session.flush()
    logger.info("Upserted dataset %s (id=%s)", dataset.name, dataset.id)
    return dataset


def link_metadata(
    session: Session,
    task_id: int,
    dataset_id: int,
    paper_id: int,
    metric_ids: dict[str, int],
) -> None:
    session.execute(
        text(
            """
            INSERT INTO task_datasets (task_id, dataset_id, featured_rank, supports_harness)
            VALUES (:task_id, :dataset_id, NULL, FALSE)
            ON CONFLICT (task_id, dataset_id) DO UPDATE
            SET featured_rank = NULL, supports_harness = FALSE
            """
        ),
        {"task_id": task_id, "dataset_id": dataset_id},
    )
    session.execute(
        text(
            """
            INSERT INTO paper_tasks (paper_id, task_id, source)
            VALUES (:paper_id, :task_id, 'manual')
            ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'
            """
        ),
        {"paper_id": paper_id, "task_id": task_id},
    )
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
            "task_id": task_id,
            "dataset_id": dataset_id,
            "metric_ids": list(metric_ids.values()),
        },
    )
    for metric_id in metric_ids.values():
        session.execute(
            text(
                """
                INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
                VALUES (:task_id, :dataset_id, :metric_id)
                ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING
                """
            ),
            {"task_id": task_id, "dataset_id": dataset_id, "metric_id": metric_id},
        )


def main() -> None:
    with db_manager.session_local() as session:
        task = get_task(session)
        source_paper = get_source_paper(session)
        metric_ids = get_metrics(session)
        dataset = ensure_dataset(session, source_paper)
        link_metadata(session, task.id, dataset.id, source_paper.id, metric_ids)
        session.commit()
        logger.info(
            "%s ready: dataset_id=%s slug=%s paper_url=%s metrics=%s",
            dataset.name,
            dataset.id,
            dataset.slug,
            dataset.paper_url,
            list(METRICS),
        )


if __name__ == "__main__":
    main()
