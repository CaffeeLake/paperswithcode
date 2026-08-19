"""Add the official Tanks and Temples MVS reconstruction benchmark.

This is the image-based multi-view stereo / point-cloud reconstruction
protocol from Knapitsch et al. (ACM TOG 2017), with F-score leaderboards on
the Intermediate and Advanced scene sets. It is intentionally distinct from:

- ``tanks-and-temples-6`` (six-scene PSNR/SSIM on 3d-understanding)
- ``tanks-and-temples-train-truck-nvs`` (Train + Truck novel-view synthesis)

The introducing paper is the original Tanks and Temples benchmark paper, indexed
as a local external paper from its canonical DOI.

Run:
    uv run --env-file backend/keys.env python \
        backend/database/datasets_setup/add_tanks_and_temples_mvs_benchmark.py
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

TASK_SLUG = "3d-reconstruction"
SOURCE_PAPER_ID = 103909

DATASET_NAME = "Tanks and Temples"
DATASET_SLUG = "tanks-and-temples"
DATASET_HOMEPAGE = "https://www.tanksandtemples.org/"
DATASET_SHORT_DESCRIPTION = (
    "Large-scale image-based 3D reconstruction benchmark with laser-scanned "
    "ground truth."
)
DATASET_DESCRIPTION = (
    "The official Tanks and Temples benchmark for image-based multi-view stereo "
    "and large-scale scene reconstruction. Methods are evaluated with the "
    "benchmark F-score (precision-recall F1 at a fixed distance threshold) on "
    "held-out test scenes. Leaderboards report the mean F-score across the "
    "Intermediate and Advanced scene sets; these MVS reconstruction scores are "
    "not comparable to the six-scene PSNR/SSIM protocol or the Train + Truck "
    "novel-view-synthesis protocol derived from the same dataset."
)

METRIC_SPECS = {
    "Mean F1 (Intermediate)": {
        "direction": "higher_is_better",
        "full_name": "Mean F1 (Intermediate)",
        "scale": "0-100",
        "description": (
            "Mean F-score across the Tanks and Temples Intermediate test scenes "
            "for multi-view stereo reconstruction; reported as a percentage."
        ),
    },
    "Mean F1 (Advanced)": {
        "direction": "higher_is_better",
        "full_name": "Mean F1 (Advanced)",
        "scale": "0-100",
        "description": (
            "Mean F-score across the Tanks and Temples Advanced test scenes for "
            "multi-view stereo reconstruction; reported as a percentage."
        ),
    },
}

PRIMARY_METRIC = "Mean F1 (Intermediate)"
SECONDARY_METRICS = ("Mean F1 (Advanced)",)


def get_task(session: Session) -> DBTask:
    task = session.query(DBTask).filter(DBTask.slug == TASK_SLUG).one_or_none()
    if task is None:
        raise RuntimeError(f"Task slug={TASK_SLUG!r} not found")
    return task


def get_source_paper(session: Session) -> DBPaper:
    paper = session.get(DBPaper, SOURCE_PAPER_ID)
    if paper is None:
        raise RuntimeError(f"Source paper id={SOURCE_PAPER_ID} not found")
    return paper


def ensure_metric(session: Session, name: str) -> int:
    row = session.execute(
        text("SELECT id FROM metrics WHERE name = :n"), {"n": name}
    ).fetchone()
    if row:
        return int(row[0])

    spec = METRIC_SPECS[name]
    metric_id = session.execute(
        text(
            """
            INSERT INTO metrics (name, direction, full_name, scale, description)
            VALUES (:name, :direction, :full_name, :scale, :description)
            RETURNING id
            """
        ),
        {"name": name, **spec},
    ).scalar_one()
    logger.info("Created metric %s (id=%s)", name, metric_id)
    return int(metric_id)


def ensure_dataset(session: Session, source_paper: DBPaper) -> DBDataset:
    dataset = (
        session.query(DBDataset).filter(DBDataset.slug == DATASET_SLUG).one_or_none()
    )
    native_paper_url = f"https://paperswithcode.co/paper/{source_paper.id}"
    if dataset is None:
        dataset = DBDataset(slug=DATASET_SLUG)
        session.add(dataset)

    dataset.name = DATASET_NAME
    dataset.full_name = DATASET_NAME
    dataset.description = DATASET_DESCRIPTION
    dataset.short_description = DATASET_SHORT_DESCRIPTION
    dataset.url = DATASET_HOMEPAGE
    dataset.homepage = DATASET_HOMEPAGE
    dataset.introducing_paper_id = source_paper.id
    dataset.introducing_paper_title = source_paper.title
    dataset.introduced_year = 2017
    dataset.paper_url = native_paper_url
    session.flush()
    logger.info("Upserted dataset %s (id=%s)", dataset.name, dataset.id)
    return dataset


def link_metadata(
    session: Session,
    task_id: int,
    dataset_id: int,
    source_paper_id: int,
    metric_ids: dict[str, int],
) -> None:
    session.execute(
        text(
            """
            INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
            VALUES (:task_id, :dataset_id, FALSE)
            ON CONFLICT (task_id, dataset_id) DO NOTHING
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
        {"paper_id": source_paper_id, "task_id": task_id},
    )
    for metric_name in (PRIMARY_METRIC, *SECONDARY_METRICS):
        session.execute(
            text(
                """
                INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
                VALUES (:task_id, :dataset_id, :metric_id)
                ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING
                """
            ),
            {
                "task_id": task_id,
                "dataset_id": dataset_id,
                "metric_id": metric_ids[metric_name],
            },
        )


def main() -> None:
    with db_manager.session_local() as session:
        task = get_task(session)
        source_paper = get_source_paper(session)
        metric_ids = {name: ensure_metric(session, name) for name in METRIC_SPECS}
        dataset = ensure_dataset(session, source_paper)
        link_metadata(session, task.id, dataset.id, source_paper.id, metric_ids)
        session.commit()
        logger.info(
            "%s ready: dataset_id=%s paper_url=%s primary_metric=%s metrics=%s",
            dataset.name,
            dataset.id,
            dataset.paper_url,
            PRIMARY_METRIC,
            list(METRIC_SPECS),
        )


if __name__ == "__main__":
    main()
