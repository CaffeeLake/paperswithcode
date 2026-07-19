"""Import PixWorld (2607.05373) evaluation rows from the arXiv paper tables.

Run after add_pixworld_benchmarks.py:
    uv run --env-file backend/keys.env \\
        python backend/database/evaluations_setup/import_pixworld_evals.py
"""

from __future__ import annotations

from sqlalchemy import text

from backend.database.connection import get_database_session
from backend.services.evaluation_service import EvaluationService

PAPER_ID = 102577
TASK_ID = 13
MODEL_NAME = "PixWorld"
NUM_PARAMETERS = 1_040_000_000
IS_OPEN = False

SCORES: dict[str, dict[str, str]] = {
    "re10k-4-view": {"PSNR": "26.21", "SSIM": "0.844", "LPIPS": "0.138"},
    "re10k-8-view": {"PSNR": "28.58", "SSIM": "0.892", "LPIPS": "0.101"},
    "re10k-1-view": {
        "PSNR": "18.88",
        "SSIM": "0.702",
        "LPIPS": "0.325",
        "AUC@5": "0.614",
    },
    "re10k-2-view": {
        "PSNR": "23.54",
        "SSIM": "0.815",
        "LPIPS": "0.210",
        "AUC@5": "0.649",
    },
    "dl3dv-10k-4-view": {"PSNR": "23.18", "SSIM": "0.714", "LPIPS": "0.226"},
    "dl3dv-10k-8-view": {"PSNR": "22.46", "SSIM": "0.681", "LPIPS": "0.257"},
    "dl3dv-10k-1-view": {
        "PSNR": "16.50",
        "SSIM": "0.527",
        "LPIPS": "0.449",
        "AUC@5": "0.485",
    },
    "dl3dv-10k-2-view": {
        "PSNR": "19.37",
        "SSIM": "0.594",
        "LPIPS": "0.340",
        "AUC@5": "0.534",
    },
    "worldscore": {"Average": "71.04"},
}

METHODOLOGY: dict[str, str] = {
    "re10k-4-view": (
        "Table 1 reconstruction on RealEstate10K with 4 posed input views; "
        "200-scene wide-baseline test split; arXiv HTML source."
    ),
    "re10k-8-view": (
        "Table 1 reconstruction on RealEstate10K with 8 posed input views; "
        "200-scene wide-baseline test split; arXiv HTML source."
    ),
    "re10k-1-view": (
        "Table 2 single-image generation averaged over First-Frame and "
        "Bidirectional configurations on RealEstate10K; arXiv HTML source."
    ),
    "re10k-2-view": (
        "Table 3 two-view generation averaged over Interpolation and "
        "Extrapolation configurations on RealEstate10K; arXiv HTML source."
    ),
    "dl3dv-10k-4-view": (
        "Table 1 reconstruction on DL3DV-10K with 4 posed input views; "
        "200-scene wide-baseline test split; arXiv HTML source."
    ),
    "dl3dv-10k-8-view": (
        "Table 1 reconstruction on DL3DV-10K with 8 posed input views; "
        "200-scene wide-baseline test split; arXiv HTML source."
    ),
    "dl3dv-10k-1-view": (
        "Table 2 single-image generation averaged over First-Frame and "
        "Bidirectional configurations on DL3DV-10K; arXiv HTML source."
    ),
    "dl3dv-10k-2-view": (
        "Table 3 two-view generation averaged over Interpolation and "
        "Extrapolation configurations on DL3DV-10K; arXiv HTML source."
    ),
    "worldscore": (
        "Table 4 official WorldScore static split average across seven "
        "component metrics; arXiv HTML source."
    ),
}


def main() -> None:
    session_gen = get_database_session()
    db = next(session_gen)
    created = 0
    skipped = 0
    try:
        slug_to_id = {
            row.slug: row.id
            for row in db.execute(
                text("SELECT id, slug FROM datasets WHERE slug = ANY(:slugs)"),
                {"slugs": list(SCORES)},
            )
        }
        missing = sorted(set(SCORES) - set(slug_to_id))
        if missing:
            raise RuntimeError(
                f"Missing datasets for slugs {missing}; run add_pixworld_benchmarks.py first"
            )

        service = EvaluationService(db)
        for slug, metrics in SCORES.items():
            dataset_id = slug_to_id[slug]
            for metric, value in metrics.items():
                params = {
                    "paper_id": PAPER_ID,
                    "task_id": TASK_ID,
                    "dataset_id": dataset_id,
                    "model_name": MODEL_NAME,
                    "harness": None,
                    "best_metric": metric,
                }
                existing = db.execute(
                    text(
                        """
                        SELECT id FROM evaluations
                        WHERE paper_id=:paper_id AND task_id=:task_id
                          AND dataset_id=:dataset_id AND model_name=:model_name
                          AND COALESCE(harness, '') = COALESCE(:harness, '')
                          AND best_metric=:best_metric
                        """
                    ),
                    params,
                ).first()
                if existing:
                    skipped += 1
                    continue
                service.create_evaluation(
                    paper_id=PAPER_ID,
                    task_id=TASK_ID,
                    dataset_id=dataset_id,
                    model_name=MODEL_NAME,
                    methodology=METHODOLOGY[slug],
                    metrics={metric: value},
                    best_metric=metric,
                    harness=None,
                    num_parameters=NUM_PARAMETERS,
                    is_open=IS_OPEN,
                )
                created += 1
        db.commit()
        print(f"created={created} skipped={skipped}")
    finally:
        try:
            next(session_gen)
        except StopIteration:
            pass


if __name__ == "__main__":
    main()
