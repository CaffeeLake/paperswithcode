#!/usr/bin/env python3
"""Import Phase 1B depth estimation evals (ScaleDepth-NK, PrimeDepth + Depth Anything)."""

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

TASK_ID = 16

EVALS = [
    {
        "arxiv_id": "2407.08187",
        "dataset_id": 242,
        "model_name": "ScaleDepth-NK",
        "best_metric": "AbsRel",
        "score": "0.562",
        "num_parameters": 47_000_000,
        "methodology": (
            "DIODE Outdoor (metric) zero-shot AbsRel from Table VI (ScaleDepth-NK "
            "trained on NYU-Depth V2 + KITTI; max eval depth 80m). Skipped RMSE "
            "and delta1 (import AbsRel only)."
        ),
    },
    {
        "arxiv_id": "2407.08187",
        "dataset_id": 246,
        "model_name": "ScaleDepth-NK",
        "best_metric": "AbsRel",
        "score": "0.381",
        "num_parameters": 47_000_000,
        "methodology": (
            "HyperSim (metric) zero-shot AbsRel from Table V (ScaleDepth-NK; max "
            "eval depth 80m). Skipped RMSE and delta1."
        ),
    },
    {
        "arxiv_id": "2407.08187",
        "dataset_id": 244,
        "model_name": "ScaleDepth-NK",
        "best_metric": "AbsRel",
        "score": "0.120",
        "num_parameters": 47_000_000,
        "methodology": (
            "Virtual KITTI 2 (metric) zero-shot AbsRel from Table VI (ScaleDepth-NK; "
            "max eval depth 80m). Skipped RMSE and delta1."
        ),
    },
    {
        "arxiv_id": "2409.09144",
        "dataset_id": 218,
        "model_name": "PrimeDepth + Depth Anything",
        "best_metric": "delta1",
        "score": "0.981",
        "methodology": (
            "ETH3D (relative) delta1 from Table 2 Pixel-wise-Average (Our & DA) row "
            "(paper reports 98.1%; stored as 0.981 fraction). Ensemble averages "
            "PrimeDepth and Depth Anything depth maps. Skipped AbsRel on this row."
        ),
    },
]

SKIPPED = [
    (
        "2407.08187",
        "ScaleDepth-NK",
        "RMSE / delta1 on metric benchmarks",
        "Leaderboards only configure AbsRel for DIODE Outdoor, HyperSim, and "
        "Virtual KITTI 2 (metric).",
    ),
    (
        "2409.09144",
        "PrimeDepth + Depth Anything",
        "AbsRel on ETH3D (relative)",
        "Import delta1 only per Phase 1B metric gate; AbsRel skipped for this row.",
    ),
    (
        "2409.09144",
        "PrimeDepth",
        "ETH3D standalone (rank-3 legacy row)",
        "Legacy rank-3 row lists PrimeDepth alone (delta1=0.967); imported the "
        "rank-1 Pixel-wise-Average ensemble (0.981) per handoff.",
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

            best_metric = spec["best_metric"]
            source_url = f"https://arxiv.org/abs/{spec['arxiv_id']}"
            exists = (
                session.query(DBEvaluation)
                .filter(
                    DBEvaluation.paper_id == paper_id,
                    DBEvaluation.task_id == TASK_ID,
                    DBEvaluation.dataset_id == spec["dataset_id"],
                    DBEvaluation.model_name == spec["model_name"],
                    DBEvaluation.best_metric == best_metric,
                )
                .first()
            )
            if exists:
                skipped += 1
                logger.info(
                    "Skip existing %s / %s / dataset=%s / %s",
                    spec["arxiv_id"],
                    spec["model_name"],
                    spec["dataset_id"],
                    best_metric,
                )
                continue

            service.create_evaluation(
                paper_id=paper_id,
                task_id=TASK_ID,
                dataset_id=spec["dataset_id"],
                model_name=spec["model_name"],
                methodology=spec["methodology"],
                metrics={best_metric: spec["score"]},
                best_metric=best_metric,
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
                best_metric,
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
