"""Wire DRealSR into Image Super-Resolution with full leaderboard metrics.

Source paper: Component Divide-and-Conquer for Real-World Image Super-Resolution
(arxiv 2008.01928). Metrics follow ASASR (2605.23264) and legacy PwC blind SR
leaderboards: PSNR, SSIM, LPIPS, DISTS, MANIQA, MUSIQ, CLIPIQA+, and NIQE.

Run:
    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/add_drealsr_benchmark.py
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

SOURCE_ARXIV_ID = "2008.01928"
TASK_SLUG = "image-super-resolution"
DATASET_SLUG = "drealsr"

DATASET_DESCRIPTION = (
    "DRealSR establishes a super-resolution benchmark with diverse real-world "
    "degradation processes, mitigating the limitations of conventional simulated "
    "image degradation. Images were collected from five DSLR cameras in natural "
    "scenes covering indoor and outdoor scenes while avoiding moving objects. "
    "Training images are cropped into 380×380, 272×272, and 192×192 patches, "
    "resulting in 31,970 patches."
)
DATASET_SHORT_DESCRIPTION = (
    "Real-world image super-resolution benchmark with diverse DSLR degradations."
)
DATASET_HOMEPAGE = (
    "https://github.com/xiezw5/"
    "Component-Divide-and-Conquer-for-Real-World-Image-Super-Resolution"
)
DATASET_URL = DATASET_HOMEPAGE

METRIC_NAMES = [
    "PSNR",
    "SSIM",
    "LPIPS",
    "DISTS",
    "MANIQA",
    "MUSIQ",
    "CLIPIQA+",
    "NIQE",
]

METRIC_SPECS = {
    "DISTS": {
        "direction": "lower_is_better",
        "full_name": "Deep Image Structure and Texture Similarity",
        "scale": "unbounded",
        "description": (
            "Full-reference perceptual similarity metric combining structure "
            "and texture cues; lower is better."
        ),
    },
    "MANIQA": {
        "direction": "higher_is_better",
        "full_name": "Multi-dimension Attention Network for Image Quality Assessment",
        "scale": "0-1",
        "description": (
            "No-reference image quality metric based on multi-dimension attention; "
            "higher is better."
        ),
    },
    "CLIPIQA+": {
        "direction": "higher_is_better",
        "full_name": "CLIP-based Image Quality Assessment Plus",
        "scale": "0-1",
        "description": (
            "No-reference image quality metric using CLIP-based perceptual "
            "features; higher is better."
        ),
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


def paper_url(paper: DBPaper) -> str:
    if paper.arxiv_id:
        return f"https://paperswithcode.co/paper/{paper.arxiv_id}"
    return f"https://paperswithcode.co/paper/{paper.id}"


def get_task(session: Session) -> DBTask:
    task = session.query(DBTask).filter(DBTask.slug == TASK_SLUG).one_or_none()
    if task is None:
        raise RuntimeError(f"Task slug={TASK_SLUG!r} not found")
    return task


def ensure_metric(session: Session, name: str) -> int:
    row = session.execute(
        text("SELECT id FROM metrics WHERE name = :n"), {"n": name}
    ).fetchone()
    if row:
        return int(row[0])

    spec = METRIC_SPECS.get(name)
    if spec is None:
        raise RuntimeError(f"Unknown metric {name!r} and no creation spec provided")

    metric_id = session.execute(
        text(
            """
            INSERT INTO metrics (name, direction, full_name, scale, description)
            VALUES (:name, :direction, :full_name, :scale, :description)
            RETURNING id
            """
        ),
        {"name": name, **spec},
    ).scalar_one()
    logger.info("Created metric %s (id=%s)", name, metric_id)
    return int(metric_id)


def ensure_dataset(session: Session, source_paper: DBPaper) -> DBDataset:
    native_url = paper_url(source_paper)
    dataset = (
        session.query(DBDataset).filter(DBDataset.slug == DATASET_SLUG).one_or_none()
    )
    if dataset is None:
        dataset = DBDataset(
            name="DRealSR",
            slug=DATASET_SLUG,
            full_name="DRealSR",
            description=DATASET_DESCRIPTION,
            short_description=DATASET_SHORT_DESCRIPTION,
            url=DATASET_URL,
            homepage=DATASET_HOMEPAGE,
            paper_url=native_url,
            introducing_paper_id=source_paper.id,
            introducing_paper_title=source_paper.title,
            introduced_year=2020,
        )
        session.add(dataset)
        session.flush()
        logger.info("Created dataset DRealSR (id=%s)", dataset.id)
    else:
        dataset.full_name = "DRealSR"
        dataset.description = DATASET_DESCRIPTION
        dataset.short_description = DATASET_SHORT_DESCRIPTION
        dataset.url = DATASET_URL
        dataset.homepage = DATASET_HOMEPAGE
        dataset.paper_url = native_url
        dataset.introducing_paper_id = source_paper.id
        dataset.introducing_paper_title = source_paper.title
        dataset.introduced_year = dataset.introduced_year or 2020
        session.flush()
        logger.info("Updated dataset DRealSR (id=%s)", dataset.id)
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
        dataset = ensure_dataset(session, source_paper)
        link_task_dataset(session, task.id, dataset.id)
        tag_source_paper(session, source_paper.id, task.id)

        metric_ids: dict[str, int] = {}
        for metric_name in METRIC_NAMES:
            metric_ids[metric_name] = ensure_metric(session, metric_name)
            link_metric(session, task.id, dataset.id, metric_ids[metric_name])

        session.commit()
        logger.info(
            "DRealSR ready: dataset_id=%s paper_id=%s paper_url=%s metrics=%s",
            dataset.id,
            source_paper.id,
            dataset.paper_url,
            METRIC_NAMES,
        )


if __name__ == "__main__":
    asyncio.run(main())
