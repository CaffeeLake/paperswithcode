#!/usr/bin/env python3
"""Import paper-native MEMFOF optical-flow evaluations.

Run with:
    uv run --env-file backend/keys.env \
        python backend/database/evaluations_setup/import_memfof_optical_flow_evals.py
"""

from sqlalchemy import text

from backend.database.connection import get_database_session
from backend.services.evaluation_service import EvaluationService


PAPER_ID = 51575
TASK_ID = 323
PARAMETERS = 75_782_921
SOURCE_URL = "paper:51575"

ROWS = [
    {
        "dataset_id": 1366,
        "model_name": "MEMFOF (Sintel fine-tuned, 3-frame)",
        "metrics": {"Average End-Point Error": 0.963},
        "best_metric": "Average End-Point Error",
        "hf_model_url": (
            "https://huggingface.co/egorchistov/"
            "optical-flow-MEMFOF-Tartan-T-TSKH-sintel"
        ),
        "methodology": (
            "Paper Table 3, MPI Sintel Clean official hidden test. MEMFOF uses "
            "three RGB frames and the benchmark-specific Sintel-fine-tuned "
            "checkpoint (TartanAir → Things → TSKH → Sintel). Inputs are "
            "bilinearly enlarged 2×, predictions are reduced 2×, and inference "
            "uses 16 iterative updates."
        ),
    },
    {
        "dataset_id": 1367,
        "model_name": "MEMFOF (Sintel fine-tuned, 3-frame)",
        "metrics": {"Average End-Point Error": 1.907},
        "best_metric": "Average End-Point Error",
        "hf_model_url": (
            "https://huggingface.co/egorchistov/"
            "optical-flow-MEMFOF-Tartan-T-TSKH-sintel"
        ),
        "methodology": (
            "Paper Table 3, MPI Sintel Final official hidden test. MEMFOF uses "
            "three RGB frames and the benchmark-specific Sintel-fine-tuned "
            "checkpoint (TartanAir → Things → TSKH → Sintel). Inputs are "
            "bilinearly enlarged 2×, predictions are reduced 2×, and inference "
            "uses 16 iterative updates."
        ),
    },
    {
        "dataset_id": 1370,
        "model_name": "MEMFOF (KITTI-15 fine-tuned, 3-frame)",
        "metrics": {"Fl-all": 2.94},
        "best_metric": "Fl-all",
        "hf_model_url": (
            "https://huggingface.co/egorchistov/optical-flow-MEMFOF-Tartan-T-TSKH-kitti"
        ),
        "methodology": (
            "Paper Table 3, KITTI 2015 official hidden test. MEMFOF uses three "
            "RGB frames and the benchmark-specific KITTI-fine-tuned checkpoint "
            "(TartanAir → Things → TSKH → KITTI). Inputs are bilinearly enlarged "
            "2× and predictions are reduced 2×; Fl-all is reported in percent."
        ),
    },
    {
        "dataset_id": 1371,
        "model_name": "MEMFOF (Spring fine-tuned, 3-frame)",
        "metrics": {"1px total": 3.289, "EPE": 0.355, "Fl": 1.238},
        "best_metric": "1px total",
        "hf_model_url": (
            "https://huggingface.co/egorchistov/"
            "optical-flow-MEMFOF-Tartan-T-TSKH-spring"
        ),
        "methodology": (
            "Paper Table 2, exact official Spring hidden-test submission. The "
            "selected benchmark-wise best MEMFOF variant is fine-tuned on Spring "
            "for 60K steps, consumes three native-1080p RGB frames, and uses eight "
            "iterative refinements. Error-rate metrics are percentages."
        ),
    },
    {
        "dataset_id": 1375,
        "model_name": "MEMFOF (TartanAir + Things, zero-shot, 3-frame)",
        "metrics": {"EPE": 2.93, "F1-all": 9.93},
        "best_metric": "EPE",
        "hf_model_url": (
            "https://huggingface.co/egorchistov/optical-flow-MEMFOF-Tartan-T"
        ),
        "methodology": (
            "Paper Table 10, KITTI 2015 training-set zero-shot evaluation after "
            "TartanAir and FlyingThings3D training, with no KITTI fine-tuning. "
            "MEMFOF consumes three RGB frames. The paper's Fl-epe value is the "
            "configured EPE quantity; its Fl-all percentage is stored under the "
            "leaderboard's configured F1-all label."
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
        if paper["arxiv_id"] != "2506.23151":
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
        exact_hf_urls = sorted({row["hf_model_url"] for row in ROWS})
        db.execute(
            text(
                "UPDATE papers SET hf_models = CAST(:models AS text[]) WHERE id = :id"
            ),
            {
                "models": sorted(set(existing_hf) | set(exact_hf_urls)),
                "id": PAPER_ID,
            },
        )
        db.commit()

        service = EvaluationService(db)
        results: list[tuple[str, int, int]] = []
        for row in ROWS:
            allowed = {
                r[0]
                for r in db.execute(
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
                      AND dataset_id = :dataset_id AND model_name = :model_name
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
                    source_url=SOURCE_URL,
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
                    source_url=SOURCE_URL,
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
