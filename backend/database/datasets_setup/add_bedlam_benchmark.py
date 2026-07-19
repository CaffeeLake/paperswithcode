"""Add BEDLAM test-split region benchmarks to 3D generation.

GUSH3R (2607.05243) Table 3 evaluates novel view synthesis on the BEDLAM test
split with three incomparable region columns: Human-Scene (full image), Scene
(background), and Human (human regions). Each region gets its own dataset row.

Source paper: BEDLAM (2306.16940) — not GUSH3R.

Run:
    uv run --env-file backend/keys.env \\
        python backend/database/datasets_setup/add_bedlam_benchmark.py
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

SOURCE_PAPER_ID = 17886
SOURCE_ARXIV = "2306.16940"

BEDLAM_HOMEPAGE = "https://bedlam.is.tue.mpg.de"
BEDLAM_URL = BEDLAM_HOMEPAGE
INTRODUCED_DATE = date(2023, 6, 29)

METRIC_NAMES = ["PSNR", "SSIM", "LPIPS"]

BENCHMARKS = [
    {
        "name": "BEDLAM (Human-Scene)",
        "slug": "bedlam-human-scene",
        "full_name": "BEDLAM Test (Human-Scene)",
        "split_name": "Human-Scene",
        "description": (
            "Novel view synthesis evaluation on the BEDLAM test split using the "
            "full Human-Scene region (entire rendered frame including humans and "
            "background). Scores from this region are not comparable to Scene-only "
            "or Human-only BEDLAM leaderboards."
        ),
        "short_description": (
            "BEDLAM test NVS on full Human-Scene frames (PSNR, SSIM, LPIPS)."
        ),
    },
    {
        "name": "BEDLAM (Scene)",
        "slug": "bedlam-scene",
        "full_name": "BEDLAM Test (Scene)",
        "split_name": "Scene",
        "description": (
            "Novel view synthesis evaluation on the BEDLAM test split restricted to "
            "background Scene regions (excluding human pixels). Scores are not "
            "comparable to Human-Scene or Human-only BEDLAM leaderboards."
        ),
        "short_description": (
            "BEDLAM test NVS on background Scene regions (PSNR, SSIM, LPIPS)."
        ),
    },
    {
        "name": "BEDLAM (Human)",
        "slug": "bedlam-human",
        "full_name": "BEDLAM Test (Human)",
        "split_name": "Human",
        "description": (
            "Novel view synthesis evaluation on the BEDLAM test split restricted to "
            "Human regions only. Scores are not comparable to Human-Scene or "
            "Scene-only BEDLAM leaderboards."
        ),
        "short_description": (
            "BEDLAM test NVS on Human regions only (PSNR, SSIM, LPIPS)."
        ),
    },
]


def paper_url(paper: DBPaper) -> str:
    if paper.arxiv_id:
        return f"https://paperswithcode.co/paper/{paper.arxiv_id}"
    return f"https://paperswithcode.co/paper/{paper.id}"


def get_task(session: Session) -> DBTask:
    task = session.query(DBTask).filter(DBTask.id == TASK_ID).one_or_none()
    if task is None:
        task = session.query(DBTask).filter(DBTask.slug == TASK_SLUG).one_or_none()
    if task is None:
        raise RuntimeError(f"Task id={TASK_ID} / slug={TASK_SLUG!r} not found")
    return task


def get_source_paper(session: Session) -> DBPaper:
    paper = (
        session.query(DBPaper)
        .filter(DBPaper.id == SOURCE_PAPER_ID, DBPaper.is_latest_version.is_(True))
        .one_or_none()
    )
    if paper is None:
        paper = (
            session.query(DBPaper)
            .filter(
                DBPaper.arxiv_id == SOURCE_ARXIV, DBPaper.is_latest_version.is_(True)
            )
            .one_or_none()
        )
    if paper is None:
        raise RuntimeError(
            f"BEDLAM source paper id={SOURCE_PAPER_ID} / arxiv={SOURCE_ARXIV} not found"
        )
    return paper


def get_metric_id(session: Session, name: str) -> int:
    row = session.execute(
        text("SELECT id FROM metrics WHERE name = :n"), {"n": name}
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Expected existing metric {name!r}")
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
            url=BEDLAM_URL,
            homepage=BEDLAM_HOMEPAGE,
            paper_url=native_url,
            introducing_paper_id=source_paper.id,
            introducing_paper_title=source_paper.title,
            introduced_date=INTRODUCED_DATE,
            introduced_year=INTRODUCED_DATE.year,
            variant_type="subset",
            split_name=spec["split_name"],
        )
        session.add(dataset)
        session.flush()
        logger.info("Created dataset %r (id=%s)", dataset.name, dataset.id)
    else:
        dataset.name = spec["name"]
        dataset.full_name = spec["full_name"]
        dataset.description = spec["description"]
        dataset.short_description = spec["short_description"]
        dataset.url = BEDLAM_URL
        dataset.homepage = BEDLAM_HOMEPAGE
        dataset.paper_url = native_url
        dataset.introducing_paper_id = source_paper.id
        dataset.introducing_paper_title = source_paper.title
        dataset.introduced_date = INTRODUCED_DATE
        dataset.introduced_year = INTRODUCED_DATE.year
        dataset.variant_type = "subset"
        dataset.split_name = spec["split_name"]
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
        source_paper = get_source_paper(session)
        tag_source_paper(session, source_paper.id, task.id)

        metric_ids = {name: get_metric_id(session, name) for name in METRIC_NAMES}

        for spec in BENCHMARKS:
            dataset = ensure_dataset(session, spec, source_paper)
            link_task_dataset(session, task.id, dataset.id)
            for metric_name in METRIC_NAMES:
                link_metric(session, task.id, dataset.id, metric_ids[metric_name])
            logger.info(
                "%s ready: dataset_id=%s slug=%s paper_id=%s paper_url=%s metrics=%s",
                spec["name"],
                dataset.id,
                dataset.slug,
                source_paper.id,
                dataset.paper_url,
                METRIC_NAMES,
            )

        session.commit()


if __name__ == "__main__":
    main()
