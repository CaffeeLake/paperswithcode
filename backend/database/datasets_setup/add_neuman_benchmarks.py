"""Wire NeuMan 4-view and 16-view NVS benchmarks into 3D Generation.

Source paper: NeuMan: Neural Human Radiance Field from a Single Video
(arxiv 2203.12575). GUSH3R (2607.05243) Table 2 reports PSNR, SSIM, and LPIPS
at separate 4-view and 16-view input settings — each gets its own leaderboard.

Run:
    uv run --env-file backend/keys.env \\
        python backend/database/datasets_setup/add_neuman_benchmarks.py
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

SOURCE_ARXIV_ID = "2203.12575"
TASK_SLUG = "3d-generation"
DATASET_HOMEPAGE = "https://github.com/apple/ml-neuman"

METRIC_NAMES = ["PSNR", "SSIM", "LPIPS"]

BASE_DESCRIPTION = (
    "NeuMan reconstructs an animatable human and the surrounding background scene "
    "from a single in-the-wild monocular video using dual neural radiance fields, "
    "enabling photorealistic novel-view synthesis of dynamic human-scene content. "
    "The benchmark evaluates image quality of rendered novel views against ground "
    "truth using PSNR, SSIM, and LPIPS."
)

BENCHMARKS = [
    {
        "name": "NeuMan (4-view)",
        "slug": "neuman-4-view",
        "full_name": "NeuMan (4-view)",
        "short_description": (
            "Monocular dynamic human-scene NVS benchmark with 4 input views."
        ),
        "description": (
            f"{BASE_DESCRIPTION} This leaderboard uses a 4-view input setting "
            "for sparse-view novel view synthesis evaluation."
        ),
    },
    {
        "name": "NeuMan (16-view)",
        "slug": "neuman-16-view",
        "full_name": "NeuMan (16-view)",
        "short_description": (
            "Monocular dynamic human-scene NVS benchmark with 16 input views."
        ),
        "description": (
            f"{BASE_DESCRIPTION} This leaderboard uses a 16-view input setting "
            "for sparse-view novel view synthesis evaluation."
        ),
    },
]


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


def paper_url(paper: DBPaper) -> str:
    if paper.arxiv_id:
        return f"https://paperswithcode.co/paper/{paper.arxiv_id}"
    return f"https://paperswithcode.co/paper/{paper.id}"


def get_task(session: Session) -> DBTask:
    task = session.query(DBTask).filter(DBTask.slug == TASK_SLUG).one_or_none()
    if task is None:
        raise RuntimeError(f"Task slug={TASK_SLUG!r} not found")
    return task


def get_metric_id(session: Session, name: str) -> int:
    row = session.execute(
        text("SELECT id FROM metrics WHERE name = :n"), {"n": name}
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Metric {name!r} not found")
    return int(row[0])


def ensure_dataset(session: Session, spec: dict, source_paper: DBPaper) -> DBDataset:
    native_url = paper_url(source_paper)
    dataset = (
        session.query(DBDataset).filter(DBDataset.slug == spec["slug"]).one_or_none()
    )
    if dataset is None:
        dataset = DBDataset(
            name=spec["name"],
            slug=spec["slug"],
            full_name=spec["full_name"],
            description=spec["description"],
            short_description=spec["short_description"],
            url=DATASET_HOMEPAGE,
            homepage=DATASET_HOMEPAGE,
            paper_url=native_url,
            introducing_paper_id=source_paper.id,
            introducing_paper_title=source_paper.title,
            introduced_year=2022,
        )
        session.add(dataset)
        session.flush()
        logger.info("Created dataset %s (id=%s)", spec["name"], dataset.id)
    else:
        dataset.name = spec["name"]
        dataset.full_name = spec["full_name"]
        dataset.description = spec["description"]
        dataset.short_description = spec["short_description"]
        dataset.url = DATASET_HOMEPAGE
        dataset.homepage = DATASET_HOMEPAGE
        dataset.paper_url = native_url
        dataset.introducing_paper_id = source_paper.id
        dataset.introducing_paper_title = source_paper.title
        dataset.introduced_year = dataset.introduced_year or 2022
        session.flush()
        logger.info("Updated dataset %s (id=%s)", spec["name"], dataset.id)
    return dataset


def link_task_dataset(session: Session, task_id: int, dataset_id: int) -> None:
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


def link_metric(
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


async def main() -> None:
    with db_manager.session_local() as session:
        task = get_task(session)
        source_paper = await ensure_arxiv_paper(session, SOURCE_ARXIV_ID)
        tag_source_paper(session, source_paper.id, task.id)

        metric_ids = {name: get_metric_id(session, name) for name in METRIC_NAMES}

        for spec in BENCHMARKS:
            dataset = ensure_dataset(session, spec, source_paper)
            link_task_dataset(session, task.id, dataset.id)
            for metric_name in METRIC_NAMES:
                link_metric(session, task.id, dataset.id, metric_ids[metric_name])
            logger.info(
                "%s ready: dataset_id=%s slug=%s paper_url=%s metrics=%s",
                spec["name"],
                dataset.id,
                spec["slug"],
                dataset.paper_url,
                METRIC_NAMES,
            )

        session.commit()
        logger.info(
            "NeuMan benchmarks ready: source_paper_id=%s paper_url=%s",
            source_paper.id,
            paper_url(source_paper),
        )


if __name__ == "__main__":
    asyncio.run(main())
