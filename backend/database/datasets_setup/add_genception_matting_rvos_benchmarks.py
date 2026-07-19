"""Add the missing matting and referring-video benchmarks used by GenCeption.

This only creates benchmark/task/metric wiring. It deliberately adds no evaluation
rows for GenCeption or any other paper.

Run:
    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/add_genception_matting_rvos_benchmarks.py
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import Dataset as DBDataset
from backend.models.database import Paper as DBPaper
from backend.models.database import Task as DBTask
from backend.services.arxiv_service import ArxivService
from backend.services.paper_service import PaperService

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

BENCHMARKS = [
    {
        "name": "PhotoMatte85",
        "slug": "photomatte85",
        "full_name": "PhotoMatte85",
        "task_slug": "image-matting",
        "metric": "MSE",
        "source_arxiv": "2012.07810",
        "homepage": "https://grail.cs.washington.edu/projects/background-matting-v2/#/datasets",
        "introduced_year": 2020,
        "introduced_date": "2020-12-14",
        "license_name": "Custom",
        "license_url": "https://grail.cs.washington.edu/projects/background-matting-v2/#/datasets",
        "modalities": ["Images"],
        "short_description": (
            "A held-out set of 85 professionally lit portrait images with alpha "
            "mattes and foregrounds for high-resolution image matting evaluation."
        ),
        "description": (
            "PhotoMatte85 is the public evaluation subset of PhotoMatte13K/85 "
            "introduced with Background Matting V2. It contains 85 professionally "
            "lit green-screen portrait images with released alpha mattes and "
            "foregrounds; the remaining 13K training images are not publicly "
            "released because of licensing restrictions."
        ),
    },
    {
        "name": "RefVOS-DAVIS",
        "slug": "refvos-davis",
        "full_name": "Referring Expressions for DAVIS 2016 & 2017",
        "task_slug": "referring-video-object-segmentation",
        "metric": "J&F",
        "source_arxiv": "1803.08006",
        "homepage": (
            "https://www.mpi-inf.mpg.de/de/departments/computer-vision-and-"
            "machine-learning/research/video-segmentation/video-object-"
            "segmentation-with-language-referring-expressions"
        ),
        "introduced_year": 2018,
        "introduced_date": "2018-03-21",
        "modalities": ["Videos", "Texts"],
        "short_description": (
            "The DAVIS 2016/2017 referring-expression protocol for language-guided "
            "video object segmentation, commonly reported as Ref-DAVIS17."
        ),
        "description": (
            "RefVOS-DAVIS augments DAVIS 2016 and DAVIS 2017 objects with "
            "unambiguous natural-language referring expressions. Modern referring "
            "video object segmentation work typically reports J&F on the DAVIS "
            "2017 validation protocol (Ref-DAVIS17). This is distinct from the "
            "ordinary first-mask DAVIS 2016/2017 video segmentation benchmarks."
        ),
    },
    {
        "name": "MeViS",
        "slug": "mevis",
        "full_name": "Motion expressions Video Segmentation",
        "task_slug": "referring-video-object-segmentation",
        "metric": "J&F",
        "source_arxiv": "2308.08544",
        "homepage": "https://henghuiding.github.io/MeViS/",
        "introduced_year": 2023,
        "introduced_date": "2023-08-16",
        "modalities": ["Videos", "Texts"],
        "short_description": (
            "A large-scale referring video segmentation benchmark whose language "
            "expressions identify objects primarily through motion."
        ),
        "description": (
            "MeViS contains 2,006 videos, 8,171 annotated objects, and 28,570 "
            "motion-focused referring expressions. It evaluates whether models can "
            "segment one or more target objects from language that requires temporal "
            "motion understanding rather than single-frame appearance cues."
        ),
    },
]


async def ensure_arxiv_paper(session: Session, arxiv_id: str) -> DBPaper:
    paper = (
        session.query(DBPaper)
        .filter(DBPaper.arxiv_id == arxiv_id, DBPaper.is_latest_version.is_(True))
        .one_or_none()
    )
    if paper is not None:
        return paper

    metadata = await ArxivService().get_paper_metadata(arxiv_id)
    if not metadata.success:
        raise RuntimeError(
            f"Failed to fetch arXiv metadata for {arxiv_id}: {metadata.error_message}"
        )
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
        raise RuntimeError(f"Failed to load newly imported paper {arxiv_id}")
    logger.info("Imported source paper %s (id=%s)", arxiv_id, paper.id)
    return paper


def native_paper_url(paper: DBPaper) -> str:
    if paper.arxiv_id:
        return f"https://paperswithcode.co/paper/{paper.arxiv_id}"
    return f"https://paperswithcode.co/paper/{paper.id}"


def get_task(session: Session, slug: str) -> DBTask:
    task = session.query(DBTask).filter(DBTask.slug == slug).one_or_none()
    if task is None:
        raise RuntimeError(f"Task {slug!r} not found")
    return task


def get_metric_id(session: Session, name: str) -> int:
    metric_id = session.execute(
        text("SELECT id FROM metrics WHERE name = :name"), {"name": name}
    ).scalar_one_or_none()
    if metric_id is None:
        raise RuntimeError(f"Metric {name!r} not found")
    return int(metric_id)


def ensure_dataset(
    session: Session, spec: dict, source_paper: DBPaper
) -> tuple[DBDataset, bool]:
    dataset = (
        session.query(DBDataset).filter(DBDataset.slug == spec["slug"]).one_or_none()
    )
    created = dataset is None
    if dataset is None:
        dataset = DBDataset(name=spec["name"], slug=spec["slug"])
        session.add(dataset)

    dataset.name = spec["name"]
    dataset.full_name = spec["full_name"]
    dataset.description = spec["description"]
    dataset.short_description = spec["short_description"]
    dataset.url = spec["homepage"]
    dataset.homepage = spec["homepage"]
    dataset.paper_url = native_paper_url(source_paper)
    dataset.introducing_paper_id = source_paper.id
    dataset.introducing_paper_title = source_paper.title
    dataset.introduced_year = spec["introduced_year"]
    dataset.introduced_date = spec["introduced_date"]
    dataset.modalities = spec["modalities"]
    dataset.license_name = spec.get("license_name")
    dataset.license_url = spec.get("license_url")
    session.flush()
    return dataset, created


def wire_benchmark(
    session: Session,
    task: DBTask,
    dataset: DBDataset,
    metric_id: int,
    source_paper: DBPaper,
) -> None:
    session.execute(
        text(
            """
            INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
            VALUES (:task_id, :dataset_id, FALSE)
            ON CONFLICT (task_id, dataset_id) DO NOTHING
            """
        ),
        {"task_id": task.id, "dataset_id": dataset.id},
    )
    session.execute(
        text(
            """
            INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
            VALUES (:task_id, :dataset_id, :metric_id)
            ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING
            """
        ),
        {"task_id": task.id, "dataset_id": dataset.id, "metric_id": metric_id},
    )
    session.execute(
        text(
            """
            INSERT INTO paper_tasks (paper_id, task_id, source)
            VALUES (:paper_id, :task_id, 'manual')
            ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'
            """
        ),
        {"paper_id": source_paper.id, "task_id": task.id},
    )


async def main() -> None:
    with db_manager.session_local() as session:
        for spec in BENCHMARKS:
            task = get_task(session, spec["task_slug"])
            metric_id = get_metric_id(session, spec["metric"])
            source_paper = await ensure_arxiv_paper(session, spec["source_arxiv"])
            dataset, created = ensure_dataset(session, spec, source_paper)
            wire_benchmark(session, task, dataset, metric_id, source_paper)
            logger.info(
                "%s benchmark %s (id=%s), task=%s, metric=%s, source=%s",
                "Created" if created else "Updated",
                dataset.name,
                dataset.id,
                task.slug,
                spec["metric"],
                dataset.paper_url,
            )
        session.commit()


if __name__ == "__main__":
    asyncio.run(main())
