"""Add MOT tracking benchmarks to the Object Tracking task.

Benchmarks covered: MOT17, MOT20, BDD100K val/test, DanceTrack, SportsMOT.

Run:
    uv run --env-file backend/keys.env \\
        python backend/database/datasets_setup/add_mot_tracking_benchmarks.py
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

TASK_SLUG = "object-tracking"

METRIC_SPECS = {
    "MOTA": {
        "direction": "higher_is_better",
        "full_name": "Multiple Object Tracking Accuracy",
        "scale": "percentage",
        "description": "CLEAR MOT accuracy combining FP, FN, and ID switches.",
    },
    "IDF1": {
        "direction": "higher_is_better",
        "full_name": "ID F1 Score",
        "scale": "percentage",
        "description": "Identity-aware F1 score for multi-object tracking.",
    },
    "HOTA": {
        "direction": "higher_is_better",
        "full_name": "Higher Order Tracking Accuracy",
        "scale": "percentage",
        "description": "Balanced MOT metric combining detection, association, and localization.",
    },
    "mMOTA": {
        "direction": "higher_is_better",
        "full_name": "Mean MOTA",
        "scale": "percentage",
        "description": "Class-averaged MOTA used on multi-class BDD100K tracking.",
    },
    "mIDF1": {
        "direction": "higher_is_better",
        "full_name": "Mean IDF1",
        "scale": "percentage",
        "description": "Class-averaged IDF1 used on multi-class BDD100K tracking.",
    },
}

BENCHMARKS = [
    {
        "slug": "mot17",
        "name": "MOT17",
        "full_name": "Multiple Object Tracking 17",
        "short_description": "MOTChallenge benchmark with public and private detection protocols.",
        "description": (
            "MOT17 is the MOTChallenge multi-object tracking benchmark with seven "
            "training and seven test sequences, public detections, and private "
            "detector submissions evaluated on the hidden test set."
        ),
        "homepage": "https://motchallenge.net/data/MOT17/",
        "url": "https://motchallenge.net/data/MOT17/",
        "introduced_year": 2016,
        "source_arxiv": "1603.00831",
        "metrics": ["MOTA", "IDF1", "HOTA"],
        "primary_metric": "MOTA",
    },
    {
        "slug": "mot20",
        "name": "MOT20",
        "full_name": "MOT20",
        "short_description": "Crowded-scene MOT benchmark with up to 246 pedestrians per frame.",
        "description": (
            "MOT20 extends MOTChallenge with eight extremely crowded sequences "
            "featuring very high pedestrian density for evaluating trackers in "
            "dense crowd scenarios."
        ),
        "homepage": "https://motchallenge.net/data/MOT20/",
        "url": "https://motchallenge.net/data/MOT20/",
        "introduced_year": 2020,
        "source_arxiv": "2003.09003",
        "metrics": ["MOTA", "IDF1", "HOTA"],
        "primary_metric": "MOTA",
    },
    {
        "slug": "bdd100k-val",
        "name": "BDD100K val",
        "full_name": "BDD100K Tracking Validation",
        "short_description": "Multi-class tracking validation split of BDD100K.",
        "description": (
            "BDD100K tracking validation split with eight object classes in "
            "autonomous driving scenes; leaderboard reports class-averaged mMOTA "
            "and mIDF1."
        ),
        "homepage": "https://www.bdd100k.com/",
        "url": "https://www.bdd100k.com/",
        "introduced_year": 2018,
        "source_arxiv": "1805.04687",
        "metrics": ["mMOTA", "mIDF1"],
        "primary_metric": "mMOTA",
    },
    {
        "slug": "bdd100k-test",
        "name": "BDD100K test",
        "full_name": "BDD100K Tracking Test",
        "short_description": "Multi-class tracking test split of BDD100K.",
        "description": (
            "BDD100K tracking test split with eight object classes in autonomous "
            "driving scenes; leaderboard reports class-averaged mMOTA and mIDF1."
        ),
        "homepage": "https://www.bdd100k.com/",
        "url": "https://www.bdd100k.com/",
        "introduced_year": 2018,
        "source_arxiv": "1805.04687",
        "metrics": ["mMOTA", "mIDF1"],
        "primary_metric": "mMOTA",
    },
    {
        "slug": "dancetrack",
        "name": "DanceTrack",
        "full_name": "DanceTrack",
        "short_description": "MOT benchmark with uniform appearance and diverse motion.",
        "description": (
            "DanceTrack is a 100-video multi-object tracking benchmark focused on "
            "group dancing scenes with similar appearance and challenging motion, "
            "designed to stress motion-based association over re-ID."
        ),
        "homepage": "https://dancetrack.github.io/",
        "url": "https://github.com/DanceTrack/DanceTrack",
        "introduced_year": 2022,
        "source_arxiv": "2111.14690",
        "metrics": ["HOTA", "MOTA", "IDF1"],
        "primary_metric": "HOTA",
    },
    {
        "slug": "sportsmot",
        "name": "SportsMOT",
        "full_name": "SportsMOT",
        "short_description": "Large-scale sports-scene MOT benchmark across three sports.",
        "description": (
            "SportsMOT contains 240 sports video sequences across basketball, "
            "volleyball, and football with fast motion and similar player "
            "appearance for multi-object tracking evaluation."
        ),
        "homepage": "https://deeperaction.github.io/datasets/sportsmot.html",
        "url": "https://github.com/MCG-NJU/SportsMOT",
        "introduced_year": 2023,
        "source_arxiv": "2304.05170",
        "metrics": ["HOTA", "MOTA", "IDF1"],
        "primary_metric": "HOTA",
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


def paper_url(paper: DBPaper) -> str:
    if paper.arxiv_id:
        return f"https://paperswithcode.co/paper/{paper.arxiv_id}"
    return f"https://paperswithcode.co/paper/{paper.id}"


def ensure_metric(session: Session, name: str) -> int:
    row = session.execute(
        text("SELECT id FROM metrics WHERE name = :n"), {"n": name}
    ).fetchone()
    if row:
        return int(row[0])

    spec = METRIC_SPECS[name]
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
        tagged_papers: set[int] = set()

        for spec in BENCHMARKS:
            source_paper = await ensure_arxiv_paper(session, spec["source_arxiv"])
            dataset = ensure_dataset(session, spec, source_paper)
            link_task_dataset(session, task.id, dataset.id)
            for metric_name in spec["metrics"]:
                mid = ensure_metric(session, metric_name)
                link_metric(session, task.id, dataset.id, mid)
            if source_paper.id not in tagged_papers:
                tag_source_paper(session, source_paper.id, task.id)
                tagged_papers.add(source_paper.id)
            logger.info(
                "Ready %s -> https://paperswithcode.co/benchmark/%s (primary metric %s)",
                dataset.name,
                dataset.slug,
                spec["primary_metric"],
            )

        session.commit()


if __name__ == "__main__":
    asyncio.run(main())
