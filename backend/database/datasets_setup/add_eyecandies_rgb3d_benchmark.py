"""Add the standard Eyecandies RGB+3D fusion benchmark.

The source is the original Eyecandies dataset paper (ACCV 2022), not a later
result paper. Eligible evaluations fuse aligned RGB and 3D information and use
the standard test split.

Run:
    uv run --env-file backend/keys.env python \
        backend/database/datasets_setup/add_eyecandies_rgb3d_benchmark.py
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import Author as DBAuthor
from backend.models.database import Dataset as DBDataset
from backend.models.database import Paper as DBPaper
from backend.models.database import PaperAuthor as DBPaperAuthor
from backend.models.database import Task as DBTask
from backend.services.arxiv_service import ArxivService
from backend.services.paper_service import PaperService

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

TASK_ID = 317
TASK_SLUG = "anomaly-detection"
SOURCE_ARXIV_ID = "2210.04570"
SOURCE_TITLE = (
    "The Eyecandies Dataset for Unsupervised Multimodal Anomaly Detection "
    "and Localization"
)
SOURCE_AUTHORS = (
    "Luca Bonfiglioli",
    "Marco Toschi",
    "Davide Silvestri",
    "Nicola Fioraio",
    "Daniele De Gregorio",
)

DATASET_NAME = "Eyecandies (RGB+3D Fusion)"
DATASET_SLUG = "eyecandies-rgb-3d-fusion"
DATASET_HOMEPAGE = "https://eyecan-ai.github.io/eyecandies/"
DATASET_SHORT_DESCRIPTION = (
    "Fusion of aligned color and 3D information on the standard Eyecandies test set."
)
DATASET_DESCRIPTION = (
    "Multimodal anomaly detection and localization on Eyecandies using aligned "
    "RGB and 3D information (depth, surface normals, or geometric features "
    "derived from them). Eligible results fuse both modalities and evaluate on "
    "the standard source-defined test split. RGB-only, 3D-only, zero-shot, "
    "few-shot, and nonstandard split results are not comparable and must not "
    "be added to this board."
)
METRICS = (
    "Detection AUROC",
    "Segmentation AUROC",
    "Segmentation AUPRO@30% FPR",
)


def get_task(session: Session) -> DBTask:
    task = session.query(DBTask).filter(DBTask.slug == TASK_SLUG).one_or_none()
    if task is None:
        raise RuntimeError(f"Task slug={TASK_SLUG!r} not found")
    if task.id != TASK_ID:
        raise RuntimeError(f"Expected task id={TASK_ID}, found id={task.id}")
    return task


async def ensure_source_paper(session: Session) -> DBPaper:
    paper = (
        session.query(DBPaper)
        .filter(
            DBPaper.arxiv_id == SOURCE_ARXIV_ID,
            DBPaper.is_latest_version.is_(True),
        )
        .order_by(DBPaper.id)
        .first()
    )
    if paper is None:
        metadata = await ArxivService().get_paper_metadata(SOURCE_ARXIV_ID)
        if not metadata.success:
            raise RuntimeError(
                f"Failed to fetch arXiv metadata for {SOURCE_ARXIV_ID}: "
                f"{metadata.error_message}"
            )
        paper_id = PaperService(session).add_paper(
            {
                "arxiv_id": metadata.arxiv_id,
                "title": metadata.title,
                "abstract": metadata.abstract,
                "version": metadata.version,
                "date_published": (
                    metadata.published.date() if metadata.published else None
                ),
                "primary_category": metadata.primary_category,
                "all_categories": metadata.categories,
                "is_latest_version": True,
            }
        )
        paper = session.get(DBPaper, paper_id)
        if paper is None:
            raise RuntimeError("Failed to reload the Eyecandies source paper")
        logger.info("Imported Eyecandies source paper id=%s", paper.id)

    if paper.title != SOURCE_TITLE:
        raise RuntimeError(
            f"Unexpected title for arXiv {SOURCE_ARXIV_ID}: {paper.title!r}"
        )
    paper.proceeding = paper.proceeding or "ACCV 2022"
    paper.conference = paper.conference or "ACCV"
    paper.conference_url_abs = (
        "https://openaccess.thecvf.com/content/ACCV2022/html/"
        "Bonfiglioli_The_Eyecandies_Dataset_for_Unsupervised_Multimodal_"
        "Anomaly_Detection_and_Localization_ACCV_2022_paper.html"
    )
    paper.conference_url_pdf = paper.conference_url_abs.replace(
        "/html/", "/papers/"
    ).replace("_paper.html", "_paper.pdf")
    return paper


def ensure_source_authors(session: Session, paper_id: int) -> None:
    for order, name in enumerate(SOURCE_AUTHORS, start=1):
        author = (
            session.query(DBAuthor)
            .filter(DBAuthor.name == name)
            .order_by(DBAuthor.id)
            .first()
        )
        if author is None:
            author = DBAuthor(name=name)
            session.add(author)
            session.flush()
        link = session.get(
            DBPaperAuthor, {"paper_id": paper_id, "author_id": author.id}
        )
        if link is None:
            session.add(
                DBPaperAuthor(
                    paper_id=paper_id,
                    author_id=author.id,
                    author_order=order,
                )
            )
        else:
            link.author_order = order


def get_metrics(session: Session) -> dict[str, int]:
    rows = session.execute(
        text(
            """
            SELECT id, name, direction
            FROM metrics
            WHERE name = ANY(:names)
            """
        ),
        {"names": list(METRICS)},
    ).all()
    by_name = {str(row.name): row for row in rows}
    missing = set(METRICS) - by_name.keys()
    if missing:
        raise RuntimeError(f"Missing metrics: {sorted(missing)}")
    wrong_direction = sorted(
        name for name, row in by_name.items() if row.direction != "higher_is_better"
    )
    if wrong_direction:
        raise RuntimeError(f"Metrics are not higher-is-better: {wrong_direction}")
    return {name: int(by_name[name].id) for name in METRICS}


def ensure_dataset(session: Session, source_paper: DBPaper) -> DBDataset:
    dataset = (
        session.query(DBDataset).filter(DBDataset.slug == DATASET_SLUG).one_or_none()
    )
    if dataset is None:
        dataset = DBDataset(slug=DATASET_SLUG)
        session.add(dataset)

    dataset.name = DATASET_NAME
    dataset.full_name = DATASET_NAME
    dataset.description = DATASET_DESCRIPTION
    dataset.short_description = DATASET_SHORT_DESCRIPTION
    dataset.url = DATASET_HOMEPAGE
    dataset.homepage = DATASET_HOMEPAGE
    dataset.variant_type = "variant"
    dataset.split_name = "Aligned RGB+3D fusion; standard test"
    dataset.introducing_paper_id = source_paper.id
    dataset.introducing_paper_title = source_paper.title
    dataset.introduced_year = 2022
    dataset.introduced_date = source_paper.date_published
    dataset.paper_url = f"https://paperswithcode.co/paper/{SOURCE_ARXIV_ID}"
    session.flush()
    logger.info("Upserted dataset %s (id=%s)", dataset.name, dataset.id)
    return dataset


def link_metadata(
    session: Session,
    task_id: int,
    dataset_id: int,
    paper_id: int,
    metric_ids: dict[str, int],
) -> None:
    session.execute(
        text(
            """
            INSERT INTO task_datasets (task_id, dataset_id, featured_rank, supports_harness)
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
            INSERT INTO paper_tasks (paper_id, task_id, source)
            VALUES (:paper_id, :task_id, 'manual')
            ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'
            """
        ),
        {"paper_id": paper_id, "task_id": task_id},
    )
    session.execute(
        text(
            """
            DELETE FROM task_dataset_metrics
            WHERE task_id = :task_id
              AND dataset_id = :dataset_id
              AND metric_id <> ALL(:metric_ids)
            """
        ),
        {
            "task_id": task_id,
            "dataset_id": dataset_id,
            "metric_ids": list(metric_ids.values()),
        },
    )
    for metric_id in metric_ids.values():
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
        task = get_task(session)
        source_paper = await ensure_source_paper(session)
        ensure_source_authors(session, source_paper.id)
        metric_ids = get_metrics(session)
        dataset = ensure_dataset(session, source_paper)
        link_metadata(session, task.id, dataset.id, source_paper.id, metric_ids)
        session.commit()
        logger.info(
            "%s ready: dataset_id=%s slug=%s paper_url=%s metrics=%s",
            dataset.name,
            dataset.id,
            dataset.slug,
            dataset.paper_url,
            list(METRICS),
        )


if __name__ == "__main__":
    asyncio.run(main())
