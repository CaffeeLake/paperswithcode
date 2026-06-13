"""Add PubTabNet, FinTabNet, and TableBank to Document Understanding.

These benchmarks support TableFormer (2203.01017) and related table-structure
recognition papers. Primary leaderboard metric is TEDS; PubTabNet also supports mAP
for cell bounding-box detection.

Run:
    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/add_table_recognition_benchmarks.py
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import Dataset as DBDataset, Paper, Task as DBTask
from backend.services.arxiv_service import ArxivService
from backend.services.paper_service import PaperService

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

TASK_SLUG = "document-understanding"
TEDS_METRIC_NAME = "TEDS"
MAP_METRIC_NAME = "mAP"

BENCHMARKS = [
    {
        "name": "PubTabNet",
        "slug": "pubtabnet",
        "full_name": "PubTabNet",
        "description": (
            "PubTabNet is a large image-based table recognition dataset with 568k "
            "table images and HTML structure annotations from PubMed Central Open "
            "Access articles."
        ),
        "short_description": "Image-based table recognition benchmark (~568K tables).",
        "homepage": "https://github.com/ibm-aur-nlp/PubTabNet",
        "url": "https://huggingface.co/datasets/ajimeno/PubTabNet",
        "source_arxiv": "1911.10683",
        "introduced_year": 2019,
        "featured_rank": 11,
        "metrics": [TEDS_METRIC_NAME, MAP_METRIC_NAME],
    },
    {
        "name": "FinTabNet",
        "slug": "fintabnet",
        "full_name": "FinTabNet",
        "description": (
            "FinTabNet contains complex tables from S&P 500 annual reports with "
            "detailed cell structure annotations for table detection and structure "
            "recognition."
        ),
        "short_description": "Financial table structure benchmark (~113K tables).",
        "homepage": "https://developer.ibm.com/exchanges/data/all/fintabnet/",
        "url": "https://developer.ibm.com/exchanges/data/all/fintabnet/",
        "source_arxiv": "2005.00589",
        "introduced_year": 2020,
        "featured_rank": 12,
        "metrics": [TEDS_METRIC_NAME],
    },
    {
        "name": "TableBank",
        "slug": "tablebank",
        "full_name": "TableBank",
        "description": (
            "TableBank is a weakly supervised image-based table detection and "
            "recognition dataset built from Word and LaTeX documents on the web."
        ),
        "short_description": "Weakly supervised table benchmark (417K labeled tables).",
        "homepage": "https://github.com/doc-analysis/TableBank",
        "url": "https://github.com/doc-analysis/TableBank",
        "source_arxiv": "1903.01949",
        "introduced_year": 2019,
        "featured_rank": 13,
        "metrics": [TEDS_METRIC_NAME],
    },
]


async def ensure_arxiv_paper(session: Session, arxiv_id: str) -> Paper:
    existing = (
        session.query(Paper)
        .filter(Paper.arxiv_id == arxiv_id, Paper.is_latest_version.is_(True))
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
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise RuntimeError(f"Failed to load newly created paper {paper_id}")
    logger.info("Imported paper %s (id=%s)", arxiv_id, paper.id)
    return paper


def _ensure_teds_metric(session: Session) -> int:
    row = session.execute(
        text("SELECT id FROM metrics WHERE name = :n"), {"n": TEDS_METRIC_NAME}
    ).fetchone()
    if row:
        return int(row[0])

    metric_id = session.execute(
        text(
            """
            INSERT INTO metrics (name, direction, full_name, scale, description)
            VALUES (:n, 'higher_is_better', :full, '0-100', :desc)
            RETURNING id
            """
        ),
        {
            "n": TEDS_METRIC_NAME,
            "full": "Tree-Edit-Distance-based Similarity",
            "desc": (
                "Table structure similarity metric based on tree edit distance "
                "between predicted and ground-truth HTML table structures."
            ),
        },
    ).scalar_one()
    logger.info("Created metric TEDS (id=%s)", metric_id)
    return int(metric_id)


def _metric_id(session: Session, name: str) -> int:
    row = session.execute(
        text("SELECT id FROM metrics WHERE name = :n"), {"n": name}
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Metric {name!r} not found")
    return int(row[0])


def _get_task(session: Session) -> DBTask:
    task = session.query(DBTask).filter(DBTask.slug == TASK_SLUG).one_or_none()
    if task is None:
        raise RuntimeError(f"Task slug={TASK_SLUG!r} not found")
    return task


def _ensure_dataset(session: Session, spec: dict, source_paper: Paper) -> DBDataset:
    paper_url = f"https://paperswithcode.co/paper/{source_paper.arxiv_id}"
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
            paper_url=paper_url,
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
        dataset.paper_url = paper_url
        dataset.introducing_paper_id = source_paper.id
        dataset.introducing_paper_title = source_paper.title
        dataset.introduced_year = dataset.introduced_year or spec["introduced_year"]
        session.flush()
        logger.info("Updated dataset %r (id=%s)", dataset.name, dataset.id)
    return dataset


def _link_task_dataset(
    session: Session, task_id: int, dataset_id: int, featured_rank: int
) -> None:
    session.execute(
        text(
            """
            INSERT INTO task_datasets (task_id, dataset_id, featured_rank, supports_harness)
            VALUES (:task_id, :dataset_id, :featured_rank, FALSE)
            ON CONFLICT (task_id, dataset_id) DO UPDATE
            SET featured_rank = COALESCE(EXCLUDED.featured_rank, task_datasets.featured_rank)
            """
        ),
        {
            "task_id": task_id,
            "dataset_id": dataset_id,
            "featured_rank": featured_rank,
        },
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
        task = _get_task(session)
        teds_id = _ensure_teds_metric(session)
        map_id = _metric_id(session, MAP_METRIC_NAME)
        metric_ids = {TEDS_METRIC_NAME: teds_id, MAP_METRIC_NAME: map_id}

        for spec in BENCHMARKS:
            source_paper = await ensure_arxiv_paper(session, spec["source_arxiv"])
            dataset = _ensure_dataset(session, spec, source_paper)
            _link_task_dataset(session, task.id, dataset.id, spec["featured_rank"])
            for metric_name in spec["metrics"]:
                _link_metric(session, task.id, dataset.id, metric_ids[metric_name])
            _tag_source_paper(session, source_paper.id, task.id)
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
