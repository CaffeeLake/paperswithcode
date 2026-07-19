"""Import paper-native LightGaussian novel-view-synthesis averages.

Only introduced LightGaussian results from arXiv:2311.17245 are included. The
paper does not evaluate Deep Blending, so that leaderboard is deliberately
excluded rather than populated from a comparison baseline.

Run:
    uv run --env-file backend/keys.env python \
        backend/database/evaluations_setup/import_lightgaussian_paper_evals.py
"""

from __future__ import annotations

from dataclasses import dataclass


from backend.database.connection import get_database_session
from backend.services.evaluation_service import EvaluationService
from backend.database.evaluations_setup.paper_eval_import import (
    resolve_scope,
    upsert_evaluation,
    validate_leaderboard,
)

ARXIV_ID = "2311.17245"
TASK_SLUG = "novel-view-synthesis"
BEST_METRIC = "PSNR"
SOURCE_URL = f"https://arxiv.org/abs/{ARXIV_ID}"
MODEL_NAME = "LightGaussian"


@dataclass(frozen=True)
class EvalSpec:
    dataset_slug: str
    metrics: dict[str, str]
    methodology: str


EVALS = (
    EvalSpec(
        dataset_slug="mip-nerf-360",
        metrics={"PSNR": "27.13", "SSIM": "0.806", "LPIPS": "0.237"},
        methodology=(
            "Paper-native Ours result from Table 1, averaged over all nine "
            "Mip-NeRF 360 scenes. LightGaussian compresses a trained 3DGS "
            "representation using global-significance Gaussian pruning and "
            "5K-step recovery, spherical-harmonic distillation with "
            "pseudo-view augmentation, and significance-aware vector "
            "quantization of lower-importance SH coefficients."
        ),
    ),
    EvalSpec(
        dataset_slug="tanks-and-temples-train-truck-nvs",
        metrics={"PSNR": "23.44", "SSIM": "0.832", "LPIPS": "0.202"},
        methodology=(
            "Paper-native Ours result from Table 1, averaged over exactly the "
            "Tanks and Temples Train and Truck scenes used by 3DGS. "
            "LightGaussian compresses a trained 3DGS representation using "
            "global-significance Gaussian pruning and 5K-step recovery, "
            "spherical-harmonic distillation with pseudo-view augmentation, "
            "and significance-aware vector quantization of lower-importance "
            "SH coefficients."
        ),
    ),
    EvalSpec(
        dataset_slug="nerf-synthetic-full-view",
        metrics={"PSNR": "32.725", "SSIM": "0.965", "LPIPS": "0.0370"},
        methodology=(
            "Paper-native Ours average from supplementary Table 7 over all "
            "eight Synthetic-NeRF scenes: Chair, Drums, Ficus, Hotdog, Lego, "
            "Materials, Mic, and Ship. The experiment uses the standard 100 "
            "training and 200 testing views per object with random "
            "initialization, followed by LightGaussian global-significance "
            "pruning, SH compaction, and 8192-entry vector quantization."
        ),
    ),
)


def _resolve_scope(db) -> tuple[int, int, dict[str, int]]:
    return resolve_scope(
        db,
        arxiv_id=ARXIV_ID,
        task_slug=TASK_SLUG,
        dataset_slugs=(spec.dataset_slug for spec in EVALS),
    )


def _validate_leaderboard(db, task_id: int, dataset_id: int, spec: EvalSpec) -> None:
    validate_leaderboard(
        db,
        task_id=task_id,
        dataset_id=dataset_id,
        dataset_slug=spec.dataset_slug,
        metrics=spec.metrics,
        best_metric=BEST_METRIC,
    )


def _upsert_eval(
    db,
    service: EvaluationService,
    paper_id: int,
    task_id: int,
    dataset_id: int,
    spec: EvalSpec,
) -> tuple[str, int]:
    model_name = spec.model_name if hasattr(spec, "model_name") else MODEL_NAME
    return upsert_evaluation(
        db,
        service,
        paper_id=paper_id,
        task_id=task_id,
        dataset_id=dataset_id,
        model_name=model_name,
        metrics=spec.metrics,
        methodology=spec.methodology,
        best_metric=BEST_METRIC,
        source_url=SOURCE_URL,
        num_parameters=getattr(spec, "num_parameters", None),
        hf_model_url=getattr(spec, "hf_model_url", None),
    )


def main() -> None:
    session_gen = get_database_session()
    db = next(session_gen)
    try:
        paper_id, task_id, dataset_ids = _resolve_scope(db)
        service = EvaluationService(db)
        counts = {"created": 0, "updated": 0, "unchanged": 0}
        for spec in EVALS:
            dataset_id = dataset_ids[spec.dataset_slug]
            _validate_leaderboard(db, task_id, dataset_id, spec)
            status, evaluation_id = _upsert_eval(
                db, service, paper_id, task_id, dataset_id, spec
            )
            counts[status] += 1
            print(
                status,
                f"evaluation_id={evaluation_id}",
                f"dataset_id={dataset_id}",
                f"slug={spec.dataset_slug}",
                f"model={MODEL_NAME}",
                f"metrics={spec.metrics}",
            )
        print(
            "skipped dataset_id=1139 "
            "slug=deep-blending-drjohnson-playroom-nvs "
            "reason=paper does not evaluate Deep Blending"
        )
        print("summary", counts)
    finally:
        try:
            next(session_gen)
        except StopIteration:
            pass


if __name__ == "__main__":
    main()
