#!/usr/bin/env python3
"""Import paper-native LiteFlowNet optical-flow evaluations.

Run with:
    uv run --env-file backend/keys.env \
        python backend/database/evaluations_setup/import_liteflownet_optical_flow_evals.py
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from sqlalchemy import text

from backend.database.connection import get_database_session
from backend.models.database import Paper
from backend.services.arxiv_service import ArxivService
from backend.services.evaluation_service import EvaluationService
from backend.services.paper_service import PaperService


ARXIV_ID = "1805.07036"
TASK_ID = 323
PAPER_SOURCE_URL = "https://arxiv.org/abs/1805.07036"
REPOSITORY_SOURCE_URL = "https://github.com/twhui/LiteFlowNet"

# Exact count of learned blobs in the authors' released
# liteflownet-ft-sintel.caffemodel. This excludes lr_mult=0 augmentation and
# fixed bilinear-deconvolution blobs and agrees with Table 3's rounded 5.37M.
NUM_PARAMETERS = 5_377_701


@dataclass(frozen=True)
class EvaluationSpec:
    dataset_id: int
    model_name: str
    metrics: dict[str, float]
    best_metric: str
    methodology: str
    source_url: str = PAPER_SOURCE_URL


SPECS = (
    EvaluationSpec(
        dataset_id=1366,
        model_name="LiteFlowNet-ft (Sintel mixture fine-tune)",
        metrics={"Average End-Point Error": 4.54},
        best_metric="Average End-Point Error",
        methodology=(
            "Paper Table 2 hidden MPI-Sintel Clean test result for the introduced "
            "LiteFlowNet-ft checkpoint. LiteFlowNet is first trained with the "
            "FlyingChairs to FlyingThings3D schedule, then fine-tuned on a mixture "
            "of Sintel Clean and Final training data using generalized Charbonnier "
            "loss, image mirroring, and no noise augmentation."
        ),
    ),
    EvaluationSpec(
        dataset_id=1367,
        model_name="LiteFlowNet-ft (Sintel mixture fine-tune)",
        metrics={"Average End-Point Error": 5.38},
        best_metric="Average End-Point Error",
        methodology=(
            "Paper Table 2 hidden MPI-Sintel Final test result for the introduced "
            "LiteFlowNet-ft checkpoint. LiteFlowNet is first trained with the "
            "FlyingChairs to FlyingThings3D schedule, then fine-tuned on a mixture "
            "of Sintel Clean and Final training data using generalized Charbonnier "
            "loss, image mirroring, and no noise augmentation."
        ),
    ),
    EvaluationSpec(
        dataset_id=1373,
        model_name="LiteFlowNet-ft (KITTI12+15 mixture fine-tune)",
        metrics={"Average End-Point Error": 1.6, "Out-Noc": 3.27},
        best_metric="Average End-Point Error",
        methodology=(
            "Paper Table 2 hidden KITTI 2012 test AEE for LiteFlowNet-ft, paired "
            "with the same CVPR 2018 model's Out-Noc result from the authors' "
            "official release. The checkpoint starts from FlyingChairs to "
            "FlyingThings3D training and is fine-tuned on a mixture of KITTI 2012 "
            "and KITTI 2015 training data with reduced spatial augmentation."
        ),
        source_url=REPOSITORY_SOURCE_URL,
    ),
    EvaluationSpec(
        dataset_id=1370,
        model_name="LiteFlowNet-ft (KITTI12+15 mixture fine-tune)",
        metrics={"Fl-all": 9.38},
        best_metric="Fl-all",
        methodology=(
            "Paper Table 2 hidden KITTI 2015 test Fl-all for LiteFlowNet-ft. The "
            "checkpoint starts from FlyingChairs to FlyingThings3D training and is "
            "fine-tuned on a mixture of KITTI 2012 and KITTI 2015 training data "
            "with reduced spatial augmentation for driving scenes."
        ),
    ),
    EvaluationSpec(
        dataset_id=1375,
        model_name="LiteFlowNet-ft (KITTI12+15 mixture fine-tune)",
        metrics={"EPE": 1.62, "F1-all": 5.58},
        best_metric="EPE",
        methodology=(
            "Paper Table 2 KITTI 2015 training-set result for LiteFlowNet-ft. The "
            "parenthesized EPE and Fl-all values are measured on data included in "
            "the checkpoint's KITTI 2012 plus KITTI 2015 mixture fine-tune and are "
            "therefore kept on the explicitly configured training leaderboard, not "
            "the hidden-test leaderboard."
        ),
    ),
)


async def ensure_paper(db) -> Paper:
    paper = (
        db.query(Paper)
        .filter(Paper.arxiv_id == ARXIV_ID, Paper.is_latest_version)
        .first()
    )
    if paper is not None:
        return paper

    metadata = await ArxivService().get_paper_metadata(ARXIV_ID)
    if not metadata.success:
        raise RuntimeError(
            f"ArXiv metadata failure for {ARXIV_ID}: {metadata.error_message}"
        )

    result = await PaperService(db).refresh_arxiv_paper(ARXIV_ID)
    paper = db.get(Paper, result.paper.id)
    if paper is None:
        raise RuntimeError(f"Created paper {result.paper.id} but could not reload it")
    return paper


def validate_board(db, spec: EvaluationSpec) -> None:
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
            {"task_id": TASK_ID, "dataset_id": spec.dataset_id},
        )
        .mappings()
        .one()
    )
    if board["supports_harness"]:
        raise RuntimeError(f"Dataset {spec.dataset_id} unexpectedly supports harness")
    if not set(spec.metrics).issubset(set(board["metrics"])):
        raise RuntimeError(
            f"Leaderboard metric mismatch for dataset {spec.dataset_id}: {dict(board)}"
        )
    if spec.best_metric not in board["metrics"]:
        raise RuntimeError(
            f"Invalid best metric for dataset {spec.dataset_id}: {spec.best_metric}"
        )


async def main() -> None:
    session_gen = get_database_session()
    db = next(session_gen)
    try:
        paper = await ensure_paper(db)
        db.execute(
            text(
                """
                INSERT INTO paper_tasks (paper_id, task_id, source)
                VALUES (:paper_id, :task_id, 'manual')
                ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'
                """
            ),
            {"paper_id": paper.id, "task_id": TASK_ID},
        )
        db.commit()

        service = EvaluationService(db)
        for spec in SPECS:
            validate_board(db, spec)
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
                    "paper_id": paper.id,
                    "task_id": TASK_ID,
                    "dataset_id": spec.dataset_id,
                    "model_name": spec.model_name,
                    "best_metric": spec.best_metric,
                },
            ).scalar_one_or_none()

            if existing_id is None:
                evaluation = service.create_evaluation(
                    paper_id=paper.id,
                    task_id=TASK_ID,
                    dataset_id=spec.dataset_id,
                    model_name=spec.model_name,
                    methodology=spec.methodology,
                    metrics=spec.metrics,
                    best_metric=spec.best_metric,
                    harness=None,
                    uses_additional_data=True,
                    is_open=True,
                    source_url=spec.source_url,
                    num_parameters=NUM_PARAMETERS,
                    hf_model_url=None,
                )
                evaluation_id = evaluation.id
                action = "created"
            else:
                service.update_evaluation(
                    existing_id,
                    model_name=spec.model_name,
                    methodology=spec.methodology,
                    metrics=spec.metrics,
                    best_metric=spec.best_metric,
                    harness=None,
                    harness_set=True,
                    uses_additional_data=True,
                    is_open=True,
                    source_url=spec.source_url,
                    source_url_set=True,
                    num_parameters=NUM_PARAMETERS,
                    num_parameters_set=True,
                    hf_model_url=None,
                    hf_model_url_set=True,
                )
                evaluation_id = existing_id
                action = "updated"

            for metric in spec.metrics:
                service.recalculate_ranks(TASK_ID, spec.dataset_id, metric_name=metric)
            print(
                f"{action} evaluation_id={evaluation_id} "
                f"dataset_id={spec.dataset_id} metrics={spec.metrics}"
            )
        print(f"paper_id={paper.id}")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
