#!/usr/bin/env python3
"""Import paper-native FlowSeek optical-flow evaluations.

Run with:
    uv run --env-file backend/keys.env \
        python backend/database/evaluations_setup/import_flowseek_optical_flow_evals.py
"""

from sqlalchemy import text

from backend.database.connection import get_database_session
from backend.services.evaluation_service import EvaluationService


PAPER_ID = 87796
TASK_ID = 323
SOURCE_URL = "https://arxiv.org/abs/2509.05297"

ROWS = [
    {
        "dataset_id": 1375,
        "model_name": ("FlowSeek L (DAv2-B + motion bases, TartanAir, zero-shot)"),
        "metrics": {"EPE": 3.31},
        "best_metric": "EPE",
        "methodology": (
            "Paper Table 3, KITTI 2015 training-set zero-shot evaluation. "
            "This is the benchmark-metric-wise best introduced FlowSeek variant "
            "for EPE: the large configuration uses a ResNet-34 optical-flow "
            "backbone, Depth Anything v2 Base priors, the motion-basis BaseNet, "
            "and 12 recurrent iterations. Training is TartanAir pretraining "
            "followed by FlyingChairs and FlyingThings3D; no KITTI fine-tuning "
            "is used. The official evaluation code uses scale=0 (native KITTI "
            "resolution), and the source row is not marked as tiled. The paper's "
            "Fl-EPE column is the configured EPE quantity."
        ),
    },
    {
        "dataset_id": 1375,
        "model_name": ("FlowSeek S (DAv2-S + motion bases, TartanAir, zero-shot)"),
        "metrics": {"F1-all": 11.0},
        "best_metric": "F1-all",
        "methodology": (
            "Paper Table 3, KITTI 2015 training-set zero-shot evaluation. "
            "This is the benchmark-metric-wise best introduced FlowSeek variant "
            "for F1-all: the small configuration uses a ResNet-18 optical-flow "
            "backbone, Depth Anything v2 Small priors, the motion-basis BaseNet, "
            "and 12 recurrent iterations. Training is TartanAir pretraining "
            "followed by FlyingChairs and FlyingThings3D; no KITTI fine-tuning "
            "is used. The official evaluation code uses scale=0 (native KITTI "
            "resolution), and the source row is not marked as tiled. The paper's "
            "Fl-all percentage is stored under the leaderboard's configured "
            "F1-all label."
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
                SELECT arxiv_id, date_published
                FROM papers
                WHERE id = :id AND is_latest_version
                """
                ),
                {"id": PAPER_ID},
            )
            .mappings()
            .one()
        )
        if paper["arxiv_id"] != "2509.05297":
            raise RuntimeError(f"Unexpected source paper: {dict(paper)}")

        db.execute(
            text(
                """
                UPDATE papers
                SET date_published = COALESCE(date_published, DATE '2025-09-05'),
                    updated_at = NOW()
                WHERE id = :id
                """
            ),
            {"id": PAPER_ID},
        )
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
        results: list[tuple[str, int, int, str]] = []
        for row in ROWS:
            leaderboard = (
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
                    WHERE td.task_id = :task_id
                      AND td.dataset_id = :dataset_id
                    GROUP BY td.supports_harness
                    """
                    ),
                    {"task_id": TASK_ID, "dataset_id": row["dataset_id"]},
                )
                .mappings()
                .one()
            )
            if leaderboard["supports_harness"]:
                raise RuntimeError("FlowSeek target leaderboard must not use harnesses")
            allowed = set(leaderboard["metrics"])
            if not set(row["metrics"]).issubset(allowed):
                raise RuntimeError(
                    f"Metric mismatch for dataset {row['dataset_id']}: "
                    f"outgoing={set(row['metrics'])}, allowed={allowed}"
                )

            params = {
                "paper_id": PAPER_ID,
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
                      AND dataset_id = :dataset_id AND model_name = :model_name
                      AND harness IS NULL AND best_metric = :best_metric
                    ORDER BY id LIMIT 1
                    """
                ),
                params,
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
                    is_open=False,
                    num_parameters=None,
                    hf_model_url=None,
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
                    is_open=False,
                    harness=None,
                    harness_set=True,
                    source_url=SOURCE_URL,
                    source_url_set=True,
                    num_parameters=None,
                    num_parameters_set=True,
                    hf_model_url=None,
                    hf_model_url_set=True,
                )
                evaluation_id = int(existing_id)
                action = "updated"

            service.recalculate_ranks(
                TASK_ID, row["dataset_id"], metric_name=row["best_metric"]
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
