"""Import paper-native Self-Organizing Gaussian Grids NVS averages.

Only introduced variants from arXiv:2312.13299 are included. Each result is
an exact aggregate over the scene set configured by the corresponding local
leaderboard; comparison baselines are deliberately excluded.

Run:
    uv run --env-file backend/keys.env python \
        backend/database/evaluations_setup/import_self_organizing_gaussian_grids_evals.py
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

ARXIV_ID = "2312.13299"
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
        model_name="Self-Organizing Gaussian Grids",
        metrics={"PSNR": "27.64", "SSIM": "0.814", "LPIPS": "0.220"},
        methodology=(
            "Paper-native Ours result from Table 1 (PSNR and LPIPS) and "
            "Appendix Table 5 (SSIM), averaged over all nine Mip-NeRF 360 "
            "scenes. The method periodically organizes Gaussian attributes "
            "with PLAS during 3DGS training, applies grid-neighborhood "
            "smoothness regularization, then quantizes and JPEG XL encodes "
            "the resulting attribute grids."
        ),
    ),
    EvalSpec(
        dataset_slug="tanks-and-temples-train-truck-nvs",
        model_name="Self-Organizing Gaussian Grids",
        metrics={"PSNR": "25.63", "SSIM": "0.864", "LPIPS": "0.208"},
        methodology=(
            "Paper-native Ours result from Table 1 (PSNR and LPIPS) and "
            "Appendix Table 5 (SSIM), averaged over exactly the Tanks and "
            "Temples Train and Truck scenes. The method periodically "
            "organizes Gaussian attributes with PLAS during 3DGS training, "
            "applies grid-neighborhood smoothness regularization, then "
            "quantizes and JPEG XL encodes the resulting attribute grids."
        ),
    ),
    EvalSpec(
        dataset_slug="deep-blending-drjohnson-playroom-nvs",
        model_name="Self-Organizing Gaussian Grids (w/o SH)",
        metrics={"PSNR": "30.50", "SSIM": "0.908", "LPIPS": "0.261"},
        methodology=(
            "Paper-native Ours w/o SH result from Table 1 (PSNR and LPIPS) "
            "and Appendix Table 5 (SSIM), averaged over exactly the Deep "
            "Blending Dr Johnson and Playroom scenes. This introduced "
            "variant has the paper's best PSNR on this benchmark; all three "
            "metrics come from that same variant. It omits spherical "
            "harmonics while retaining PLAS organization, smoothness "
            "regularization, quantization, and grid encoding."
        ),
    ),
    EvalSpec(
        dataset_slug="nerf-synthetic-full-view",
        model_name="Self-Organizing Gaussian Grids",
        metrics={"PSNR": "33.70", "SSIM": "0.969", "LPIPS": "0.031"},
        methodology=(
            "Paper-native Ours result from Table 1 (PSNR and LPIPS) and "
            "Appendix Table 5 (SSIM), averaged over all eight NeRF Synthetic "
            "scenes. The method periodically organizes Gaussian attributes "
            "with PLAS during 3DGS training, applies grid-neighborhood "
            "smoothness regularization, then quantizes and JPEG XL encodes "
            "the resulting attribute grids."
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
        print("summary", counts)
    finally:
        try:
            next(session_gen)
        except StopIteration:
            pass


if __name__ == "__main__":
    main()
