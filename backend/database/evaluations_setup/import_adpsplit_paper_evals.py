"""Import paper-native AdpSplit novel-view-synthesis averages.

Only rows that apply the introduced AdpSplit operator from arXiv:2605.06876
are included; bare backbone baselines are deliberately excluded.

Run:
    uv run --env-file backend/keys.env python \
        backend/database/evaluations_setup/import_adpsplit_paper_evals.py
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text

from backend.database.connection import get_database_session
from backend.services.evaluation_service import EvaluationService
from backend.database.evaluations_setup.paper_eval_import import (
    resolve_scope,
    upsert_evaluation,
    validate_leaderboard,
)

ARXIV_ID = "2605.06876"
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
        model_name="DashGaussian-AdpSplit",
        metrics={"PSNR": "27.70", "SSIM": "0.820", "LPIPS": "0.213"},
        methodology=(
            "Paper-native DashGaussian-AdpSplit result from Table 1, averaged "
            "over all nine Mip-NeRF 360 scenes under the standard 3DGS image "
            "resize and train/test protocol. This is the highest-PSNR "
            "AdpSplit row on the benchmark. AdpSplit replaces the standard "
            "binary split operator within DashGaussian's shortened 19K "
            "densification plus 5K fine-tuning schedule, selecting adaptive "
            "child counts and initial parameters from multi-view L1-error "
            "region statistics."
        ),
    ),
    EvalSpec(
        dataset_slug="deep-blending-drjohnson-playroom-nvs",
        model_name="MiniSplatting-AdpSplit",
        metrics={"PSNR": "29.97", "SSIM": "0.910", "LPIPS": "0.242"},
        methodology=(
            "Paper-native MiniSplatting-AdpSplit result from Table 1, averaged "
            "over exactly the Deep Blending Dr Johnson and Playroom scenes "
            "under the standard 3DGS image resize and train/test protocol. "
            "This is the highest-PSNR AdpSplit row on the benchmark. AdpSplit "
            "replaces MiniSplatting's standard split operator within the "
            "shortened 9K densification and 24K total optimization schedule, "
            "selecting adaptive child counts and initial parameters from "
            "multi-view L1-error region statistics."
        ),
    ),
    EvalSpec(
        dataset_slug="tanks-and-temples-train-truck-nvs",
        model_name="FastGS-AdpSplit",
        metrics={"PSNR": "24.17", "SSIM": "0.840", "LPIPS": "0.209"},
        methodology=(
            "Paper-native FastGS-AdpSplit result from Table 1, averaged over "
            "exactly the Tanks and Temples Train and Truck scenes under the "
            "standard 3DGS image resize and train/test protocol. This is the "
            "highest-PSNR AdpSplit row on the benchmark. AdpSplit replaces "
            "FastGS's standard split operator within the shortened 9K "
            "densification and 24K total optimization schedule, selecting "
            "adaptive child counts and initial parameters from multi-view "
            "L1-error region statistics."
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
        db.commit()

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
