"""Import paper-native Octree-GS novel-view-synthesis averages.

Only introduced Octree-GS variants from arXiv:2403.17898 are included. The
paper does not evaluate NeRF Synthetic, so that leaderboard is deliberately
excluded rather than populated from an incompatible or derived result.

Run:
    uv run --env-file backend/keys.env python \
        backend/database/evaluations_setup/import_octree_gs_paper_evals.py
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

ARXIV_ID = "2403.17898"
TASK_SLUG = "novel-view-synthesis"
BEST_METRIC = "PSNR"
SOURCE_URL = f"https://arxiv.org/abs/{ARXIV_ID}"


@dataclass(frozen=True)
class EvalSpec:
    dataset_slug: str
    model_name: str
    metrics: dict[str, str]
    methodology: str


EVALS = (
    EvalSpec(
        dataset_slug="mip-nerf-360",
        model_name="Octree-GS (Scaffold-GS)",
        metrics={"PSNR": "28.05", "SSIM": "0.819", "LPIPS": "0.214"},
        methodology=(
            "Paper-native Our-Scaffold-GS result from Table I, averaged over "
            "all nine Mip-NeRF 360 scenes with one of every eight images used "
            "for testing. It has the best reported PSNR among the introduced "
            "Octree-GS backbones on this benchmark. The Scaffold-GS-backed "
            "model organizes anchors into cumulative octree LOD levels and "
            "uses LOD-aware growing, view-frequency pruning, and progressive "
            "coarse-to-fine training for 40K iterations."
        ),
    ),
    EvalSpec(
        dataset_slug="tanks-and-temples-train-truck-nvs",
        model_name="Octree-GS (Scaffold-GS)",
        metrics={"PSNR": "24.68", "SSIM": "0.866", "LPIPS": "0.153"},
        methodology=(
            "Paper-native Our-Scaffold-GS result from Table I, averaged over "
            "exactly the Tanks and Temples Train and Truck scenes with one of "
            "every eight images used for testing. It has the best reported "
            "PSNR among the introduced Octree-GS backbones on this benchmark. "
            "The Scaffold-GS-backed model organizes anchors into cumulative "
            "octree LOD levels and uses LOD-aware growing, view-frequency "
            "pruning, and progressive coarse-to-fine training for 40K "
            "iterations."
        ),
    ),
    EvalSpec(
        dataset_slug="deep-blending-drjohnson-playroom-nvs",
        model_name="Octree-GS (Scaffold-GS)",
        metrics={"PSNR": "30.49", "SSIM": "0.912", "LPIPS": "0.241"},
        methodology=(
            "Paper-native Our-Scaffold-GS result from Table I, averaged over "
            "exactly the Deep Blending Dr Johnson and Playroom scenes with one "
            "of every eight images used for testing. It has the best reported "
            "PSNR among the introduced Octree-GS backbones on this benchmark. "
            "The Scaffold-GS-backed model organizes anchors into cumulative "
            "octree LOD levels and uses LOD-aware growing, view-frequency "
            "pruning, and progressive coarse-to-fine training for 40K "
            "iterations."
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
    model_name = spec.model_name
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
                f"model={spec.model_name}",
                f"metrics={spec.metrics}",
            )
        print(
            "skipped dataset_id=1135 slug=nerf-synthetic-full-view "
            "reason=paper reports no NeRF Synthetic experiment or exact aggregate"
        )
        print("summary", counts)
    finally:
        try:
            next(session_gen)
        except StopIteration:
            pass


if __name__ == "__main__":
    main()
