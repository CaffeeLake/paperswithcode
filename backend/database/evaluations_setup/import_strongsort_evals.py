"""Import StrongSORT / StrongSORT++ (2202.13514) evaluation rows.

Scores from paper Tables IV–VI (test sets, private detection) and GitHub README.
Uses StrongSORT++ as the best introduced variant per benchmark.

Run:
    uv run --env-file backend/keys.env \\
        python backend/database/evaluations_setup/import_strongsort_evals.py
"""

from __future__ import annotations

import logging

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.services.evaluation_service import EvaluationService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ARXIV_ID = "2202.13514"
TASK_SLUG = "object-tracking"
MODEL_NAME = "StrongSORT++"
GITHUB = "https://github.com/dyhBUPT/StrongSORT"

EVALS = [
    {
        "dataset_slug": "mot17",
        "best_metric": "MOTA",
        "score": "79.6",
        "methodology": (
            "MOT17 test set, private detection protocol. Paper Table IV "
            "(StrongSORT++: HOTA 64.4, MOTA 79.6, IDF1 79.5)."
        ),
    },
    {
        "dataset_slug": "mot20",
        "best_metric": "MOTA",
        "score": "73.8",
        "methodology": (
            "MOT20 test set, private detection protocol. Paper Table V "
            "(StrongSORT++: HOTA 62.6, MOTA 73.8, IDF1 77.0)."
        ),
    },
    {
        "dataset_slug": "dancetrack",
        "best_metric": "HOTA",
        "score": "55.6",
        "methodology": (
            "DanceTrack test set. Paper Table VI "
            "(StrongSORT++: HOTA 55.6, MOTA 91.1, IDF1 55.2)."
        ),
    },
]


def link_paper_task(session, paper_id: int, task_id: int) -> None:
    session.execute(
        text(
            """
            INSERT INTO paper_tasks (paper_id, task_id, source)
            VALUES (:paper_id, :task_id, 'manual')
            ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'
            """
        ),
        {"paper_id": paper_id, "task_id": task_id},
    )


def upsert_eval(session, service: EvaluationService, **kwargs) -> str:
    params = {
        "paper_id": kwargs["paper_id"],
        "task_id": kwargs["task_id"],
        "dataset_id": kwargs["dataset_id"],
        "model_name": MODEL_NAME,
        "harness": None,
        "best_metric": kwargs["best_metric"],
    }
    existing = session.execute(
        text(
            """
            SELECT id FROM evaluations
            WHERE paper_id = :paper_id AND task_id = :task_id AND dataset_id = :dataset_id
              AND model_name = :model_name
              AND COALESCE(harness, '') = COALESCE(:harness, '')
              AND best_metric = :best_metric
            """
        ),
        params,
    ).first()
    if existing:
        return "skipped"

    service.create_evaluation(
        paper_id=kwargs["paper_id"],
        task_id=kwargs["task_id"],
        dataset_id=kwargs["dataset_id"],
        model_name=MODEL_NAME,
        methodology=kwargs["methodology"],
        metrics={kwargs["best_metric"]: kwargs["score"]},
        best_metric=kwargs["best_metric"],
        source_url=GITHUB,
        is_open=True,
    )
    return "created"


def main() -> None:
    created = skipped = 0
    with db_manager.session_local() as session:
        paper_id = session.execute(
            text(
                "SELECT id FROM papers WHERE arxiv_id = :a AND is_latest_version LIMIT 1"
            ),
            {"a": ARXIV_ID},
        ).scalar_one()
        task_id = session.execute(
            text("SELECT id FROM tasks WHERE slug = :s"), {"s": TASK_SLUG}
        ).scalar_one()
        link_paper_task(session, paper_id, task_id)
        session.commit()

        service = EvaluationService(session)
        for spec in EVALS:
            dataset_id = session.execute(
                text("SELECT id FROM datasets WHERE slug = :s"),
                {"s": spec["dataset_slug"]},
            ).scalar_one()
            status = upsert_eval(
                session,
                service,
                paper_id=paper_id,
                task_id=task_id,
                dataset_id=dataset_id,
                best_metric=spec["best_metric"],
                score=spec["score"],
                methodology=spec["methodology"],
            )
            if status == "created":
                created += 1
                logger.info(
                    "Added %s on %s: %s=%s",
                    MODEL_NAME,
                    spec["dataset_slug"],
                    spec["best_metric"],
                    spec["score"],
                )
            else:
                skipped += 1
                logger.info("Already exists: %s / %s", MODEL_NAME, spec["dataset_slug"])

        session.commit()

    logger.info("Done: created=%s skipped=%s", created, skipped)


if __name__ == "__main__":
    main()
