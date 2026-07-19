#!/usr/bin/env python3
"""Import paper-native CroCo v2 optical-flow evaluations.

Run with:
    uv run --env-file backend/keys.env \
        python backend/database/evaluations_setup/import_croco_v2_optical_flow_evals.py
"""

from sqlalchemy import text

from backend.database.connection import get_database_session
from backend.services.evaluation_service import EvaluationService


PAPER_ID = 11434
TASK_ID = 323
PARAMETERS = 437_400_000

ROWS = [
    {
        "dataset_id": 1366,
        "model_name": "CroCo-Flow (ViT-L, Sintel submission, 2-frame)",
        "metrics": {"Average End-Point Error": 1.092},
        "best_metric": "Average End-Point Error",
        "source_url": (
            "https://sintel.is.tue.mpg.de/quant?metric_id=5&selected_pass=1"
        ),
        "methodology": (
            "Official MPI Sintel Clean hidden-test submission. The CroCo-Flow "
            "ViT-L/Base-decoder model consumes two RGB frames and does not use "
            "a previous-frame flow initialization. It was trained for 240 "
            "epochs on MPI-Sintel, FlyingThings3D, FlyingChairs, and TartanAir "
            "using 384x320 crops; test frames are evaluated with 0.9-overlap "
            "tiling. The exact EPE is from the official Sintel leaderboard."
        ),
    },
    {
        "dataset_id": 1367,
        "model_name": "CroCo-Flow (ViT-L, Sintel submission, 2-frame)",
        "metrics": {"Average End-Point Error": 2.436},
        "best_metric": "Average End-Point Error",
        "source_url": (
            "https://sintel.is.tue.mpg.de/results?metric_id=7&selected_pass=0"
        ),
        "methodology": (
            "Official MPI Sintel Final hidden-test submission. The CroCo-Flow "
            "ViT-L/Base-decoder model consumes two RGB frames and does not use "
            "a previous-frame flow initialization. It was trained for 240 "
            "epochs on MPI-Sintel, FlyingThings3D, FlyingChairs, and TartanAir "
            "using 384x320 crops; test frames are evaluated with 0.9-overlap "
            "tiling. The exact EPE is from the official Sintel leaderboard."
        ),
    },
    {
        "dataset_id": 1370,
        "model_name": "CroCo-Flow (KITTI fine-tuned, 2-frame)",
        "metrics": {"Fl-all": 3.64},
        "best_metric": "Fl-all",
        "source_url": (
            "https://www.cvlibs.net/datasets/kitti/"
            "eval_scene_flow_detail.php?benchmark=flow&"
            "result=f8b82c2d6e0d80ce2bcbcb31d7e4b260193271ff"
        ),
        "methodology": (
            "Paper Table 7 and the official KITTI 2015 hidden-test submission. "
            "This two-frame CroCo-Flow ViT-L/Base-decoder checkpoint starts "
            "from the main flow model and is fine-tuned jointly on KITTI 2012 "
            "and KITTI 2015 for 150 epochs using 1216x352 crops. Submission "
            "inference uses 0.99-overlap tiling; Fl-all is a percentage."
        ),
    },
    {
        "dataset_id": 1371,
        "model_name": "CroCo-Flow (Spring fine-tuned, 2-frame)",
        "metrics": {"1px total": 4.565, "EPE": 0.498, "Fl": 1.508},
        "best_metric": "1px total",
        "source_url": ("https://spring-benchmark.org/opticalflow?s=err_WAUC_Fl_total"),
        "methodology": (
            "Paper Table 8 and the exact official Spring hidden-test "
            "submission. This two-frame CroCo-Flow ViT-L/Base-decoder "
            "checkpoint starts from the main flow model and is fine-tuned for "
            "12 epochs on Spring train using the model's 384x320 crop size. "
            "Native-resolution test frames are processed with 0.9-overlap "
            "tiling. The 1px and Fl error rates are percentages."
        ),
    },
    {
        "dataset_id": 1373,
        "model_name": "CroCo-Flow (KITTI fine-tuned, 2-frame)",
        "metrics": {"Average End-Point Error": 0.8, "Out-Noc": 1.57},
        "best_metric": "Out-Noc",
        "source_url": (
            "https://www.cvlibs.net/datasets/kitti/eval_stereo_flow.php?benchmark=flow"
        ),
        "methodology": (
            "Exact official KITTI 2012 hidden-test submission. This two-frame "
            "CroCo-Flow ViT-L/Base-decoder checkpoint starts from the main "
            "flow model and is fine-tuned jointly on KITTI 2012 and KITTI "
            "2015 for 150 epochs using 1216x352 crops. Submission inference "
            "uses 0.99-overlap tiling. Average EPE is Avg-All on the official "
            "board; Out-Noc is a percentage."
        ),
    },
]


def main() -> None:
    session_gen = get_database_session()
    db = next(session_gen)
    try:
        paper = (
            db.execute(
                text("SELECT arxiv_id FROM papers WHERE id = :id"),
                {"id": PAPER_ID},
            )
            .mappings()
            .one()
        )
        if paper["arxiv_id"] != "2211.10408":
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
                    source_url=row["source_url"],
                    uses_additional_data=True,
                    is_open=True,
                    num_parameters=PARAMETERS,
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
                    hf_model_url=None,
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
