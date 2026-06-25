#!/usr/bin/env python3
"""Import REACT and Semi-ViT papers + ImageNet 10% labeled evals."""

from __future__ import annotations

import asyncio
import logging


from backend.database.connection import db_manager
from backend.database.evaluations_setup.import_scannet_benchmark_evals import (
    ensure_arxiv_paper,
    link_paper_task,
)
from backend.models.database import Evaluation as DBEvaluation
from backend.services.evaluation_service import EvaluationService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TASK_ID = 342
DATASET_ID = 809

EVALS = [
    {
        "arxiv_id": "2301.07094",
        "model_name": "REACT (ViT-Large)",
        "best_metric": "Top-1 Accuracy",
        "score": "85.1",
        "num_parameters": 304_000_000,
        "methodology": (
            "ImageNet 10% labeled split; top-1 from Table 2 (React Locked-Text, "
            "ViT-L/14, language-augmented linear head initialization)."
        ),
        "is_open": False,
    },
    {
        "arxiv_id": "2208.05688",
        "model_name": "Semi-ViT (ViT-Large)",
        "best_metric": "Top-1 Accuracy",
        "score": "83.3",
        "num_parameters": 307_000_000,
        "methodology": (
            "ImageNet 10% labeled split; top-1 from Table 6. MAE pre-training, "
            "supervised fine-tuning, then semi-supervised fine-tuning with "
            "EMA-Teacher and probabilistic pseudo mixup (ViT-Large)."
        ),
        "is_open": False,
    },
    {
        "arxiv_id": "2208.05688",
        "model_name": "Semi-ViT (ViT-Huge)",
        "best_metric": "Top-1 Accuracy",
        "score": "84.3",
        "num_parameters": 632_000_000,
        "methodology": (
            "ImageNet 10% labeled split; top-1 from Table 6/7. MAE pre-training, "
            "supervised fine-tuning, then semi-supervised fine-tuning with "
            "EMA-Teacher and probabilistic pseudo mixup."
        ),
        "is_open": False,
    },
    {
        "arxiv_id": "2208.05688",
        "model_name": "Semi-ViT (ViT-Huge)",
        "best_metric": "Top-5 Accuracy",
        "score": "96.6",
        "num_parameters": 632_000_000,
        "methodology": (
            "ImageNet 10% labeled split; top-5 from Table 7. Same Semi-ViT-Huge "
            "setup as the Top-1 row (MAE pre-train + EMA-Teacher + probabilistic "
            "pseudo mixup)."
        ),
        "is_open": False,
    },
]


async def main() -> None:
    session = db_manager.session_local()
    created = skipped = 0
    imported_papers: dict[str, int] = {}
    try:
        for arxiv_id in {spec["arxiv_id"] for spec in EVALS}:
            paper = await ensure_arxiv_paper(session, arxiv_id)
            session.commit()
            link_paper_task(session, paper.id, TASK_ID)
            session.commit()
            imported_papers[arxiv_id] = paper.id
            logger.info("Paper %s ready (id=%s)", arxiv_id, paper.id)

        service = EvaluationService(session)
        for spec in EVALS:
            session.rollback()
            paper_id = imported_papers[spec["arxiv_id"]]
            source_url = f"https://arxiv.org/abs/{spec['arxiv_id']}"
            exists = (
                session.query(DBEvaluation)
                .filter(
                    DBEvaluation.paper_id == paper_id,
                    DBEvaluation.task_id == TASK_ID,
                    DBEvaluation.dataset_id == DATASET_ID,
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

            service.create_evaluation(
                paper_id=paper_id,
                task_id=TASK_ID,
                dataset_id=DATASET_ID,
                model_name=spec["model_name"],
                methodology=spec["methodology"],
                metrics={spec["best_metric"]: spec["score"]},
                best_metric=spec["best_metric"],
                source_url=source_url,
                num_parameters=spec.get("num_parameters"),
                is_open=spec.get("is_open", True),
            )
            created += 1
            logger.info(
                "Created %s / %s / %s = %s (open=%s)",
                spec["arxiv_id"],
                spec["model_name"],
                spec["best_metric"],
                spec["score"],
                spec.get("is_open", True),
            )
        logger.info("Done: %s created, %s skipped", created, skipped)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    asyncio.run(main())
