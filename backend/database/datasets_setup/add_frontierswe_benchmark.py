"""Wire FrontierSWE into the Coding Agents task.

FrontierSWE benchmarks coding agents on ultra-long-horizon software engineering
tasks spanning implementation, performance optimization, and ML research.
Leaderboard source: https://www.frontierswe.com/

Run:
    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/add_frontierswe_benchmark.py
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

SOURCE_URL = "https://www.frontierswe.com/"
SOURCE_TITLE = "FrontierSWE"
SOURCE_DATE = date(2026, 6, 1)
SOURCE_AUTHORS = ["Proximal Labs"]
SOURCE_ABSTRACT = (
    "FrontierSWE benchmarks coding agents on the hardest ultra-long-horizon "
    "technical challenges collected with partners from academia and industry. "
    "Tasks span implementation (reimplementing complex systems), performance "
    "optimization (speedups without breaking correctness), and research "
    "(designing and training ML models on held-out data). Models are ranked by "
    "mean average position across tasks (lower is better) and dominance win rate "
    "against a random opponent."
)

TASK_SLUG = "coding-agents"
DATASET_NAME = "FrontierSWE"
DATASET_SLUG = "frontierswe"
DATASET_FULL_NAME = "FrontierSWE"
DATASET_SHORT_DESCRIPTION = (
    "Ultra-long-horizon coding-agent benchmark across implementation, "
    "performance, and research tasks."
)
DATASET_DESCRIPTION = (
    "FrontierSWE evaluates frontier coding agents on 17 expert-crafted tasks "
    "that sit at the edge of human software engineering ability. Implementation "
    "tasks require building or reimplementing complex systems; performance tasks "
    "optimize speed or compression without breaking behavior; research tasks "
    "require designing and training ML models on held-out evaluation data. "
    "The headline leaderboard reports mean@5 average rank across tasks (lower "
    "is better) and dominance (win rate vs a random opponent)."
)
HOMEPAGE = SOURCE_URL
GITHUB = "https://github.com/Proximal-Labs/frontier-swe"

RANK_METRIC = "Average Rank"
DOMINANCE_METRIC = "Dominance"


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
    dataset.homepage = HOMEPAGE
    dataset.paper_url = paper_url
    dataset.introducing_paper_id = paper.id
    dataset.introducing_paper_title = paper.title
    dataset.introduced_year = dataset.introduced_year or SOURCE_DATE.year
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
            VALUES (:n, :direction, :full, 'unbounded', :desc)
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
        rank_metric_id = _ensure_metric(
            session,
            RANK_METRIC,
            "lower_is_better",
            "Mean average position across FrontierSWE tasks (lower is better).",
        )
        dominance_metric_id = _ensure_metric(
            session,
            DOMINANCE_METRIC,
            "higher_is_better",
            "Win rate against a random opponent on each task, reported as a percentage.",
        )
        _link_task_dataset(session, task.id, dataset.id)
        _link_metric(session, task.id, dataset.id, rank_metric_id)
        _link_metric(session, task.id, dataset.id, dominance_metric_id)
        _tag_source_paper(session, paper.id, task.id)
        session.commit()
        logger.info(
            "FrontierSWE ready: dataset_id=%s task_id=%s paper_url=%s",
            dataset.id,
            task.id,
            _paper_url(paper),
        )


if __name__ == "__main__":
    main()
