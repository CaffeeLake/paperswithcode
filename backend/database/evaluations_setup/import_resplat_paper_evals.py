"""Import the paper-native ReSplat RealEstate10K two-view result.

Only the introduced ReSplat row from arXiv:2510.08575 is included. The
comparison baselines and results for other datasets or view counts are excluded.

Run:
    uv run --env-file backend/keys.env python \
        backend/database/evaluations_setup/import_resplat_paper_evals.py
"""

from __future__ import annotations


from sqlalchemy import text

from backend.database.connection import get_database_session
from backend.services.evaluation_service import EvaluationService
from backend.database.evaluations_setup.paper_eval_import import (
    resolve_scope,
    upsert_evaluation,
    validate_leaderboard,
)

ARXIV_ID = "2510.08575"
TASK_SLUG = "novel-view-synthesis"
DATASET_SLUG = "realestate10k-pixelsplat-2-view"
MODEL_NAME = "ReSplat"
BEST_METRIC = "PSNR"
SOURCE_URL = f"https://arxiv.org/abs/{ARXIV_ID}"
HF_MODEL_URL = "https://huggingface.co/haofeixu/resplat"
NUM_PARAMETERS = 223_000_000
METRICS = {"PSNR": "29.75", "SSIM": "0.912", "LPIPS": "0.100"}
METHODOLOGY = (
    "Paper-native ReSplat result from Table 4 on the standard pixelSplat "
    "RealEstate10K validation protocol at 256x256 resolution. Evaluation uses "
    "exactly two posed and calibrated context views and three target views per "
    "example; the official ReSplat evaluation index is byte-identical to "
    "pixelSplat's evaluation_index_re10k.json. The paper reports PSNR 29.75, "
    "SSIM 0.912, and LPIPS 0.100; the official evaluation script prints the "
    "unrounded PSNR as 29.751. This is the 223M-parameter ReSplat-Base model "
    "with two recurrent refinement iterations."
)


def _resolve_scope(db) -> tuple[int, int, int]:
    paper_id, task_id, datasets = resolve_scope(
        db,
        arxiv_id=ARXIV_ID,
        task_slug=TASK_SLUG,
        dataset_slugs=[DATASET_SLUG],
    )
    return paper_id, task_id, datasets[DATASET_SLUG]


def _validate_leaderboard(db, task_id: int, dataset_id: int) -> None:
    validate_leaderboard(
        db,
        task_id=task_id,
        dataset_id=dataset_id,
        dataset_slug=DATASET_SLUG,
        metrics=METRICS,
        best_metric=BEST_METRIC,
    )


def _upsert_eval(
    db,
    service: EvaluationService,
    paper_id: int,
    task_id: int,
    dataset_id: int,
) -> tuple[str, int]:
    return upsert_evaluation(
        db,
        service,
        paper_id=paper_id,
        task_id=task_id,
        dataset_id=dataset_id,
        model_name=MODEL_NAME,
        metrics=METRICS,
        methodology=METHODOLOGY,
        best_metric=BEST_METRIC,
        source_url=SOURCE_URL,
        num_parameters=NUM_PARAMETERS,
        hf_model_url=HF_MODEL_URL,
    )


def main() -> None:
    session_gen = get_database_session()
    db = next(session_gen)
    try:
        paper_id, task_id, dataset_id = _resolve_scope(db)
        _validate_leaderboard(db, task_id, dataset_id)
        db.execute(
            text(
                """
                INSERT INTO paper_tasks (paper_id, task_id, source)
                VALUES (:paper_id, :task_id, 'manual')
                ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'
                """
            ),
            {"paper_id": paper_id, "task_id": task_id},
        )
        db.execute(
            text(
                """
                UPDATE papers
                SET hf_models = CASE
                    WHEN :hf_model_url = ANY(COALESCE(hf_models, ARRAY[]::text[]))
                    THEN hf_models
                    ELSE array_append(COALESCE(hf_models, ARRAY[]::text[]), :hf_model_url)
                END,
                updated_at = NOW()
                WHERE id = :paper_id
                """
            ),
            {"paper_id": paper_id, "hf_model_url": HF_MODEL_URL},
        )
        db.commit()

        status, evaluation_id = _upsert_eval(
            db, EvaluationService(db), paper_id, task_id, dataset_id
        )
        print(
            status,
            f"evaluation_id={evaluation_id}",
            f"paper_id={paper_id}",
            f"dataset_id={dataset_id}",
            f"model={MODEL_NAME}",
            f"metrics={METRICS}",
            f"num_parameters={NUM_PARAMETERS}",
            f"hf_model_url={HF_MODEL_URL}",
        )
    finally:
        try:
            next(session_gen)
        except StopIteration:
            pass


if __name__ == "__main__":
    main()
