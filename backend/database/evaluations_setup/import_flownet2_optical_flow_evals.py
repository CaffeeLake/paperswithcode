#!/usr/bin/env python3
"""Import paper-native FlowNet 2.0 optical-flow evaluations.

Run with:
    uv run --env-file backend/keys.env \
        python backend/database/evaluations_setup/import_flownet2_optical_flow_evals.py
"""

from sqlalchemy import text

from backend.database.connection import get_database_session
from backend.services.evaluation_service import EvaluationService


ARXIV_ID = "1612.01925"
EXPECTED_PAPER_ID = 82303
TASK_ID = 323
SOURCE_URL = f"https://arxiv.org/abs/{ARXIV_ID}"
FLOWNET2_PARAMETERS = 162_518_834

ROWS = [
    {
        "dataset_id": 1366,
        "model_name": "FlowNet2",
        "metrics": {"Average End-Point Error": 3.96},
        "best_metric": "Average End-Point Error",
        "methodology": (
            "Paper Table 4, MPI Sintel Clean official hidden test, AEE=3.96. "
            "This is the benchmark-wise best result introduced by the paper: "
            "the full FlowNet2 model fuses FlowNet2-CSS-ft-sd with FlowNet2-SD "
            "and is trained with the paper's staged FlyingChairs, FlyingThings3D, "
            "and ChairsSDHom schedules. It is not fine-tuned on Sintel; the "
            "Sintel-fine-tuned variant scores 4.16 on the Clean hidden test."
        ),
    },
    {
        "dataset_id": 1367,
        "model_name": "FlowNet2-ft-sintel",
        "metrics": {"Average End-Point Error": 5.74},
        "best_metric": "Average End-Point Error",
        "methodology": (
            "Paper Table 4, MPI Sintel Final official hidden test, AEE=5.74. "
            "This is the full fused FlowNet2 architecture fine-tuned on a "
            "mixture of the Sintel Clean and Final training passes, and is the "
            "paper's best introduced variant on the Final hidden test."
        ),
    },
    {
        "dataset_id": 1370,
        "model_name": "FlowNet2-ft-kitti",
        "metrics": {"Fl-all": 11.48},
        "best_metric": "Fl-all",
        "methodology": (
            "Paper Table 4, KITTI 2015 official hidden test, Fl-all=11.48%. "
            "The full fused FlowNet2 model is fine-tuned jointly on the KITTI "
            "2012 and KITTI 2015 training sets. This is the paper-native "
            "FlowNet2-ft-kitti submission, not a later external result."
        ),
    },
    {
        "dataset_id": 1373,
        "model_name": "FlowNet2-ft-kitti",
        "metrics": {"Average End-Point Error": 1.8},
        "best_metric": "Average End-Point Error",
        "methodology": (
            "Paper Table 4, KITTI 2012 official hidden test, AEE=1.8. The full "
            "fused FlowNet2 model is fine-tuned jointly on the KITTI 2012 and "
            "KITTI 2015 training sets. The paper does not print Out-Noc for "
            "this introduced submission, so only AEE is stored."
        ),
    },
    {
        "dataset_id": 1375,
        "model_name": "FlowNet2-ft-kitti",
        "metrics": {"EPE": 2.30},
        "best_metric": "EPE",
        "methodology": (
            "Paper Table 4, KITTI 2015 training split, AEE/EPE=2.30. The value "
            "is parenthesized in the source because FlowNet2-ft-kitti is "
            "fine-tuned jointly on the KITTI 2012 and KITTI 2015 training "
            "sets. The paper's AEE label is the configured EPE quantity."
        ),
    },
    {
        "dataset_id": 1375,
        "model_name": "FlowNet2-ft-kitti",
        "metrics": {"F1-all": 8.61},
        "best_metric": "F1-all",
        "methodology": (
            "Paper Table 4, KITTI 2015 training split, Fl-all=8.61%. The value "
            "is parenthesized in the source because FlowNet2-ft-kitti is "
            "fine-tuned jointly on the KITTI 2012 and KITTI 2015 training "
            "sets. The paper's Fl-all label maps to this board's configured "
            "F1-all metric."
        ),
    },
]


def main() -> None:
    session_gen = get_database_session()
    db = next(session_gen)
    try:
        paper = (
            db.execute(
                text(
                    """
                SELECT id, arxiv_id
                FROM papers
                WHERE arxiv_id = :arxiv_id
                """
                ),
                {"arxiv_id": ARXIV_ID},
            )
            .mappings()
            .one()
        )
        paper_id = int(paper["id"])
        if paper_id != EXPECTED_PAPER_ID:
            raise RuntimeError(
                f"Expected paper {EXPECTED_PAPER_ID}, resolved {paper_id}"
            )

        service = EvaluationService(db)
        results: list[tuple[str, int, int, str]] = []
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

            identity = {
                "paper_id": paper_id,
                "task_id": TASK_ID,
                "dataset_id": row["dataset_id"],
                "model_name": row["model_name"],
                "best_metric": row["best_metric"],
            }
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
                identity,
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
                    num_parameters=FLOWNET2_PARAMETERS,
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
                    num_parameters=FLOWNET2_PARAMETERS,
                    num_parameters_set=True,
                    hf_model_url=None,
                    hf_model_url_set=True,
                )
                evaluation_id = int(existing_id)
                action = "updated"

            service.recalculate_ranks(
                TASK_ID,
                row["dataset_id"],
                metric_name=row["best_metric"],
            )
            results.append(
                (action, evaluation_id, row["dataset_id"], row["best_metric"])
            )

        for result in results:
            print(result)
    finally:
        db.close()


if __name__ == "__main__":
    main()
