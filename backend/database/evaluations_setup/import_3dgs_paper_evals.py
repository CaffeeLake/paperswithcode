"""Import the paper-native 3DGS novel-view-synthesis averages.

Only the best introduced configuration (Ours-30K) from arXiv:2308.04079 is
included. Comparator methods and incompatible sparse or reduced-scene
protocols are intentionally excluded.

Run:
    uv run --env-file backend/keys.env python \
        backend/database/evaluations_setup/import_3dgs_paper_evals.py
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

ARXIV_ID = "2308.04079"
TASK_SLUG = "novel-view-synthesis"
MODEL_NAME = "3D Gaussian Splatting (30K)"
BEST_METRIC = "PSNR"
SOURCE_URL = f"https://arxiv.org/abs/{ARXIV_ID}"


@dataclass(frozen=True)
class EvalSpec:
    dataset_slug: str
    metrics: dict[str, str]
    methodology: str


EVALS = (
    EvalSpec(
        dataset_slug="mip-nerf-360",
        metrics={"PSNR": "27.21", "SSIM": "0.815", "LPIPS": "0.214"},
        methodology=(
            "Paper-native Ours-30K result from 3DGS Table 1. Unweighted mean "
            "over all nine Mip-NeRF 360 scenes (bicycle, flowers, garden, "
            "stump, treehill, room, counter, kitchen, and bonsai), using every "
            "eighth photo as a held-out test view under the Mip-NeRF 360 "
            "protocol. The paper uses one hyperparameter configuration across "
            "the real-scene experiments and reports PSNR, SSIM, and LPIPS."
        ),
    ),
    EvalSpec(
        dataset_slug="tanks-and-temples-train-truck-nvs",
        metrics={"PSNR": "23.14", "SSIM": "0.841", "LPIPS": "0.183"},
        methodology=(
            "Paper-native Ours-30K result from 3DGS Table 1. Unweighted mean "
            "over exactly the Tanks and Temples Train and Truck scenes, using "
            "every eighth photo as a held-out test view. The paper uses one "
            "hyperparameter configuration across the real-scene experiments "
            "and reports PSNR, SSIM, and LPIPS."
        ),
    ),
    EvalSpec(
        dataset_slug="deep-blending-drjohnson-playroom-nvs",
        metrics={"PSNR": "29.41", "SSIM": "0.903", "LPIPS": "0.243"},
        methodology=(
            "Paper-native Ours-30K result from 3DGS Table 1. Unweighted mean "
            "over exactly the Deep Blending DrJohnson and Playroom scenes, "
            "using every eighth photo as a held-out test view. The paper uses "
            "one hyperparameter configuration across the real-scene "
            "experiments and reports PSNR, SSIM, and LPIPS."
        ),
    ),
    EvalSpec(
        dataset_slug="nerf-synthetic-full-view",
        metrics={"PSNR": "33.32"},
        methodology=(
            "Paper-native Ours-30K average from 3DGS Table 2 over all eight "
            "NeRF Synthetic scenes (Mic, Chair, Ship, Materials, Lego, Drums, "
            "Ficus, and Hotdog). The experiment uses a white background and "
            "initializes 100K points uniformly at random. Table 2 reports only "
            "the compatible full-set average PSNR."
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
        print("summary", counts)
    finally:
        try:
            next(session_gen)
        except StopIteration:
            pass


if __name__ == "__main__":
    main()
