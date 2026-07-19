"""Add the standard frame-level UCSD Ped2 video anomaly benchmark.

Run:
    uv run --env-file backend/keys.env python \
        backend/database/datasets_setup/add_ucsd_ped2_frame_benchmark.py
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import Dataset as DBDataset
from backend.models.database import Paper as DBPaper
from backend.models.database import Task as DBTask
from backend.services.external_resource_service import (
    ExternalResourceInput,
    ExternalResourceService,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

TASK_ID = 317
TASK_SLUG = "anomaly-detection"

SOURCE_TITLE = "Anomaly Detection in Crowded Scenes"
SOURCE_URL = "https://doi.org/10.1109/CVPR.2010.5539872"
SOURCE_DATE = date(2010, 6, 13)
SOURCE_AUTHORS = [
    "Vijay Mahadevan",
    "Weixin Li",
    "Viral Bhalodia",
    "Nuno Vasconcelos",
]
SOURCE_ABSTRACT = (
    "Presents a localized video representation for crowded-scene anomaly "
    "detection that jointly models appearance and dynamics with mixtures of "
    "dynamic textures, and introduces the UCSD Anomaly Detection Dataset with "
    "frame-level and pixel-level ground truth."
)
SOURCE_PDF = "https://iacl.ece.jhu.edu/proceedings/cvpr2010/papers/2009.pdf"

DATASET_NAME = "UCSD Ped2 (Standard Frame-Level)"
DATASET_SLUG = "ucsd-ped2-standard-frame-level"
DATASET_HOMEPAGE = "https://www.svcl.ucsd.edu/projects/anomaly/"
DATASET_SHORT_DESCRIPTION = (
    "Standard UCSD Ped2 test set evaluated using one frame-level anomaly score."
)
DATASET_DESCRIPTION = (
    "Video anomaly detection on the standard UCSD Ped2 split. Models learn "
    "normal pedestrian behavior from the 16 training clips and output one "
    "anomaly score per frame on the 12 test clips; performance is the standard "
    "frame-level ROC AUC. Pixel-level AUC, skeleton-only, zero-shot "
    "pseudo-anomaly, and cross-domain protocols are not comparable and must "
    "not be added to this board."
)
METRIC_NAME = "Frame AUC"


def get_task(session: Session) -> DBTask:
    task = session.query(DBTask).filter(DBTask.slug == TASK_SLUG).one_or_none()
    if task is None:
        raise RuntimeError(f"Task slug={TASK_SLUG!r} not found")
    if task.id != TASK_ID:
        raise RuntimeError(f"Expected task id={TASK_ID}, found id={task.id}")
    return task


def ensure_source_paper(session: Session) -> DBPaper:
    paper = (
        session.query(DBPaper)
        .filter(
            DBPaper.source == "external",
            (DBPaper.source_url == SOURCE_URL) | (DBPaper.title == SOURCE_TITLE),
        )
        .order_by(DBPaper.id)
        .first()
    )
    if paper is None:
        result = ExternalResourceService(session).add_external_resource(
            ExternalResourceInput(
                source_url=SOURCE_URL,
                title=SOURCE_TITLE,
                abstract=SOURCE_ABSTRACT,
                authors=SOURCE_AUTHORS,
                date_published=SOURCE_DATE,
            )
        )
        paper = session.get(DBPaper, int(result.paper.id))
        if paper is None:
            raise RuntimeError("Failed to reload the UCSD source paper")
        logger.info("Created external source paper id=%s", paper.id)

    paper.proceeding = "CVPR 2010"
    paper.conference = "CVPR"
    paper.conference_url_abs = SOURCE_URL
    paper.conference_url_pdf = SOURCE_PDF
    return paper


def get_metric_id(session: Session) -> int:
    row = session.execute(
        text("SELECT id, direction FROM metrics WHERE name = :name"),
        {"name": METRIC_NAME},
    ).one_or_none()
    if row is None:
        raise RuntimeError(f"Metric {METRIC_NAME!r} not found")
    if row.direction != "higher_is_better":
        raise RuntimeError(f"Metric {METRIC_NAME!r} is not higher-is-better")
    return int(row.id)


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
    dataset.split_name = "Ped2 standard test; frame-level scoring"
    dataset.introducing_paper_id = source_paper.id
    dataset.introducing_paper_title = source_paper.title
    dataset.introduced_year = 2010
    dataset.introduced_date = SOURCE_DATE
    dataset.paper_url = f"https://paperswithcode.co/paper/{source_paper.id}"
    session.flush()
    logger.info("Upserted dataset %s (id=%s)", dataset.name, dataset.id)
    return dataset


def link_metadata(
    session: Session, task_id: int, dataset_id: int, paper_id: int, metric_id: int
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
              AND metric_id != :metric_id
            """
        ),
        {"task_id": task_id, "dataset_id": dataset_id, "metric_id": metric_id},
    )
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
        source_paper = ensure_source_paper(session)
        metric_id = get_metric_id(session)
        dataset = ensure_dataset(session, source_paper)
        link_metadata(session, task.id, dataset.id, source_paper.id, metric_id)
        session.commit()
        logger.info(
            "%s ready: dataset_id=%s slug=%s paper_url=%s metric=%s",
            dataset.name,
            dataset.id,
            dataset.slug,
            dataset.paper_url,
            METRIC_NAME,
        )


if __name__ == "__main__":
    main()
