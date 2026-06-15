"""Add Composition-1k and Distinctions-646 to Image Matting.

Composition-1k is from Deep Image Matting (1706.03137). Distinctions-646 was
introduced in HAttMatting (CVPR 2020). Primary leaderboard metric: SAD.

Run:
    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/add_image_matting_benchmarks.py
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

TASK_SLUG = "image-matting"
SAD_METRIC = "SAD"

COMPOSITION_1K_ARXIV = "1706.03137"
HATTMATTING_SOURCE_URL = (
    "https://openaccess.thecvf.com/content_CVPR_2020/html/"
    "Qiao_Attention-Guided_Hierarchical_Structure_Aggregation_for_Image_Matting_CVPR_2020_paper.html"
)

BENCHMARKS = [
    {
        "name": "Composition-1k",
        "slug": "composition-1k",
        "full_name": "Composition-1k",
        "description": (
            "Composition-1k is the standard natural-image matting test set from "
            "Deep Image Matting: 50 foreground objects composited with 20 VOC2012 "
            "backgrounds (1000 images). Metrics are typically measured in the "
            "unknown trimap region."
        ),
        "short_description": "Classic trimap-based matting benchmark (1000 test images).",
        "homepage": "https://github.com/JDongian/composition-1k",
        "url": "https://github.com/JDongian/composition-1k",
        "introduced_year": 2017,
        "source_kind": "arxiv",
        "source_arxiv": COMPOSITION_1K_ARXIV,
    },
    {
        "name": "Distinctions-646",
        "slug": "distinctions-646",
        "full_name": "Distinctions-646",
        "description": (
            "Distinctions-646 is a high-resolution natural-image matting benchmark "
            "with 646 foreground objects split into 59600 training and 1000 test "
            "composited images. It follows the same synthetic compositing protocol "
            "as Composition-1k."
        ),
        "short_description": "High-resolution matting benchmark (1000 test images).",
        "homepage": HATTMATTING_SOURCE_URL,
        "url": HATTMATTING_SOURCE_URL,
        "introduced_year": 2020,
        "source_kind": "external",
        "source_url": HATTMATTING_SOURCE_URL,
        "source_title": (
            "Attention-Guided Hierarchical Structure Aggregation for Image Matting"
        ),
        "source_date": date(2020, 6, 14),
        "source_authors": [
            "Yu Qiao",
            "Yuhao Liu",
            "Xin Yang",
            "Dongsheng Zhou",
            "Mingliang Xu",
            "Qiang Zhang",
            "Xiaopeng Wei",
        ],
        "source_abstract": (
            "Introduces hierarchical structure aggregation for image matting and "
            "the Distinctions-646 benchmark of 646 unique foreground objects for "
            "training and evaluation."
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


def ensure_sad_metric(session: Session) -> int:
    row = session.execute(
        text("SELECT id FROM metrics WHERE name = :n"), {"n": SAD_METRIC}
    ).fetchone()
    if row:
        return int(row[0])

    metric_id = session.execute(
        text(
            """
            INSERT INTO metrics (name, direction, full_name, scale, description)
            VALUES (:n, 'lower_is_better', :full, 'unbounded', :desc)
            RETURNING id
            """
        ),
        {
            "n": SAD_METRIC,
            "full": "Sum of Absolute Differences",
            "desc": (
                "Matting quality metric: sum of absolute differences between "
                "predicted and ground-truth alpha mattes."
            ),
        },
    ).scalar_one()
    logger.info("Created metric SAD (id=%s)", metric_id)
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
            ON CONFLICT DO NOTHING
            """
        ),
        {"paper_id": paper_id, "task_id": task_id},
    )


async def main() -> None:
    with db_manager.session_local() as session:
        task = get_task(session)
        sad_id = ensure_sad_metric(session)

        for spec in BENCHMARKS:
            if spec["source_kind"] == "arxiv":
                source_paper = await ensure_arxiv_paper(session, spec["source_arxiv"])
            else:
                source_paper = ensure_external_paper(session, spec)

            dataset = ensure_dataset(session, spec, source_paper)
            link_task_dataset(session, task.id, dataset.id)
            link_metric(session, task.id, dataset.id, sad_id)
            tag_source_paper(session, source_paper.id, task.id)
            logger.info(
                "%s ready: dataset_id=%s paper_url=%s",
                spec["name"],
                dataset.id,
                dataset.paper_url,
            )

        session.commit()


if __name__ == "__main__":
    asyncio.run(main())
