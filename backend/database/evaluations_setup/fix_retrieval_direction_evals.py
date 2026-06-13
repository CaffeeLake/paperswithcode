#!/usr/bin/env python3
"""Fix Flickr30K / COCO Captions retrieval direction and migrate T→I rows.

Creates Flickr30K Text-to-Image Retrieval and COCO Captions Text-to-Image Retrieval benchmarks,
corrects image-to-text scores on the original leaderboards, and moves text-to-image
rows to the new benchmarks.

Run with:

    uv run --env-file backend/keys.env \\
        python backend/database/evaluations_setup/fix_retrieval_direction_evals.py
"""

from __future__ import annotations

import logging
import re

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import Dataset as DBDataset
from backend.services.evaluation_service import EvaluationService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TASK_ID = 8
METRIC_NAME = "R@1"
R1_METRIC_ID = 32

FLICKR_DATASET_ID = 484
COCO_DATASET_ID = 10

FLICKR_I2T_SLUG = "flickr30k-image-to-text"
FLICKR_T2I_SLUG = "flickr30k-text-to-image"
COCO_I2T_SLUG = "coco-captions-image-to-text"
COCO_T2I_SLUG = "coco-captions-text-to-image"

FLICKR_DESCRIPTION = (
    "Flickr30K is an image-caption dataset. This leaderboard tracks "
    "image-to-text retrieval (image retrieval): given a query image, retrieve "
    "the matching caption. R@1 on the standard 1K test split."
)
COCO_DESCRIPTION = (
    "COCO Captions image-to-text retrieval (image retrieval): given a query "
    "image, retrieve the matching caption. R@1 on the MSCOCO 5K Karpathy test split."
)
FLICKR_TEXT_DESCRIPTION = (
    "Flickr30K text-to-image retrieval (text retrieval): given a query caption, "
    "retrieve the matching image. R@1 on the standard 1K test split."
)
COCO_TEXT_DESCRIPTION = (
    "COCO Captions text-to-image retrieval (text retrieval): given a query "
    "caption, retrieve the matching image. R@1 on the MSCOCO 5K Karpathy test split."
)

# Explicit text-retrieval rows to migrate (keep scores).
FLICKR_MIGRATE_IDS = [7801, 7778, 7743, 7358, 9184, 9180, 6509, 5870, 5681, 5691]
COCO_MIGRATE_IDS = [7799, 7780, 7745, 7360, 9186, 9182, 6511, 5869, 5682, 5692, 6404]

DELETE_IDS = [7254, 7255]

# Sole wrong-direction rows corrected in place (TIPSv2).
FLICKR_UPDATE_IN_PLACE = {
    6258: {
        "score": "95.1",
        "methodology_suffix": (
            "Paper Table 6: TIPSv2 g/14 image-to-text retrieval on Flickr30K, "
            "recall@1. Migrated text-to-image R@1=85.9 to Flickr30K Text-to-Image Retrieval."
        ),
    },
}
COCO_UPDATE_IN_PLACE = {
    6257: {
        "score": "75.7",
        "methodology_suffix": (
            "Paper Table 6: TIPSv2 g/14 image-to-text retrieval on COCO, recall@1. "
            "Migrated text-to-image R@1=60.7 to COCO Captions Text-to-Image Retrieval."
        ),
    },
}

# New I→T rows after migrating sole T→I entries away.
FLICKR_CREATE_I2T = [
    {
        "paper_id": 7794,
        "model_name": "BLIP ViT-L",
        "score": "97.4",
        "methodology": (
            "Paper Table 5: BLIP ViT-L fine-tuned on Flickr30K; image-to-text TR@1 "
            "on 1K test set (COCO-first column layout). Source: arXiv 2201.12086."
        ),
        "num_parameters": None,
        "is_open": True,
    },
    {
        "paper_id": 5020,
        "model_name": "ALIGN",
        "score": "95.3",
        "methodology": (
            "Paper Table 1: fine-tuned ALIGN on Flickr30K 1K test set; "
            "image-to-text retrieval R@1. Source: arXiv 2102.05918."
        ),
        "num_parameters": None,
        "is_open": True,
    },
    {
        "paper_id": 11316,
        "model_name": "AltCLIP",
        "score": "86.0",
        "methodology": (
            "Paper Table 2: AltCLIP ViT-L on Flickr30K EN; image-to-text R@1. "
            "Source: arXiv 2211.06679."
        ),
        "num_parameters": None,
        "is_open": True,
    },
]

