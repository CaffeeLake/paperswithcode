#!/usr/bin/env python3
"""add-evals follow-up: Faster R-CNN COCO + Copy-Paste COCO/VOC2012 semseg."""

from __future__ import annotations

import logging

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.models.database import Evaluation as DBEvaluation
from backend.services.evaluation_service import EvaluationService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

EVALS = [
    {
        "arxiv_id": "1506.01497",
        "task_id": 2,
        "dataset_id": 3,
        "model_name": "Faster R-CNN (VGG-16)",
        "best_metric": "mAP",
        "score": "21.9",
        "methodology": (
            "COCO test-dev; mAP@[0.5:0.95] from Table 11 (Faster R-CNN, RPN 300 proposals). "
            "Trained on COCO trainval; VGG-16; single-scale testing (s=600)."
        ),
    },
    {
        "arxiv_id": "2012.07177",
        "task_id": 2,
        "dataset_id": 3,
        "model_name": "Cascade Eff-B7 NAS-FPN (self-training Copy-Paste)",
        "best_metric": "mAP",
        "score": "57.3",
        "num_parameters": 185_000_000,
        "methodology": (
            "COCO test-dev box AP from Table 4 (1280 input). "
            "Cascade Mask R-CNN with EfficientNet-B7 + NAS-FPN; Copy-Paste plus "
            "self-training on unlabeled COCO and Objects365; no test-time augmentation."
        ),
    },
    {
        "arxiv_id": "2012.07177",
        "task_id": 3,
        "dataset_id": 417,
        "model_name": "Cascade Eff-B7 NAS-FPN (self-training Copy-Paste)",
        "best_metric": "mAP",
        "score": "49.1",
        "num_parameters": 185_000_000,
        "methodology": (
            "COCO test-dev mask AP from Table 4 (1280 input). "
            "Same setup as detection row: Copy-Paste + self-training; no TTA."
        ),
    },
    {
        "arxiv_id": "2012.07177",
        "task_id": 3,
        "dataset_id": 271,
        "model_name": "Eff-B7 NAS-FPN (Copy-Paste pre-training)",
        "best_metric": "mIoU",
        "score": "86.6",
        "methodology": (
            "PASCAL VOC 2012 val; mIoU from Table 6. "
            "COCO Copy-Paste pre-training then fine-tuned on VOC 2012 segmentation train."
        ),
    },
]


def ensure_paper_task(session, paper_id: int, task_id: int) -> None:
    exists = session.execute(
        text("SELECT 1 FROM paper_tasks WHERE paper_id = :p AND task_id = :t LIMIT 1"),
        {"p": paper_id, "t": task_id},
    ).first()
    if exists:
        return
    session.execute(
        text(
            "INSERT INTO paper_tasks (paper_id, task_id, source) "
            "VALUES (:p, :t, 'manual') ON CONFLICT DO NOTHING"
        ),
        {"p": paper_id, "t": task_id},
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
            ensure_paper_task(session, paper_id, spec["task_id"])
            session.commit()

            source_url = f"https://arxiv.org/abs/{spec['arxiv_id']}"
            exists = (
                session.query(DBEvaluation)
                .filter(
                    DBEvaluation.paper_id == paper_id,
                    DBEvaluation.task_id == spec["task_id"],
                    DBEvaluation.dataset_id == spec["dataset_id"],
                    DBEvaluation.model_name == spec["model_name"],
                    DBEvaluation.best_metric == spec["best_metric"],
                )
                .first()
            )
            if exists:
                skipped += 1
                logger.info(
                    "Skip existing %s / %s / %s",
                    spec["arxiv_id"],
                    spec["model_name"],
                    spec["best_metric"],
                )
                continue

            kwargs = dict(
                paper_id=paper_id,
                task_id=spec["task_id"],
                dataset_id=spec["dataset_id"],
                model_name=spec["model_name"],
                methodology=spec["methodology"],
                metrics={spec["best_metric"]: spec["score"]},
                best_metric=spec["best_metric"],
                source_url=source_url,
                is_open=True,
            )
            if spec.get("num_parameters") is not None:
                kwargs["num_parameters"] = spec["num_parameters"]

            service.create_evaluation(**kwargs)
            created += 1
            logger.info(
                "Created %s / %s / %s = %s on dataset %s",
                spec["arxiv_id"],
                spec["model_name"],
                spec["best_metric"],
                spec["score"],
                spec["dataset_id"],
            )
        logger.info("Done: %s created, %s skipped", created, skipped)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
