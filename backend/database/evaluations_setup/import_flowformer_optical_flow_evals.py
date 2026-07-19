#!/usr/bin/env python3
"""Import paper-native FlowFormer optical-flow evaluations.

Run with:
    uv run --env-file backend/keys.env \
        python backend/database/evaluations_setup/import_flowformer_optical_flow_evals.py
"""

import asyncio

from sqlalchemy import text

from backend.database.connection import get_database_session
from backend.services.evaluation_service import EvaluationService
from backend.services.paper_service import PaperService


ARXIV_ID = "2203.16194"
TASK_ID = 323
PARAMETERS = 18_200_000

ROWS = [
    {
        "dataset_id": 1366,
        "model_name": "FlowFormer (Sintel fine-tuned, no warm-start)",
        "metrics": {"Average End-Point Error": 1.159},
        "best_metric": "Average End-Point Error",
        "source_url": (
            "https://sintel.is.tue.mpg.de/quant?metric_id=1&selected_pass=1"
        ),
        "methodology": (
            "Exact official MPI Sintel Clean hidden-test submission. FlowFormer "
            "takes one image pair and does not use warm-start or flow from "
            "previous frames. After 120K iterations each on FlyingChairs and "
            "FlyingThings3D, it is fine-tuned for 120K iterations on the "
            "combined FlyingThings3D, Sintel, KITTI 2015, and HD1K data using "
            "432x960 crops."
        ),
    },
    {
        "dataset_id": 1367,
        "model_name": "FlowFormer (Sintel fine-tuned, no warm-start)",
        "metrics": {"Average End-Point Error": 2.088},
        "best_metric": "Average End-Point Error",
        "source_url": (
            "https://sintel.is.tue.mpg.de/quant?metric_id=1&selected_pass=0"
        ),
        "methodology": (
            "Exact official MPI Sintel Final hidden-test submission. FlowFormer "
            "takes one image pair and does not use warm-start or flow from "
            "previous frames. After 120K iterations each on FlyingChairs and "
            "FlyingThings3D, it is fine-tuned for 120K iterations on the "
            "combined FlyingThings3D, Sintel, KITTI 2015, and HD1K data using "
            "432x960 crops."
        ),
    },
    {
        "dataset_id": 1370,
        "model_name": "FlowFormer (KITTI fine-tuned, tiled)",
        "metrics": {"Fl-all": 4.68},
        "best_metric": "Fl-all",
        "source_url": (
            "https://www.cvlibs.net/datasets/kitti/"
            "eval_scene_flow_detail.php?benchmark=flow&"
            "result=6cfc440d081a2b5255cab6b198fb8c60d2419fc4"
        ),
        "methodology": (
            "Paper Table 1 and the exact official KITTI 2015 hidden-test "
            "submission. The two-frame FlowFormer checkpoint is further "
            "fine-tuned for 50K iterations on KITTI 2015 after the combined "
            "C+T+S+K+H fine-tuning stage. Test images are cropped to the "
            "432x960 training size, and four Gaussian-weighted tile predictions "
            "are blended. Fl-all is a percentage."
        ),
    },
    {
        "dataset_id": 1375,
        "model_name": "FlowFormer# (C+T, tiled, zero-shot)",
        "metrics": {"EPE": 4.09, "F1-all": 14.72},
        "best_metric": "EPE",
        "source_url": "https://arxiv.org/abs/2203.16194",
        "methodology": (
            "Paper Table 1 and supplementary Section 3, KITTI 2015 public "
            "training-set evaluation. FlowFormer# uses the full 18.2M-parameter "
            "architecture, is trained only on FlyingChairs (368x498 crops) and "
            "FlyingThings3D (400x720 crops), and receives no KITTI fine-tuning. "
            "Evaluation uses the paper's Gaussian-weighted tiling technique. "
            "The paper's F1-epe is stored under the configured EPE label, and "
            "F1-all is a percentage."
        ),
    },
]


async def main() -> None:
    session_gen = get_database_session()
    db = next(session_gen)
    try:
        paper_service = PaperService(db)
        refresh = await paper_service.refresh_arxiv_paper(ARXIV_ID)
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
                      AND dataset_id = :dataset_id AND model_name = :model_name
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
    asyncio.run(main())
