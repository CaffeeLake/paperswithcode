"""Import the paper-native Deformable Beta Splatting Synthetic-NeRF result.

Only the introduced best full eight-scene aggregate from arXiv:2501.18630 is
included. Dynamic and other datasets and all comparison baselines are excluded.

Run:
    uv run --env-file backend/keys.env python \
        backend/database/evaluations_setup/import_deformable_beta_splatting_evals.py
"""

from __future__ import annotations


from backend.database.connection import get_database_session
from backend.services.evaluation_service import EvaluationService
from backend.database.evaluations_setup.paper_eval_import import (
    resolve_scope,
    upsert_evaluation,
    validate_leaderboard,
)

ARXIV_ID = "2501.18630"
TASK_SLUG = "novel-view-synthesis"
DATASET_SLUG = "nerf-synthetic-full-view"
MODEL_NAME = "Deformable Beta Splatting (full)"
BEST_METRIC = "PSNR"
SOURCE_URL = f"https://arxiv.org/abs/{ARXIV_ID}"
METRICS = {"PSNR": "34.66", "SSIM": "0.973", "LPIPS": "0.028"}
METHODOLOGY = (
    "Paper-native Ours (full) result from Table 1, averaged over all eight "
    "static NeRF Synthetic scenes under the standard dense 3DGS evaluation "
    "pipeline. Synthetic primitives are randomly initialized. This flexible-"
    "stopping variant has the best introduced PSNR and combines deformable "
    "Beta geometry kernels, two-light-source Spherical Beta color encoding, "
    "and kernel-agnostic MCMC densification. All metrics come from the same "
    "aggregate row."
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
        num_parameters=None,
        hf_model_url=None,
    )


def main() -> None:
    session_gen = get_database_session()
    db = next(session_gen)
    try:
        paper_id, task_id, dataset_id = _resolve_scope(db)
        _validate_leaderboard(db, task_id, dataset_id)
        status, evaluation_id = _upsert_eval(
            db, EvaluationService(db), paper_id, task_id, dataset_id
        )
        print(
            status,
            f"evaluation_id={evaluation_id}",
            f"dataset_id={dataset_id}",
            f"slug={DATASET_SLUG}",
            f"model={MODEL_NAME}",
            f"metrics={METRICS}",
        )
    finally:
        try:
            next(session_gen)
        except StopIteration:
            pass


if __name__ == "__main__":
    main()
