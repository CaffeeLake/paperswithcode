#!/usr/bin/env python3
"""Wire 3D object detection benchmarks, starting with nuScenes.

Run with:

    uv run --env-file backend/keys.env \\
        python backend/database/datasets_setup/add_3d_object_detection_benchmarks.py
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.models.api import TaskCreateRequest
from backend.models.database import Paper
from backend.services.arxiv_service import ArxivService
from backend.services.paper_service import PaperService
from backend.services.task_service import TaskService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

VISION_AREA_ID = 1
MAP_METRIC_ID = 11

TASK = {
    "name": "3D object detection",
    "description": (
        "Identify and localize objects in 3D space from point clouds, depth maps, "
        "multi-view images, or fused sensor data. Core to autonomous driving, "
        "robotics, and augmented reality."
    ),
    "keywords": "3D object detection",
}

NUSCENES_ARXIV = "1903.11027"

NUSCENES_DATASET = {
    "slug": "nuscenes",
    "description": (
        "Large-scale autonomous driving dataset with 3D bounding boxes for 1,000 scenes "
        "collected in Boston and Singapore. Each scene is 20 seconds long and annotated "
        "at 2Hz, yielding 28,130 training, 6,019 validation, and 6,008 test samples. "
        "The sensor suite includes a 32-beam LiDAR, 6 cameras, and radars with full "
        "360° coverage. The 3D object detection challenge evaluates 10 classes: cars, "
        "trucks, buses, trailers, construction vehicles, pedestrians, motorcycles, "
        "bicycles, traffic cones, and barriers."
    ),
    "short_description": (
        "Large-scale autonomous driving dataset with multimodal sensors and 3D boxes."
    ),
}


def paper_url_for(paper: Paper) -> str:
    if paper.arxiv_id:
        return f"https://paperswithcode.co/paper/{paper.arxiv_id}"
    return f"https://paperswithcode.co/paper/{paper.id}"


async def ensure_arxiv_paper(session, arxiv_id: str) -> Paper:
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
    return paper


def ensure_task(session) -> int:
    row = session.execute(
        text("SELECT id FROM tasks WHERE slug = '3d-object-detection'"),
    ).first()
    if row:
        return int(row[0])

    task = TaskService(session).create_task(
        TaskCreateRequest(
            name=TASK["name"],
            description=TASK["description"],
            keywords=TASK["keywords"],
            area_id=VISION_AREA_ID,
        )
    )
    return int(task.id)


def ensure_nds_metric(session) -> int:
    row = session.execute(
        text("SELECT id FROM metrics WHERE name = 'NDS'"),
    ).first()
    if row:
        return int(row[0])

    metric_id = session.execute(
        text(
            """
            INSERT INTO metrics (name, direction, full_name, scale, description)
            VALUES (
                'NDS',
                'higher_is_better',
                'nuScenes Detection Score',
                '0-1',
                'Official nuScenes 3D detection leaderboard score combining mAP and attribute errors.'
            )
            RETURNING id
            """
        ),
    ).scalar_one()
    return int(metric_id)


def wire_task_dataset(session, task_id: int, dataset_id: int) -> None:
    session.execute(
        text(
            """
            INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
            VALUES (:t, :d, FALSE)
            ON CONFLICT (task_id, dataset_id) DO NOTHING
            """
        ),
        {"t": task_id, "d": dataset_id},
    )


def wire_metric(session, task_id: int, dataset_id: int, metric_id: int) -> None:
    session.execute(
        text(
            """
            INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
            VALUES (:t, :d, :m)
            ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING
            """
        ),
        {"t": task_id, "d": dataset_id, "m": metric_id},
    )


def promote_paper_task(session, paper_id: int, task_id: int) -> None:
    session.execute(
        text(
            """
            INSERT INTO paper_tasks (paper_id, task_id, source)
            VALUES (:p, :t, 'manual')
            ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'
            """
        ),
        {"p": paper_id, "t": task_id},
    )


def ensure_nuscenes_dataset(session, source_paper: Paper) -> int:
    row = session.execute(
        text("SELECT id FROM datasets WHERE slug = :slug"),
        {"slug": NUSCENES_DATASET["slug"]},
    ).first()
    if row is None:
        raise RuntimeError(
            f"Expected existing dataset {NUSCENES_DATASET['slug']!r}; "
            "run add_3d_segmentation_benchmarks.py first or create it manually."
        )

    dataset_id = int(row[0])
    session.execute(
        text(
            """
            UPDATE datasets
            SET introducing_paper_id = :pid,
                introducing_paper_title = :title,
                paper_url = :paper_url,
                description = :description,
                short_description = :short_description,
                introduced_year = COALESCE(introduced_year, :year)
            WHERE id = :did
            """
        ),
        {
            "pid": source_paper.id,
            "title": source_paper.title,
            "paper_url": paper_url_for(source_paper),
            "description": NUSCENES_DATASET["description"],
            "short_description": NUSCENES_DATASET["short_description"],
            "year": date(2019, 3, 26).year,
            "did": dataset_id,
        },
    )
    return dataset_id


async def main() -> None:
    session = db_manager.session_local()
    try:
        source_paper = await ensure_arxiv_paper(session, NUSCENES_ARXIV)
        task_id = ensure_task(session)
        nds_metric_id = ensure_nds_metric(session)
        dataset_id = ensure_nuscenes_dataset(session, source_paper)

        wire_task_dataset(session, task_id, dataset_id)
        wire_metric(session, task_id, dataset_id, nds_metric_id)
        wire_metric(session, task_id, dataset_id, MAP_METRIC_ID)
        promote_paper_task(session, source_paper.id, task_id)

        session.commit()
        logger.info("3d-object-detection task_id=%s", task_id)
        logger.info("nuScenes dataset_id=%s", dataset_id)
        logger.info("source paper=%s", paper_url_for(source_paper))
        logger.info("metrics: NDS (id=%s), mAP (id=%s)", nds_metric_id, MAP_METRIC_ID)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    asyncio.run(main())
