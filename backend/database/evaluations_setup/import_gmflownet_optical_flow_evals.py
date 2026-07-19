#!/usr/bin/env python3
"""Import paper-native GMFlowNet optical-flow evaluations.

Run with:
    uv run --env-file backend/keys.env \
        python backend/database/evaluations_setup/import_gmflownet_optical_flow_evals.py
"""

import asyncio

from sqlalchemy import text

from backend.database.connection import get_database_session
from backend.services.evaluation_service import EvaluationService
from backend.services.paper_service import PaperService


ARXIV_ID = "2203.11335"
TASK_ID = 323
SOURCE_URL = f"https://arxiv.org/abs/{ARXIV_ID}"
STANDARD_PARAMETERS = 9_343_696
MIXED_ATTENTION_PARAMETERS = 8_687_992

ROWS = [
    {
        "dataset_id": 1366,
        "model_name": "GMFlowNet (mixed POLA/axial attention, C+T+S+K+H)",
        "metrics": {"Average End-Point Error": 1.39},
        "best_metric": "Average End-Point Error",
        "num_parameters": MIXED_ATTENTION_PARAMETERS,
        "methodology": (
            "Paper Table 2, MPI Sintel Clean hidden test set. This is the "
            "benchmark-wise best introduced result, trained first on "
            "FlyingChairs and FlyingThings3D and then on the combined "
            "FlyingThings3D, Sintel Clean/Final, KITTI 2015, and HD1K mixture. "
            "For Sintel, four of the eight POLA heads in each block are "
            "replaced by two vertical and two horizontal axial-attention "
            "heads. The exact trainable parameter count was derived from the "
            "authors' released gmflownet_mix checkpoint."
        ),
    },
    {
        "dataset_id": 1367,
        "model_name": "GMFlowNet (mixed POLA/axial attention, C+T+S+K+H)",
        "metrics": {"Average End-Point Error": 2.65},
        "best_metric": "Average End-Point Error",
        "num_parameters": MIXED_ATTENTION_PARAMETERS,
        "methodology": (
            "Paper Table 2, MPI Sintel Final hidden test set. This is the "
            "benchmark-wise best introduced result, trained first on "
            "FlyingChairs and FlyingThings3D and then on the combined "
            "FlyingThings3D, Sintel Clean/Final, KITTI 2015, and HD1K mixture. "
            "For Sintel, four of the eight POLA heads in each block are "
            "replaced by two vertical and two horizontal axial-attention "
            "heads. The exact trainable parameter count was derived from the "
            "authors' released gmflownet_mix checkpoint."
        ),
    },
    {
        "dataset_id": 1370,
        "model_name": "GMFlowNet (C+T+S+K+H)",
        "metrics": {"Fl-all": 4.79},
        "best_metric": "Fl-all",
        "num_parameters": STANDARD_PARAMETERS,
        "methodology": (
            "Paper Table 2, KITTI 2015 hidden test set. This is the "
            "benchmark-wise best introduced result and uses the standard "
            "six-block POLA GMFlowNet. It is trained first on FlyingChairs "
            "and FlyingThings3D and then on the combined FlyingThings3D, "
            "Sintel Clean/Final, KITTI 2015, and HD1K mixture. Fl-all is a "
            "percentage. The exact trainable parameter count was derived from "
            "the authors' released standard GMFlowNet checkpoint."
        ),
    },
    {
        "dataset_id": 1375,
        "model_name": "GMFlowNet (C+T+K, KITTI fine-tuned)",
        "metrics": {"EPE": 0.63, "F1-all": 1.49},
        "best_metric": "EPE",
        "num_parameters": STANDARD_PARAMETERS,
        "methodology": (
            "Paper Table 2, KITTI 2015 public training-set evaluation. This "
            "is the benchmark-wise best introduced row: the standard "
            "six-block POLA GMFlowNet is pretrained on FlyingChairs and "
            "FlyingThings3D, then fine-tuned on KITTI 2015 itself. The paper "
            "prints these in-sample values in parentheses. Its F1-epe column "
            "is stored under the configured EPE label, and F1-all is a "
            "percentage. The exact trainable parameter count was derived from "
            "the authors' released standard GMFlowNet checkpoint."
        ),
    },
]


async def main() -> None:
    session_gen = get_database_session()
    db = next(session_gen)
    try:
        refresh = await PaperService(db).refresh_arxiv_paper(ARXIV_ID)
        paper_id = int(refresh.paper.id)
        print(
            "paper",
            paper_id,
            "created" if refresh.created else "existing",
            refresh.latest_version,
        )

        db.execute(
            text(
                """
                INSERT INTO paper_tasks (paper_id, task_id, source)
                VALUES (:paper_id, :task_id, 'manual')
                ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'
                """
            ),
            {"paper_id": paper_id, "task_id": TASK_ID},
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
                    "paper_id": paper_id,
                    "task_id": TASK_ID,
                    "dataset_id": row["dataset_id"],
                    "model_name": row["model_name"],
                    "best_metric": row["best_metric"],
                },
            ).scalar_one_or_none()

            if existing_id is None:
                evaluation = service.create_evaluation(
                    paper_id=paper_id,
                    task_id=TASK_ID,
                    dataset_id=row["dataset_id"],
                    model_name=row["model_name"],
                    methodology=row["methodology"],
                    metrics=row["metrics"],
                    best_metric=row["best_metric"],
                    source_url=SOURCE_URL,
                    uses_additional_data=True,
                    is_open=True,
                    num_parameters=row["num_parameters"],
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
                    num_parameters=row["num_parameters"],
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
    asyncio.run(main())
