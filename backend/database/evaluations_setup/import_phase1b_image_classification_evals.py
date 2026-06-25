#!/usr/bin/env python3
"""Import Phase 1B image classification evals (SAM, CCT, MetaFormer, Bamboo, etc.)."""

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

TASK_ID = 1
BEST_METRIC = "Accuracy"

EVALS = [
    {
        "arxiv_id": "2010.01412",
        "dataset_id": 224,
        "model_name": "EffNet-L2 (SAM)",
        "score": "97.10",
        "methodology": (
            "Oxford-IIIT Pets top-1 accuracy from Table 3 (EfficientNet-L2 fine-tuned "
            "with SAM; reported as 2.90% top-1 error rate)."
        ),
    },
    {
        "arxiv_id": "2010.01412",
        "dataset_id": 222,
        "model_name": "EffNet-L2 (SAM)",
        "score": "96.08",
        "methodology": (
            "CIFAR-100 top-1 accuracy from Table 3 (EfficientNet-L2 fine-tuned with "
            "SAM; reported as 3.92% top-1 error rate)."
        ),
    },
    {
        "arxiv_id": "2104.05704",
        "dataset_id": 223,
        "model_name": "CCT-14/7x2",
        "score": "99.76",
        "methodology": (
            "Oxford Flowers-102 top-1 validation accuracy from Table 4 with ImageNet "
            "pre-training (Compact Convolutional Transformer 14/7x2)."
        ),
    },
    {
        "arxiv_id": "2203.02751",
        "dataset_id": 378,
        "model_name": "MetaFormer-2 (384)",
        "score": "92.9",
        "methodology": (
            "CUB-200-2011 top-1 accuracy from Appendix Table 11 (MetaFormer-2, "
            "ImageNet-21k pre-training, 384px fine-tuning; image-only input)."
        ),
    },
    {
        "arxiv_id": "2203.07845",
        "dataset_id": 590,
        "model_name": "Bamboo (ViT-B/16)",
        "score": "92.9",
        "methodology": (
            "Food-101 fine-tuning accuracy from Table 3 (Bamboo ViT-B/16 supervised "
            "pre-training on 69M Bamboo images)."
        ),
    },
    {
        "arxiv_id": "2206.07394",
        "dataset_id": 351,
        "model_name": "efficient adaptive ensembling",
        "score": "96.879",
        "methodology": (
            "Stanford Cars top-1 accuracy from the main results table (efficient "
            "adaptive ensembling of fine-tuned classifiers)."
        ),
    },
    {
        "arxiv_id": "2211.05778",
        "dataset_id": 334,
        "model_name": "InternImage-H",
        "score": "71.7",
        "num_parameters": 1_310_000_000,
        "methodology": (
            "Places205 validation top-1 accuracy from Table 10 (InternImage-H "
            "fine-tuned after M3I-style large-scale pre-training)."
        ),
    },
    {
        "arxiv_id": "2303.13496",
        "dataset_id": 590,
        "model_name": "MAWS (ViT-2B)",
        "score": "96.2",
        "num_parameters": 2_000_000_000,
        "methodology": (
            "Food-101 zero-shot top-1 accuracy from Table 6 (MAE pre-pretraining "
            "then weakly-supervised pretraining; LiT text encoder for zero-shot "
            "transfer)."
        ),
    },
    {
        "arxiv_id": "2403.13430",
        "dataset_id": 574,
        "model_name": "IMP+MTP (InternImage-XL)",
        "score": "99.24",
        "methodology": (
            "EuroSAT overall accuracy from Table IV (InternImage-XL with ImageNet-22K "
            "pre-training plus multi-task remote-sensing pretraining)."
        ),
    },
    {
        "arxiv_id": "2404.03323",
        "dataset_id": 378,
        "model_name": "Sparse-CBM",
        "score": "80.02",
        "methodology": (
            "CUB-200-2011 top-1 accuracy from Table 2 / appendix (Sparse Concept "
            "Bottleneck Model with Gumbel-trick concept selection)."
        ),
    },
]

SKIPPED = [
    (
        "2305.12827",
        "Linear FT (ViT-L/14)",
        "DTD",
        "Legacy 90.0% matches Table 1 post-hoc linearized normalized multi-task "
        "average for ViT-L/14, not a tabulated DTD single-task linear-FT score "
        "(per-task numbers appear only in Appendix Figure 7).",
    ),
    (
        "2411.14402",
        "AIMv2-3B (448 res)",
        "iNaturalist 2021",
        "Table 3 reports iNAT-18 attentive-probing results (85.9% for "
        "ViT-3B/14_448px); paper does not evaluate iNaturalist 2021.",
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
