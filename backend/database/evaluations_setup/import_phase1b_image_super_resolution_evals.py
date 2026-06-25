#!/usr/bin/env python3
"""Import Phase 1B image super-resolution evals (DRCT-L, HMA)."""

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

TASK_ID = 314
BEST_METRIC = "PSNR"

EVALS = [
    {
        "arxiv_id": "2404.00722",
        "dataset_id": 753,
        "model_name": "DRCT-L",
        "score": "39.82",
        "num_parameters": 27_580_000,
        "methodology": (
            "Set5 ×2 PSNR (dB) from Table 1 (DRCT-L with ImageNet pre-training "
            "and same-task progressive training on DF2K)."
        ),
    },
    {
        "arxiv_id": "2404.00722",
        "dataset_id": 755,
        "model_name": "DRCT-L",
        "score": "35.24",
        "num_parameters": 27_580_000,
        "methodology": (
            "Set14 ×2 PSNR (dB) from Table 1 (DRCT-L; luminance-channel evaluation "
            "on standard SR benchmarks)."
        ),
    },
    {
        "arxiv_id": "2404.00722",
        "dataset_id": 756,
        "model_name": "DRCT-L",
        "score": "29.54",
        "num_parameters": 27_580_000,
        "methodology": ("Set14 ×4 PSNR (dB) from Table 1 (DRCT-L large variant)."),
    },
    {
        "arxiv_id": "2404.00722",
        "dataset_id": 758,
        "model_name": "DRCT-L",
        "score": "28.16",
        "num_parameters": 27_580_000,
        "methodology": ("BSD100 ×4 PSNR (dB) from Table 1 (DRCT-L)."),
    },
    {
        "arxiv_id": "2405.05001",
        "dataset_id": 753,
        "model_name": "HMA†",
        "score": "38.95",
        "methodology": (
            "Set5 ×2 PSNR (dB) from Table 4 (HMA with pre-training strategy †; "
            "legacy queue mis-mapped the ×3 Set5 score 35.35 onto this benchmark)."
        ),
    },
    {
        "arxiv_id": "2405.05001",
        "dataset_id": 754,
        "model_name": "HMA†",
        "score": "33.38",
        "methodology": (
            "Set5 ×4 PSNR (dB) from Table 4 (HMA† with progressive pre-training)."
        ),
    },
    {
        "arxiv_id": "2405.05001",
        "dataset_id": 759,
        "model_name": "HMA†",
        "score": "35.24",
        "methodology": ("Urban100 ×2 PSNR (dB) from Table 4 (HMA†)."),
    },
]

SKIPPED = [
    (
        "1906.12021",
        "DRLN+",
        "BSD100 / Urban100 (8×)",
        "Table 2 reports 8× bicubic SR (BSD100 PSNR 25.06, Urban100 23.24); "
        "no bsd100-8x or urban100-8x benchmarks exist in DB — legacy rows "
        "were mis-mapped onto 2× leaderboards.",
    ),
    (
        "2404.00722",
        "DRCT-L",
        "Set5 / Set14 (2×) legacy scores",
        "Legacy CSV had 39.14 / 35.36; paper Table 1 lists DRCT-L ×2 as "
        "39.82 / 35.24 — imported paper values instead.",
    ),
    (
        "2405.05001",
        "HMA†",
        "Set5 (2×) legacy score 35.35",
        "Legacy row came from set5-3x slug; 35.35 is HMA† ×3 Set5 PSNR. "
        "Imported correct ×2 score 38.95 on Set5 - 2x upscaling.",
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
        for arxiv_id, model, benchmark, reason in SKIPPED:
            logger.info("Skipped %s / %s on %s: %s", arxiv_id, model, benchmark, reason)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
