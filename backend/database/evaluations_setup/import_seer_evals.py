#!/usr/bin/env python3
"""Import SEER (2202.08360) evaluation rows from the paper and SEER README."""

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

ARXIV_ID = "2202.08360"
PAPER_ID = 7990
NUM_PARAMETERS = 10_000_000_000
SOURCE_URL = "https://arxiv.org/abs/2202.08360"

EVALS = [
    {
        "task_id": 1,
        "dataset_id": 72,
        "model_name": "SEER (RegNet10B)",
        "best_metric": "Accuracy",
        "score": "85.8",
        "methodology": (
            "ImageNet-1K validation top-1 from Table 7; RegNetY-10B pretrained on "
            "1B Instagram images, full fine-tuned on ImageNet-1K (384px inference)."
        ),
    },
    {
        "task_id": 1,
        "dataset_id": 483,
        "model_name": "SEER (RegNet10B)",
        "best_metric": "Accuracy",
        "score": "52.7",
        "methodology": (
            "ImageNet-A top-1 from Table 7 after ImageNet-1K fine-tuning of SEER "
            "RegNetY-10B (out-of-domain inference only)."
        ),
    },
    {
        "task_id": 1,
        "dataset_id": 279,
        "model_name": "SEER (RegNet10B)",
        "best_metric": "Accuracy",
        "score": "56.1",
        "methodology": (
            "ImageNet-R top-1 from Table 7 after ImageNet-1K fine-tuning of SEER "
            "RegNetY-10B (out-of-domain inference only)."
        ),
    },
    {
        "task_id": 1,
        "dataset_id": 280,
        "model_name": "SEER (RegNet10B)",
        "best_metric": "Accuracy",
        "score": "45.6",
        "methodology": (
            "ImageNet-Sketch top-1 from Table 7 after ImageNet-1K fine-tuning of "
            "SEER RegNetY-10B (out-of-domain inference only)."
        ),
    },
    {
        "task_id": 1,
        "dataset_id": 229,
        "model_name": "SEER (RegNet10B)",
        "best_metric": "Accuracy",
        "score": "89.8",
        "methodology": (
            "ImageNet-ReaL top-1 from Table 7 after ImageNet-1K fine-tuning of SEER "
            "RegNetY-10B (out-of-domain inference only)."
        ),
    },
    {
        "task_id": 1,
        "dataset_id": 278,
        "model_name": "SEER (RegNet10B)",
        "best_metric": "Accuracy",
        "score": "76.2",
        "methodology": (
            "ImageNet-V2 top-1 from Table 7 after ImageNet-1K fine-tuning of SEER "
            "RegNetY-10B (out-of-domain inference only)."
        ),
    },
    {
        "task_id": 1,
        "dataset_id": 268,
        "model_name": "SEER (RegNet10B)",
        "best_metric": "Accuracy",
        "score": "60.2",
        "methodology": (
            "ObjectNet top-1 from Table 7 after ImageNet-1K fine-tuning of SEER "
            "RegNetY-10B (out-of-domain inference only)."
        ),
    },
    {
        "task_id": 23,
        "dataset_id": 350,
        "model_name": "SEER (RegNet10B)",
        "best_metric": "mAP",
        "score": "90.6",
        "methodology": (
            "Copydays strong-subset copy detection mAP from Table 10 (CD10K setting "
            "with 10K YFCC distractors; R-MAC pooling, PCA whitening, 9500-dim "
            "features, 384px input)."
        ),
    },
    {
        "task_id": 8,
        "dataset_id": 636,
        "model_name": "SEER (RegNet10B)",
        "best_metric": "ROC-AUC",
        "score": "73.4",
        "methodology": (
            "HatefulMemes dev ROC-AUC from Table 6 (visual encoder + BERT-Base text "
            "encoder + MLP head; average over three seeds)."
        ),
    },
    {
        "task_id": 1,
        "dataset_id": 334,
        "model_name": "SEER (RegNet10B - finetuned - 384px)",
        "best_metric": "Accuracy",
        "score": "69.0",
        "methodology": (
            "Places205 top-1 from SEER README pretrained-model table and legacy PwC "
            "leaderboard; ImageNet-1K fine-tuned RegNetY-10B at 384px."
        ),
    },
    {
        "task_id": 1,
        "dataset_id": 592,
        "model_name": "SEER (RegNet10B - linear eval)",
        "best_metric": "Accuracy",
        "score": "80.0",
        "methodology": (
            "SUN397 linear probe from Appendix Table 17 / legacy PwC (frozen SEER "
            "RegNetY-10B trunk, logistic regression head)."
        ),
    },
    {
        "task_id": 1,
        "dataset_id": 590,
        "model_name": "SEER (RegNet10B - linear eval)",
        "best_metric": "Accuracy",
        "score": "90.3",
        "methodology": (
            "Food-101 linear probe from Appendix Table 17 / legacy PwC (frozen SEER "
            "RegNetY-10B trunk, logistic regression head)."
        ),
    },
    {
        "task_id": 1,
        "dataset_id": 359,
        "model_name": "SEER (RegNet10B - linear eval)",
        "best_metric": "Accuracy",
        "score": "80.5",
        "methodology": (
            "DTD linear probe from Appendix Table 17 / legacy PwC (frozen SEER "
            "RegNetY-10B trunk)."
        ),
    },
    {
        "task_id": 1,
        "dataset_id": 574,
        "model_name": "SEER (RegNet10B - linear eval)",
        "best_metric": "Accuracy",
        "score": "97.5",
        "methodology": (
            "EuroSAT linear probe from Appendix Table 17 / legacy PwC (frozen SEER "
            "RegNetY-10B trunk)."
        ),
    },
    {
        "task_id": 1,
        "dataset_id": 575,
        "model_name": "SEER (RegNet10B - linear eval)",
        "best_metric": "Accuracy",
        "score": "54.82",
        "methodology": (
            "FGVC Aircraft linear probe from Appendix Table 17 / legacy PwC (frozen "
            "SEER RegNetY-10B trunk)."
        ),
    },
    {
        "task_id": 1,
        "dataset_id": 223,
        "model_name": "SEER (RegNet10B - linear eval)",
        "best_metric": "Accuracy",
        "score": "96.3",
        "methodology": (
            "Oxford Flowers-102 linear probe from Appendix Table 17 / legacy PwC "
            "(frozen SEER RegNetY-10B trunk)."
        ),
    },
    {
        "task_id": 1,
        "dataset_id": 351,
        "model_name": "SEER (RegNet10B - linear eval)",
        "best_metric": "Accuracy",
        "score": "68.03",
        "methodology": (
            "Stanford Cars linear probe from Appendix Table 17 / legacy PwC (frozen "
            "SEER RegNetY-10B trunk)."
        ),
    },
    {
        "task_id": 1,
        "dataset_id": 221,
        "model_name": "SEER (RegNet10B - linear eval)",
        "best_metric": "Accuracy",
        "score": "90.0",
        "methodology": (
            "CIFAR-10 linear probe from Appendix Table 17 / legacy PwC (frozen SEER "
            "RegNetY-10B trunk)."
        ),
    },
    {
        "task_id": 1,
        "dataset_id": 222,
        "model_name": "SEER (RegNet10B - linear eval)",
        "best_metric": "Accuracy",
        "score": "81.53",
        "methodology": (
            "CIFAR-100 linear probe from Appendix Table 17 / legacy PwC (frozen SEER "
            "RegNetY-10B trunk)."
        ),
    },
    {
        "task_id": 261,
        "dataset_id": 681,
        "model_name": "SEER (RegNet10B - linear eval)",
        "best_metric": "Accuracy",
        "score": "51.9",
        "methodology": (
            "Kinetics-700 middle-frame linear probe from Appendix Table 17 / legacy "
            "PwC (frozen SEER RegNetY-10B trunk)."
        ),
    },
    {
        "task_id": 8,
        "dataset_id": 637,
        "model_name": "SEER (RegNet10B - linear eval)",
        "best_metric": "Accuracy",
        "score": "89.28",
        "methodology": (
            "CLEVR Count linear probe from Appendix Table 17 / legacy PwC (frozen "
            "SEER RegNetY-10B trunk)."
        ),
    },
]