COCO_CREATE_I2T = [
    {
        "paper_id": 7794,
        "model_name": "BLIP ViT-L",
        "score": "82.4",
        "methodology": (
            "Paper Table 5: BLIP ViT-L fine-tuned on COCO; image-to-text TR@1 "
            "on 5K test set. Source: arXiv 2201.12086."
        ),
        "num_parameters": None,
        "is_open": True,
    },
    {
        "paper_id": 5020,
        "model_name": "ALIGN",
        "score": "77.0",
        "methodology": (
            "Paper Table 1: fine-tuned ALIGN on MSCOCO 5K test set; "
            "image-to-text retrieval R@1. Source: arXiv 2102.05918."
        ),
        "num_parameters": None,
        "is_open": True,
    },
    {
        "paper_id": 11316,
        "model_name": "AltCLIP",
        "score": "58.6",
        "methodology": (
            "Paper Table 2: AltCLIP ViT-L on MSCOCO EN; image-to-text R@1. "
            "Source: arXiv 2211.06679."
        ),
        "num_parameters": None,
        "is_open": True,
    },
    {
        "paper_id": 14181,
        "model_name": "SigLIP SO",
        "score": "82.9",
        "methodology": (
            "Paper Table 3: SigLIP Shape-Optimized 400M zero-shot MSCOCO "
            "image-to-text R@1 (not text-to-image 52.0). Source: arXiv 2303.15343."
        ),
        "num_parameters": None,
        "is_open": True,
    },
]

# New T→I rows for TIPSv2 after in-place I→T correction.
TIPS_PAPER_ID = 57563
TIPS_NUM_PARAMETERS = 1_500_000_000
FLICKR_CREATE_T2I = [
    {
        "paper_id": TIPS_PAPER_ID,
        "model_name": "TIPSv2 g/14",
        "score": "85.9",
        "methodology": (
            "Paper Table 6: TIPSv2 g/14 text-to-image retrieval on Flickr30K, "
            "recall@1. Source: arXiv 2604.12012."
        ),
        "num_parameters": TIPS_NUM_PARAMETERS,
        "is_open": True,
    },
]
COCO_CREATE_T2I = [
    {
        "paper_id": TIPS_PAPER_ID,
        "model_name": "TIPSv2 g/14",
        "score": "60.7",
        "methodology": (
            "Paper Table 6: TIPSv2 g/14 text-to-image retrieval on COCO, recall@1. "
            "Source: arXiv 2604.12012."
        ),
        "num_parameters": TIPS_NUM_PARAMETERS,
        "is_open": True,
    },
]

# Strip direction suffixes from model names on I→T leaderboards.
FLICKR_STRIP_SUFFIX_IDS = [7802, 7777, 7742, 7359, 6510]
COCO_STRIP_SUFFIX_IDS = [7800, 7779, 7744, 7361, 6512]

# ViLT keeps (zero-shot) to distinguish fine-tuned rows on the same leaderboard.
VILT_ZERO_SHOT_IDS = {9181, 9180, 9182, 9183}

_SUFFIX_RE = re.compile(
    r"\s*\((?:image|text) retrieval(?:,\s*zero-shot)?\)\s*$",
    re.IGNORECASE,
)


def _clean_model_name(name: str) -> str:
    return _SUFFIX_RE.sub("", name).strip()


