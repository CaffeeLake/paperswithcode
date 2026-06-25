#!/usr/bin/env python3
"""Import Phase 1B object detection evals (Mask R-CNN, MOAT, M3I, Co-DETR)."""

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

TASK_ID = 2
BEST_METRIC = "mAP"

EVALS = [
    {
        "arxiv_id": "1703.06870",
        "dataset_id": 5,
        "model_name": "Mask R-CNN X-152-32x8d",
        "score": "45.2",
        "methodology": (
            "COCO minival box AP from Detectron model zoo (Mask R-CNN with bells "
            "& whistles: ResNeXt-152-32x8d-FPN-IN5k, e2e training, train-time scale "
            "jitter; no test-time augmentation). Matches Appendix B enhanced results."
        ),
    },
    {
        "arxiv_id": "2210.01820",
        "dataset_id": 5,
        "model_name": "MOAT-3 22K+1K",
        "score": "59.2",
        "num_parameters": 227_000_000,
        "methodology": (
            "COCO 2017 val box AP from Table 3 (Cascade Mask R-CNN head, "
            "ImageNet-22K pre-training + ImageNet-1K fine-tuning, single-scale "
            "inference). Legacy minival queue; COCO minival is equivalent to val2017."
        ),
    },
    {
        "arxiv_id": "2211.09807",
        "dataset_id": 3,
        "model_name": "M3I Pre-training (InternImage-H)",
        "score": "65.4",
        "methodology": (
            "COCO test-dev box AP from Table 2. M3I single-stage pre-training on "
            "427M image-text + 15M category pairs; downstream InternImage-H with "
            "composite parameter doubling + DINO detector, Objects365 then COCO "
            "fine-tuning."
        ),
    },
    {
        "arxiv_id": "2211.12860",
        "dataset_id": 5,
        "model_name": "Co-DETR (ViT-L)",
        "score": "66.0",
        "num_parameters": 304_000_000,
        "methodology": (
            "COCO minival box AP from Table 5 (Co-DINO-Deformable-DETR++ with ViT-L, "
            "Objects365 intermediate fine-tuning). Legacy CSV cited 65.9 (val split)."
        ),
    },
]

SKIPPED = [
    (
        "2112.03857",
        "GLIP",
        "Roboflow100-VL (RF100-VL)",
        "GLIP ODinW reports average AP on 13 Roboflow datasets (legacy 0.112), "
        "not RF100-VL 100-dataset mAP@50:95 (incomparable to existing leaderboard).",
    ),
    (
        "2410.13842",
        "D-FINE-X+",
        "COCO minival",
        "D-FINE-X+ (Objects365 pretrained) 59.3% AP already on coco-val2017; "
        "paper does not report a separate minival score.",
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
