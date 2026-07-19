#!/usr/bin/env python3
"""Import paper-native SplatFlow optical-flow evaluations.

Run with:
    uv run --env-file backend/keys.env \
        python backend/database/evaluations_setup/import_splatflow_optical_flow_evals.py
"""

from sqlalchemy import text

from backend.database.connection import get_database_session
from backend.services.evaluation_service import EvaluationService


PAPER_ID = 17449
TASK_ID = 323
PARAMETERS = 9_000_000
HF_KITTI_MODEL = "https://huggingface.co/wwcreator/SplatFlow"

ROWS = [
    {
        "dataset_id": 1366,
        "model_name": ("SplatFlow-GMA (Sintel fine-tuned, 3-frame, no WarmStart)"),
        "metrics": {"Average End-Point Error": 1.119},
        "best_metric": "Average End-Point Error",
        "source_url": (
            "https://sintel.is.tue.mpg.de/quant?metric_id=0&selected_pass=1"
        ),
        "hf_model_url": None,
        "methodology": (
            "Paper Table 7 and the exact official MPI Sintel Clean hidden-test "
            "submission. The final SplatFlow-GMA model consumes three "
            "consecutive frames and propagates a splatted previous-frame motion "
            "feature; it does not use RAFT's separate WarmStart initialization. "
            "The C+T model is fine-tuned for 120K steps on a Sintel-dominant "
            "Things+Sintel+KITTI+HD1K mixture with 368x768 crops. Evaluation "
            "uses 32 recurrent flow iterations."
        ),
    },
    {
        "dataset_id": 1367,
        "model_name": ("SplatFlow-GMA (Sintel fine-tuned, 3-frame, no WarmStart)"),
        "metrics": {"Average End-Point Error": 2.072},
        "best_metric": "Average End-Point Error",
        "source_url": (
            "https://sintel.is.tue.mpg.de/quant?metric_id=1&selected_pass=0"
        ),
        "hf_model_url": None,
        "methodology": (
            "Paper Table 7 and the exact official MPI Sintel Final hidden-test "
            "submission. The final SplatFlow-GMA model consumes three "
            "consecutive frames and propagates a splatted previous-frame motion "
            "feature; it does not use RAFT's separate WarmStart initialization. "
            "The C+T model is fine-tuned for 120K steps on a Sintel-dominant "
            "Things+Sintel+KITTI+HD1K mixture with 368x768 crops. Evaluation "
            "uses 32 recurrent flow iterations."
        ),
    },
    {
        "dataset_id": 1370,
        "model_name": "SplatFlow-GMA (KITTI fine-tuned, 3-frame)",
        "metrics": {"Fl-all": 4.61},
        "best_metric": "Fl-all",
        "source_url": (
            "https://www.cvlibs.net/datasets/kitti/"
            "eval_scene_flow_detail.php?benchmark=flow&"
            "result=23907662493c2776ea86ab082bc770a731ee19e2"
        ),
        "hf_model_url": HF_KITTI_MODEL,
        "methodology": (
            "Paper Table 7 and the exact official KITTI 2015 hidden-test "
            "submission. This three-frame SplatFlow-GMA checkpoint is further "
            "fine-tuned for 50K steps from the Sintel checkpoint on a "
            "KITTI-enhanced Things+Sintel+KITTI+HD1K mixture using 368x768 "
            "crops. KITTI samples recover the preceding raw frame, and "
            "evaluation uses 24 recurrent flow iterations."
        ),
    },
    {
        "dataset_id": 1375,
        "model_name": "SplatFlow-GMA (KITTI fine-tuned, 3-frame)",
        "legacy_model_name": "SplatFlow-GMA (C+T, 3-frame, zero-shot)",
        "metrics": {"EPE": 0.80, "F1-all": 2.4},
        "best_metric": "EPE",
        "source_url": "https://arxiv.org/abs/2306.08887",
        "hf_model_url": HF_KITTI_MODEL,
        "methodology": (
            "Paper Table 7, KITTI 2015 public training-set evaluation. This "
            "benchmark-wise best introduced row uses the final three-frame "
            "SplatFlow-GMA checkpoint after the 50K-step KITTI-enhanced "
            "fine-tuning stage on the Things+Sintel+KITTI+HD1K mixture with "
            "368x768 crops. Evaluation uses 24 recurrent iterations. The "
            "configured EPE label stores the paper's AEPE quantity; F1-all is "
            "a percentage."
        ),
    },
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
        if paper["arxiv_id"] != "2306.08887":
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
                "models": sorted(set(existing_hf) | {HF_KITTI_MODEL}),
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
                      AND model_name IN (:model_name, :legacy_model_name)
                      AND harness IS NULL AND best_metric = :best_metric
                    ORDER BY id LIMIT 1
                    """
                ),
                {
                    "paper_id": PAPER_ID,
                    "task_id": TASK_ID,
                    "dataset_id": row["dataset_id"],
                    "model_name": row["model_name"],
                    "legacy_model_name": row.get(
                        "legacy_model_name", row["model_name"]
                    ),
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
                    hf_model_url=row["hf_model_url"],
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
                    hf_model_url=row["hf_model_url"],
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
