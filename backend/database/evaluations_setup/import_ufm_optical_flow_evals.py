#!/usr/bin/env python3
"""Import paper-native UFM optical-flow evaluations.

Run with:
    uv run --env-file backend/keys.env \
        python backend/database/evaluations_setup/import_ufm_optical_flow_evals.py
"""

from sqlalchemy import text

from backend.database.connection import get_database_session
from backend.services.evaluation_service import EvaluationService


PAPER_ID = 50916
TASK_ID = 323
PARAMETERS = 428_254_727
HF_MODEL = "https://huggingface.co/infinity1096/UFM-Base-980"

ROWS = [
    {
        "dataset_id": 1375,
        "model_name": "UFM980 Base (DINOv2 ViT-L, 2-frame, 980x644)",
        "metrics": {"EPE": 2.94, "F1-all": 11.0},
        "best_metric": "EPE",
        "source_url": "https://arxiv.org/abs/2506.09278",
        "methodology": (
            "Paper Table 4, KITTI 2015 public training-set evaluation at the "
            "dataset's original resolution. This benchmark-wise best "
            "introduced row uses the base UFM980 checkpoint without the "
            "separate refinement module and consumes one image pair. It uses "
            "a fine-tuned DINOv2 ViT-L encoder, 12 global self-attention "
            "layers, and DPT flow/covisibility heads, with inference at "
            "980x644. UFM980 is initialized from the unified UFM560 model and "
            "then trained for 15 epochs at high resolution on the paper's "
            "optical-flow training mixture. EPE is the all-valid-pixel mean; "
            "F1-all is the KITTI percentage of pixels exceeding both 3 px "
            "absolute and 5% relative error."
        ),
    }
]


def main() -> None:
    session_gen = get_database_session()
    db = next(session_gen)
    try:
        paper = (
            db.execute(
                text("SELECT arxiv_id, hf_models FROM papers WHERE id = :id"),
                {"id": PAPER_ID},
            )
            .mappings()
            .one()
        )
        if paper["arxiv_id"] != "2506.09278":
            raise RuntimeError(f"Unexpected source paper: {dict(paper)}")

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
        existing_hf = paper["hf_models"] or []
        if not isinstance(existing_hf, list):
            existing_hf = []
        db.execute(
            text(
                "UPDATE papers SET hf_models = CAST(:models AS text[]) WHERE id = :id"
            ),
            {
                "models": sorted(set(existing_hf) | {HF_MODEL}),
                "id": PAPER_ID,
            },
        )
        db.commit()

        service = EvaluationService(db)
        results: list[tuple[str, int, int]] = []
        for row in ROWS:
            allowed = {
                result[0]
                for result in db.execute(
                    text(
                        """
                        SELECT m.name
                        FROM task_dataset_metrics tdm
                        JOIN metrics m ON m.id = tdm.metric_id
                        WHERE tdm.task_id = :task_id
                          AND tdm.dataset_id = :dataset_id
                        """
                    ),
                    {"task_id": TASK_ID, "dataset_id": row["dataset_id"]},
                )
            }
            if not set(row["metrics"]).issubset(allowed):
                raise RuntimeError(
                    f"Metric mismatch for dataset {row['dataset_id']}: "
                    f"outgoing={set(row['metrics'])}, allowed={allowed}"
                )

            existing_id = db.execute(
                text(
                    """
                    SELECT id
                    FROM evaluations
                    WHERE paper_id = :paper_id AND task_id = :task_id
                      AND dataset_id = :dataset_id
                      AND model_name = :model_name
                      AND harness IS NULL AND best_metric = :best_metric
                    ORDER BY id LIMIT 1
                    """
                ),
                {
                    "paper_id": PAPER_ID,
                    "task_id": TASK_ID,
                    "dataset_id": row["dataset_id"],
                    "model_name": row["model_name"],
                    "best_metric": row["best_metric"],
                },
            ).scalar_one_or_none()

            if existing_id is None:
                evaluation = service.create_evaluation(
                    paper_id=PAPER_ID,
                    task_id=TASK_ID,
                    dataset_id=row["dataset_id"],
                    model_name=row["model_name"],
                    methodology=row["methodology"],
                    metrics=row["metrics"],
                    best_metric=row["best_metric"],
                    source_url=row["source_url"],
                    uses_additional_data=True,
                    is_open=True,
                    num_parameters=PARAMETERS,
                    hf_model_url=HF_MODEL,
                )
                evaluation_id = int(evaluation.id)
                action = "created"
            else:
                service.update_evaluation(
                    existing_id,
                    model_name=row["model_name"],
                    methodology=row["methodology"],
                    metrics=row["metrics"],
                    best_metric=row["best_metric"],
                    uses_additional_data=True,
                    is_open=True,
                    harness=None,
                    harness_set=True,
                    source_url=row["source_url"],
                    source_url_set=True,
                    num_parameters=PARAMETERS,
                    num_parameters_set=True,
                    hf_model_url=HF_MODEL,
                    hf_model_url_set=True,
                )
                evaluation_id = int(existing_id)
                action = "updated"

            for metric in row["metrics"]:
                service.recalculate_ranks(
                    TASK_ID, row["dataset_id"], metric_name=metric
                )
            results.append((action, evaluation_id, row["dataset_id"]))

        for result in results:
            print(result)
    finally:
        db.close()


if __name__ == "__main__":
    main()
