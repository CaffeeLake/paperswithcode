"""Wire EMDB (4-view and 16-view) into 3D generation for novel-view synthesis evals.

Source paper: EMDB: The Electromagnetic Database of Global 3D Human Pose and Shape
in the Wild (arxiv 2308.16894, paper_id=19987). Metrics follow GUSH3R Table 2:
PSNR, SSIM, LPIPS.

Run:
    uv run --env-file backend/keys.env \\
        python backend/database/datasets_setup/add_emdb_benchmark.py
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

SOURCE_ARXIV_ID = "2308.16894"
SOURCE_PAPER_ID = 19987
TASK_SLUG = "3d-generation"
TASK_ID = 13

DATASET_HOMEPAGE = "https://ait.ethz.ch/emdb"
DATASET_URL = DATASET_HOMEPAGE

BASE_DESCRIPTION = (
    "EMDB contains in-the-wild monocular human activity videos with SMPL pose and "
    "shape parameters, global body root trajectories, and camera trajectories. "
    "Videos were recorded with a hand-held iPhone; reference 3D poses were obtained "
    "by jointly fitting SMPL to body-worn electromagnetic sensors and image data."
)

METRIC_NAMES = ["PSNR", "SSIM", "LPIPS"]

BENCHMARKS = [
    {
        "name": "EMDB (4-view)",
        "slug": "emdb-4-view",
        "full_name": "EMDB (4-view novel view synthesis)",
        "short_description": (
            "EMDB novel-view synthesis split using 4 input views for 3D human scenes."
        ),
        "description": (
            f"{BASE_DESCRIPTION} This leaderboard tracks novel-view synthesis "
            "quality with 4 input views (PSNR, SSIM, LPIPS)."
        ),
    },
    {
        "name": "EMDB (16-view)",
        "slug": "emdb-16-view",
        "full_name": "EMDB (16-view novel view synthesis)",
        "short_description": (
            "EMDB novel-view synthesis split using 16 input views for 3D human scenes."
        ),
        "description": (
            f"{BASE_DESCRIPTION} This leaderboard tracks novel-view synthesis "
            "quality with 16 input views (PSNR, SSIM, LPIPS)."
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
    if task.id != TASK_ID:
        raise RuntimeError(
            f"Task slug={TASK_SLUG!r} has id={task.id}, expected {TASK_ID}"
        )
    return task


def ensure_metric(session: Session, name: str) -> int:
    row = session.execute(
        text("SELECT id FROM metrics WHERE name = :n"), {"n": name}
    ).fetchone()
    if row:
        return int(row[0])
    raise RuntimeError(f"Metric {name!r} not found in metrics table")


def ensure_dataset(
    session: Session, source_paper: DBPaper, spec: dict[str, str]
) -> DBDataset:
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
            url=DATASET_URL,
            homepage=DATASET_HOMEPAGE,
            paper_url=native_url,
            introducing_paper_id=source_paper.id,
            introducing_paper_title=source_paper.title,
            introduced_year=2023,
        )
        session.add(dataset)
        session.flush()
        logger.info("Created dataset %s (id=%s)", spec["name"], dataset.id)
    else:
        dataset.name = spec["name"]
        dataset.full_name = spec["full_name"]
        dataset.description = spec["description"]
        dataset.short_description = spec["short_description"]
        dataset.url = DATASET_URL
        dataset.homepage = DATASET_HOMEPAGE
        dataset.paper_url = native_url
        dataset.introducing_paper_id = source_paper.id
        dataset.introducing_paper_title = source_paper.title
        dataset.introduced_year = dataset.introduced_year or 2023
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
        if source_paper.id != SOURCE_PAPER_ID:
            raise RuntimeError(
                f"Expected source paper id={SOURCE_PAPER_ID}, got {source_paper.id}"
            )

        tag_source_paper(session, source_paper.id, task.id)

        metric_ids = {name: ensure_metric(session, name) for name in METRIC_NAMES}

        for spec in BENCHMARKS:
            dataset = ensure_dataset(session, source_paper, spec)
            link_task_dataset(session, task.id, dataset.id)
            for metric_name in METRIC_NAMES:
                link_metric(session, task.id, dataset.id, metric_ids[metric_name])
            logger.info(
                "%s ready: dataset_id=%s slug=%s metrics=%s paper_url=%s",
                spec["name"],
                dataset.id,
                spec["slug"],
                METRIC_NAMES,
                dataset.paper_url,
            )

        session.commit()
        logger.info("EMDB benchmarks linked to task %s (id=%s)", TASK_SLUG, task.id)


if __name__ == "__main__":
    asyncio.run(main())
