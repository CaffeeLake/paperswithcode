#!/usr/bin/env python3
"""Import E2FAI's official DSEC-Flow hidden-test evaluation.

Run with:
    uv run --env-file backend/keys.env \
        python backend/database/evaluations_setup/import_e2fai_dsec_flow_evals.py
"""

from datetime import date

from sqlalchemy import text

from backend.database.connection import get_database_session
from backend.services.evaluation_service import EvaluationService


PAPER_ID = 87897
TASK_ID = 323
DATASET_ID = 1384
MODEL_NAME = "E2FAI [selfsup]"
BEST_METRIC = "EPE"
SOURCE_URL = (
    "https://dsec.ifi.uzh.ch/uzh/dsec-flow-optical-flow-benchmark/e2fai-selfsup/"
)
DATE_PUBLISHED = date(2025, 3, 21)
METRICS = {
    "EPE": 1.781,
    "1PE": 37.462,
    "2PE": 17.587,
    "3PE": 11.241,
}
METHODOLOGY = (
    "Exact all-sequence aggregate from the official DSEC hidden-test server's "
    "E2FAI [selfsup] submission (submission report 315), evaluated on the "
    "undistorted/rectified left event-camera view, forward flow, and all valid "
    "ground-truth pixels. The model is trained self-supervised on selected "
    "DSEC training sequences without ground-truth flow and is evaluated without "
    "test fine-tuning. Its only input is an events-only 15-bin voxel grid; no "
    "global-shutter intensity-camera frames are used. A single bilinear U-Net "
    "jointly predicts two-channel optical flow and one-channel reconstructed "
    "intensity, so intensity is an internal prediction/loss signal rather than "
    "an input modality. Raw flow is average-pooled with a 16-pixel kernel and "
    "bilinearly interpolated to full resolution. EPE is in pixels; 1PE, 2PE, "
    "and 3PE are percentages."
)


def main() -> None:
    session_gen = get_database_session()
    db = next(session_gen)
    try:
        paper = (
            db.execute(
                text("SELECT arxiv_id, title FROM papers WHERE id = :id"),
                {"id": PAPER_ID},
            )
            .mappings()
            .one()
        )
        if paper["arxiv_id"] != "2503.17262":
            raise RuntimeError(f"Unexpected source paper: {dict(paper)}")

        board = (
            db.execute(
                text(
                    """
                SELECT td.supports_harness,
                       array_agg(m.name ORDER BY m.name) AS metrics
                FROM task_datasets td
                JOIN task_dataset_metrics tdm
                  ON tdm.task_id = td.task_id
                 AND tdm.dataset_id = td.dataset_id
                JOIN metrics m ON m.id = tdm.metric_id
                WHERE td.task_id = :task_id AND td.dataset_id = :dataset_id
                GROUP BY td.supports_harness
                """
                ),
                {"task_id": TASK_ID, "dataset_id": DATASET_ID},
            )
            .mappings()
            .one()
        )
        if board["supports_harness"]:
            raise RuntimeError("DSEC-Flow unexpectedly supports harness metadata")
        if not set(METRICS).issubset(set(board["metrics"])):
            raise RuntimeError(f"Leaderboard metric mismatch: {dict(board)}")

        db.execute(
            text(
                """
                INSERT INTO paper_tasks (paper_id, task_id, source)
                VALUES (:paper_id, :task_id, 'manual')
                ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'
                """
            ),
            {"paper_id": PAPER_ID, "task_id": TASK_ID},
        )
        db.execute(
            text(
                """
                UPDATE papers
                SET date_published = COALESCE(date_published, :date_published)
                WHERE id = :paper_id
                """
            ),
            {"paper_id": PAPER_ID, "date_published": DATE_PUBLISHED},
        )
        db.commit()

        existing_id = db.execute(
            text(
                """
                SELECT id
                FROM evaluations
                WHERE paper_id = :paper_id
                  AND task_id = :task_id
                  AND dataset_id = :dataset_id
                  AND model_name = :model_name
                  AND harness IS NULL
                  AND best_metric = :best_metric
                ORDER BY id
                LIMIT 1
                """
            ),
            {
                "paper_id": PAPER_ID,
                "task_id": TASK_ID,
                "dataset_id": DATASET_ID,
                "model_name": MODEL_NAME,
                "best_metric": BEST_METRIC,
            },
        ).scalar_one_or_none()

        service = EvaluationService(db)
        if existing_id is None:
            evaluation = service.create_evaluation(
                paper_id=PAPER_ID,
                task_id=TASK_ID,
                dataset_id=DATASET_ID,
                model_name=MODEL_NAME,
                methodology=METHODOLOGY,
                metrics=METRICS,
                best_metric=BEST_METRIC,
                harness=None,
                source_url=SOURCE_URL,
                uses_additional_data=False,
                is_open=True,
                num_parameters=None,
                hf_model_url=None,
            )
            evaluation_id = evaluation.id
            action = "created"
        else:
            service.update_evaluation(
                existing_id,
                model_name=MODEL_NAME,
                methodology=METHODOLOGY,
                metrics=METRICS,
                best_metric=BEST_METRIC,
                uses_additional_data=False,
                is_open=True,
                harness=None,
                harness_set=True,
                source_url=SOURCE_URL,
                source_url_set=True,
                num_parameters=None,
                num_parameters_set=True,
                hf_model_url=None,
                hf_model_url_set=True,
            )
            evaluation_id = existing_id
            action = "updated"

        for metric in METRICS:
            service.recalculate_ranks(TASK_ID, DATASET_ID, metric_name=metric)
        print(f"{action} evaluation_id={evaluation_id} metrics={METRICS}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
