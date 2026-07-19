#!/usr/bin/env python3
"""Import paper-native FlowNet optical-flow evaluations.

Run with:
    uv run --env-file backend/keys.env \
        python backend/database/evaluations_setup/import_flownet_optical_flow_evals.py
"""

import asyncio

from sqlalchemy import text

from backend.database.connection import get_database_session
from backend.services.evaluation_service import EvaluationService
from backend.services.paper_service import PaperService


ARXIV_ID = "1504.06852"
TASK_ID = 323
SOURCE_URL = f"https://arxiv.org/abs/{ARXIV_ID}"

ROWS = [
    {
        "dataset_id": 1366,
        "model_name": "FlowNetC+ft+v (Sintel fine-tuned, variational refinement)",
        "metrics": {"Average End-Point Error": 6.08},
        "best_metric": "Average End-Point Error",
        "num_parameters": 39_175_298,
        "methodology": (
            "Paper Table 2, MPI Sintel Clean hidden test set. This is the "
            "benchmark-wise best introduced FlowNetS/FlowNetC variant: "
            "FlowNetC is trained on Flying Chairs, fine-tuned on the combined "
            "Sintel Clean and Final training images, and followed by the "
            "paper's variational refinement (+v). At test time FlowNetC uses "
            "the paper's fixed 1.25 input upscaling. The exact trainable "
            "network count comes from the authors' released FlowNetC Caffe "
            "checkpoint; variational refinement adds no trainable parameters."
        ),
    },
    {
        "dataset_id": 1367,
        "model_name": "FlowNetS+ft+v (Sintel fine-tuned, variational refinement)",
        "metrics": {"Average End-Point Error": 7.22},
        "best_metric": "Average End-Point Error",
        "num_parameters": 38_676_514,
        "methodology": (
            "Paper Table 2, MPI Sintel Final hidden test set. This is the "
            "benchmark-wise best introduced FlowNetS/FlowNetC variant: "
            "FlowNetS is trained on Flying Chairs, fine-tuned on the combined "
            "Sintel Clean and Final training images, and followed by the "
            "paper's variational refinement (+v). FlowNetS uses native input "
            "scale at test time. The exact trainable network count comes from "
            "the authors' released FlowNetS Caffe checkpoint; variational "
            "refinement adds no trainable parameters."
        ),
    },
    {
        "dataset_id": 1373,
        "model_name": "FlowNetS+ft+v (Sintel fine-tuned, variational refinement)",
        "metrics": {"Average End-Point Error": 7.6},
        "best_metric": "Average End-Point Error",
        "num_parameters": 38_676_514,
        "methodology": (
            "Paper Table 2, KITTI 2012 hidden test set. This is the "
            "benchmark-wise best introduced FlowNetS/FlowNetC variant: "
            "FlowNetS is trained on Flying Chairs, fine-tuned on the combined "
            "Sintel Clean and Final training images (not KITTI), and followed "
            "by the paper's variational refinement (+v). The paper reports "
            "only test-set average endpoint error, so no Out-Noc value is "
            "stored. The exact trainable network count comes from the authors' "
            "released FlowNetS Caffe checkpoint; variational refinement adds "
            "no trainable parameters."
        ),
    },
]


async def main() -> None:
    session_gen = get_database_session()
    db = next(session_gen)
    try:
        # refresh_arxiv_paper obtains canonical metadata through ArxivService,
        # creates the missing paper/version, and replaces its author links.
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
