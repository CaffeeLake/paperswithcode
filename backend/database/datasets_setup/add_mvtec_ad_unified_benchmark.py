"""Add the unified multi-class MVTec AD anomaly-detection benchmark.

This board is deliberately restricted to methods that train one model across
all 15 MVTec AD categories using only normal training images and evaluate on
the standard test set. Category-specific models and zero/few-shot protocols
are not comparable and belong on separate boards.

Source paper: MVTec AD -- A Comprehensive Real-World Dataset for Unsupervised
Anomaly Detection (CVPR 2019).

Run:
    uv run --env-file backend/keys.env python \
        backend/database/datasets_setup/add_mvtec_ad_unified_benchmark.py
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
    "MVTec AD -- A Comprehensive Real-World Dataset for Unsupervised Anomaly Detection"
)
SOURCE_URL = (
    "https://openaccess.thecvf.com/content_CVPR_2019/html/"
    "Bergmann_MVTec_AD_--_A_Comprehensive_Real-World_Dataset_for_"
    "Unsupervised_Anomaly_CVPR_2019_paper.html"
)
SOURCE_DATE = date(2019, 6, 16)
SOURCE_AUTHORS = [
    "Paul Bergmann",
    "Michael Fauser",
    "David Sattlegger",
    "Carsten Steger",
]
SOURCE_ABSTRACT = (
    "Introduces MVTec AD, a real-world industrial anomaly-detection dataset "
    "with 5,354 high-resolution images across object and texture categories. "
    "Training images are defect-free; the test data contains more than 70 "
    "defect types with pixel-precise anomaly annotations."
)

DATASET_NAME = "MVTec AD (Unified Multi-Class)"
DATASET_SLUG = "mvtec-ad-unified-multi-class"
DATASET_HOMEPAGE = "https://www.mvtec.com/research-teaching/datasets/mvtec-ad"
DATASET_SHORT_DESCRIPTION = (
    "One normal-only model trained jointly across all MVTec AD categories and "
    "evaluated on the standard test set."
)
DATASET_DESCRIPTION = (
    "Unified multi-class anomaly detection and localization on the standard "
    "MVTec AD test set. Eligible results train one shared model jointly across "
    "all 15 categories using only the normal training images. Scores aggregate "
    "over all categories. Category-specific per-class models and zero-shot or "
    "few-shot protocols are not comparable and must not be added to this board."
)
METRICS = (
    "Detection AUROC",
    "Detection AP",
    "Detection F1-max",
    "Segmentation AUROC",
    "Segmentation AP",
    "Segmentation F1-max",
    "Segmentation AUPRO@30% FPR",
)


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
            raise RuntimeError("Failed to reload the MVTec AD source paper")
        logger.info("Created external source paper id=%s", paper.id)

    paper.proceeding = "CVPR 2019"
    paper.conference = "CVPR"
    paper.conference_url_abs = SOURCE_URL
    paper.conference_url_pdf = SOURCE_URL.replace("/html/", "/papers/").replace(
        "_paper.html", "_paper.pdf"
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
    dataset.split_name = "Unified multi-class; normal-only train; standard test"
    dataset.introducing_paper_id = source_paper.id
    dataset.introducing_paper_title = source_paper.title
    dataset.introduced_year = 2019
    dataset.introduced_date = SOURCE_DATE
    dataset.license_name = "CC BY-NC-SA 4.0"
    dataset.license_url = "https://creativecommons.org/licenses/by-nc-sa/4.0/"
    dataset.paper_url = f"https://paperswithcode.co/paper/{source_paper.id}"
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
        source_paper = ensure_source_paper(session)
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
