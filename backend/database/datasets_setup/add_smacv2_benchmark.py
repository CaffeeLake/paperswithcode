"""Add the conservative SMACv2 benchmark suite row for cooperative MARL.

The source paper defines 15 race/scenario configurations, but reports their
test win rates as learning curves rather than scalar result tables. Keep one
suite leaderboard until repeatable, scenario-level scalar results are sourced.

Run:
    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/add_smacv2_benchmark.py
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import Author, Dataset, Paper, PaperAuthor, Task
from backend.services.arxiv_service import ArxivService
from backend.services.paper_service import PaperService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SOURCE_ARXIV_ID = "2212.07489"
SOURCE_URL = f"https://paperswithcode.co/paper/{SOURCE_ARXIV_ID}"
TASK_ID = 365
TASK_SLUG = "multi-agent-reinforcement-learning"
RL_TASK_SLUG = "reinforcement-learning"
METRIC_NAME = "Win Rate"
HOMEPAGE = "https://github.com/oxwhirl/smacv2"

DESCRIPTION = (
    "SMACv2 evaluates cooperative multi-agent reinforcement learning on "
    "procedurally sampled StarCraft II micromanagement scenarios with random "
    "team compositions and start positions, requiring held-out generalization "
    "to previously unseen samples from the same train/test distribution. The "
    "canonical experiments use StarCraft II 4.10. The Extended Partial "
    "Observability (EPO) protocol uses 6 allies versus 5 enemies, p=0 enemy "
    "observation sharing (only the first spotter is guaranteed visibility), "
    "and removes the available-action mask. SMACv2 results are not comparable "
    "to, and must be excluded from, fixed-map SMAC leaderboards."
)


async def ensure_source_paper(session: Session) -> Paper:
    paper = (
        session.query(Paper)
        .filter(Paper.arxiv_id == SOURCE_ARXIV_ID, Paper.is_latest_version)
        .one_or_none()
    )
    has_authors = (
        paper is not None
        and session.query(PaperAuthor).filter(PaperAuthor.paper_id == paper.id).first()
    )
    if paper is not None and has_authors:
        return paper

    metadata = await ArxivService().get_paper_metadata(SOURCE_ARXIV_ID)
    if not metadata.success:
        raise RuntimeError(
            f"Failed to fetch arXiv metadata for {SOURCE_ARXIV_ID}: "
            f"{metadata.error_message}"
        )

    if paper is None:
        paper_id = PaperService(session).add_paper(
            {
                "arxiv_id": metadata.arxiv_id,
                "title": metadata.title,
                "abstract": metadata.abstract,
                "version": metadata.version,
                "date_published": metadata.published.date()
                if metadata.published
                else None,
                "primary_category": metadata.primary_category,
                "all_categories": metadata.categories,
                "is_latest_version": True,
            }
        )
        paper = session.get(Paper, paper_id)
        if paper is None:
            raise RuntimeError(f"Failed to load imported paper {SOURCE_ARXIV_ID}")
        logger.info("Imported source paper %s (id=%s)", SOURCE_ARXIV_ID, paper.id)

    for order, author_name in enumerate(metadata.authors, start=1):
        author = session.query(Author).filter(Author.name == author_name).first()
        if author is None:
            author = Author(name=author_name)
            session.add(author)
            session.flush()
        session.execute(
            text(
                """
                INSERT INTO paper_authors (paper_id, author_id, author_order)
                VALUES (:paper_id, :author_id, :author_order)
                ON CONFLICT (paper_id, author_id) DO UPDATE
                SET author_order = EXCLUDED.author_order
                """
            ),
            {
                "paper_id": paper.id,
                "author_id": author.id,
                "author_order": order,
            },
        )
    return paper


def get_task(session: Session, slug: str, expected_id: int | None = None) -> Task:
    task = session.query(Task).filter(Task.slug == slug).one_or_none()
    if task is None:
        raise RuntimeError(f"Task {slug!r} not found")
    if expected_id is not None and task.id != expected_id:
        raise RuntimeError(f"Task {slug!r} has id={task.id}, expected {expected_id}")
    return task


def ensure_dataset(session: Session, paper: Paper) -> Dataset:
    dataset = session.query(Dataset).filter(Dataset.slug == "smacv2").one_or_none()
    if dataset is None:
        dataset = Dataset(name="SMACv2", slug="smacv2")
        session.add(dataset)
        session.flush()
        logger.info("Created SMACv2 suite dataset (id=%s)", dataset.id)
    else:
        logger.info("Repairing SMACv2 suite dataset (id=%s)", dataset.id)

    dataset.name = "SMACv2"
    dataset.full_name = (
        "SMACv2: An Improved Benchmark for Cooperative Multi-Agent "
        "Reinforcement Learning"
    )
    dataset.description = DESCRIPTION
    dataset.short_description = (
        "Procedurally generated StarCraft II scenarios for held-out cooperative "
        "multi-agent generalization."
    )
    dataset.url = HOMEPAGE
    dataset.homepage = HOMEPAGE
    dataset.parent_dataset_id = None
    dataset.variant_type = None
    dataset.paper_url = SOURCE_URL
    dataset.introducing_paper_id = paper.id
    dataset.introducing_paper_title = paper.title
    dataset.introduced_year = 2023
    session.flush()
    return dataset


def tag_paper(session: Session, paper_id: int, task_ids: list[int]) -> None:
    for task_id in task_ids:
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


def wire_leaderboard(session: Session, dataset_id: int, task_id: int) -> None:
    metric_id = session.execute(
        text("SELECT id FROM metrics WHERE name = :name"), {"name": METRIC_NAME}
    ).scalar_one()
    session.execute(
        text(
            """
            INSERT INTO task_datasets (
                task_id, dataset_id, featured_rank, supports_harness
            )
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
            DELETE FROM task_dataset_metrics
            WHERE task_id = :task_id AND dataset_id = :dataset_id
              AND metric_id <> :metric_id
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


async def main() -> None:
    with db_manager.session_local() as session:
        marl_task = get_task(session, TASK_SLUG, TASK_ID)
        rl_task = get_task(session, RL_TASK_SLUG)
        paper = await ensure_source_paper(session)
        dataset = ensure_dataset(session, paper)
        tag_paper(session, paper.id, [marl_task.id, rl_task.id])
        wire_leaderboard(session, dataset.id, marl_task.id)
        session.commit()
        logger.info(
            "SMACv2 ready: dataset_id=%s paper_id=%s metric=%s",
            dataset.id,
            paper.id,
            METRIC_NAME,
        )


if __name__ == "__main__":
    asyncio.run(main())
