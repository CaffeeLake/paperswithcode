"""Split CharXiv into separate DQ and RQ leaderboards.

CharXiv reports two distinct tracks — Descriptive Questions (DQ) and Reasoning
Questions (RQ) — that must not share a single Accuracy leaderboard.

Run with:

    uv run --env-file backend/keys.env \\
        python backend/database/datasets_setup/split_charxiv_dq_rq.py
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.database.evaluations_setup.evaluation_helpers import (
    get_or_create_evaluation,
)
from backend.models.database import Dataset as DBDataset
from backend.services.evaluation_service import EvaluationService

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

PARENT_DATASET_ID = 432
TASK_SLUG = "image-understanding"
METRIC_NAME = "Accuracy"
CHARXIV_ARXIV_ID = "2406.18521"

DQ_DATASET_NAME = "CharXiv (DQ)"
DQ_DATASET_SLUG = "charxiv-dq"
RQ_DATASET_NAME = "CharXiv (RQ)"
RQ_DATASET_SLUG = "charxiv-rq"

DQ_DESCRIPTION = (
    "CharXiv Descriptive Questions (DQ): chart understanding via descriptive "
    "QA over scientific figures from arXiv papers."
)
RQ_DESCRIPTION = (
    "CharXiv Reasoning Questions (RQ): chart reasoning QA requiring multi-step "
    "inference over scientific figures from arXiv papers."
)

PARENT_DESCRIPTION = (
    "CharXiv is a benchmark for realistic chart understanding in multimodal LLMs. "
    "It has two evaluation tracks that are reported separately: "
    "Descriptive Questions (DQ) and Reasoning Questions (RQ). "
    "See the DQ and RQ leaderboards for comparable results."
)

# Evaluations whose scores belong on the DQ leaderboard.
DQ_EVAL_IDS = [1199, 4750, 4751, 8781, 1280]

# Evaluations whose scores belong on the RQ leaderboard (all remaining rows).
RQ_EVAL_IDS = [
    9128,
    8284,
    1009,
    1200,
    1008,
    8874,
    8309,
    5561,
    5560,
    8887,
    1247,
    8900,
    8852,
    5328,
    6347,
    4752,
    4753,
    1149,
    8321,
    5971,
    8780,
    1281,
    6883,
    1119,
]


def _get_task_id(session: Session) -> int:
    task_id = session.execute(
        text("SELECT id FROM tasks WHERE slug = :slug"), {"slug": TASK_SLUG}
    ).scalar_one()
    return task_id


def _get_metric_id(session: Session) -> int:
    return session.execute(
        text("SELECT id FROM metrics WHERE name = :n"), {"n": METRIC_NAME}
    ).scalar_one()


def _get_parent(session: Session) -> DBDataset:
    parent = (
        session.query(DBDataset).filter(DBDataset.id == PARENT_DATASET_ID).one_or_none()
    )
    if parent is None:
        raise RuntimeError(f"CharXiv parent dataset id={PARENT_DATASET_ID} not found")
    return parent


def _ensure_child_dataset(
    session: Session,
    parent: DBDataset,
    *,
    name: str,
    slug: str,
    description: str,
    variant_type: str,
) -> DBDataset:
    dataset = session.query(DBDataset).filter(DBDataset.slug == slug).one_or_none()
    if dataset is None:
        dataset = DBDataset(
            name=name,
            slug=slug,
            description=description,
            hf_url=parent.hf_url,
            homepage=parent.homepage,
            paper_url=parent.paper_url,
            introducing_paper_id=parent.introducing_paper_id,
            introducing_paper_title=parent.introducing_paper_title,
            introduced_year=parent.introduced_year,
            parent_dataset_id=parent.id,
            variant_type=variant_type,
        )
        session.add(dataset)
        session.flush()
        logger.info("Created dataset %r (id=%s)", dataset.name, dataset.id)
        return dataset

    dataset.description = description
    dataset.parent_dataset_id = parent.id
    dataset.variant_type = variant_type
    dataset.paper_url = parent.paper_url
    dataset.introducing_paper_id = parent.introducing_paper_id
    dataset.introducing_paper_title = parent.introducing_paper_title
    dataset.hf_url = parent.hf_url
    dataset.homepage = parent.homepage
    session.flush()
    logger.info("Updated dataset %r (id=%s)", dataset.name, dataset.id)
    return dataset


def _ensure_task_links(
    session: Session, task_id: int, dataset_id: int, metric_id: int
) -> None:
    session.execute(
        text(
            "INSERT INTO task_datasets (task_id, dataset_id) "
            "VALUES (:t, :d) ON CONFLICT (task_id, dataset_id) DO NOTHING"
        ),
        {"t": task_id, "d": dataset_id},
    )
    session.execute(
        text(
            "INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id) "
            "VALUES (:t, :d, :m) ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING"
        ),
        {"t": task_id, "d": dataset_id, "m": metric_id},
    )


def _unlink_parent_from_task(session: Session, task_id: int, parent_id: int) -> None:
    session.execute(
        text("DELETE FROM task_datasets WHERE task_id = :t AND dataset_id = :d"),
        {"t": task_id, "d": parent_id},
    )
    session.execute(
        text("DELETE FROM task_dataset_metrics WHERE task_id = :t AND dataset_id = :d"),
        {"t": task_id, "d": parent_id},
    )


def _migrate_evaluations(
    session: Session,
    service: EvaluationService,
    *,
    task_id: int,
    dq_dataset_id: int,
    rq_dataset_id: int,
) -> None:
    for eval_id in DQ_EVAL_IDS:
        service.update_evaluation(evaluation_id=eval_id, dataset_id=dq_dataset_id)
        logger.info("Moved evaluation %s -> CharXiv (DQ)", eval_id)

    for eval_id in RQ_EVAL_IDS:
        service.update_evaluation(evaluation_id=eval_id, dataset_id=rq_dataset_id)
        logger.info("Moved evaluation %s -> CharXiv (RQ)", eval_id)

    service.recalculate_ranks(task_id, dq_dataset_id, metric_name=METRIC_NAME)
    service.recalculate_ranks(task_id, rq_dataset_id, metric_name=METRIC_NAME)


def _add_internvl3_dq(session: Session, task_id: int, dq_dataset_id: int) -> None:
    get_or_create_evaluation(
        session,
        paper_id=47682,
        task_id=task_id,
        dataset_id=dq_dataset_id,
        model_name="InternVL3-78B",
        metrics={"Accuracy": "85.1"},
        methodology=(
            "arXiv 2504.10479 Table 3; InternVL3-78B CharXiv Descriptive Questions "
            "(DQ) track. Source reports CharXiv as RQ / DQ = 46.0 / 85.1."
        ),
        best_metric=METRIC_NAME,
        external_source_url="https://arxiv.org/abs/2504.10479",
        is_open=True,
    )
    logger.info("Added InternVL3-78B evaluation on CharXiv (DQ)")


def main() -> None:
    session = db_manager.session_local()
    try:
        parent = _get_parent(session)
        parent.description = PARENT_DESCRIPTION
        task_id = _get_task_id(session)
        metric_id = _get_metric_id(session)

        dq = _ensure_child_dataset(
            session,
            parent,
            name=DQ_DATASET_NAME,
            slug=DQ_DATASET_SLUG,
            description=DQ_DESCRIPTION,
            variant_type="subset",
        )
        rq = _ensure_child_dataset(
            session,
            parent,
            name=RQ_DATASET_NAME,
            slug=RQ_DATASET_SLUG,
            description=RQ_DESCRIPTION,
            variant_type="subset",
        )

        _ensure_task_links(session, task_id, dq.id, metric_id)
        _ensure_task_links(session, task_id, rq.id, metric_id)
        _unlink_parent_from_task(session, task_id, parent.id)
        session.commit()

        service = EvaluationService(session)
        _migrate_evaluations(
            session,
            service,
            task_id=task_id,
            dq_dataset_id=dq.id,
            rq_dataset_id=rq.id,
        )
        _add_internvl3_dq(session, task_id, dq.id)
        service.recalculate_ranks(task_id, dq.id, metric_name=METRIC_NAME)
        session.commit()

        dq_count = session.execute(
            text("SELECT COUNT(*) FROM evaluations WHERE dataset_id = :d"),
            {"d": dq.id},
        ).scalar_one()
        rq_count = session.execute(
            text("SELECT COUNT(*) FROM evaluations WHERE dataset_id = :d"),
            {"d": rq.id},
        ).scalar_one()
        parent_count = session.execute(
            text("SELECT COUNT(*) FROM evaluations WHERE dataset_id = :d"),
            {"d": parent.id},
        ).scalar_one()

        logger.info(
            "Done. parent evals=%s, DQ evals=%s (slug=%s), RQ evals=%s (slug=%s)",
            parent_count,
            dq_count,
            dq.slug,
            rq_count,
            rq.slug,
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
