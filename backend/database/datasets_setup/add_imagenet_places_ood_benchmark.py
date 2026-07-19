"""Add the ImageNet-1K ID versus Places OOD benchmark from MOS.

This is the legacy MOS/MCM protocol: all 50,000 ImageNet-1K validation
images are the ID test set and a curated 10,000-image Places subset is the
OOD test set. It is not the later OpenOOD v1.5 45k-test/5k-validation split.

Run:
    uv run --env-file backend/keys.env python \
        backend/database/datasets_setup/add_imagenet_places_ood_benchmark.py
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
SOURCE_PAPER_ID = 5641
SOURCE_ARXIV_ID = "2105.01879"
SOURCE_TITLE = (
    "MOS: Towards Scaling Out-of-distribution Detection for Large Semantic Space"
)

DATASET_ID = 1224
DATASET_NAME = "ImageNet-1K vs Places OOD (MOS protocol)"
DATASET_SLUG = "imagenet-1k-vs-places-ood"
DATASET_HOMEPAGE = "https://github.com/deeplearning-wisc/large_scale_ood"
DATASET_SHORT_DESCRIPTION = (
    "MOS/MCM evaluation using all 50,000 ImageNet-1K validation images as ID "
    "and the curated 10,000-image Places subset as OOD."
)
DATASET_DESCRIPTION = (
    "Out-of-distribution detection under the fixed large-scale protocol "
    "introduced by MOS and subsequently used by MCM-style evaluations. The ID "
    "test set is the complete 50,000-image ImageNet-1K validation split, and "
    "the OOD test set is the curated 10,000-image Places subset released for "
    "this protocol, giving 60,000 scored images for the pair. Scores using "
    "OpenOOD v1.5's 45,000-image ID test and 5,000-image ID validation split, "
    "a different Places subset, another ID dataset, another OOD component, or "
    "an aggregate over multiple OOD datasets are not comparable and must not "
    "be added. Each row must identify its checkpoint and backbone, plus any "
    "outlier-exposure or auxiliary-training data, in the model metadata."
)
DATASET_WARNING = (
    "Legacy MOS/MCM full-50k protocol—not OpenOOD v1.5. Only report results "
    "using all 50,000 ImageNet-1K validation images and the curated 10,000-image "
    "MOS Places subset; do not mix in OpenOOD's 45k-test/5k-validation results."
)
METRICS = {
    "FPR95": {
        "full_name": "False Positive Rate at 95% True Positive Rate",
        "direction": "lower_is_better",
        "description": (
            "False-positive rate when the true-positive rate is 95%, reported "
            "as a percentage."
        ),
    },
    "AUROC": {
        "full_name": "Area Under the Receiver Operating Characteristic Curve",
        "direction": "higher_is_better",
        "description": (
            "Area under the ROC curve for separating ImageNet-1K ID samples "
            "from Places OOD samples, reported as a percentage."
        ),
    },
}


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


def ensure_metrics(session: Session) -> dict[str, int]:
    metric_ids: dict[str, int] = {}
    for name, spec in METRICS.items():
        row = session.execute(
            text("SELECT id, direction FROM metrics WHERE name = :name"),
            {"name": name},
        ).one_or_none()
        if row is None:
            row = session.execute(
                text(
                    """
                    INSERT INTO metrics (
                        name, full_name, direction, description, scale
                    )
                    VALUES (
                        :name, :full_name, :direction, :description, 'percentage'
                    )
                    RETURNING id, direction
                    """
                ),
                {"name": name, **spec},
            ).one()
        if row.direction != spec["direction"]:
            raise RuntimeError(
                f"Metric {name!r} direction={row.direction!r}, "
                f"expected {spec['direction']!r}"
            )
        metric_ids[name] = int(row.id)
    return metric_ids


def ensure_dataset(session: Session, source_paper: DBPaper) -> DBDataset:
    dataset = (
        session.query(DBDataset).filter(DBDataset.slug == DATASET_SLUG).one_or_none()
    )
    if dataset is None:
        raise RuntimeError(
            f"Expected existing dataset id={DATASET_ID}, slug={DATASET_SLUG!r}"
        )
    if dataset.id != DATASET_ID:
        raise RuntimeError(
            f"Expected dataset id={DATASET_ID}, found id={dataset.id} for "
            f"slug={DATASET_SLUG!r}"
        )

    dataset.name = DATASET_NAME
    dataset.full_name = DATASET_NAME
    dataset.description = DATASET_DESCRIPTION
    dataset.short_description = DATASET_SHORT_DESCRIPTION
    dataset.url = DATASET_HOMEPAGE
    dataset.homepage = DATASET_HOMEPAGE
    dataset.variant_type = "variant"
    dataset.split_name = (
        "ImageNet-1K validation (all 50,000 ID images); "
        "MOS curated Places subset (10,000 OOD images)"
    )
    dataset.warning = DATASET_WARNING
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
        metric_ids = ensure_metrics(session)
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
