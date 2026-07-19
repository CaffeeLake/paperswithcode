"""Add HPSv3 benchmark to the database (benchmark wiring only).

HPSv3 (Human Preference Score v3) is a VLM-based human-preference metric for
text-to-image evaluation, introduced alongside the HPDv3 preference dataset in
arXiv:2508.03789.

Run with:

    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/add_hpsv3_benchmark.py
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
from backend.utils.slug_utils import slugify

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

HPSV3_ARXIV_ID = "2508.03789"
TASK_SLUG = "image-generation"
DATASET_NAME = "HPSv3"
DATASET_SLUG = slugify(DATASET_NAME)
DATASET_FULL_NAME = "HPSv3: Wide-Spectrum Human Preference Score"
DATASET_HOMEPAGE = "https://huggingface.co/spaces/zzliang/HPSv3"
PAPER_URL = f"https://paperswithcode.co/paper/{HPSV3_ARXIV_ID}"

DATASET_DESCRIPTION = (
    "HPSv3 (Human Preference Score v3) is a VLM-based preference model for "
    "wide-spectrum text-to-image evaluation. It is trained on HPDv3, a human "
    "preference dataset with 1.08M text-image pairs and 1.17M pairwise "
    "comparisons spanning state-of-the-art generative models and real-world "
    "images across quality levels. Higher HPSv3 scores indicate stronger "
    "human-aligned image quality and preference alignment."
)
DATASET_SHORT_DESCRIPTION = (
    "VLM-based human preference score for wide-spectrum text-to-image "
    "evaluation, trained on the HPDv3 preference dataset."
)

METRIC_NAME = "HPSv3 Score"
METRIC_DIRECTION = "higher_is_better"
METRIC_FULL_NAME = "Human Preference Score v3"
METRIC_SCALE = "unbounded"
METRIC_DESCRIPTION = (
    "Automated human-preference score from the HPSv3 VLM preference model; "
    "higher is better."
)


def _get_paper(session: Session) -> DBPaper:
    paper = (
        session.query(DBPaper)
        .filter(DBPaper.arxiv_id == HPSV3_ARXIV_ID, DBPaper.is_latest_version)
        .one_or_none()
    )
    if paper is None:
        raise RuntimeError(f"HPSv3 paper (arxiv_id={HPSV3_ARXIV_ID}) not found in DB")
    return paper


def _get_task(session: Session) -> DBTask:
    task = session.query(DBTask).filter(DBTask.slug == TASK_SLUG).one_or_none()
    if task is None:
        raise RuntimeError(f"Task slug={TASK_SLUG!r} not found in DB")
    return task


def _ensure_dataset(session: Session, paper: DBPaper) -> DBDataset:
    dataset = (
        session.query(DBDataset).filter(DBDataset.slug == DATASET_SLUG).one_or_none()
    )

    if dataset is None:
        dataset = DBDataset(
            name=DATASET_NAME,
            slug=DATASET_SLUG,
            full_name=DATASET_FULL_NAME,
            description=DATASET_DESCRIPTION,
            short_description=DATASET_SHORT_DESCRIPTION,
            url=DATASET_HOMEPAGE,
            hf_url=DATASET_HOMEPAGE,
            homepage=DATASET_HOMEPAGE,
            paper_url=PAPER_URL,
            introducing_paper_id=paper.id,
            introducing_paper_title=paper.title,
            introduced_date=paper.date_published,
            modalities=["Image"],
        )
        session.add(dataset)
        session.flush()
        logger.info(
            "Created dataset %r (id=%s, slug=%s)",
            dataset.name,
            dataset.id,
            dataset.slug,
        )
        return dataset

    changed = False
    updates = {
        "full_name": DATASET_FULL_NAME,
        "description": DATASET_DESCRIPTION,
        "short_description": DATASET_SHORT_DESCRIPTION,
        "url": DATASET_HOMEPAGE,
        "hf_url": DATASET_HOMEPAGE,
        "homepage": DATASET_HOMEPAGE,
        "paper_url": PAPER_URL,
        "introducing_paper_id": paper.id,
        "introducing_paper_title": paper.title,
        "modalities": ["Image"],
    }
    for field, value in updates.items():
        if getattr(dataset, field) != value:
            setattr(dataset, field, value)
            changed = True
    if dataset.introduced_date is None and paper.date_published is not None:
        dataset.introduced_date = paper.date_published
        changed = True

    if changed:
        session.flush()
        logger.info("Updated existing dataset %r (id=%s)", dataset.name, dataset.id)
    else:
        logger.info("Dataset %r already up-to-date (id=%s)", dataset.name, dataset.id)
    return dataset


def _ensure_metric(session: Session) -> int:
    row = session.execute(
        text("SELECT id, direction, full_name, scale FROM metrics WHERE name = :n"),
        {"n": METRIC_NAME},
    ).fetchone()
    if row is not None:
        metric_id = int(row[0])
        if row[1] != METRIC_DIRECTION:
            session.execute(
                text("UPDATE metrics SET direction = :d WHERE id = :id"),
                {"d": METRIC_DIRECTION, "id": metric_id},
            )
        if not row[2]:
            session.execute(
                text("UPDATE metrics SET full_name = :f WHERE id = :id"),
                {"f": METRIC_FULL_NAME, "id": metric_id},
            )
        if not row[3]:
            session.execute(
                text("UPDATE metrics SET scale = :s WHERE id = :id"),
                {"s": METRIC_SCALE, "id": metric_id},
            )
        logger.info("Reusing metric %r (id=%s)", METRIC_NAME, metric_id)
        return metric_id

    metric_id = session.execute(
        text(
            "INSERT INTO metrics (name, direction, full_name, scale, description) "
            "VALUES (:n, :d, :f, :s, :desc) RETURNING id"
        ),
        {
            "n": METRIC_NAME,
            "d": METRIC_DIRECTION,
            "f": METRIC_FULL_NAME,
            "s": METRIC_SCALE,
            "desc": METRIC_DESCRIPTION,
        },
    ).scalar_one()
    logger.info(
        "Created metric %r (id=%s, direction=%s)",
        METRIC_NAME,
        metric_id,
        METRIC_DIRECTION,
    )
    return int(metric_id)


def _ensure_task_dataset(session: Session, task_id: int, dataset_id: int) -> None:
    session.execute(
        text(
            "INSERT INTO task_datasets (task_id, dataset_id, supports_harness) "
            "VALUES (:t, :d, FALSE) "
            "ON CONFLICT (task_id, dataset_id) DO NOTHING"
        ),
        {"t": task_id, "d": dataset_id},
    )


def _ensure_task_dataset_metric(
    session: Session, task_id: int, dataset_id: int, metric_id: int
) -> None:
    session.execute(
        text(
            "INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id) "
            "VALUES (:t, :d, :m) "
            "ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING"
        ),
        {"t": task_id, "d": dataset_id, "m": metric_id},
    )


def _promote_paper_task_to_manual(
    session: Session, paper_id: int, task_id: int
) -> None:
    session.execute(
        text(
            "INSERT INTO paper_tasks (paper_id, task_id, source) "
            "VALUES (:p, :t, 'manual') "
            "ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'"
        ),
        {"p": paper_id, "t": task_id},
    )


def main() -> None:
    session = db_manager.session_local()
    try:
        paper = _get_paper(session)
        task = _get_task(session)
        logger.info(
            "Source paper id=%s arxiv=%s; task id=%s slug=%s",
            paper.id,
            paper.arxiv_id,
            task.id,
            task.slug,
        )

        dataset = _ensure_dataset(session, paper)
        metric_id = _ensure_metric(session)
        _ensure_task_dataset(session, task.id, dataset.id)
        _ensure_task_dataset_metric(session, task.id, dataset.id, metric_id)
        _promote_paper_task_to_manual(session, paper.id, task.id)
        session.commit()
        logger.info(
            "Wired (task_id=%s, dataset_id=%s, metric_id=%s, slug=%s)",
            task.id,
            dataset.id,
            metric_id,
            dataset.slug,
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
