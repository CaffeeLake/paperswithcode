#!/usr/bin/env python3
"""Import Phase 1B scene text recognition evals (CLIP4STR, CPPD, DTrOCR, TPS++)."""

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

TASK_ID = 313
BEST_METRIC = "Accuracy"

EVALS = [
    {
        "arxiv_id": "2305.05322",
        "dataset_id": 657,
        "model_name": "ABINet-LV+TPS++",
        "score": "97.8",
        "methodology": (
            "IC13 (857-image split); word accuracy from Table 5. "
            "ABINet-LV recognizer with TPS++ attention-enhanced rectification; "
            "trained on 90K+SynthText synthetic data."
        ),
    },
    {
        "arxiv_id": "2305.14014",
        "dataset_id": 659,
        "model_name": "CLIP4STR-L (DataComp-1B)",
        "score": "99.6",
        "methodology": (
            "IIIT5K word accuracy from Table XI (CLIP ViT-L/14, DataComp-1B "
            "pre-training, Real 3.3M training mix)."
        ),
    },
    {
        "arxiv_id": "2305.14014",
        "dataset_id": 658,
        "model_name": "CLIP4STR-H (DFN-5B)",
        "score": "99.1",
        "methodology": (
            "SVT word accuracy from Table XI (CLIP ViT-H/14, DFN-5B pre-training, "
            "Real 3.3M training mix)."
        ),
    },
    {
        "arxiv_id": "2307.12270",
        "dataset_id": 662,
        "model_name": "CPPD Base (32×128)",
        "score": "99.7",
        "methodology": (
            "CUTE80 word accuracy from PaddleOCR CPPD release table "
            "(CPPD Base 32×128; official benchmark numbers linked from arXiv "
            "2307.12270). MJ+SynthText training."
        ),
    },
    {
        "arxiv_id": "2308.15996",
        "dataset_id": 661,
        "model_name": "DTrOCR 105M",
        "score": "98.6",
        "num_parameters": 105_000_000,
        "methodology": (
            "SVTP word accuracy from Table 1 (Real training: COCO-Text, RCTW, "
            "Uber-Text, ArT, LSVT, MLT19, ReCTS). Decoder-only GPT-2 backbone "
            "(105M parameters)."
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
