#!/usr/bin/env python3
"""Backfill GenEval / DPG-Bench / text-rendering evals for flagship T2I models.

Sources: HiDream-O1-Image README, Qwen-Image / Z-Image / X-Omni arXiv papers,
FLUX.2 blog comparators (via HiDream README table).

HunyuanImage 3.0: no GenEval/DPG scores in tech report or README — skipped.

Benchmark watch-list (do NOT add dataset rows until triggered):
- 7Bench (2508.12919): add when >=5 papers report eval rows OR >=10 corpus mentions
  with >=3 model families in last 12 months.
- SpatialGenEval (2601.20354): same adoption gate.
"""

from __future__ import annotations

import logging

from backend.database.connection import get_database_session
from backend.database.evaluations_setup.evaluation_helpers import (
    get_or_create_evaluation,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TASK_ID = 19
DATASETS = {
    "geneval": 340,
    "dpg-bench": 692,
    "longtext-bench": 402,
    "cvtg-2k": 406,
    "oneig-en": 409,
}

# (paper_id, model_name, dataset_key, metric_name, score, source_url)
ROWS: list[tuple[int, str, str, str, str, str]] = [
    # HiDream-O1-Image — github.com/HiDream-ai/HiDream-O1-Image README
    (
        98580,
        "HiDream-O1-Image (8B)",
        "geneval",
        "GenEval Score",
        "0.90",
        "https://github.com/HiDream-ai/HiDream-O1-Image",
    ),
    (
        98580,
        "HiDream-O1-Image (8B)",
        "dpg-bench",
        "DPG-Bench Score",
        "89.83",
        "https://github.com/HiDream-ai/HiDream-O1-Image",
    ),
    (
        98580,
        "HiDream-O1-Image (8B)",
        "cvtg-2k",
        "Word Accuracy",
        "0.9128",
        "https://github.com/HiDream-ai/HiDream-O1-Image",
    ),
    (
        98580,
        "HiDream-O1-Image (8B)",
        "longtext-bench",
        "Accuracy",
        "97.85",
        "https://github.com/HiDream-ai/HiDream-O1-Image",
    ),
    # Qwen-Image — arXiv:2508.02324 Tables 3–5, 8, 10
    (
        52192,
        "Qwen-Image",
        "geneval",
        "GenEval Score",
        "0.87",
        "https://arxiv.org/abs/2508.02324",
    ),
    (
        52192,
        "Qwen-Image",
        "dpg-bench",
        "DPG-Bench Score",
        "88.32",
        "https://arxiv.org/abs/2508.02324",
    ),
    (
        52192,
        "Qwen-Image",
        "cvtg-2k",
        "Word Accuracy",
        "0.8288",
        "https://arxiv.org/abs/2508.02324",
    ),
    (
        52192,
        "Qwen-Image",
        "longtext-bench",
        "Accuracy",
        "94.45",
        "https://arxiv.org/abs/2508.02324",
    ),
    (
        52192,
        "Qwen-Image",
        "oneig-en",
        "OneIG Overall Score",
        "0.539",
        "https://arxiv.org/abs/2508.02324",
    ),
    # Z-Image-Turbo — arXiv:2511.22699 (open-weight flagship)
    (
        54409,
        "Z-Image-Turbo",
        "geneval",
        "GenEval Score",
        "0.82",
        "https://arxiv.org/abs/2511.22699",
    ),
    (
        54409,
        "Z-Image-Turbo",
        "dpg-bench",
        "DPG-Bench Score",
        "84.86",
        "https://arxiv.org/abs/2511.22699",
    ),
    (
        54409,
        "Z-Image-Turbo",
        "cvtg-2k",
        "Word Accuracy",
        "0.8585",
        "https://arxiv.org/abs/2511.22699",
    ),
    (
        54409,
        "Z-Image-Turbo",
        "longtext-bench",
        "Accuracy",
        "92.15",
        "https://arxiv.org/abs/2511.22699",
    ),
    (
        54409,
        "Z-Image-Turbo",
        "oneig-en",
        "OneIG Overall Score",
        "0.528",
        "https://arxiv.org/abs/2511.22699",
    ),
    # X-Omni — arXiv:2507.22058 Tables 1–3
    (
        52106,
        "X-Omni",
        "geneval",
        "GenEval Score",
        "0.83",
        "https://arxiv.org/abs/2507.22058",
    ),
    (
        52106,
        "X-Omni",
        "dpg-bench",
        "DPG-Bench Score",
        "87.65",
        "https://arxiv.org/abs/2507.22058",
    ),
    (
        52106,
        "X-Omni",
        "longtext-bench",
        "Accuracy",
        "85.70",
        "https://arxiv.org/abs/2507.22058",
    ),
    # FLUX.2 [Dev] — bfl.ai/blog/flux-2; benchmark table cross-ref HiDream README
    (
        98581,
        "FLUX.2 [Dev]",
        "geneval",
        "GenEval Score",
        "0.87",
        "https://bfl.ai/blog/flux-2",
    ),
    (
        98581,
        "FLUX.2 [Dev]",
        "dpg-bench",
        "DPG-Bench Score",
        "87.57",
        "https://bfl.ai/blog/flux-2",
    ),
    (
        98581,
        "FLUX.2 [Dev]",
        "cvtg-2k",
        "Word Accuracy",
        "0.8926",
        "https://github.com/HiDream-ai/HiDream-O1-Image",
    ),
    (
        98581,
        "FLUX.2 [Dev]",
        "longtext-bench",
        "Accuracy",
        "86.00",
        "https://github.com/HiDream-ai/HiDream-O1-Image",
    ),
]


def main() -> None:
    session_gen = get_database_session()
    db = next(session_gen)
    added = 0
    try:
        for paper_id, model_name, dataset_key, metric_name, score, source_url in ROWS:
            dataset_id = DATASETS[dataset_key]
            get_or_create_evaluation(
                db,
                paper_id=paper_id,
                task_id=TASK_ID,
                dataset_id=dataset_id,
                model_name=model_name,
                metrics={metric_name: score},
                external_source_url=source_url,
                best_metric=metric_name,
            )
            logger.info(
                "Upserted paper=%s model=%s %s=%s",
                paper_id,
                model_name,
                metric_name,
                score,
            )
            added += 1
        db.commit()
        logger.info("Done: %s evaluation metric rows upserted.", added)
    finally:
        db.close()


if __name__ == "__main__":
    main()
