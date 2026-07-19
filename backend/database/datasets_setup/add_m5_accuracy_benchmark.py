"""Add the M5 Accuracy benchmark to Time-series forecasting.

Run:
    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/add_m5_accuracy_benchmark.py
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

TASK_SLUG = "time-series-forecasting"

SOURCE_URL = "https://doi.org/10.1016/j.ijforecast.2021.11.013"
SOURCE_URL_ALTERNATES = (
    SOURCE_URL,
    "https://www.sciencedirect.com/science/article/pii/S0169207021001874",
)
SOURCE_TITLE = "M5 accuracy competition: Results, findings, and conclusions"
SOURCE_AUTHORS = [
    "Spyros Makridakis",
    "Evangelos Spiliotis",
    "Vassilios Assimakopoulos",
]
SOURCE_DATE = date(2022, 10, 1)
SOURCE_ABSTRACT = (
    'In this study, we present the results of the M5 "Accuracy" competition, '
    "which was the first of two parallel challenges in the latest M competition "
    "with the aim of advancing the theory and practice of forecasting. The main "
    'objective in the M5 "Accuracy" competition was to accurately predict '
    "42,840 time series representing the hierarchical unit sales for the largest "
    "retail company in the world by revenue, Walmart. The competition required "
    "the submission of 30,490 point forecasts for the lowest cross-sectional "
    "aggregation level of the data, which could then be summed up accordingly to "
    "estimate forecasts for the remaining upward levels. We provide details of "
    'the implementation of the M5 "Accuracy" challenge, as well as the results '
    "and best performing methods, and summarize the major findings and "
    "conclusions. Finally, we discuss the implications of these findings and "
    "suggest directions for future research."
)
SOURCE_REPOSITORY = "https://github.com/Mcompetitions/M5-methods"

DATASET_NAME = "M5 Accuracy"
DATASET_SLUG = "m5-accuracy"
DATASET_FULL_NAME = "M5 Forecasting Competition - Accuracy"
DATASET_HOMEPAGE = "https://www.kaggle.com/competitions/m5-forecasting-accuracy"
DATASET_REPOSITORY = SOURCE_REPOSITORY
DATASET_DESCRIPTION = (
    "M5 Accuracy is the point-forecasting track of the M5 Forecasting "
    "Competition. It evaluates forecasts for 42,840 hierarchical Walmart unit "
    "sales time series, requiring 30,490 bottom-level point forecasts that are "
    "aggregated across the hierarchy. The official overall leaderboard ranks "
    "methods with Weighted Root Mean Squared Scaled Error (WRMSSE), where lower "
    "scores are better."
)
DATASET_SHORT_DESCRIPTION = (
    "Point-forecasting benchmark for hierarchical Walmart retail sales time "
    "series from the M5 Forecasting Competition."
)

METRIC_NAME = "WRMSSE"
METRIC_FULL_NAME = "Weighted Root Mean Squared Scaled Error"
METRIC_DIRECTION = "lower_is_better"
METRIC_SCALE = "unbounded"
METRIC_DESCRIPTION = (
    "Weighted Root Mean Squared Scaled Error, the official overall accuracy "
    "metric for the M5 Accuracy competition; lower scores indicate more "
    "accurate forecasts."
)


def paper_url(paper: DBPaper) -> str:
    if paper.arxiv_id:
        return f"https://paperswithcode.co/paper/{paper.arxiv_id}"
    return f"https://paperswithcode.co/paper/{paper.id}"


def get_task(session: Session) -> DBTask:
    task = session.query(DBTask).filter(DBTask.slug == TASK_SLUG).one_or_none()
    if task is None:
        raise RuntimeError(f"Task slug={TASK_SLUG!r} not found")
    return task


def ensure_source_paper(session: Session) -> tuple[DBPaper, bool]:
    paper = (
        session.query(DBPaper)
        .filter(
            DBPaper.source == "external", DBPaper.source_url.in_(SOURCE_URL_ALTERNATES)
        )
        .order_by(DBPaper.id)
        .first()
    )
    if paper is not None:
        return paper, False

    paper = (
        session.query(DBPaper)
        .filter(
            DBPaper.source == "external",
            DBPaper.title.ilike(SOURCE_TITLE),
        )
        .order_by(DBPaper.id)
        .first()
    )
    if paper is not None:
        return paper, False

    result = ExternalResourceService(session).add_external_resource(
        ExternalResourceInput(
            source_url=SOURCE_URL,
            title=SOURCE_TITLE,
            abstract=SOURCE_ABSTRACT,
            authors=SOURCE_AUTHORS,
            date_published=SOURCE_DATE,
            github_repository_urls=[SOURCE_REPOSITORY],
        )
    )
    paper = session.query(DBPaper).filter(DBPaper.id == int(result.paper.id)).one()
    return paper, True


def ensure_dataset(session: Session, source_paper: DBPaper) -> tuple[DBDataset, bool]:
    dataset = (
        session.query(DBDataset)
        .filter(
            (DBDataset.slug == DATASET_SLUG)
            | (DBDataset.name.ilike(DATASET_NAME))
            | (DBDataset.full_name.ilike(DATASET_FULL_NAME))
            | (DBDataset.name.ilike("M5 Forecasting Competition"))
        )
        .order_by(DBDataset.id)
        .first()
    )
    created = dataset is None
    if dataset is None:
        dataset = DBDataset(name=DATASET_NAME, slug=DATASET_SLUG)
        session.add(dataset)
        session.flush()

    native_paper_url = paper_url(source_paper)
    dataset.name = DATASET_NAME
    dataset.slug = DATASET_SLUG
    dataset.full_name = DATASET_FULL_NAME
    dataset.description = DATASET_DESCRIPTION
    dataset.short_description = DATASET_SHORT_DESCRIPTION
    dataset.url = DATASET_REPOSITORY
    dataset.homepage = DATASET_HOMEPAGE
    dataset.paper_url = native_paper_url
    dataset.introducing_paper_id = source_paper.id
    dataset.introducing_paper_title = source_paper.title
    dataset.introduced_date = SOURCE_DATE
    dataset.introduced_year = SOURCE_DATE.year
    dataset.modalities = ["Time Series"]
    session.flush()
    return dataset, created


def ensure_metric(session: Session) -> tuple[int, bool]:
    row = (
        session.execute(
            text(
                """
            SELECT id, direction, full_name, scale, description
            FROM metrics
            WHERE lower(name) = lower(:name)
            """
            ),
            {"name": METRIC_NAME},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        metric_id = session.execute(
            text(
                """
                INSERT INTO metrics (name, full_name, direction, scale, description)
                VALUES (:name, :full_name, :direction, :scale, :description)
                RETURNING id
                """
            ),
            {
                "name": METRIC_NAME,
                "full_name": METRIC_FULL_NAME,
                "direction": METRIC_DIRECTION,
                "scale": METRIC_SCALE,
                "description": METRIC_DESCRIPTION,
            },
        ).scalar_one()
        return int(metric_id), True

    metric_id = int(row["id"])
    updates: dict[str, str | int] = {"id": metric_id}
    assignments = []
    if row["direction"] != METRIC_DIRECTION:
        assignments.append("direction = :direction")
        updates["direction"] = METRIC_DIRECTION
    if not row["full_name"]:
        assignments.append("full_name = :full_name")
        updates["full_name"] = METRIC_FULL_NAME
    if not row["scale"]:
        assignments.append("scale = :scale")
        updates["scale"] = METRIC_SCALE
    if not row["description"]:
        assignments.append("description = :description")
        updates["description"] = METRIC_DESCRIPTION
    if assignments:
        session.execute(
            text(f"UPDATE metrics SET {', '.join(assignments)} WHERE id = :id"),
            updates,
        )
    return metric_id, False


def ensure_task_dataset(session: Session, task_id: int, dataset_id: int) -> None:
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


def ensure_task_dataset_metric(
    session: Session, task_id: int, dataset_id: int, metric_id: int
) -> None:
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


def tag_source_paper(session: Session, paper_id: int, task_id: int) -> None:
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


def main() -> None:
    session = db_manager.session_local()
    try:
        task = get_task(session)
        source_paper, paper_created = ensure_source_paper(session)
        dataset, dataset_created = ensure_dataset(session, source_paper)
        metric_id, metric_created = ensure_metric(session)
        ensure_task_dataset(session, task.id, dataset.id)
        ensure_task_dataset_metric(session, task.id, dataset.id, metric_id)
        tag_source_paper(session, source_paper.id, task.id)
        session.commit()
        logger.info(
            "M5 Accuracy ready: dataset_id=%s slug=%s dataset_created=%s "
            "paper_id=%s paper_created=%s metric_id=%s metric_created=%s "
            "native_paper_url=%s",
            dataset.id,
            dataset.slug,
            dataset_created,
            source_paper.id,
            paper_created,
            metric_id,
            metric_created,
            paper_url(source_paper),
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
