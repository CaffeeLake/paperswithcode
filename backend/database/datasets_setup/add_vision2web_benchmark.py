"""Wire Vision2Web into the Coding Agents task.

Vision2Web evaluates multimodal coding agents on visual website development,
from static UI-to-code through interactive frontends to full-stack builds.
The introducing paper is arxiv:2603.26648.

Run:
    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/add_vision2web_benchmark.py
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

VISION2WEB_ARXIV_ID = "2603.26648"
TASK_SLUG = "coding-agents"
DATASET_NAME = "Vision2Web"
DATASET_SLUG = "vision2web"
DATASET_FULL_NAME = "Vision2Web"
DATASET_HOMEPAGE = "https://vision2web-bench.github.io/"
DATASET_GITHUB = "https://github.com/zai-org/Vision2Web"
PAPER_URL = f"https://paperswithcode.co/paper/{VISION2WEB_ARXIV_ID}"

DATASET_DESCRIPTION = (
    "Vision2Web is a hierarchical benchmark for visual website development with "
    "agent verification. Tasks span three levels: static responsive UI-to-code, "
    "interactive multi-page frontend reproduction, and long-horizon full-stack "
    "website development. The benchmark contains 193 tasks across 16 categories "
    "with 918 prototype images and 1,255 test cases curated from real-world "
    "websites. Evaluation uses workflow-based GUI agent verification plus a "
    "VLM judge, reporting functional and visual scores on a 0–100 scale."
)
DATASET_SHORT_DESCRIPTION = (
    "193-task hierarchical benchmark for visual website development."
)

METRICS = [
    (
        "Functional Score",
        "higher_is_better",
        "Pass rate over structured GUI workflow test cases (0–100).",
    ),
    (
        "Visual Score",
        "higher_is_better",
        "VLM-judged visual fidelity against UI prototypes (0–100).",
    ),
]


def _get_paper(session: Session) -> DBPaper:
    paper = (
        session.query(DBPaper)
        .filter(
            DBPaper.arxiv_id == VISION2WEB_ARXIV_ID,
            DBPaper.is_latest_version,
        )
        .one_or_none()
    )
    if paper is None:
        raise RuntimeError(
            f"Vision2Web paper {VISION2WEB_ARXIV_ID!r} not found; import it first"
        )
    logger.info("Reusing paper id=%s title=%r", paper.id, paper.title)
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
            url=DATASET_GITHUB,
            homepage=DATASET_HOMEPAGE,
            paper_url=PAPER_URL,
            introducing_paper_id=paper.id,
            introducing_paper_title=paper.title,
            introduced_year=2026,
        )
        session.add(dataset)
        session.flush()
        logger.info("Created dataset %r (id=%s)", dataset.name, dataset.id)
        return dataset

    dataset.full_name = DATASET_FULL_NAME
    dataset.description = DATASET_DESCRIPTION
    dataset.short_description = DATASET_SHORT_DESCRIPTION
    dataset.url = DATASET_GITHUB
    dataset.homepage = DATASET_HOMEPAGE
    dataset.paper_url = PAPER_URL
    dataset.introducing_paper_id = paper.id
    dataset.introducing_paper_title = paper.title
    dataset.introduced_year = dataset.introduced_year or 2026
    session.flush()
    logger.info("Updated dataset %r (id=%s)", dataset.name, dataset.id)
    return dataset


def _ensure_metric(
    session: Session, name: str, direction: str, description: str
) -> int:
    row = session.execute(
        text("SELECT id FROM metrics WHERE name = :n"), {"n": name}
    ).fetchone()
    if row:
        return int(row[0])

    metric_id = session.execute(
        text(
            """
            INSERT INTO metrics (name, direction, full_name, scale, description)
            VALUES (:n, :direction, :full, '0-100', :desc)
            RETURNING id
            """
        ),
        {
            "n": name,
            "direction": direction,
            "full": name,
            "desc": description,
        },
    ).scalar_one()
    logger.info("Created metric %r (id=%s)", name, metric_id)
    return int(metric_id)


def _link_task_dataset(session: Session, task_id: int, dataset_id: int) -> None:
    session.execute(
        text(
            """
            INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
            VALUES (:task_id, :dataset_id, TRUE)
            ON CONFLICT (task_id, dataset_id) DO UPDATE
            SET supports_harness = EXCLUDED.supports_harness
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
        paper = _get_paper(session)
        task = _get_task(session)
        dataset = _ensure_dataset(session, paper)
        for name, direction, description in METRICS:
            metric_id = _ensure_metric(session, name, direction, description)
            _link_metric(session, task.id, dataset.id, metric_id)
        _link_task_dataset(session, task.id, dataset.id)
        _tag_source_paper(session, paper.id, task.id)
        session.commit()
        logger.info(
            "Vision2Web ready: dataset_id=%s task_id=%s paper_url=%s",
            dataset.id,
            task.id,
            PAPER_URL,
        )


if __name__ == "__main__":
    main()
