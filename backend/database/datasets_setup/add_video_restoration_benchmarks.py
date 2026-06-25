"""Add SPMCS, UDM10, YouHQ40, and VideoLQ to Video Restoration.

Source papers follow SwiftVR (2606.09516) citations — not SwiftVR itself:
- SPMCS: Detail-Revealing Deep Video Super-Resolution (1704.02738)
- UDM10: PFNL / ICCV 2019 (external)
- YouHQ40: Upscale-A-Video (2312.06640)
- VideoLQ: RealBasicVSR (2111.12704)

Run:
    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/add_video_restoration_benchmarks.py
"""

from __future__ import annotations

import asyncio
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
from backend.services.arxiv_service import ArxivService
from backend.services.external_resource_service import (
    ExternalResourceInput,
    ExternalResourceService,
)
from backend.services.paper_service import PaperService

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

TASK_SLUG = "video-restoration"

PFNL_SOURCE_URL = (
    "https://openaccess.thecvf.com/content_ICCV_2019/html/"
    "Yi_Progressive_Fusion_Video_Super-Resolution_Network_via_Exploiting_"
    "Non-Local_Spatio-Temporal_Correlations_ICCV_2019_paper.html"
)

BENCHMARKS = [
    {
        "name": "SPMCS",
        "slug": "spmcs",
        "full_name": "SPMCS",
        "description": (
            "SPMCS is a classic video super-resolution / restoration test set of "
            "30 sequences (31 frames each at 540×960) introduced in Detail-Revealing "
            "Deep Video Super-Resolution. It is widely reused for synthetic "
            "degradation benchmarks in real-world video restoration."
        ),
        "short_description": "30-sequence synthetic video restoration benchmark (540×960).",
        "homepage": "https://github.com/jiangsutx/SPMC_VideoSR",
        "url": "https://opendatalab.com/OpenDataLab/SPMCS",
        "introduced_year": 2017,
        "source_kind": "arxiv",
        "source_arxiv": "1704.02738",
        "metrics": ["PSNR", "SSIM", "LPIPS"],
    },
    {
        "name": "UDM10",
        "slug": "udm10",
        "full_name": "UDM10",
        "description": (
            "UDM10 is a standard video super-resolution test set of 10 sequences "
            "(32 frames each at 720×1272) released with the PFNL ICCV 2019 paper. "
            "It is commonly evaluated with bicubic or blur-downsampled low-quality inputs."
        ),
        "short_description": "10-sequence synthetic video restoration benchmark (720×1272).",
        "homepage": "https://github.com/psychopa4/PFNL",
        "url": "https://opendatalab.com/OpenDataLab/UDM10",
        "introduced_year": 2019,
        "source_kind": "external",
        "source_url": PFNL_SOURCE_URL,
        "source_title": (
            "Progressive Fusion Video Super-Resolution Network via Exploiting "
            "Non-Local Spatio-Temporal Correlations"
        ),
        "source_date": date(2019, 10, 27),
        "source_authors": [
            "Peng Yi",
            "Zhongyuan Wang",
            "Kui Jiang",
            "Junjun Jiang",
            "Jiayi Ma",
        ],
        "source_abstract": (
            "Introduces PFNL for video super-resolution and releases the UDM10 "
            "testing dataset of 10 video sequences with 32 consecutive frames each."
        ),
        "metrics": ["PSNR", "SSIM", "LPIPS"],
    },
    {
        "name": "YouHQ40",
        "slug": "youhq40",
        "full_name": "YouHQ40",
        "description": (
            "YouHQ40 is a 40-video synthetic test split from the YouHQ high-definition "
            "YouTube dataset introduced in Upscale-A-Video. Low-quality inputs are "
            "generated with the RealBasicVSR degradation pipeline for real-world "
            "video restoration evaluation."
        ),
        "short_description": "40-video synthetic restoration benchmark from YouHQ.",
        "homepage": "https://github.com/sczhou/Upscale-A-Video",
        "url": "https://github.com/sczhou/Upscale-A-Video",
        "introduced_year": 2024,
        "source_kind": "arxiv",
        "source_arxiv": "2312.06640",
        "metrics": ["PSNR", "SSIM", "LPIPS"],
    },
    {
        "name": "VideoLQ",
        "slug": "videolq",
        "full_name": "VideoLQ",
        "description": (
            "VideoLQ is a real-world low-quality video benchmark introduced in "
            "RealBasicVSR for evaluating restoration on in-the-wild degradations "
            "without paired high-quality ground truth."
        ),
        "short_description": "Real-world low-quality video restoration benchmark.",
        "homepage": "https://github.com/ckkelvinchan/RealBasicVSR",
        "url": "https://github.com/ckkelvinchan/RealBasicVSR",
        "introduced_year": 2022,
        "source_kind": "arxiv",
        "source_arxiv": "2111.12704",
        "metrics": ["MUSIQ"],
    },
]

METRIC_SPECS = {
    "MUSIQ": {
        "direction": "higher_is_better",
        "full_name": "Multi-Scale Image Quality Transformer",
        "scale": "0-100",
        "description": (
            "No-reference image quality metric used for real-world video "
            "restoration benchmarks without ground truth."
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


def ensure_external_paper(session: Session, spec: dict) -> DBPaper:
    paper = (
        session.query(DBPaper)
        .filter(
            DBPaper.source == "external",
            DBPaper.source_url == spec["source_url"],
        )
        .one_or_none()
    )
    if paper is not None:
        return paper

    result = ExternalResourceService(session).add_external_resource(
        ExternalResourceInput(
            source_url=spec["source_url"],
            title=spec["source_title"],
            abstract=spec["source_abstract"],
            authors=spec["source_authors"],
            date_published=spec["source_date"],
        )
    )
    paper = session.query(DBPaper).filter(DBPaper.id == int(result.paper.id)).one()
    logger.info("Created external paper id=%s", paper.id)
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
        metric_ids = {
            name: metric_id(session, name)
            for name in ["PSNR", "SSIM", "LPIPS", "MUSIQ"]
        }

        for spec in BENCHMARKS:
            if spec["source_kind"] == "arxiv":
                source_paper = await ensure_arxiv_paper(session, spec["source_arxiv"])
            else:
                source_paper = ensure_external_paper(session, spec)

            dataset = ensure_dataset(session, spec, source_paper)
            link_task_dataset(session, task.id, dataset.id)
            for metric_name in spec["metrics"]:
                link_metric(session, task.id, dataset.id, metric_ids[metric_name])
            tag_source_paper(session, source_paper.id, task.id)
            logger.info(
                "%s ready: dataset_id=%s metrics=%s paper_url=%s",
                spec["name"],
                dataset.id,
                spec["metrics"],
                dataset.paper_url,
            )

        session.commit()


if __name__ == "__main__":
    asyncio.run(main())
