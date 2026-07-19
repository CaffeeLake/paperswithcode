#!/usr/bin/env python3
"""Add the official DSEC-Flow hidden-test optical-flow leaderboard.

Run with:
    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/add_dsec_flow_optical_flow_test_benchmark.py
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import Author, Paper, PaperAuthor
from backend.services.arxiv_service import ArxivService
from backend.services.paper_service import PaperService


logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TASK_ID = 323
TASK_SLUG = "optical-flow"
SOURCE_ARXIV_ID = "2103.06011"
DATASET_SLUG = "dsec-flow-optical-flow-test"
NATIVE_PAPER_URL = f"https://paperswithcode.co/paper/{SOURCE_ARXIV_ID}"
HOMEPAGE = "https://dsec.ifi.uzh.ch/uzh/dsec-flow-optical-flow-benchmark/"

METRICS = {
    "EPE": {
        "full_name": "Average Endpoint Error",
        "scale": "pixels",
        "description": (
            "Mean Euclidean endpoint error between predicted and ground-truth "
            "optical-flow vectors, in pixels."
        ),
    },
    "1PE": {
        "full_name": "1-Pixel Error Rate",
        "scale": "percentage",
        "description": (
            "Percentage of evaluated ground-truth pixels with optical-flow "
            "endpoint error greater than one pixel."
        ),
    },
    "2PE": {
        "full_name": "2-Pixel Error Rate",
        "scale": "percentage",
        "description": (
            "Percentage of evaluated ground-truth pixels with optical-flow "
            "endpoint error greater than two pixels."
        ),
    },
    "3PE": {
        "full_name": "3-Pixel Error Rate",
        "scale": "percentage",
        "description": (
            "Percentage of evaluated ground-truth pixels with optical-flow "
            "endpoint error greater than three pixels."
        ),
    },
}


async def ensure_source_paper(session: Session) -> Paper:
    paper = (
        session.query(Paper)
        .filter(Paper.arxiv_id == SOURCE_ARXIV_ID, Paper.is_latest_version)
        .one_or_none()
    )
    has_authors = (
        paper is not None
        and session.query(PaperAuthor).filter(PaperAuthor.paper_id == paper.id).first()
    )
    if paper is not None and has_authors:
        return paper

    metadata = await ArxivService().get_paper_metadata(SOURCE_ARXIV_ID)
    if not metadata.success:
        raise RuntimeError(
            f"Failed to fetch arXiv metadata for {SOURCE_ARXIV_ID}: "
            f"{metadata.error_message}"
        )

    if paper is None:
        paper_id = PaperService(session).add_paper(
            {
                "arxiv_id": metadata.arxiv_id,
                "title": metadata.title,
                "abstract": metadata.abstract,
                "version": metadata.version,
                "date_published": metadata.published.date()
                if metadata.published
                else None,
                "primary_category": metadata.primary_category,
                "all_categories": metadata.categories,
                "is_latest_version": True,
            }
        )
        paper = session.get(Paper, paper_id)
        if paper is None:
            raise RuntimeError(f"Failed to import source paper {SOURCE_ARXIV_ID}")
        logger.info("Imported source paper %s (id=%s)", SOURCE_ARXIV_ID, paper.id)

    for order, author_name in enumerate(metadata.authors, start=1):
        author = session.query(Author).filter(Author.name == author_name).first()
        if author is None:
            author = Author(name=author_name)
            session.add(author)
            session.flush()
        session.execute(
            text(
                """
                INSERT INTO paper_authors (paper_id, author_id, author_order)
                VALUES (:paper_id, :author_id, :author_order)
                ON CONFLICT (paper_id, author_id) DO UPDATE
                SET author_order = EXCLUDED.author_order
                """
            ),
            {
                "paper_id": paper.id,
                "author_id": author.id,
                "author_order": order,
            },
        )
    return paper


async def main() -> None:
    with db_manager.session_local() as session:
        task = (
            session.execute(
                text("SELECT id, slug FROM tasks WHERE id = :id"), {"id": TASK_ID}
            )
            .mappings()
            .one()
        )
        if task["slug"] != TASK_SLUG:
            raise RuntimeError(f"Task {TASK_ID} is {task['slug']!r}, not {TASK_SLUG!r}")

        paper = await ensure_source_paper(session)
        if paper.arxiv_id != SOURCE_ARXIV_ID:
            raise RuntimeError(f"Resolved the wrong source paper: {paper.arxiv_id!r}")

        dataset_id = session.execute(
            text(
                """
                INSERT INTO datasets (
                    name, slug, full_name, description, short_description,
                    homepage, variant_type, split_name, introducing_paper_id,
                    introducing_paper_title, paper_url, introduced_year,
                    modalities, warning
                )
                VALUES (
                    'DSEC-Flow Optical Flow Test', :slug,
                    'DSEC-Flow — Official Hidden Optical Flow Test Set',
                    'The official DSEC-Flow hidden-test leaderboard for forward '
                    'optical flow in driving scenes. Evaluation uses the '
                    'undistorted/rectified left event-camera view and reports EPE and '
                    'one-, two-, and three-pixel error rates over all pixels with '
                    'ground-truth flow. Every evaluation row must document whether the '
                    'method also uses the paired global-shutter intensity-camera '
                    'images, along with its input and training regime.',
                    'Official DSEC-Flow hidden-test forward-flow evaluation on the rectified left event-camera view.',
                    :homepage, 'split',
                    'Official hidden test — forward flow, all GT pixels',
                    :paper_id, :paper_title, :paper_url, 2021,
                    CAST('["Events", "Images", "Optical Flow", "Driving"]' AS jsonb),
                    'Keep the official test geometry fixed: undistorted/rectified '
                    'left event-camera view, forward flow, and all ground-truth '
                    'pixels. Record global-shutter camera use and training/input '
                    'protocol per row. Self-supervised results may share this board '
                    'only when their test contract is identical; flag any source that '
                    'uses a non-comparable test setup. Do not add AE to this board.'
                )
                ON CONFLICT (slug) DO UPDATE SET
                    name = EXCLUDED.name,
                    full_name = EXCLUDED.full_name,
                    description = EXCLUDED.description,
                    short_description = EXCLUDED.short_description,
                    homepage = EXCLUDED.homepage,
                    variant_type = EXCLUDED.variant_type,
                    split_name = EXCLUDED.split_name,
                    introducing_paper_id = EXCLUDED.introducing_paper_id,
                    introducing_paper_title = EXCLUDED.introducing_paper_title,
                    paper_url = EXCLUDED.paper_url,
                    introduced_year = EXCLUDED.introduced_year,
                    modalities = EXCLUDED.modalities,
                    warning = EXCLUDED.warning,
                    updated_at = NOW()
                RETURNING id
                """
            ),
            {
                "slug": DATASET_SLUG,
                "homepage": HOMEPAGE,
                "paper_id": paper.id,
                "paper_title": paper.title,
                "paper_url": NATIVE_PAPER_URL,
            },
        ).scalar_one()

        metric_ids: dict[str, int] = {}
        for name, spec in METRICS.items():
            metric_ids[name] = int(
                session.execute(
                    text(
                        """
                        INSERT INTO metrics (
                            name, full_name, direction, scale, description
                        )
                        VALUES (
                            :name, :full_name, 'lower_is_better', :scale, :description
                        )
                        ON CONFLICT (name) DO UPDATE SET
                            direction = EXCLUDED.direction,
                            scale = EXCLUDED.scale,
                            description = EXCLUDED.description,
                            updated_at = NOW()
                        RETURNING id
                        """
                    ),
                    {"name": name, **spec},
                ).scalar_one()
            )

        session.execute(
            text(
                """
                INSERT INTO paper_tasks (paper_id, task_id, source)
                VALUES (:paper_id, :task_id, 'manual')
                ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'
                """
            ),
            {"paper_id": paper.id, "task_id": TASK_ID},
        )
        session.execute(
            text(
                """
                INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
                VALUES (:task_id, :dataset_id, FALSE)
                ON CONFLICT (task_id, dataset_id) DO UPDATE SET
                    supports_harness = FALSE,
                    updated_at = NOW()
                """
            ),
            {"task_id": TASK_ID, "dataset_id": dataset_id},
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
                {
                    "task_id": TASK_ID,
                    "dataset_id": dataset_id,
                    "metric_id": metric_id,
                },
            )

        session.commit()
        logger.info(
            "DSEC-Flow ready: dataset_id=%s paper_id=%s metrics=%s",
            dataset_id,
            paper.id,
            metric_ids,
        )


if __name__ == "__main__":
    asyncio.run(main())
