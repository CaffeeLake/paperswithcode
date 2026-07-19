"""Import paper-native Scaffold-GS novel-view-synthesis averages.

Only Scaffold-GS results from arXiv:2312.00109 are included. The paper's
Mip-NeRF 360 result averages seven scenes, so it is deliberately excluded from
the configured full nine-scene leaderboard.

Run:
    uv run --env-file backend/keys.env python \
        backend/database/evaluations_setup/import_scaffold_gs_paper_evals.py
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

ARXIV_ID = "2312.00109"
TASK_SLUG = "novel-view-synthesis"
MODEL_NAME = "Scaffold-GS"
BEST_METRIC = "PSNR"
SOURCE_URL = f"https://arxiv.org/abs/{ARXIV_ID}"


@dataclass(frozen=True)
class EvalSpec:
    dataset_slug: str
    metrics: dict[str, str]
    methodology: str


EVALS = (
    EvalSpec(
        dataset_slug="tanks-and-temples-train-truck-nvs",
        metrics={"PSNR": "23.96", "SSIM": "0.853", "LPIPS": "0.177"},
        methodology=(
            "Paper-native Scaffold-GS result from Table 1, with the exact "
            "Train and Truck scene values documented in supplementary Tables "
            "10-12. Unweighted mean over those two Tanks and Temples scenes. "
            "Scaffold-GS is trained for 30K iterations with k=10 neural "
            "Gaussians per anchor and follows the original 3D-GS dataset "
            "preparation for this benchmark."
        ),
    ),
    EvalSpec(
        dataset_slug="deep-blending-drjohnson-playroom-nvs",
        metrics={"PSNR": "30.21", "SSIM": "0.906", "LPIPS": "0.254"},
        methodology=(
            "Paper-native Scaffold-GS result from Table 1, with the exact Dr "
            "Johnson and Playroom scene values documented in supplementary "
            "Tables 10-12. Unweighted mean over those two Deep Blending "
            "scenes. Scaffold-GS is trained for 30K iterations with k=10 "
            "neural Gaussians per anchor and follows the original 3D-GS "
            "dataset preparation for this benchmark."
        ),
    ),
    EvalSpec(
        dataset_slug="nerf-synthetic-full-view",
        metrics={"PSNR": "33.68"},
        methodology=(
            "Paper-native Scaffold-GS result from Table 3, averaged over all "
            "eight Synthetic Blender scenes; the per-scene PSNR values are in "
            "supplementary Table 14. The method starts from 100K grid points, "
            "trains for 30K iterations to grow and prune anchors, then uses "
            "the remaining points as initialized anchors and reruns the "
            "framework. Only full-set average PSNR is reported."
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
                f"metrics={spec.metrics}",
            )
        print(
            "skipped dataset_id=1117 slug=mip-nerf-360 "
            "reason=paper reports a seven-scene average, not the configured "
            "full nine-scene protocol"
        )
        print("summary", counts)
    finally:
        try:
            next(session_gen)
        except StopIteration:
            pass


if __name__ == "__main__":
    main()