def _ensure_text_retrieval_dataset(
    session: Session,
    *,
    slug: str,
    name: str,
    description: str,
    parent: DBDataset,
) -> DBDataset:
    dataset = session.query(DBDataset).filter(DBDataset.slug == slug).one_or_none()
    if dataset is None:
        dataset = DBDataset(
            name=name,
            slug=slug,
            description=description,
            hf_url=parent.hf_url,
            homepage=parent.homepage,
            paper_url=parent.paper_url,
            introducing_paper_id=parent.introducing_paper_id,
            introducing_paper_title=parent.introducing_paper_title,
            introduced_year=parent.introduced_year,
            parent_dataset_id=parent.id,
        )
        session.add(dataset)
        session.flush()
        logger.info("Created dataset %r id=%s", name, dataset.id)
    else:
        dataset.description = description
        dataset.paper_url = parent.paper_url
        dataset.introducing_paper_id = parent.introducing_paper_id
        dataset.introducing_paper_title = parent.introducing_paper_title
        dataset.hf_url = parent.hf_url
        dataset.homepage = parent.homepage
        dataset.parent_dataset_id = parent.id
        session.flush()
        logger.info("Updated dataset %r id=%s", name, dataset.id)

    session.execute(
        text(
            "INSERT INTO task_datasets (task_id, dataset_id, supports_harness) "
            "VALUES (:t, :d, FALSE) ON CONFLICT (task_id, dataset_id) DO NOTHING"
        ),
        {"t": TASK_ID, "d": dataset.id},
    )
    session.execute(
        text(
            "INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id) "
            "VALUES (:t, :d, :m) ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING"
        ),
        {"t": TASK_ID, "d": dataset.id, "m": R1_METRIC_ID},
    )
    return dataset


def _migrate_row(
    service: EvaluationService,
    eval_id: int,
    text_dataset_id: int,
) -> None:
    row = service.db.execute(
        text("SELECT model_name, methodology FROM evaluations WHERE id = :id"),
        {"id": eval_id},
    ).first()
    if row is None:
        logger.warning("Skip missing evaluation id=%s", eval_id)
        return

    clean_name = _clean_model_name(row.model_name)
    methodology = row.methodology or ""
    if "text-to-image" not in methodology.lower():
        methodology = (
            f"{methodology} Text-to-image retrieval R@1; moved to text-retrieval benchmark."
        ).strip()

    service.update_evaluation(
        evaluation_id=eval_id,
        dataset_id=text_dataset_id,
        model_name=clean_name,
        methodology=methodology,
    )
    logger.info(
        "Migrated eval %s -> dataset %s as %r", eval_id, text_dataset_id, clean_name
    )


def _update_in_place(
    service: EvaluationService,
    eval_id: int,
    dataset_id: int,
    score: str,
    methodology: str,
) -> None:
    service.update_evaluation(
        evaluation_id=eval_id,
        dataset_id=dataset_id,
        model_name=_clean_model_name(
            service.db.execute(
                text("SELECT model_name FROM evaluations WHERE id = :id"),
                {"id": eval_id},
            ).scalar_one()
        ),
        metrics={METRIC_NAME: score},
        best_metric=METRIC_NAME,
        methodology=methodology,
    )
    logger.info("Updated eval %s -> I→T R@1=%s", eval_id, score)


def _strip_suffixes(service: EvaluationService, eval_ids: list[int]) -> None:
    for eval_id in eval_ids:
        row = service.db.execute(
            text("SELECT model_name FROM evaluations WHERE id = :id"),
            {"id": eval_id},
        ).first()
        if row is None:
            continue
        clean = _clean_model_name(row.model_name)
        if eval_id in VILT_ZERO_SHOT_IDS and "(zero-shot)" not in clean.lower():
            clean = f"{clean} (zero-shot)"
        if clean != row.model_name:
            service.update_evaluation(evaluation_id=eval_id, model_name=clean)
            logger.info("Renamed eval %s -> %r", eval_id, clean)


