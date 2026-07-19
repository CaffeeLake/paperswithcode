"""Add the standard frame-level ShanghaiTech Campus VAD benchmark.

This board is distinct from the ShanghaiTech crowd-counting datasets. Its
source is the ICCV 2017 paper that introduced the ShanghaiTech Campus anomaly
detection dataset.

Run:
    uv run --env-file backend/keys.env python \
        backend/database/datasets_setup/add_shanghaitech_vad_benchmark.py
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

SOURCE_TITLE = (
    "A Revisit of Sparse Coding Based Anomaly Detection in Stacked RNN Framework"
)
SOURCE_URL = "https://doi.org/10.1109/ICCV.2017.45"
SOURCE_DATE = date(2017, 10, 22)
SOURCE_AUTHORS = ["Weixin Luo", "Wen Liu", "Shenghua Gao"]
SOURCE_ABSTRACT = (
    "Introduces temporally coherent sparse coding and a stacked recurrent "
    "network for video anomaly detection, together with the ShanghaiTech "
    "Campus dataset: 13 scenes, more than 270,000 training frames, 130 "
    "abnormal events, and pixel-level annotations."
)
SOURCE_PDF = (
    "https://openaccess.thecvf.com/content_ICCV_2017/papers/"
    "Luo_A_Revisit_of_ICCV_2017_paper.pdf"
)

DATASET_NAME = "ShanghaiTech Video Anomaly Detection (Standard Frame-Level)"
DATASET_SLUG = "shanghaitech-video-anomaly-detection-standard-frame-level"
DATASET_HOMEPAGE = "https://svip-lab.github.io/dataset/campus_dataset.html"
DATASET_SHORT_DESCRIPTION = (
    "Standard ShanghaiTech Campus VAD train/test split evaluated with a "
    "frame-level anomaly score."
)
DATASET_DESCRIPTION = (
    "Video anomaly detection on the original ShanghaiTech Campus benchmark: "
    "normal-only training videos from 13 scenes and the standard test videos "
    "containing normal and anomalous frames. Eligible methods output one "
    "anomaly score per frame and report the standard frame-level ROC AUC. "
    "ShanghaiTech-HR, skeleton-only, cross-domain, and custom C-ShT protocols "
    "are not comparable and must not be added to this board. This dataset is "
    "unrelated to the ShanghaiTech Part A/B crowd-counting datasets."
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
            raise RuntimeError("Failed to reload the ShanghaiTech source paper")
        logger.info("Created external source paper id=%s", paper.id)

    paper.proceeding = "ICCV 2017"
    paper.conference = "ICCV"
    paper.conference_url_abs = SOURCE_URL
    paper.conference_url_pdf = SOURCE_PDF
    return paper


def ensure_metric(session: Session) -> int:
    row = session.execute(
        text("SELECT id, direction FROM metrics WHERE name = :name"),
        {"name": METRIC_NAME},
    ).first()
    if row is None:
        row = session.execute(
            text(
                """
                INSERT INTO metrics (name, full_name, direction, description, scale)
                VALUES (
                    :name,
                    'Frame-level Area Under the ROC Curve',
                    'higher_is_better',
                    'Frame-level ROC AUC on the standard video anomaly detection test set, reported as a percentage.',
                    'percentage'
                )
                RETURNING id, direction
                """
            ),
            {"name": METRIC_NAME},
        ).one()
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
    dataset.split_name = "Standard train/test; frame-level scoring"
    dataset.introducing_paper_id = source_paper.id
    dataset.introducing_paper_title = source_paper.title
    dataset.introduced_year = 2017
    dataset.introduced_date = SOURCE_DATE
    dataset.paper_url = f"https://paperswithcode.co/paper/{source_paper.id}"
    session.flush()
    if dataset.id in (770, 771):
        raise RuntimeError("Refusing to reuse a ShanghaiTech crowd-counting dataset")
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
        metric_id = ensure_metric(session)
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
