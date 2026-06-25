"""Add DocLayNet and PubLayNet to the Document Layout Analysis task.

DocLayNet (arxiv 2206.01062) and PubLayNet (arxiv 1908.07836) are standard
document layout detection benchmarks evaluated with COCO-style mAP.

Run:
    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/add_doclaynet_publaynet_benchmarks.py
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

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

TASK_SLUG = "document-layout-analysis"
TASK_MIGRATION = Path(
    "backend/database/migrations/add_document_layout_analysis_task.sql"
)
MAP_METRIC_NAME = "mAP"
OVERALL_METRIC_NAME = "Overall"

BENCHMARKS = [
    {
        "name": "DocLayNet",
        "slug": "doclaynet",
        "full_name": "DocLayNet",
        "description": (
            "DocLayNet is a human-annotated document layout dataset in COCO format "
            "with 80,863 pages from diverse sources and 11 layout element classes. "
            "Models are typically evaluated on the held-out test split with "
            "COCO-style mAP@0.5-0.95."
        ),
        "short_description": (
            "Human-annotated document layout benchmark (80K+ pages, 11 classes)."
        ),
        "homepage": "https://github.com/DS4SD/DocLayNet",
        "url": "https://huggingface.co/datasets/ds4sd/DocLayNet",
        "source_arxiv": "2206.01062",
        "introduced_year": 2022,
    },
    {
        "name": "PubLayNet",
        "slug": "publaynet",
        "full_name": "PubLayNet",
        "description": (
            "PubLayNet is a large-scale document layout dataset built by aligning "
            "PubMed Central PDFs with XML annotations. It contains over 360,000 "
            "document images with five layout classes (Text, Title, List, Table, "
            "Figure) and is commonly evaluated on the validation split with mAP."
        ),
        "short_description": (
            "Large-scale PMC document layout benchmark (~360K images, 5 classes)."
        ),
        "homepage": "https://github.com/ibm-aur-nlp/PubLayNet",
        "url": "https://github.com/ibm-aur-nlp/PubLayNet",
        "source_arxiv": "1908.07836",
        "introduced_year": 2019,
        "metrics": [MAP_METRIC_NAME, OVERALL_METRIC_NAME],
    },
]

for spec in BENCHMARKS:
    spec.setdefault("metrics", [MAP_METRIC_NAME])


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


def _apply_task_migration(session: Session) -> None:
    sql = TASK_MIGRATION.read_text()
    session.execute(text(sql))
    logger.info("Applied %s", TASK_MIGRATION)


def _get_task(session: Session) -> DBTask:
    task = session.query(DBTask).filter(DBTask.slug == TASK_SLUG).one_or_none()
    if task is None:
        raise RuntimeError(f"Task slug={TASK_SLUG!r} not found after migration")
    return task


def _metric_id(session: Session, name: str) -> int:
    row = session.execute(
        text("SELECT id FROM metrics WHERE name = :n"), {"n": name}
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Metric {name!r} not found")
    return int(row[0])


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
        _apply_task_migration(session)
        task = _get_task(session)
        metric_ids = {
            name: _metric_id(session, name)
            for name in {MAP_METRIC_NAME, OVERALL_METRIC_NAME}
        }

        for spec in BENCHMARKS:
            source_paper = await ensure_arxiv_paper(session, spec["source_arxiv"])
            dataset = _ensure_dataset(session, spec, source_paper)
            _link_task_dataset(session, task.id, dataset.id)
            for metric_name in spec["metrics"]:
                _link_metric(session, task.id, dataset.id, metric_ids[metric_name])
            _tag_source_paper(session, source_paper.id, task.id)
            logger.info(
                "%s ready: dataset_id=%s metric=%s paper_url=%s",
                spec["name"],
                dataset.id,
                spec["metrics"],
                dataset.paper_url,
            )

        session.commit()


if __name__ == "__main__":
    asyncio.run(main())
