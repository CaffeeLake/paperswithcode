"""Add GIFT-Eval benchmark to the database (benchmark wiring only).

This script wires up the GIFT-Eval benchmark for the
``Time-series forecasting`` task. It is idempotent and does NOT create
evaluation rows or per-model paper rows. Evaluation import is handled by
a separate, manifest-driven script that runs after the manifest is
reviewed (see ``build_gift_eval_manifest.py``).

Steps:
  1. Resolve the source paper row (arxiv_id=2410.10393).
  2. Create or update the ``GIFT-Eval`` dataset with
     ``paper_url=https://paperswithcode.co/paper/2410.10393``,
     ``introducing_paper_id`` set, and HF Space + GitHub links populated.
  3. Ensure the ``MASE`` metric exists with ``lower_is_better`` direction.
  4. Idempotently link
     ``(time-series-forecasting, GIFT-Eval)`` via ``task_datasets`` and
     ``(time-series-forecasting, GIFT-Eval, MASE)`` via
     ``task_dataset_metrics``.
  5. Promote the GIFT-Eval source paper's task tag for
     ``time-series-forecasting`` to ``source='manual'`` so the keyword
     cron does not strip it.

Run with:

    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/add_gift_eval_benchmark.py
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

GIFT_EVAL_ARXIV_ID = "2410.10393"
TASK_SLUG = "time-series-forecasting"
DATASET_NAME = "GIFT-Eval"
DATASET_SLUG = slugify(DATASET_NAME)
DATASET_FULL_NAME = (
    "GIFT-Eval: A Benchmark For General Time Series Forecasting Model Evaluation"
)
DATASET_HOMEPAGE = "https://huggingface.co/spaces/Salesforce/GIFT-Eval"
DATASET_GITHUB = "https://github.com/SalesforceAIResearch/gift-eval"
PAPER_URL = f"https://paperswithcode.co/paper/{GIFT_EVAL_ARXIV_ID}"

DATASET_DESCRIPTION = (
    "GIFT-Eval is a comprehensive benchmark for general time-series forecasting. "
    "It spans 24 datasets, ~144,000 series, and ~177M data points across seven "
    "domains (Econ/Fin, Energy, Healthcare, Nature, Sales, Transport, "
    "Web/CloudOps), 10 frequencies, multiple prediction horizons, and both "
    "univariate and multivariate setups. The companion non-leaking pretraining "
    "corpus contains ~230B data points across 88 datasets. Models are ranked "
    "by MASE (point) and CRPS (probabilistic, mean weighted sum quantile loss)."
)
DATASET_SHORT_DESCRIPTION = (
    "General time-series forecasting benchmark spanning 24 datasets, 7 domains, "
    "and 10 frequencies; ranks models by MASE and CRPS."
)

METRIC_NAME = "MASE"
METRIC_DIRECTION = "lower_is_better"
METRIC_FULL_NAME = "Mean Absolute Scaled Error (geometric mean over GIFT-Eval slices)"
METRIC_SCALE = "unbounded"
METRIC_DESCRIPTION = (
    "Mean Absolute Scaled Error normalised by Seasonal Naive on each "
    "(dataset, frequency, horizon) slice; lower is better. The GIFT-Eval "
    "leaderboard reports the geometric mean of MASE across all slices "
    "alongside an average MASE rank."
)


def _get_paper(session: Session) -> DBPaper:
    paper = (
        session.query(DBPaper)
        .filter(DBPaper.arxiv_id == GIFT_EVAL_ARXIV_ID, DBPaper.is_latest_version)
        .one_or_none()
    )
    if paper is None:
        raise RuntimeError(
            f"GIFT-Eval paper (arxiv_id={GIFT_EVAL_ARXIV_ID}) not found in DB"
        )
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
            url=DATASET_GITHUB,
            hf_url=DATASET_HOMEPAGE,
            homepage=DATASET_HOMEPAGE,
            paper_url=PAPER_URL,
            introducing_paper_id=paper.id,
            introducing_paper_title=paper.title,
            introduced_date=paper.date_published,
            modalities=["Time Series"],
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
    if dataset.full_name != DATASET_FULL_NAME:
        dataset.full_name = DATASET_FULL_NAME
        changed = True
    if dataset.description != DATASET_DESCRIPTION:
        dataset.description = DATASET_DESCRIPTION
        changed = True
    if dataset.short_description != DATASET_SHORT_DESCRIPTION:
        dataset.short_description = DATASET_SHORT_DESCRIPTION
        changed = True
    if dataset.url != DATASET_GITHUB:
        dataset.url = DATASET_GITHUB
        changed = True
    if dataset.hf_url != DATASET_HOMEPAGE:
        dataset.hf_url = DATASET_HOMEPAGE
        changed = True
    if dataset.homepage != DATASET_HOMEPAGE:
        dataset.homepage = DATASET_HOMEPAGE
        changed = True
    if dataset.paper_url != PAPER_URL:
        dataset.paper_url = PAPER_URL
        changed = True
    if dataset.introducing_paper_id != paper.id:
        dataset.introducing_paper_id = paper.id
        changed = True
    if dataset.introducing_paper_title != paper.title:
        dataset.introducing_paper_title = paper.title
        changed = True
    if dataset.introduced_date is None and paper.date_published is not None:
        dataset.introduced_date = paper.date_published
        changed = True
    if dataset.modalities != ["Time Series"]:
        dataset.modalities = ["Time Series"]
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
            logger.info(
                "Updated metric %r direction -> %s", METRIC_NAME, METRIC_DIRECTION
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
            "INSERT INTO task_datasets (task_id, dataset_id) "
            "VALUES (:t, :d) "
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
            "Wired (task_id=%s, dataset_id=%s, metric_id=%s)",
            task.id,
            dataset.id,
            metric_id,
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