def _create_row(
    service: EvaluationService,
    *,
    dataset_id: int,
    paper_id: int,
    model_name: str,
    score: str,
    methodology: str,
    num_parameters: int | None,
    is_open: bool,
) -> None:
    existing = service.db.execute(
        text(
            """
            SELECT id FROM evaluations
            WHERE paper_id = :paper_id AND task_id = :task_id AND dataset_id = :dataset_id
              AND model_name = :model_name AND best_metric = :metric
              AND COALESCE(harness, '') = ''
            """
        ),
        {
            "paper_id": paper_id,
            "task_id": TASK_ID,
            "dataset_id": dataset_id,
            "model_name": model_name,
            "metric": METRIC_NAME,
        },
    ).first()
    if existing:
        logger.info("Skip create; row already exists id=%s", existing.id)
        return

    kwargs = {
        "paper_id": paper_id,
        "task_id": TASK_ID,
        "dataset_id": dataset_id,
        "model_name": model_name,
        "methodology": methodology,
        "metrics": {METRIC_NAME: score},
        "best_metric": METRIC_NAME,
        "is_open": is_open,
    }
    if num_parameters is not None:
        kwargs["num_parameters"] = num_parameters
    service.create_evaluation(**kwargs)
    logger.info("Created %r R@1=%s on dataset %s", model_name, score, dataset_id)


def main() -> None:
    session = db_manager.session_local()
    try:
        flickr = session.get(DBDataset, FLICKR_DATASET_ID)
        coco = session.get(DBDataset, COCO_DATASET_ID)
        if flickr is None or coco is None:
            raise RuntimeError("Parent Flickr30K or COCO Captions dataset missing")

        flickr.description = FLICKR_DESCRIPTION
        coco.description = COCO_DESCRIPTION

        flickr_text = _ensure_text_retrieval_dataset(
            session,
            slug=FLICKR_T2I_SLUG,
            name="Flickr30K Text-to-Image Retrieval",
            description=FLICKR_TEXT_DESCRIPTION,
            parent=flickr,
        )
        coco_text = _ensure_text_retrieval_dataset(
            session,
            slug=COCO_T2I_SLUG,
            name="COCO Captions Text-to-Image Retrieval",
            description=COCO_TEXT_DESCRIPTION,
            parent=coco,
        )
        session.commit()

        service = EvaluationService(session)

        for eval_id in DELETE_IDS:
            row = service.db.execute(
                text("SELECT id FROM evaluations WHERE id = :id"),
                {"id": eval_id},
            ).first()
            if row:
                service.delete_evaluation(eval_id)
                logger.info("Deleted eval %s (DataComp mean score)", eval_id)

        for eval_id in FLICKR_MIGRATE_IDS:
            _migrate_row(service, eval_id, flickr_text.id)

        for eval_id in COCO_MIGRATE_IDS:
            _migrate_row(service, eval_id, coco_text.id)

        for eval_id, payload in FLICKR_UPDATE_IN_PLACE.items():
            _update_in_place(
                service,
                eval_id,
                FLICKR_DATASET_ID,
                payload["score"],
                payload["methodology_suffix"],
            )

        for eval_id, payload in COCO_UPDATE_IN_PLACE.items():
            _update_in_place(
                service,
                eval_id,
                COCO_DATASET_ID,
                payload["score"],
                payload["methodology_suffix"],
            )

        for payload in FLICKR_CREATE_I2T:
            _create_row(service, dataset_id=FLICKR_DATASET_ID, **payload)

        for payload in COCO_CREATE_I2T:
            _create_row(service, dataset_id=COCO_DATASET_ID, **payload)

        for payload in FLICKR_CREATE_T2I:
            _create_row(service, dataset_id=flickr_text.id, **payload)

        for payload in COCO_CREATE_T2I:
            _create_row(service, dataset_id=coco_text.id, **payload)

        _strip_suffixes(service, FLICKR_STRIP_SUFFIX_IDS)
        _strip_suffixes(service, COCO_STRIP_SUFFIX_IDS)

        session.commit()

        for dataset_id in [
            FLICKR_DATASET_ID,
            COCO_DATASET_ID,
            flickr_text.id,
            coco_text.id,
        ]:
            count = service.recalculate_ranks(
                TASK_ID, dataset_id, metric_name=METRIC_NAME
            )
            logger.info(
                "Recalculated ranks for dataset %s (%s rows)", dataset_id, count
            )

        session.commit()
        logger.info(
            "Done. Flickr text-retrieval id=%s, COCO text-retrieval id=%s",
            flickr_text.id,
            coco_text.id,
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
