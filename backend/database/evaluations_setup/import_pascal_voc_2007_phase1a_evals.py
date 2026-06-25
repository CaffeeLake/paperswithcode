#!/usr/bin/env python3
"""Import Phase 1A legacy PASCAL VOC 2007 evals (YOLO, Faster R-CNN, Copy-Paste)."""

from __future__ import annotations

import logging

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.models.database import Evaluation as DBEvaluation
from backend.services.evaluation_service import EvaluationService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TASK_ID = 2
DATASET_ID = 331
BEST_METRIC = "mAP"

EVALS = [
    {
        "arxiv_id": "1506.02640",
        "model_name": "YOLO",
        "score": "63.4",
        "methodology": (
            "PASCAL VOC 2007 test; mAP from Table 1 (real-time detectors). "
            "Trained on VOC 2007+2012 trainval; single-scale inference."
        ),
    },
    {
        "arxiv_id": "1506.01497",
        "model_name": "Faster R-CNN",
        "score": "73.2",
        "methodology": (
            "PASCAL VOC 2007 test; mAP from Table 3 (RPN+VGG, shared features). "
            "Trained on union of VOC 2007 trainval and VOC 2012 trainval."
        ),
    },
    {
        "arxiv_id": "2012.07177",
        "model_name": "Cascade Eff-B7 NAS-FPN (Copy-Paste pre-training)",
        "score": "89.3",
        "methodology": (
            "PASCAL VOC 2007 test; AP50 from Table 5 (reported as VOC detection AP). "
            "COCO Copy-Paste pre-training, then fine-tuned on VOC 2007+2012 trainval."
        ),
    },
]


def ensure_paper_task(session, paper_id: int) -> None:
    exists = session.execute(
        text("SELECT 1 FROM paper_tasks WHERE paper_id = :p AND task_id = :t LIMIT 1"),
        {"p": paper_id, "t": TASK_ID},
    ).first()
    if exists:
        return
    session.execute(
        text(
            "INSERT INTO paper_tasks (paper_id, task_id, source) "
            "VALUES (:p, :t, 'manual') ON CONFLICT DO NOTHING"
        ),
        {"p": paper_id, "t": TASK_ID},
    )


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
                    DBEvaluation.dataset_id == DATASET_ID,
                    DBEvaluation.model_name == spec["model_name"],
                    DBEvaluation.best_metric == BEST_METRIC,
                )
                .first()
            )
            if exists:
                skipped += 1
                logger.info(
                    "Skip existing %s / %s", spec["arxiv_id"], spec["model_name"]
                )
                continue

            service.create_evaluation(
                paper_id=paper_id,
                task_id=TASK_ID,
                dataset_id=DATASET_ID,
                model_name=spec["model_name"],
                methodology=spec["methodology"],
                metrics={BEST_METRIC: spec["score"]},
                best_metric=BEST_METRIC,
                source_url=source_url,
                is_open=True,
            )
            created += 1
            logger.info(
                "Created %s / %s / %s = %s",
                spec["arxiv_id"],
                spec["model_name"],
                BEST_METRIC,
                spec["score"],
            )
        logger.info("Done: %s created, %s skipped", created, skipped)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
