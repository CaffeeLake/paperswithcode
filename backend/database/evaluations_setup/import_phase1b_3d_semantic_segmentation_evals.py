#!/usr/bin/env python3
"""Import Phase 1B 3D semantic segmentation evals (PTv3 + PPT on ScanNet200)."""

from __future__ import annotations

import logging

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.database.evaluations_setup.import_scannet_benchmark_evals import (
    link_paper_task,
)
from backend.models.database import Evaluation as DBEvaluation
from backend.services.evaluation_service import EvaluationService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TASK_ID = 326
BEST_METRIC = "mIoU"

EVALS = [
    {
        "arxiv_id": "2410.13924",
        "dataset_id": 675,
        "model_name": "PTv3 ArKitLabelmaker",
        "score": "41.4",
        "methodology": (
            "ScanNet200 hidden test mIoU from Table 2 PPT(Ours) row (PTv3 + PPT "
            "joint training on ScanNet, ScanNet200, ScanNet++, Structured3D, and "
            "ARKit LabelMaker). Paper val mIoU is 37.5; imported test split per "
            "leaderboard convention. Legacy queue val=40.3 does not appear in paper."
        ),
    },
]

SKIPPED = [
    (
        "2410.13924",
        "PTv3 ArKitLabelmaker",
        "ScanNet200 val mIoU",
        "Only test mIoU imported (41.4); val mIoU in paper Table 2 is 37.5, not "
        "legacy CSV 40.3.",
    ),
]


def ensure_paper_task(session, paper_id: int) -> None:
    link_paper_task(session, paper_id, TASK_ID)


def main() -> None:
    session = db_manager.session_local()
    created = skipped = 0
    try:
        service = EvaluationService(session)
        for spec in EVALS:
            session.rollback()
            paper = session.execute(
                text(
                    "SELECT id FROM papers "
                    "WHERE arxiv_id = :a AND is_latest_version LIMIT 1"
                ),
                {"a": spec["arxiv_id"]},
            ).first()
            if not paper:
                raise RuntimeError(f"Paper {spec['arxiv_id']} not in DB")
            paper_id = int(paper.id)
            ensure_paper_task(session, paper_id)
            session.commit()

            source_url = f"https://arxiv.org/abs/{spec['arxiv_id']}"
            exists = (
                session.query(DBEvaluation)
                .filter(
                    DBEvaluation.paper_id == paper_id,
                    DBEvaluation.task_id == TASK_ID,
                    DBEvaluation.dataset_id == spec["dataset_id"],
                    DBEvaluation.model_name == spec["model_name"],
                    DBEvaluation.best_metric == BEST_METRIC,
                )
                .first()
            )
            if exists:
                skipped += 1
                logger.info(
                    "Skip existing %s / %s / dataset=%s",
                    spec["arxiv_id"],
                    spec["model_name"],
                    spec["dataset_id"],
                )
                continue

            service.create_evaluation(
                paper_id=paper_id,
                task_id=TASK_ID,
                dataset_id=spec["dataset_id"],
                model_name=spec["model_name"],
                methodology=spec["methodology"],
                metrics={BEST_METRIC: spec["score"]},
                best_metric=BEST_METRIC,
                source_url=source_url,
                is_open=True,
            )
            created += 1
            logger.info(
                "Created %s / %s / dataset=%s / %s = %s",
                spec["arxiv_id"],
                spec["model_name"],
                spec["dataset_id"],
                BEST_METRIC,
                spec["score"],
            )
        logger.info("Done: %s created, %s skipped", created, skipped)
        for arxiv_id, model, benchmark, reason in SKIPPED:
            logger.info("Skipped %s / %s on %s: %s", arxiv_id, model, benchmark, reason)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
