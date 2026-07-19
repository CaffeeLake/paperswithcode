"""Import paper-native CompGS novel-view-synthesis averages.

Only introduced CompGS variants from arXiv:2311.18159 are included. The final
CompGS Deep Blending result is reported per scene without an aggregate, so that
leaderboard is deliberately excluded rather than deriving an unpublished mean.

Run:
    uv run --env-file backend/keys.env python \
        backend/database/evaluations_setup/import_compgs_paper_evals.py
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

ARXIV_ID = "2311.18159"
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
        model_name="CompGS 32K",
        metrics={"PSNR": "27.12", "SSIM": "0.806", "LPIPS": "0.240"},
        methodology=(
            "Paper-native CompGS 32K result from Table 1, averaged over all "
            "nine Mip-NeRF 360 scenes with the Mip-NeRF 360/3DGS train-test "
            "split. This is the best reported introduced CompGS quality "
            "variant on this benchmark. Training runs for 30K iterations on a "
            "single RTX 6000; vector quantization is active for the final 10K "
            "iterations and opacity regularization is used during training."
        ),
    ),
    EvalSpec(
        dataset_slug="tanks-and-temples-train-truck-nvs",
        model_name="CompGS 32K",
        metrics={"PSNR": "23.44", "SSIM": "0.838", "LPIPS": "0.198"},
        methodology=(
            "Paper-native CompGS 32K result from Table 1, averaged over "
            "exactly the Tanks and Temples Train and Truck scenes with the "
            "Mip-NeRF 360/3DGS train-test split. This is the best reported "
            "introduced CompGS quality variant on this benchmark. Training "
            "runs for 30K iterations on a single RTX 6000; vector quantization "
            "is active for the final 10K iterations and opacity regularization "
            "is used during training."
        ),
    ),
    EvalSpec(
        dataset_slug="nerf-synthetic-full-view",
        model_name="CompGS 4K",
        metrics={"PSNR": "33.10"},
        methodology=(
            "Paper-native CompGS 4K result from supplementary Table A.1, "
            "averaged over all eight NeRF Synthetic scenes. This is the only "
            "introduced CompGS variant with an exact full-set aggregate in "
            "that table, which reports PSNR only."
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
            "skipped dataset_id=1139 "
            "slug=deep-blending-drjohnson-playroom-nvs "
            "reason=final CompGS 32K is reported per scene without an exact "
            "aggregate; aggregate tables cover component ablations"
        )
        print("summary", counts)
    finally:
        try:
            next(session_gen)
        except StopIteration:
            pass


if __name__ == "__main__":
    main()
