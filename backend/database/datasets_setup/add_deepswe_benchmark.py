"""Wire DeepSWE into the Coding Agents task.

DeepSWE measures frontier coding agents on original, long-horizon software
engineering tasks across 113 tasks and 91 repositories.
Leaderboard source: https://deepswe.datacurve.ai/

Run:
    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/add_deepswe_benchmark.py
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import (
    Dataset as DBDataset,
    Paper as DBPaper,
    Task as DBTask,
)
from backend.services.external_resource_service import (
    ExternalResourceInput,
    ExternalResourceService,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

SOURCE_URL = "https://deepswe.datacurve.ai/"
SOURCE_TITLE = "DeepSWE"
SOURCE_DATE = date(2026, 6, 14)
SOURCE_AUTHORS = ["Datacurve"]
SOURCE_ABSTRACT = (
    "DeepSWE is a long-horizon software engineering benchmark built to separate "
    "frontier coding agents on original tasks drawn from 91 active open-source "
    "repositories across TypeScript, Go, Python, JavaScript, and Rust. Tasks are "
    "written from scratch (contamination-free), use hand-written behavioral "
    "verifiers, and require substantially more code and output tokens than "
    "public SWE-style benchmarks. The headline leaderboard reports Pass@1 on "
    "113 tasks with all models evaluated through mini-swe-agent for consistency."
)

TASK_SLUG = "coding-agents"
DATASET_NAME = "DeepSWE"
DATASET_SLUG = "deepswe"
DATASET_FULL_NAME = "DeepSWE"
DATASET_SHORT_DESCRIPTION = (
    "113-task long-horizon coding-agent benchmark across 91 repositories."
)
DATASET_DESCRIPTION = (
    "DeepSWE evaluates frontier coding agents on 113 original, long-horizon "
    "software engineering tasks spanning 91 repositories in TypeScript, Go, "
    "Python, JavaScript, and Rust. Tasks are contamination-free, use behavioral "
    "verifiers rather than implementation matching, and reflect real-world "
    "complexity with shorter prompts but much larger solutions than SWE-bench Pro. "
    "All public leaderboard runs use mini-swe-agent for a consistent harness."
)
HOMEPAGE = SOURCE_URL
GITHUB = "https://github.com/datacurve-ai/deep-swe"
HF_DATASET_URL = "https://huggingface.co/datasets/datacurve/deep-swe"
METRIC_NAME = "Pass@1"


def _ensure_source_paper(session: Session) -> DBPaper:
    paper = (
        session.query(DBPaper)
        .filter(DBPaper.source == "external", DBPaper.source_url == SOURCE_URL)
        .one_or_none()
    )
    if paper is not None:
        logger.info("Reusing external paper id=%s title=%r", paper.id, paper.title)
        return paper

    result = ExternalResourceService(session).add_external_resource(
        ExternalResourceInput(
            source_url=SOURCE_URL,
            title=SOURCE_TITLE,
            abstract=SOURCE_ABSTRACT,
            authors=SOURCE_AUTHORS,
            date_published=SOURCE_DATE,
        )
    )
    paper = session.query(DBPaper).filter(DBPaper.id == int(result.paper.id)).one()
    logger.info("Created external paper id=%s", paper.id)
    return paper


def _paper_url(paper: DBPaper) -> str:
    if paper.arxiv_id:
        return f"https://paperswithcode.co/paper/{paper.arxiv_id}"
    return f"https://paperswithcode.co/paper/{paper.id}"


def _get_task(session: Session) -> DBTask:
    task = session.query(DBTask).filter(DBTask.slug == TASK_SLUG).one_or_none()
    if task is None:
        raise RuntimeError(f"Task slug={TASK_SLUG!r} not found")
    return task


def _ensure_dataset(session: Session, paper: DBPaper) -> DBDataset:
    paper_url = _paper_url(paper)
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
            url=GITHUB,
            hf_url=HF_DATASET_URL,
            homepage=HOMEPAGE,
            paper_url=paper_url,
            introducing_paper_id=paper.id,
            introducing_paper_title=paper.title,
            introduced_year=SOURCE_DATE.year,
        )
        session.add(dataset)
        session.flush()
        logger.info("Created dataset %r (id=%s)", dataset.name, dataset.id)
        return dataset

    dataset.full_name = DATASET_FULL_NAME
    dataset.description = DATASET_DESCRIPTION
    dataset.short_description = DATASET_SHORT_DESCRIPTION
    dataset.url = GITHUB
    dataset.hf_url = HF_DATASET_URL
    dataset.homepage = HOMEPAGE
    dataset.paper_url = paper_url
    dataset.introducing_paper_id = paper.id
    dataset.introducing_paper_title = paper.title
    dataset.introduced_year = dataset.introduced_year or SOURCE_DATE.year
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
            INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
            VALUES (:task_id, :dataset_id, TRUE)
            ON CONFLICT (task_id, dataset_id) DO UPDATE
            SET supports_harness = TRUE
            """
        ),
        {"task_id": task_id, "dataset_id": dataset_id},
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


def _link_hf_dataset_to_paper(session: Session, paper: DBPaper) -> None:
    ExternalResourceService(session)._set_hf_artifacts(paper.id, [HF_DATASET_URL])


def _tag_source_paper(session: Session, paper_id: int, task_id: int) -> None:
    session.execute(
        text(
            """
            INSERT INTO paper_tasks (paper_id, task_id, source)
            VALUES (:paper_id, :task_id, 'manual')
            ON CONFLICT DO NOTHING
            """
        ),
        {"paper_id": paper_id, "task_id": task_id},
    )


def main() -> None:
    with db_manager.session_local() as session:
        paper = _ensure_source_paper(session)
        task = _get_task(session)
        dataset = _ensure_dataset(session, paper)
        metric_id = _ensure_metric_id(session)
        _link_task_dataset(session, task.id, dataset.id)
        _link_metric(session, task.id, dataset.id, metric_id)
        _link_hf_dataset_to_paper(session, paper)
        _tag_source_paper(session, paper.id, task.id)
        session.commit()
        logger.info(
            "DeepSWE ready: dataset_id=%s task_id=%s paper_url=%s",
            dataset.id,
            task.id,
            _paper_url(paper),
        )


if __name__ == "__main__":
    main()
