#!/usr/bin/env python3
"""Import legacy/comparator evals for Volt 3D segmentation leaderboards."""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.database.evaluations_setup.evaluation_helpers import (
    get_or_create_evaluation,
)
from backend.models.database import (
    Author,
    Evaluation as DBEvaluation,
    Paper,
    PaperAuthor,
)
from backend.services.arxiv_service import ArxivService
from backend.services.paper_service import PaperService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SEM_TASK_ID = 326
INST_TASK_ID = 327

DATASETS = {
    "scannet-plus-plus": 676,
    "nuscenes": 677,
    "semantickitti": 678,
    "waymo-open-dataset": 679,
    "scannet": 276,
}

EVALS = [
    {
        "arxiv_id": "2210.05666",
        "task_id": SEM_TASK_ID,
        "dataset": "scannet-plus-plus",
        "model_name": "Point Transformer V2",
        "metric": "mIoU",
        "score": "47.0",
        "methodology": (
            "ScanNet++ test mIoU from Volt Table 1 (PTv2 row); "
            "source: arXiv 2604.19609 Table 1."
        ),
        "source_url": "https://arxiv.org/pdf/2604.19609",
    },
    {
        "arxiv_id": "1904.08755",
        "task_id": SEM_TASK_ID,
        "dataset": "scannet-plus-plus",
        "model_name": "MinkUNet",
        "metric": "mIoU",
        "score": "45.6",
        "methodology": (
            "ScanNet++ test mIoU from Volt Table 1 (MinkUNet row); "
            "source: arXiv 2604.19609 Table 1."
        ),
        "source_url": "https://arxiv.org/pdf/2604.19609",
    },
    {
        "arxiv_id": "2210.05666",
        "task_id": SEM_TASK_ID,
        "dataset": "nuscenes",
        "model_name": "Point Transformer V2",
        "metric": "mIoU",
        "score": "82.6",
        "methodology": (
            "nuScenes test mIoU from Volt Table 2 (PTv2 row); "
            "source: arXiv 2604.19609 Table 2."
        ),
        "source_url": "https://arxiv.org/pdf/2604.19609",
    },
    {
        "arxiv_id": "2211.15766",
        "task_id": INST_TASK_ID,
        "dataset": "scannet",
        "model_name": "SPFormer",
        "metric": "AP50",
        "score": "77.0",
        "methodology": (
            "ScanNet(v2) test AP50 (legacy mAP@50) from SPFormer paper / "
            "legacy PwC evaluation-tables.json; source: arXiv 2211.15766."
        ),
        "source_url": "https://arxiv.org/abs/2211.15766",
    },
    {
        "arxiv_id": "2203.01509",
        "task_id": INST_TASK_ID,
        "dataset": "scannet",
        "model_name": "SoftGroup",
        "metric": "AP50",
        "score": "76.1",
        "methodology": (
            "ScanNet(v2) test AP50 (legacy mAP@50) from SoftGroup paper / "
            "legacy PwC evaluation-tables.json; source: arXiv 2203.01509."
        ),
        "source_url": "https://arxiv.org/abs/2203.01509",
    },
    {
        "arxiv_id": "2011.10033",
        "task_id": SEM_TASK_ID,
        "dataset": "semantickitti",
        "model_name": "Cylinder3D",
        "metric": "mIoU",
        "score": "68.9",
        "methodology": (
            "SemanticKITTI test mIoU from legacy PwC evaluation-tables.json; "
            "source: arXiv 2011.10033."
        ),
        "source_url": "https://arxiv.org/abs/2011.10033",
    },
    {
        "arxiv_id": "2207.04397",
        "task_id": SEM_TASK_ID,
        "dataset": "semantickitti",
        "model_name": "2DPASS",
        "metric": "mIoU",
        "score": "72.9",
        "methodology": (
            "SemanticKITTI test mIoU from legacy PwC evaluation-tables.json; "
            "source: arXiv 2207.04397."
        ),
        "source_url": "https://arxiv.org/abs/2207.04397",
    },
    {
        "arxiv_id": "2408.15254",
        "task_id": SEM_TASK_ID,
        "dataset": "waymo-open-dataset",
        "model_name": "vFusedSeg3D",
        "metric": "mIoU",
        "score": "72.46",
        "methodology": (
            "Waymo Open Dataset validation mIoU from legacy PwC "
            "evaluation-tables.json; source: arXiv 2408.15254."
        ),
        "source_url": "https://arxiv.org/abs/2408.15254",
    },
]


async def ensure_arxiv_paper(session, arxiv_id: str) -> Paper:
    existing = (
        session.query(Paper)
        .filter(Paper.arxiv_id == arxiv_id, Paper.is_latest_version.is_(True))
        .first()
    )
    if existing:
        logger.info("Paper %s already exists (id=%s)", arxiv_id, existing.id)
        return existing

    metadata = await ArxivService().get_paper_metadata(arxiv_id)
    if not metadata.success:
        raise RuntimeError(
            f"Failed to fetch arXiv metadata for {arxiv_id}: {metadata.error_message}"
        )

    paper_service = PaperService(session)
    paper_id = paper_service.add_paper(
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
    if not paper_id:
        existing = (
            session.query(Paper)
            .filter(Paper.arxiv_id == arxiv_id, Paper.is_latest_version.is_(True))
            .first()
        )
        if existing:
            return existing
        raise RuntimeError(f"Failed to create paper row for {arxiv_id}")

    paper = session.get(Paper, paper_id)
    if paper is None:
        raise RuntimeError(f"Created paper {paper_id} but could not reload it")

    if metadata.authors:
        for order, author_name in enumerate(metadata.authors, start=1):
            author = session.query(Author).filter(Author.name == author_name).first()
            if not author:
                author = Author(name=author_name)
                session.add(author)
                session.flush()
            session.add(
                PaperAuthor(paper_id=paper.id, author_id=author.id, author_order=order)
            )
        session.flush()

    logger.info("Imported paper %s (id=%s)", arxiv_id, paper.id)
    return paper


def link_paper_task(session, paper_id: int, task_id: int) -> None:
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
    session = db_manager.session_local()
    created = 0
    skipped = 0
    try:
        for spec in EVALS:
            paper = await ensure_arxiv_paper(session, spec["arxiv_id"])
            link_paper_task(session, paper.id, spec["task_id"])
            dataset_id = DATASETS[spec["dataset"]]
            existed = (
                session.query(DBEvaluation)
                .filter(
                    DBEvaluation.paper_id == paper.id,
                    DBEvaluation.task_id == spec["task_id"],
                    DBEvaluation.dataset_id == dataset_id,
                    DBEvaluation.model_name == spec["model_name"],
                    DBEvaluation.best_metric == spec["metric"],
                )
                .first()
            )
            get_or_create_evaluation(
                session,
                paper_id=paper.id,
                task_id=spec["task_id"],
                dataset_id=dataset_id,
                model_name=spec["model_name"],
                methodology=spec["methodology"],
                metrics={spec["metric"]: spec["score"]},
                best_metric=spec["metric"],
                external_source_url=spec["source_url"],
                is_open=True,
            )
            if existed:
                skipped += 1
                logger.info(
                    "Skipped existing %s / %s / %s",
                    spec["arxiv_id"],
                    spec["dataset"],
                    spec["model_name"],
                )
            else:
                created += 1
                logger.info(
                    "Created %s / %s / %s = %s",
                    spec["arxiv_id"],
                    spec["dataset"],
                    spec["model_name"],
                    spec["score"],
                )
        session.commit()
        logger.info("Done: %s created, %s skipped", created, skipped)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    asyncio.run(main())