def main() -> None:
    session = db_manager.session_local()
    created = skipped = 0
    try:
        paper = session.execute(
            text(
                "SELECT id FROM papers "
                "WHERE arxiv_id = :a AND is_latest_version LIMIT 1"
            ),
            {"a": ARXIV_ID},
        ).first()
        if not paper or int(paper.id) != PAPER_ID:
            raise RuntimeError(f"Expected paper_id {PAPER_ID} for {ARXIV_ID}")

        task_ids = sorted({spec["task_id"] for spec in EVALS})
        for task_id in task_ids:
            link_paper_task(session, PAPER_ID, task_id)
        session.commit()

        service = EvaluationService(session)
        for spec in EVALS:
            session.rollback()
            exists = (
                session.query(DBEvaluation)
                .filter(
                    DBEvaluation.paper_id == PAPER_ID,
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
                    "Skip existing %s / dataset=%s / %s",
                    spec["model_name"],
                    spec["dataset_id"],
                    spec["best_metric"],
                )
                continue

            service.create_evaluation(
                paper_id=PAPER_ID,
                task_id=spec["task_id"],
                dataset_id=spec["dataset_id"],
                model_name=spec["model_name"],
                methodology=spec["methodology"],
                metrics={spec["best_metric"]: spec["score"]},
                best_metric=spec["best_metric"],
                source_url=SOURCE_URL,
                num_parameters=NUM_PARAMETERS,
                is_open=True,
            )
            created += 1
            logger.info(
                "Created %s / dataset=%s / %s = %s",
                spec["model_name"],
                spec["dataset_id"],
                spec["best_metric"],
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
