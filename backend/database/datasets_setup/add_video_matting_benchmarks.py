"""Add V-HIM60 Hard and YouTubeMatte to Video Matting.

V-HIM60 Hard is from MaGGIe (2404.16035). YouTubeMatte 1920x1080 is from
MatAnyone (2501.14677). Primary leaderboard metrics: MAD and Gradient; also
MSE and MAD-T for first-frame mask-guided evaluations.

Run:
    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/add_video_matting_benchmarks.py
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

TASK_SLUG = "video-matting"

METRICS = [
    {
        "name": "MAD",
        "full_name": "Mean Absolute Difference",
        "description": (
            "Video matting metric: mean absolute difference between predicted "
            "and ground-truth alpha mattes (lower is better)."
        ),
    },
    {
        "name": "Gradient",
        "full_name": "Gradient Error",
        "description": (
            "Boundary-focused matting metric from Rhemann et al. (2009); "
            "measures alpha gradient errors (lower is better)."
        ),
    },
    {
        "name": "MAD-T",
        "full_name": "Trimap-based Mean Absolute Difference",
        "description": (
            "MAD restricted to the uncertain trimap region derived from the "
            "ground-truth alpha matte (lower is better)."
        ),
    },
]

BENCHMARKS = [
    {
        "name": "V-HIM60 Hard",
        "slug": "v-him60-hard",
        "full_name": "V-HIM60 Hard",
        "description": (
            "Hard split of the V-HIM60 video instance matting test set from "
            "MaGGIe: 20 synthetic videos (30 frames each) with challenging "
            "instance overlap, used for mask-guided video matting evaluation."
        ),
        "short_description": "Hard split of MaGGIe V-HIM60 video matting test set.",
        "homepage": "https://arxiv.org/abs/2404.16035",
        "url": "https://arxiv.org/abs/2404.16035",
        "introduced_year": 2024,
        "source_arxiv": "2404.16035",
    },
    {
        "name": "YouTubeMatte",
        "slug": "youtube-matte",
        "full_name": "YouTubeMatte (1920×1080)",
        "description": (
            "Synthetic video matting benchmark from MatAnyone: 32 distinct "
            "1920×1080 green-screen foreground videos composited for evaluation "
            "with higher boundary detail than VideoMatte240K-derived sets."
        ),
        "short_description": "MatAnyone 1920×1080 synthetic video matting benchmark.",
        "homepage": "https://arxiv.org/abs/2501.14677",
        "url": "https://arxiv.org/abs/2501.14677",
        "introduced_year": 2025,
        "source_arxiv": "2501.14677",
    },
    {
        "name": "VideoMatte (512×288)",
        "slug": "videomatte-512x288",
        "full_name": "VideoMatte (512×288)",
        "description": (
            "Low-resolution split of the VideoMatte240K test benchmark from "
            "Robust Video Matting (RVM), widely used for synthetic video matting "
            "evaluation at 512×288."
        ),
        "short_description": "RVM VideoMatte test set at 512×288.",
        "homepage": "https://arxiv.org/abs/2108.11515",
        "url": "https://github.com/PeterL1n/RobustVideoMatting",
        "introduced_year": 2021,
        "source_arxiv": "2108.11515",
    },
    {
        "name": "VideoMatte (1920×1080)",
        "slug": "videomatte-1920x1080",
        "full_name": "VideoMatte (1920×1080)",
        "description": (
            "High-resolution split of the VideoMatte240K test benchmark from "
            "Robust Video Matting (RVM), used for synthetic video matting "
            "evaluation at 1920×1080."
        ),
        "short_description": "RVM VideoMatte test set at 1920×1080.",
        "homepage": "https://arxiv.org/abs/2108.11515",
        "url": "https://github.com/PeterL1n/RobustVideoMatting",
        "introduced_year": 2021,
        "source_arxiv": "2108.11515",
    },
    {
        "name": "YouTubeMatte (512×288)",
        "slug": "youtube-matte-512x288",
        "full_name": "YouTubeMatte (512×288)",
        "description": (
            "512×288 split of the YouTubeMatte synthetic benchmark introduced "
            "by MatAnyone for video matting evaluation."
        ),
        "short_description": "MatAnyone YouTubeMatte benchmark at 512×288.",
        "homepage": "https://arxiv.org/abs/2501.14677",
        "url": "https://arxiv.org/abs/2501.14677",
        "introduced_year": 2025,
        "source_arxiv": "2501.14677",
    },
]


def paper_url(paper: DBPaper) -> str:
    if paper.arxiv_id:
        return f"https://paperswithcode.co/paper/{paper.arxiv_id}"
    return f"https://paperswithcode.co/paper/{paper.id}"


def ensure_metric(session: Session, spec: dict) -> int:
    row = session.execute(
        text("SELECT id FROM metrics WHERE name = :n"), {"n": spec["name"]}
    ).fetchone()
    if row:
        return int(row[0])

    metric_id = session.execute(
        text(
            """
            INSERT INTO metrics (name, direction, full_name, scale, description)
            VALUES (:n, 'lower_is_better', :full, 'unbounded', :desc)
            RETURNING id
            """
        ),
        {
            "n": spec["name"],
            "full": spec["full_name"],
            "desc": spec["description"],
        },
    ).scalar_one()
    logger.info("Created metric %s (id=%s)", spec["name"], metric_id)
    return int(metric_id)


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
        raise RuntimeError(f"Paper {arxiv_id} not found in database")
    return paper


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
            ON CONFLICT DO NOTHING
            """
        ),
        {"paper_id": paper_id, "task_id": task_id},
    )


def main() -> None:
    with db_manager.session_local() as session:
        task = get_task(session)

        metric_ids: dict[str, int] = {}
        for spec in METRICS:
            metric_ids[spec["name"]] = ensure_metric(session, spec)

        mse_row = session.execute(
            text("SELECT id FROM metrics WHERE name = 'MSE'")
        ).fetchone()
        if mse_row is None:
            raise RuntimeError("Expected existing MSE metric")
        metric_ids["MSE"] = int(mse_row[0])

        for spec in BENCHMARKS:
            source_paper = get_source_paper(session, spec["source_arxiv"])
            dataset = ensure_dataset(session, spec, source_paper)
            link_task_dataset(session, task.id, dataset.id)
            for metric_name, metric_id in metric_ids.items():
                link_metric(session, task.id, dataset.id, metric_id)
            tag_source_paper(session, source_paper.id, task.id)
            logger.info(
                "%s ready: dataset_id=%s paper_url=%s metrics=%s",
                spec["name"],
                dataset.id,
                dataset.paper_url,
                sorted(metric_ids),
            )

        session.commit()


if __name__ == "__main__":
    main()
