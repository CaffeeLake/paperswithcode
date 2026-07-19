"""Wire PixWorld-style NVS leaderboards on RealEstate10K, DL3DV-10K, and WorldScore.

PixWorld (2607.05373) evaluates reconstruction (4/8 input views) and scene
generation (1/2 conditioning views) on RealEstate10K and DL3DV-10K, plus
WorldScore average. Each view-count / protocol gets its own leaderboard row.

Run:
    uv run --env-file backend/keys.env \\
        python backend/database/datasets_setup/add_pixworld_benchmarks.py
"""

from __future__ import annotations

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

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

TASK_ID = 13
TASK_SLUG = "3d-generation"

SOURCES = {
    "re10k": {
        "arxiv_id": "1805.09817",
        "paper_id": 82008,
        "homepage": "https://google.github.io/realestate10k/",
        "introduced_year": 2018,
        "introduced_date": date(2018, 5, 24),
        "base_description": (
            "RealEstate10K provides posed indoor/outdoor real-estate video clips "
            "widely used for novel-view synthesis and feed-forward 3D reconstruction. "
            "PixWorld and related world-model papers evaluate on a 200-scene test "
            "subset with large camera pose range."
        ),
    },
    "dl3dv": {
        "arxiv_id": "2312.16256",
        "paper_id": 25231,
        "homepage": "https://dl3dv-10k.github.io/DL3DV-10K/",
        "introduced_year": 2024,
        "introduced_date": date(2024, 6, 1),
        "base_description": (
            "DL3DV-10K is a large-scale real-world scene dataset for deep learning "
            "3D vision. PixWorld evaluates on a 200-scene DL3DV-10K test subset "
            "with wide-baseline camera motion."
        ),
    },
    "worldscore": {
        "arxiv_id": "2504.00983",
        "paper_id": 47130,
        "homepage": "https://worldscore.github.io/",
        "introduced_year": 2025,
        "introduced_date": date(2025, 4, 1),
        "base_description": (
            "WorldScore is a unified benchmark for world generation covering camera "
            "control, object control, content alignment, 3D/photometric/style "
            "consistency, and subjective quality. PixWorld reports the official "
            "static split (2000 scenes) average across seven metrics."
        ),
    },
}

RECON_METRICS = ["PSNR", "SSIM", "LPIPS"]
GEN_METRICS = ["PSNR", "SSIM", "LPIPS", "AUC@5"]
WORLDSCORE_METRICS = ["Average"]

