"""Wire PubTables-1M into the Document Understanding task.

PubTables-1M (arxiv 2110.00061) is a large-scale benchmark for table detection,
structure recognition, and functional analysis from scientific PDF documents.

Run:
    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/add_pubtables_1m_benchmark.py
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

ARXIV_ID = "2110.00061"
TASK_SLUG = "document-understanding"
DATASET_NAME = "PubTables-1M"
DATASET_SLUG = "pubtables-1m"
DATASET_FULL_NAME = "PubTables-1M"
DATASET_HOMEPAGE = "https://github.com/microsoft/table-transformer"
DATASET_URL = "https://msropendata.com/datasets/505fcbe3-1333-42b1-913a-f651b8b712d3"
PAPER_URL = f"https://paperswithcode.co/paper/{ARXIV_ID}"
FEATURED_RANK = 10

DATASET_DESCRIPTION = (
    "PubTables-1M is a large-scale benchmark for table extraction from unstructured "
    "scientific documents. It contains nearly one million tables from PubMed Central "
    "Open Access articles with canonicalized annotations for table detection, cell "
    "topology, cell content, cell location, and row/column structure."
)
DATASET_SHORT_DESCRIPTION = (
    "Large-scale table extraction benchmark (~948K tables from PMCOA documents)."
)

METRIC_NAME = "F1"


def _get_paper(session: Session) -> DBPaper:
    paper = (
        session.query(DBPaper)
        .filter(DBPaper.arxiv_id == ARXIV_ID, DBPaper.is_latest_version)
        .one_or_none()
    )
    if paper is None:
        raise RuntimeError(f"Paper arxiv_id={ARXIV_ID!r} not found")
    return paper


def _get_task(session: Session) -> DBTask:
    task = session.query(DBTask).filter(DBTask.slug == TASK_SLUG).one_or_none()
    if task is None:
        raise RuntimeError(f"Task slug={TASK_SLUG!r} not found")
    return task


def _ensure_dataset(session: Session, paper: DBPaper) -> DBDataset:
    dataset = (
        session.query(DBDataset).filter(DBDataset.slug == DATASET_SLUG).one_or_none()
    )
    if dataset is None:
        dataset = DBDataset(
            name=DATASET_NAME,
            slug=DATASET_SLUG,
            full_name=DATASET_FULL_NAME,
            description=DATASET_DESCRIPTION,
            short_description=DATASET_SHORT_DESCRIPTION,
            url=DATASET_URL,
            homepage=DATASET_HOMEPAGE,
            paper_url=PAPER_URL,
            introducing_paper_id=paper.id,
            introducing_paper_title=paper.title,
            introduced_year=2021,
        )
        session.add(dataset)
        session.flush()
        logger.info("Created dataset %r (id=%s)", dataset.name, dataset.id)
        return dataset

    dataset.full_name = DATASET_FULL_NAME
    dataset.description = DATASET_DESCRIPTION
    dataset.short_description = DATASET_SHORT_DESCRIPTION
    dataset.url = DATASET_URL
    dataset.homepage = DATASET_HOMEPAGE
    dataset.paper_url = PAPER_URL
    dataset.introducing_paper_id = paper.id
    dataset.introducing_paper_title = paper.title
    dataset.introduced_year = dataset.introduced_year or 2021
    session.flush()
    logger.info("Updated dataset %r (id=%s)", dataset.name, dataset.id)
    return dataset


def _ensure_metric_id(session: Session) -> int:
    row = session.execute(
        text("SELECT id FROM metrics WHERE name = :n"), {"n": METRIC_NAME}
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Metric {METRIC_NAME!r} not found")
    return int(row[0])


def _link_task_dataset(session: Session, task_id: int, dataset_id: int) -> None:
    session.execute(
        text(
            """
            INSERT INTO task_datasets (task_id, dataset_id, featured_rank, supports_harness)
            VALUES (:task_id, :dataset_id, :featured_rank, FALSE)
            ON CONFLICT (task_id, dataset_id) DO UPDATE
            SET featured_rank = COALESCE(EXCLUDED.featured_rank, task_datasets.featured_rank)
            """
        ),
        {
            "task_id": task_id,
            "dataset_id": dataset_id,
            "featured_rank": FEATURED_RANK,
        },
    )


def _link_metric(
    session: Session, task_id: int, dataset_id: int, metric_id: int
) -> None:
    session.execute(
        text(
            """
            INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
            VALUES (:task_id, :dataset_id, :metric_id)
            ON CONFLICT DO NOTHING
            """
        ),
        {"task_id": task_id, "dataset_id": dataset_id, "metric_id": metric_id},
    )


def _tag_source_paper(session: Session, paper_id: int, task_id: int) -> None:
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
    with db_manager.session_local() as session:
        paper = _get_paper(session)
        task = _get_task(session)
        dataset = _ensure_dataset(session, paper)
        metric_id = _ensure_metric_id(session)
        _link_task_dataset(session, task.id, dataset.id)
        _link_metric(session, task.id, dataset.id, metric_id)
        _tag_source_paper(session, paper.id, task.id)
        session.commit()
        logger.info(
            "PubTables-1M ready: dataset_id=%s task_id=%s paper_url=%s",
            dataset.id,
            task.id,
            PAPER_URL,
        )


if __name__ == "__main__":
    main()
