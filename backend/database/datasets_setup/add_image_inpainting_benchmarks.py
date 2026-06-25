"""Add legacy PapersWithCode image inpainting benchmarks.

Legacy source: data/legacy_pwc_data/evaluation-tables.json (Image Inpainting task)
and dataset metadata from jul-28-datasets.json where available.

Run:
    psql -U postgres -d paperswithcode_hf -f backend/database/migrations/add_image_inpainting_task.sql
    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/add_image_inpainting_benchmarks.py
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

TASK_SLUG = "image-inpainting"

PLACES2_URL = "http://places2.csail.mit.edu/"
CELEBA_URL = "https://paperswithcode.com/dataset/celeba"
CELEBA_HQ_URL = "https://github.com/tkarras/progressive_growing_of_gans"
FFHQ_URL = "https://github.com/NVlabs/ffhq-dataset"
IMAGENET_URL = "https://paperswithcode.com/dataset/imagenet"
APOLLOSCAPE_URL = "https://paperswithcode.com/dataset/apolloscape-1"
APOLLOSCAPE_INPAINT_URL = "https://paperswithcode.com/dataset/apolloscape-inpainting"

IMAGENET_SOURCE_URL = "https://doi.org/10.1109/CVPR.2009.5206848"
APOLLOSCAPE_SOURCE_URL = (
    "https://paperswithcode.com/paper/the-apolloscape-open-dataset-for-autonomous"
)

BENCHMARKS = [
    {
        "name": "Places2",
        "slug": "places2",
        "full_name": "Places2",
        "description": (
            "Places2 is a large-scale scene dataset widely used for image inpainting "
            "benchmarks. Legacy PapersWithCode leaderboards evaluate inpainting models "
            "on Places2 validation images with free-form or center-box masks at 256×256 "
            "or 512×512 resolution using FID and LPIPS."
        ),
        "short_description": "Scene inpainting benchmark on Places2 validation images.",
        "homepage": PLACES2_URL,
        "url": PLACES2_URL,
        "introduced_year": 2016,
        "source_kind": "arxiv",
        "source_arxiv": "1610.02055",
        "metrics": ["FID", "LPIPS"],
    },
    {
        "name": "Places2 val",
        "slug": "places2-val",
        "full_name": "Places2 val",
        "description": (
            "Places2 validation split used for inpainting evaluation in legacy "
            "PapersWithCode leaderboards, typically with free-form masks and FID."
        ),
        "short_description": "Places2 validation inpainting split.",
        "homepage": PLACES2_URL,
        "url": PLACES2_URL,
        "introduced_year": 2016,
        "source_kind": "arxiv",
        "source_arxiv": "1610.02055",
        "metrics": ["FID"],
    },
    {
        "name": "CelebA-HQ",
        "slug": "celeba-hq",
        "full_name": "CelebA-HQ",
        "description": (
            "CelebA-HQ contains 30,000 high-quality celebrity face images at up to "
            "1024×1024 resolution. It is a standard portrait inpainting benchmark in "
            "legacy PapersWithCode leaderboards."
        ),
        "short_description": "High-resolution portrait inpainting benchmark.",
        "homepage": CELEBA_HQ_URL,
        "url": CELEBA_HQ_URL,
        "introduced_year": 2017,
        "source_kind": "arxiv",
        "source_arxiv": "1710.10196",
        "metrics": ["FID", "LPIPS"],
    },
    {
        "name": "CelebA",
        "slug": "celeba",
        "full_name": "CelebFaces Attributes Dataset",
        "description": (
            "CelebA contains 202,599 celebrity face images with attribute labels. "
            "Legacy inpainting leaderboards evaluate masked-face completion with FID, "
            "LPIPS, PSNR, and SSIM."
        ),
        "short_description": "Face inpainting benchmark on CelebA.",
        "homepage": CELEBA_URL,
        "url": CELEBA_URL,
        "introduced_year": 2015,
        "source_kind": "arxiv",
        "source_arxiv": "1411.7769",
        "metrics": ["FID", "LPIPS", "PSNR", "SSIM"],
    },
    {
        "name": "FFHQ 512 x 512",
        "slug": "ffhq-512-x-512",
        "full_name": "FFHQ 512 x 512",
        "description": (
            "FFHQ portrait inpainting benchmark at 512×512 resolution from legacy "
            "PapersWithCode leaderboards."
        ),
        "short_description": "512×512 FFHQ portrait inpainting benchmark.",
        "homepage": FFHQ_URL,
        "url": FFHQ_URL,
        "introduced_year": 2018,
        "source_kind": "arxiv",
        "source_arxiv": "1812.04948",
        "metrics": ["FID", "LPIPS"],
    },
    {
        "name": "FFHQ 1024 x 1024",
        "slug": "ffhq-1024-x-1024",
        "full_name": "FFHQ 1024 x 1024",
        "description": (
            "FFHQ portrait inpainting benchmark at 1024×1024 resolution from legacy "
            "PapersWithCode leaderboards."
        ),
        "short_description": "1024×1024 FFHQ portrait inpainting benchmark.",
        "homepage": FFHQ_URL,
        "url": FFHQ_URL,
        "introduced_year": 2018,
        "source_kind": "arxiv",
        "source_arxiv": "1812.04948",
        "metrics": ["LPIPS", "PSNR", "RMSE", "SSIM"],
    },
    {
        "name": "ImageNet",
        "slug": "imagenet-inpainting",
        "full_name": "ImageNet (inpainting)",
        "description": (
            "ImageNet inpainting benchmark from legacy PapersWithCode leaderboards, "
            "evaluating masked-region completion with FID, PSNR, and SSIM."
        ),
        "short_description": "ImageNet inpainting benchmark.",
        "homepage": IMAGENET_URL,
        "url": IMAGENET_URL,
        "introduced_year": 2009,
        "source_kind": "external",
        "source_url": IMAGENET_SOURCE_URL,
        "source_title": "ImageNet: A large-scale hierarchical image database",
        "source_date": date(2009, 6, 20),
        "source_authors": [
            "Jia Deng",
            "Wei Dong",
            "Richard Socher",
            "Li-Jia Li",
            "Kai Li",
            "Li Fei-Fei",
        ],
        "source_abstract": (
            "Introduces ImageNet, a large-scale hierarchical image database that "
            "has become a standard resource for image classification and generation "
            "benchmarks including inpainting."
        ),
        "metrics": ["FID", "PSNR", "SSIM"],
    },
    {
        "name": "StreetView",
        "slug": "streetview-inpainting",
        "full_name": "StreetView",
        "description": (
            "StreetView inpainting benchmark from legacy PapersWithCode leaderboards, "
            "evaluated with SSIM."
        ),
        "short_description": "Street-view inpainting benchmark.",
        "homepage": "https://paperswithcode.com/sota/image-inpainting-on-streetview",
        "url": "https://paperswithcode.com/sota/image-inpainting-on-streetview",
        "introduced_year": 2016,
        "source_kind": "arxiv",
        "source_arxiv": "1604.07379",
        "metrics": ["SSIM"],
    },
    {
        "name": "Paris StreetView",
        "slug": "paris-streetview",
        "full_name": "Paris StreetView",
        "description": (
            "Paris StreetView inpainting benchmark introduced with Context Encoders. "
            "Legacy leaderboards report PSNR under multiple mask ratios."
        ),
        "short_description": "Paris street-view inpainting benchmark.",
        "homepage": "https://paperswithcode.com/sota/image-inpainting-on-paris-streetview-1",
        "url": "https://paperswithcode.com/sota/image-inpainting-on-paris-streetview-1",
        "introduced_year": 2016,
        "source_kind": "arxiv",
        "source_arxiv": "1604.07379",
        "metrics": ["PSNR"],
    },
    {
        "name": "ApolloScape",
        "slug": "apolloscape-inpainting",
        "full_name": "ApolloScape",
        "description": (
            "ApolloScape inpainting benchmark from legacy PapersWithCode leaderboards, "
            "evaluated with MAE, PSNR, RMSE, and SSIM."
        ),
        "short_description": "Driving-scene inpainting benchmark on ApolloScape.",
        "homepage": APOLLOSCAPE_URL,
        "url": APOLLOSCAPE_URL,
        "introduced_year": 2018,
        "source_kind": "external",
        "source_url": APOLLOSCAPE_SOURCE_URL,
        "source_title": (
            "The ApolloScape Open Dataset for Autonomous Driving and its Application"
        ),
        "source_date": date(2018, 1, 1),
        "source_authors": [
            "Hui Zhou",
            "Jianping Shi",
            "Xiaoou Tang",
            "Hongsheng Li",
        ],
        "source_abstract": (
            "Introduces ApolloScape, a large-scale dataset for autonomous driving "
            "with pixel-wise semantic annotation used for inpainting benchmarks."
        ),
        "metrics": ["MAE", "PSNR", "RMSE", "SSIM"],
    },
    {
        "name": "Apolloscape Inpainting",
        "slug": "apolloscape-inpainting-dataset",
        "full_name": "Apolloscape Inpainting",
        "description": (
            "Apolloscape Inpainting consists of synchronized labeled images and "
            "LiDAR point clouds for autonomous-driving inpainting evaluation."
        ),
        "short_description": "LiDAR-aligned ApolloScape inpainting benchmark.",
        "homepage": APOLLOSCAPE_INPAINT_URL,
        "url": APOLLOSCAPE_INPAINT_URL,
        "introduced_year": 2020,
        "source_kind": "arxiv",
        "source_arxiv": "2007.08854",
        "metrics": ["RMSE"],
    },
]

PAPER_TASK_ARXIVS = [
    "2606.19195",  # Moebius
    "2504.20438",  # PixelHacker
    "1604.07379",  # Context Encoders
    "1610.02055",  # Places2
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
    if row is None:
        raise RuntimeError(f"Metric {name!r} not found in database")
    return int(row[0])


def get_task(session: Session) -> DBTask:
    task = session.query(DBTask).filter(DBTask.slug == TASK_SLUG).one_or_none()
    if task is None:
        raise RuntimeError(
            f"Task slug={TASK_SLUG!r} not found; run add_image_inpainting_task.sql first"
        )
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
    session: Session, task_id: int, dataset_id: int, metric_id_value: int
) -> None:
    session.execute(
        text(
            """
            INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
            VALUES (:task_id, :dataset_id, :metric_id)
            ON CONFLICT DO NOTHING
            """
        ),
        {"task_id": task_id, "dataset_id": dataset_id, "metric_id": metric_id_value},
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
            for name in ["FID", "LPIPS", "PSNR", "SSIM", "MAE", "RMSE"]
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

        for arxiv_id in PAPER_TASK_ARXIVS:
            paper = await ensure_arxiv_paper(session, arxiv_id)
            tag_source_paper(session, paper.id, task.id)

        session.commit()


if __name__ == "__main__":
    asyncio.run(main())
