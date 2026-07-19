"""Add combined RealSR benchmark (Cai et al., ICCV 2019) to Image Super-Resolution.

RealSR is the paired real-world SR dataset from Canon 5D3 + Nikon D810 captures
introduced in "Toward Real-World Single Image Super-Resolution: A New Benchmark
and A New Model" (arXiv:1904.00523). ASASR and related work report a single
combined RealSR benchmark (Canon + Nikon), distinct from our separate
RealSR-Canon / RealSR-Nikon split rows (ids 823/824) and from RealSRSet
(BSRGAN, 20 images).

Run:
    uv run --env-file backend/keys.env \\
        python backend/database/datasets_setup/add_realsr_benchmark.py
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

TASK_SLUG = "image-super-resolution"
SOURCE_ARXIV = "1904.00523"
REALSR_HOMEPAGE = "https://github.com/csjcai/RealSR"

BENCHMARK = {
    "name": "RealSR",
    "slug": "realsr",
    "full_name": "RealSR",
    "description": (
        "RealSR is a real-world paired super-resolution benchmark from Cai et al. "
        "(ICCV 2019): aligned LR/HR image pairs captured on the same scene by "
        "adjusting focal length on Canon 5D3 and Nikon D810 cameras. The combined "
        "Canon + Nikon test set is the standard leaderboard used by ASASR and "
        "related real-world SR papers, evaluated at ×4 upscaling with 256×256 LR "
        "patches cropped from 1024×1024 HR inputs. Distinct from RealSR-Canon / "
        "RealSR-Nikon per-camera splits and from RealSRSet (BSRGAN, 20 images)."
    ),
    "short_description": (
        "Combined Canon+Nikon real-world paired SR benchmark (×4, 1024/256)."
    ),
    "homepage": REALSR_HOMEPAGE,
    "url": REALSR_HOMEPAGE,
    "introduced_year": 2019,
    "metrics": ["PSNR", "SSIM", "LPIPS", "MUSIQ", "DISTS", "MANIQA", "CLIPIQA+"],
}

METRIC_SPECS = {
    "MUSIQ": {
        "direction": "higher_is_better",
        "full_name": "Multi-Scale Image Quality Transformer",
        "scale": "0-100",
        "description": (
            "No-reference image quality metric used for real-world super-resolution "
            "evaluation without ground truth."
        ),
    },
    "DISTS": {
        "direction": "lower_is_better",
        "full_name": "Deep Image Structure and Texture Similarity",
        "scale": "0-1",
        "description": (
            "Perceptual similarity metric combining structure and texture cues; "
            "lower values indicate better perceptual quality."
        ),
    },
    "MANIQA": {
        "direction": "higher_is_better",
        "full_name": "Multi-dimension Attention Network for No-Reference IQA",
        "scale": "0-1",
        "description": (
            "No-reference image quality assessment metric based on multi-dimension "
            "attention; higher scores indicate better perceived quality."
        ),
    },
    "CLIPIQA+": {
        "direction": "higher_is_better",
        "full_name": "CLIPIQA+",
        "scale": "0-1",
        "description": (
            "CLIP-based no-reference image quality assessment metric; higher "
            "scores indicate better perceived quality."
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


def metric_id(session: Session, name: str) -> int:
    row = session.execute(
        text("SELECT id FROM metrics WHERE name = :n"), {"n": name}
    ).fetchone()
    if row:
        return int(row[0])

    spec = METRIC_SPECS.get(name)
    if spec is None:
        raise RuntimeError(f"Unknown metric {name!r}")

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


def get_task(session: Session) -> DBTask:
    task = session.query(DBTask).filter(DBTask.slug == TASK_SLUG).one_or_none()
    if task is None:
        raise RuntimeError(f"Task slug={TASK_SLUG!r} not found")
    return task


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
            url=spec["url"],
            homepage=spec["homepage"],
            paper_url=native_url,
            introducing_paper_id=source_paper.id,
            introducing_paper_title=source_paper.title,
            introduced_year=spec["introduced_year"],
        )
        session.add(dataset)
        session.flush()
        logger.info("Created dataset %r (id=%s)", dataset.name, dataset.id)
    else:
        dataset.full_name = spec["full_name"]
        dataset.description = spec["description"]
        dataset.short_description = spec["short_description"]
        dataset.url = spec["url"]
        dataset.homepage = spec["homepage"]
        dataset.paper_url = native_url
        dataset.introducing_paper_id = source_paper.id
        dataset.introducing_paper_title = source_paper.title
        dataset.introduced_year = dataset.introduced_year or spec["introduced_year"]
        session.flush()
        logger.info("Updated dataset %r (id=%s)", dataset.name, dataset.id)
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
            ON CONFLICT DO NOTHING
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
        source_paper = await ensure_arxiv_paper(session, SOURCE_ARXIV)
        metric_ids = {name: metric_id(session, name) for name in BENCHMARK["metrics"]}

        dataset = ensure_dataset(session, BENCHMARK, source_paper)
        link_task_dataset(session, task.id, dataset.id)
        for metric_name in BENCHMARK["metrics"]:
            link_metric(session, task.id, dataset.id, metric_ids[metric_name])
        tag_source_paper(session, source_paper.id, task.id)

        logger.info(
            "RealSR ready: dataset_id=%s slug=%s metrics=%s paper_id=%s paper_url=%s",
            dataset.id,
            dataset.slug,
            BENCHMARK["metrics"],
            source_paper.id,
            dataset.paper_url,
        )
        session.commit()


if __name__ == "__main__":
    asyncio.run(main())
