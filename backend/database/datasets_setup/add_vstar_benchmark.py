"""Wire V-STaR into the Video Understanding task.

V-STaR (arxiv 2503.11495) benchmarks Video-LLMs on reverse spatio-temporal
reasoning with coarse-to-fine chain-of-thought questions over 2094 videos.

Run:
    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/add_vstar_benchmark.py
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import (
    Dataset as DBDataset,
    Paper as DBPaper,
    Task as DBTask,
)
from backend.services.arxiv_service import ArxivService
from backend.services.paper_service import PaperService

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

ARXIV_ID = "2503.11495"
TASK_SLUG = "video-understanding"
DATASET_NAME = "V-STaR"
DATASET_SLUG = "v-star"
DATASET_FULL_NAME = "V-STaR"
DATASET_HOMEPAGE = "https://v-star-bench.github.io/"
DATASET_URL = "https://github.com/V-STaR-Bench/V-STaR"
PAPER_URL = f"https://paperswithcode.co/paper/{ARXIV_ID}"

DATASET_DESCRIPTION = (
    "V-STaR (Video Spatio-Temporal Reasoning) is a benchmark of 2094 videos "
    "(64+ hours) that evaluates Video-LLMs with reverse spatio-temporal "
    "reasoning chains asking what objects are present, when events occur, and "
    "where they are located. Questions are generated with a semi-automated "
    "GPT-4 pipeline and scored with answer-matching (AM) and logarithmic "
    "geometric mean (LGM) metrics across reasoning chains and video lengths."
)
DATASET_SHORT_DESCRIPTION = (
    "2094-video benchmark for reverse spatio-temporal reasoning in Video-LLMs."
)

METRIC_SPECS = {
    "mLGM": {
        "direction": "higher_is_better",
        "full_name": "Mean Logarithmic Geometric Mean",
        "scale": "0-100",
        "description": (
            "Mean LGM across reasoning chains on V-STaR; higher is better."
        ),
    },
    "mAM": {
        "direction": "higher_is_better",
        "full_name": "Mean Answer Matching",
        "scale": "0-100",
        "description": "Mean AM across reasoning chains on V-STaR; higher is better.",
    },
}


async def ensure_arxiv_paper(session: Session, arxiv_id: str) -> DBPaper:
    existing = (
        session.query(DBPaper)
        .filter(DBPaper.arxiv_id == arxiv_id, DBPaper.is_latest_version.is_(True))
        .first()
    )
    if existing:
        return existing

    metadata = await ArxivService().get_paper_metadata(arxiv_id)
    if not metadata.success:
        raise RuntimeError(f"Failed to fetch arXiv metadata for {arxiv_id}")

    paper_id = PaperService(session).add_paper(
        {
            "arxiv_id": metadata.arxiv_id,
            "title": metadata.title,
            "abstract": metadata.abstract,
            "version": metadata.version,
            "date_published": metadata.published.date() if metadata.published else None,
            "primary_category": metadata.primary_category,
            "all_categories": metadata.categories,
            "is_latest_version": True,
        }
    )
    paper = session.get(DBPaper, paper_id)
    if paper is None:
        raise RuntimeError(f"Failed to load newly created paper {paper_id}")
    logger.info("Imported paper %s (id=%s)", arxiv_id, paper.id)
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
            introduced_year=2025,
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
    dataset.introduced_year = dataset.introduced_year or 2025
    session.flush()
    logger.info("Updated dataset %r (id=%s)", dataset.name, dataset.id)
    return dataset


def _metric_id(session: Session, name: str) -> int:
    row = session.execute(
        text("SELECT id FROM metrics WHERE name = :n"), {"n": name}
    ).fetchone()
    if row:
        return int(row[0])

    spec = METRIC_SPECS[name]
    new_id = session.execute(
        text(
            """
            INSERT INTO metrics (name, direction, full_name, scale, description)
            VALUES (:name, :direction, :full_name, :scale, :description)
            RETURNING id
            """
        ),
        {"name": name, **spec},
    ).scalar_one()
    logger.info("Created metric %s (id=%s)", name, new_id)
    return int(new_id)


def _link_task_dataset(session: Session, task_id: int, dataset_id: int) -> None:
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


async def main() -> None:
    with db_manager.session_local() as session:
        paper = await ensure_arxiv_paper(session, ARXIV_ID)
        task = _get_task(session)
        dataset = _ensure_dataset(session, paper)
        for metric_name in METRIC_SPECS:
            metric_id = _metric_id(session, metric_name)
            _link_metric(session, task.id, dataset.id, metric_id)
        _link_task_dataset(session, task.id, dataset.id)
        _tag_source_paper(session, paper.id, task.id)
        session.commit()
        logger.info(
            "V-STaR ready: dataset_id=%s task_id=%s paper_url=%s",
            dataset.id,
            task.id,
            PAPER_URL,
        )


if __name__ == "__main__":
    asyncio.run(main())
