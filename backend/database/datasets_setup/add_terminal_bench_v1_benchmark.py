"""Wire Terminal-Bench Core v1.0 into the Coding Agents task.

Terminal-Bench 1.0 (Core) is the original beta benchmark Anthropic reported on
through Claude 4 (May 2025), before Terminal-Bench 2.0 succeeded it.

Run:
    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/add_terminal_bench_v1_benchmark.py
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

TERMINAL_BENCH_ARXIV_ID = "2601.11868"
TASK_SLUG = "coding-agents"
DATASET_NAME = "Terminal Bench 1.0"
DATASET_SLUG = "terminal-bench-1-0"
DATASET_FULL_NAME = "Terminal-Bench Core (v1.0)"
DATASET_HOMEPAGE = "https://www.tbench.ai/"
DATASET_GITHUB = "https://github.com/laude-institute/terminal-bench"
PAPER_URL = f"https://paperswithcode.co/paper/{TERMINAL_BENCH_ARXIV_ID}"

DATASET_DESCRIPTION = (
    "Terminal-Bench Core (v1.0) is the original Terminal-Bench agent evaluation "
    "suite released in beta by the Laude Institute (terminal-bench-core 0.1.1). "
    "It measures whether agents can complete realistic multi-step tasks in "
    "containerized command-line environments. Anthropic reported headline scores "
    "on this version through the Claude 4 launch (May 2025) before Terminal-Bench "
    "2.0 became the primary leaderboard."
)
DATASET_SHORT_DESCRIPTION = (
    "Original Terminal-Bench Core agent benchmark (~150 active CLI tasks)."
)

METRIC_NAME = "Accuracy"


def _get_paper(session: Session) -> DBPaper:
    paper = (
        session.query(DBPaper)
        .filter(DBPaper.arxiv_id == TERMINAL_BENCH_ARXIV_ID, DBPaper.is_latest_version)
        .one_or_none()
    )
    if paper is None:
        raise RuntimeError(
            f"Terminal-Bench paper (arxiv_id={TERMINAL_BENCH_ARXIV_ID}) not found"
        )
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
            introduced_year=2025,
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
    dataset.introduced_year = dataset.introduced_year or 2025
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
        metric_id = _ensure_metric_id(session)
        _link_task_dataset(session, task.id, dataset.id)
        _link_metric(session, task.id, dataset.id, metric_id)
        _tag_source_paper(session, paper.id, task.id)
        session.commit()
        logger.info(
            "Terminal Bench 1.0 ready: dataset_id=%s task_id=%s paper_url=%s",
            dataset.id,
            task.id,
            PAPER_URL,
        )


if __name__ == "__main__":
    main()