BENCHMARKS = [
    {
        "source_key": "re10k",
        "name": "RealEstate10K (4-view)",
        "slug": "re10k-4-view",
        "full_name": "RealEstate10K (4-view reconstruction)",
        "short_description": "NVS reconstruction with 4 posed input views on RealEstate10K.",
        "protocol": "reconstruction",
        "metrics": RECON_METRICS,
    },
    {
        "source_key": "re10k",
        "name": "RealEstate10K (8-view)",
        "slug": "re10k-8-view",
        "full_name": "RealEstate10K (8-view reconstruction)",
        "short_description": "NVS reconstruction with 8 posed input views on RealEstate10K.",
        "protocol": "reconstruction",
        "metrics": RECON_METRICS,
    },
    {
        "source_key": "re10k",
        "name": "RealEstate10K (1-view)",
        "slug": "re10k-1-view",
        "full_name": "RealEstate10K (1-view generation)",
        "short_description": (
            "Single-image 3D scene generation on RealEstate10K, averaged over "
            "First-Frame and Bidirectional trajectories."
        ),
        "protocol": "generation",
        "metrics": GEN_METRICS,
    },
    {
        "source_key": "re10k",
        "name": "RealEstate10K (2-view)",
        "slug": "re10k-2-view",
        "full_name": "RealEstate10K (2-view generation)",
        "short_description": (
            "Two-image 3D scene generation on RealEstate10K, averaged over "
            "Interpolation and Extrapolation trajectories."
        ),
        "protocol": "generation",
        "metrics": GEN_METRICS,
    },
    {
        "source_key": "dl3dv",
        "name": "DL3DV-10K (4-view)",
        "slug": "dl3dv-10k-4-view",
        "full_name": "DL3DV-10K (4-view reconstruction)",
        "short_description": "NVS reconstruction with 4 posed input views on DL3DV-10K.",
        "protocol": "reconstruction",
        "metrics": RECON_METRICS,
    },
    {
        "source_key": "dl3dv",
        "name": "DL3DV-10K (8-view)",
        "slug": "dl3dv-10k-8-view",
        "full_name": "DL3DV-10K (8-view reconstruction)",
        "short_description": "NVS reconstruction with 8 posed input views on DL3DV-10K.",
        "protocol": "reconstruction",
        "metrics": RECON_METRICS,
    },
    {
        "source_key": "dl3dv",
        "name": "DL3DV-10K (1-view)",
        "slug": "dl3dv-10k-1-view",
        "full_name": "DL3DV-10K (1-view generation)",
        "short_description": (
            "Single-image 3D scene generation on DL3DV-10K, averaged over "
            "First-Frame and Bidirectional trajectories."
        ),
        "protocol": "generation",
        "metrics": GEN_METRICS,
    },
    {
        "source_key": "dl3dv",
        "name": "DL3DV-10K (2-view)",
        "slug": "dl3dv-10k-2-view",
        "full_name": "DL3DV-10K (2-view generation)",
        "short_description": (
            "Two-image 3D scene generation on DL3DV-10K, averaged over "
            "Interpolation and Extrapolation trajectories."
        ),
        "protocol": "generation",
        "metrics": GEN_METRICS,
    },
    {
        "source_key": "worldscore",
        "name": "WorldScore",
        "slug": "worldscore",
        "full_name": "WorldScore (static split)",
        "short_description": "Official WorldScore static split average (7 metrics).",
        "protocol": "worldscore",
        "metrics": WORLDSCORE_METRICS,
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
    if task.id != TASK_ID:
        raise RuntimeError(
            f"Task slug={TASK_SLUG!r} has id={task.id}, expected {TASK_ID}"
        )
    return task


def get_source_paper(session: Session, source_key: str) -> DBPaper:
    meta = SOURCES[source_key]
    paper = session.get(DBPaper, meta["paper_id"])
    if paper is None:
        raise RuntimeError(f"Missing source paper id={meta['paper_id']}")
    if paper.arxiv_id != meta["arxiv_id"]:
        raise RuntimeError(
            f"Paper id={paper.id} arxiv_id={paper.arxiv_id!r} "
            f"!= expected {meta['arxiv_id']!r}"
        )
    return paper


def ensure_metric(session: Session, name: str) -> int:
    row = session.execute(
        text("SELECT id FROM metrics WHERE name = :n"), {"n": name}
    ).fetchone()
    if row:
        return int(row[0])
    if name != "Average":
        raise RuntimeError(f"Metric {name!r} not found in metrics table")
    session.execute(
        text(
            """
            INSERT INTO metrics (name, direction, full_name, scale, description)
            VALUES (
                :name, 'higher_is_better', :full_name, '0-100',
                'Arithmetic mean across configured WorldScore component metrics.'
            )
            ON CONFLICT (name) DO NOTHING
            """
        ),
        {
            "name": name,
            "full_name": "Average",
        },
    )
    row = session.execute(
        text("SELECT id FROM metrics WHERE name = :n"), {"n": name}
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Failed to create metric {name!r}")
    return int(row[0])


def ensure_dataset(
    session: Session, source_paper: DBPaper, source_key: str, spec: dict
) -> DBDataset:
    source_meta = SOURCES[source_key]
    native_url = paper_url(source_paper)
    protocol = spec["protocol"]
    description = (
        f"{source_meta['base_description']} "
        f"This leaderboard tracks the PixWorld {protocol} protocol "
        f"({spec['full_name']})."
    )
    dataset = (
        session.query(DBDataset).filter(DBDataset.slug == spec["slug"]).one_or_none()
    )
    if dataset is None:
        dataset = DBDataset(
            name=spec["name"],
            slug=spec["slug"],
            full_name=spec["full_name"],
            description=description,
            short_description=spec["short_description"],
            url=source_meta["homepage"],
            homepage=source_meta["homepage"],
            paper_url=native_url,
            introducing_paper_id=source_paper.id,
            introducing_paper_title=source_paper.title,
            introduced_year=source_meta["introduced_year"],
            introduced_date=source_meta["introduced_date"],
        )
        session.add(dataset)
        session.flush()
        logger.info("Created dataset %s (id=%s)", spec["name"], dataset.id)
    else:
        dataset.name = spec["name"]
        dataset.full_name = spec["full_name"]
        dataset.description = description
        dataset.short_description = spec["short_description"]
        dataset.url = source_meta["homepage"]
        dataset.homepage = source_meta["homepage"]
        dataset.paper_url = native_url
        dataset.introducing_paper_id = source_paper.id
        dataset.introducing_paper_title = source_paper.title
        dataset.introduced_year = (
            dataset.introduced_year or source_meta["introduced_year"]
        )
        dataset.introduced_date = (
            dataset.introduced_date or source_meta["introduced_date"]
        )
        session.flush()
        logger.info("Updated dataset %s (id=%s)", spec["name"], dataset.id)
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
            ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING
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


def main() -> None:
    with db_manager.session_local() as session:
        task = get_task(session)
        tagged_papers: set[int] = set()

        for spec in BENCHMARKS:
            source_paper = get_source_paper(session, spec["source_key"])
            if source_paper.id not in tagged_papers:
                tag_source_paper(session, source_paper.id, task.id)
                tagged_papers.add(source_paper.id)

            dataset = ensure_dataset(session, source_paper, spec["source_key"], spec)
            link_task_dataset(session, task.id, dataset.id)
            for metric_name in spec["metrics"]:
                metric_id = ensure_metric(session, metric_name)
                link_metric(session, task.id, dataset.id, metric_id)
            logger.info(
                "%s ready: dataset_id=%s metrics=%s",
                spec["name"],
                dataset.id,
                spec["metrics"],
            )

        session.commit()
        logger.info("PixWorld benchmarks linked to task %s", TASK_SLUG)


if __name__ == "__main__":
    main()
