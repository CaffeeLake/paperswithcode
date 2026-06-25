#!/usr/bin/env python3
"""Import Phase 1B image generation evals (DiGIT, EDM2 autoguidance, SiT+MG)."""

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

TASK_ID = 19
BEST_METRIC = "FID"

EVALS = [
    {
        "arxiv_id": "2410.12490",
        "dataset_id": 399,
        "model_name": "DiGIT (+VQGAN)",
        "score": "3.39",
        "num_parameters": 732_000_000,
        "methodology": (
            "Class-conditional ImageNet 256×256 FID from Table 4 (DiGIT large, "
            "732M params, 200 epochs; autoregressive decoder with VQGAN pixel head)."
        ),
    },
    {
        "arxiv_id": "2406.02507",
        "dataset_id": 401,
        "model_name": "EDM2-XXL + Autoguidance (M, T/3.5)",
        "score": "1.25",
        "methodology": (
            "ImageNet 512×512 class-conditional FID from Table 1 (EDM2-XXL main model "
            "guided by medium-capacity model trained for T/3.5 iterations)."
        ),
    },
    {
        "arxiv_id": "2502.12154",
        "dataset_id": 399,
        "model_name": "SiT-XL/2 + MG",
        "score": "1.34",
        "num_parameters": 675_000_000,
        "methodology": (
            "ImageNet 256×256 class-conditional FID from Table 1 without classifier-free "
            "guidance (SiT-XL/2 trained with Model-guidance objective)."
        ),
    },
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
                num_parameters=spec.get("num_parameters"),
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
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
