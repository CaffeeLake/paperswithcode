"""Add LiveCodeBench (v5) and migrate mis-versioned evaluations off v6.

Creates the v5 leaderboard for coding-agents, transfers evaluations that
explicitly report LiveCodeBench v5 (or the v5 date window), keeps generic
"LiveCodeBench" rows on v6, and deletes evaluations on older/non-v6 slices.

Run with:

    uv run --env-file backend/keys.env \\
        python backend/database/datasets_setup/add_livecodebench_v5_and_migrate_evals.py
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
from backend.services.evaluation_service import EvaluationService

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

LCB_ARXIV_ID = "2403.07974"
TASK_SLUG = "coding-agents"
V6_DATASET_ID = 95
METRIC_NAME = "Pass@1"

DATASET_NAME = "LiveCodeBench (v5)"
DATASET_SLUG = "livecodebench-v5"
PAPER_URL = f"https://paperswithcode.co/paper/{LCB_ARXIV_ID}"

DATASET_DESCRIPTION = (
    "LiveCodeBench release_v5: problems released between May 2023 and January 2025 "
    "(880 problems). Holistic, contamination-free code evaluation spanning code "
    "generation, execution, and test-output prediction."
)

# Evaluations to move from livecodebench-v6 -> livecodebench-v5.
TRANSFER_EVAL_IDS = [
    7568,  # Nemotron 3 Super (v5)
    7086,  # Llama 4 Maverick
    7077,  # Llama 4 Scout
    6140,  # dots.llm1.inst
    4917,  # Qwen3 non-thinking (v5)
    695,  # Qwen3 thinking (v5)
    4860,  # GLM-4.5-Air (2407-2501)
    628,  # GLM-4.5 355B
    359,  # Gemini 2.5 Pro (v5 window in paper)
    358,  # Gemini 2.5 Flash
]

# Evaluations on pre-v5 / unrelated LiveCodeBench slices — remove from v6.
DELETE_EVAL_IDS = [
    6065,  # DeepSeek-V2 (Sep 2023 - Apr 2024)
    6025,  # DeepSeek-V3 (Aug-Nov 2024)
    947,  # Qwen2.5 (2305-2409)
]


def _get_paper(session: Session) -> DBPaper:
    paper = (
        session.query(DBPaper)
        .filter(DBPaper.arxiv_id == LCB_ARXIV_ID, DBPaper.is_latest_version)
        .one_or_none()
    )
    if paper is None:
        raise RuntimeError(f"LiveCodeBench paper arxiv_id={LCB_ARXIV_ID} not found")
    return paper


def _get_task(session: Session) -> DBTask:
    task = session.query(DBTask).filter(DBTask.slug == TASK_SLUG).one_or_none()
    if task is None:
        raise RuntimeError(f"Task slug={TASK_SLUG!r} not found")
    return task


def _get_v6_dataset(session: Session) -> DBDataset:
    dataset = (
        session.query(DBDataset).filter(DBDataset.id == V6_DATASET_ID).one_or_none()
    )
    if dataset is None:
        raise RuntimeError(f"LiveCodeBench v6 dataset id={V6_DATASET_ID} not found")
    return dataset


def _ensure_v5_dataset(session: Session, paper: DBPaper, v6: DBDataset) -> DBDataset:
    dataset = (
        session.query(DBDataset).filter(DBDataset.slug == DATASET_SLUG).one_or_none()
    )

    if dataset is None:
        dataset = DBDataset(
            name=DATASET_NAME,
            slug=DATASET_SLUG,
            description=DATASET_DESCRIPTION,
            hf_url=v6.hf_url,
            homepage=v6.homepage,
            paper_url=PAPER_URL,
            introducing_paper_id=paper.id,
            introducing_paper_title=paper.title,
            introduced_year=v6.introduced_year,
            parent_dataset_id=v6.parent_dataset_id,
        )
        session.add(dataset)
        session.flush()
        logger.info("Created dataset %r (id=%s)", dataset.name, dataset.id)
        return dataset

    dataset.description = DATASET_DESCRIPTION
    dataset.paper_url = PAPER_URL
    dataset.introducing_paper_id = paper.id
    dataset.introducing_paper_title = paper.title
    dataset.hf_url = v6.hf_url
    dataset.homepage = v6.homepage
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


def _migrate_evaluations(session: Session, v5_dataset_id: int, task_id: int) -> None:
    service = EvaluationService(session)

    for eval_id in TRANSFER_EVAL_IDS:
        service.update_evaluation(evaluation_id=eval_id, dataset_id=v5_dataset_id)
        logger.info("Transferred evaluation %s -> dataset %s", eval_id, v5_dataset_id)

    for eval_id in DELETE_EVAL_IDS:
        service.delete_evaluation(eval_id)
        logger.info("Deleted evaluation %s", eval_id)

    service.recalculate_ranks(task_id, V6_DATASET_ID, metric_name=METRIC_NAME)
    service.recalculate_ranks(task_id, v5_dataset_id, metric_name=METRIC_NAME)


def main() -> None:
    session = db_manager.session_local()
    try:
        paper = _get_paper(session)
        task = _get_task(session)
        v6 = _get_v6_dataset(session)
        v5 = _ensure_v5_dataset(session, paper, v6)

        metric_id = session.execute(
            text("SELECT id FROM metrics WHERE name = :n"), {"n": METRIC_NAME}
        ).scalar_one()

        _ensure_task_links(session, task.id, v5.id, metric_id)
        _promote_paper_task_to_manual(session, paper.id, task.id)
        session.commit()

        _migrate_evaluations(session, v5.id, task.id)
        session.commit()

        v6_count = session.execute(
            text("SELECT COUNT(*) FROM evaluations WHERE dataset_id = :d"),
            {"d": V6_DATASET_ID},
        ).scalar_one()
        v5_count = session.execute(
            text("SELECT COUNT(*) FROM evaluations WHERE dataset_id = :d"),
            {"d": v5.id},
        ).scalar_one()

        logger.info(
            "Done. v6 evals=%s, v5 evals=%s, v5 dataset slug=%s paper_url=%s",
            v6_count,
            v5_count,
            v5.slug,
            v5.paper_url,
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
