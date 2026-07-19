"""Add GeoBench, PANGEABench, and SpectralEarth to Earth Observation.

Source papers (benchmark introducing papers, not UniverSat):
- GEO-Bench: arXiv:2306.03831
- PANGEABench: arXiv:2412.04204
- SpectralEarth: arXiv:2408.08447

Run:
    uv run --env-file backend/keys.env \\
        python backend/database/datasets_setup/add_earth_observation_benchmarks.py
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import (
    Dataset as DBDataset,
    Paper as DBPaper,
    Task as DBTask,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

TASK_SLUG = "earth-observation"

BENCHMARKS = [
    {
        "name": "GEO-Bench",
        "slug": "geo-bench",
        "full_name": "GEO-Bench: Toward Foundation Models for Earth Monitoring",
        "description": (
            "GEO-Bench is a curated benchmark suite for geospatial foundation models "
            "introduced by Lacoste et al. (NeurIPS 2023). It comprises six image "
            "classification and six semantic segmentation tasks assembled from diverse "
            "Earth-observation datasets with a standardized evaluation protocol for "
            "probing pretrained backbones."
        ),
        "short_description": (
            "12-task EO benchmark suite (6 classification + 6 segmentation)."
        ),
        "homepage": "https://github.com/ServiceNow/geo-bench",
        "url": "https://github.com/ServiceNow/geo-bench",
        "hf_url": "https://huggingface.co/datasets/kshitijrajsharma/geobench1-vhr",
        "introduced_year": 2023,
        "source_arxiv": "2306.03831",
        "metrics": ["Accuracy", "mIoU"],
    },
    {
        "name": "PANGEABench",
        "slug": "pangea-bench",
        "full_name": "PANGAEA: A Global and Inclusive Benchmark for Geospatial Foundation Models",
        "description": (
            "PANGEABench (PANGAEA) is a standardized evaluation protocol for "
            "geospatial foundation models covering diverse datasets, tasks, spatial "
            "resolutions, sensor modalities, and geographies. It integrates Geo-Bench "
            "tasks alongside additional global EO datasets for classification and "
            "semantic segmentation."
        ),
        "short_description": (
            "Global GFM benchmark spanning multiple EO tasks and sensor modalities."
        ),
        "homepage": "https://github.com/VMarsocci/pangaea-bench",
        "url": "https://github.com/VMarsocci/pangaea-bench",
        "introduced_year": 2024,
        "source_arxiv": "2412.04204",
        "metrics": ["Accuracy", "mIoU"],
    },
    {
        "name": "SpectralEarth",
        "slug": "spectralearth",
        "full_name": "SpectralEarth: Training Hyperspectral Foundation Models at Scale",
        "description": (
            "SpectralEarth is a large-scale EnMAP hyperspectral pretraining corpus "
            "with nine downstream benchmark tasks for land-cover, crop-type, and "
            "tree-species classification and segmentation. It is the standard "
            "evaluation suite for hyperspectral foundation models on EnMAP data."
        ),
        "short_description": (
            "EnMAP hyperspectral benchmark suite (9 downstream tasks)."
        ),
        "homepage": "https://github.com/AABNassim/spectral_earth",
        "url": "https://geoservice.dlr.de/web/datasets/enmap_spectralearth",
        "introduced_year": 2024,
        "source_arxiv": "2408.08447",
        "metrics": ["F1", "mIoU"],
    },
]


def paper_url(paper: DBPaper) -> str:
    if paper.arxiv_id:
        return f"https://paperswithcode.co/paper/{paper.arxiv_id}"
    return f"https://paperswithcode.co/paper/{paper.id}"


def get_task(session: Session) -> DBTask:
    task = session.query(DBTask).filter(DBTask.slug == TASK_SLUG).one_or_none()
    if task is None:
        raise RuntimeError(f"Task slug={TASK_SLUG!r} not found")
    return task


def get_source_paper(session: Session, arxiv_id: str) -> DBPaper:
    paper = (
        session.query(DBPaper)
        .filter(DBPaper.arxiv_id == arxiv_id, DBPaper.is_latest_version.is_(True))
        .one_or_none()
    )
    if paper is None:
        raise RuntimeError(f"Paper arxiv_id={arxiv_id!r} not found — import it first")
    return paper


def metric_id(session: Session, name: str) -> int:
    row = session.execute(
        text("SELECT id FROM metrics WHERE name = :n"), {"n": name}
    ).one()
    return int(row[0])


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
            hf_url=spec.get("hf_url"),
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
        if spec.get("hf_url"):
            dataset.hf_url = spec["hf_url"]
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


def fix_legacy_geo_bench_paper_url(session: Session) -> None:
    """Point the older classification-suite row at the native paper URL too."""
    session.execute(
        text(
            """
            UPDATE datasets
            SET paper_url = 'https://paperswithcode.co/paper/2306.03831',
                updated_at = CURRENT_TIMESTAMP
            WHERE slug = 'geo-bench-classification-suite'
              AND paper_url NOT LIKE 'https://paperswithcode.co/paper/%'
            """
        )
    )


def main() -> None:
    with db_manager.session_local() as session:
        task = get_task(session)
        fix_legacy_geo_bench_paper_url(session)

        for spec in BENCHMARKS:
            source_paper = get_source_paper(session, spec["source_arxiv"])
            dataset = ensure_dataset(session, spec, source_paper)
            link_task_dataset(session, task.id, dataset.id)
            for metric_name in spec["metrics"]:
                link_metric(
                    session, task.id, dataset.id, metric_id(session, metric_name)
                )
            tag_source_paper(session, source_paper.id, task.id)
            logger.info(
                "%s ready: dataset_id=%s metrics=%s paper_url=%s",
                spec["name"],
                dataset.id,
                spec["metrics"],
                dataset.paper_url,
            )

        session.commit()


if __name__ == "__main__":
    main()
