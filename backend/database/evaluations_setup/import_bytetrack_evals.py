"""Import ByteTrack evaluation rows for object-tracking MOT benchmarks.

Scores from arXiv 2110.06864 (ByteTrack paper) for MOT17, MOT20, and BDD100K.
DanceTrack and SportsMOT scores come from legacy PwC evaluation-tables.json because
they are not reported in the ByteTrack paper or official README.

Run:
    uv run --env-file backend/keys.env \\
        python backend/database/evaluations_setup/import_bytetrack_evals.py
"""

from __future__ import annotations

import logging

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.services.evaluation_service import EvaluationService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BYTETrack_ARXIV = "2110.06864"
TASK_SLUG = "object-tracking"
MODEL_NAME = "ByteTrack"

# Paper-backed rows (MOT17/MOT20 Table 4-5; BDD100K Table 7).
PAPER_EVALS = [
    {
        "dataset_slug": "mot17",
        "best_metric": "MOTA",
        "score": "80.3",
        "methodology": (
            "MOT17 test set, private detection protocol. YOLOX-X detector; "
            "Table 4 / README main results (MOTA 80.3, IDF1 77.3, HOTA 63.1)."
        ),
    },
    {
        "dataset_slug": "mot20",
        "best_metric": "MOTA",
        "score": "77.8",
        "methodology": (
            "MOT20 test set, private detection protocol. YOLOX-X detector; "
            "Table 5 / README main results (MOTA 77.8, IDF1 75.2, HOTA 61.3)."
        ),
    },
    {
        "dataset_slug": "bdd100k-val",
        "best_metric": "mMOTA",
        "score": "45.5",
        "methodology": (
            "BDD100K tracking validation split with UniTrack Re-ID features; "
            "Table 7 (mMOTA 45.5, mIDF1 54.8)."
        ),
    },
    {
        "dataset_slug": "bdd100k-test",
        "best_metric": "mMOTA",
        "score": "40.1",
        "methodology": (
            "BDD100K tracking test split with UniTrack Re-ID features; "
            "Table 7 (mMOTA 40.1, mIDF1 55.8)."
        ),
    },
]

# Legacy PwC rows only (not in ByteTrack paper).
LEGACY_EVALS = [
    {
        "dataset_slug": "dancetrack",
        "best_metric": "HOTA",
        "score": "47.1",
        "methodology": (
            "Legacy PapersWithCode leaderboard row (multi-object-tracking-on-dancetrack). "
            "Score not reported in ByteTrack arXiv paper or GitHub README."
        ),
    },
    {
        "dataset_slug": "sportsmot",
        "best_metric": "HOTA",
        "score": "64.1",
        "methodology": (
            "Legacy PapersWithCode leaderboard row (multi-object-tracking-on-sportsmot). "
            "Score not reported in ByteTrack arXiv paper or GitHub README."
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


def upsert_eval(
    session,
    service: EvaluationService,
    *,
    paper_id: int,
    task_id: int,
    dataset_id: int,
    best_metric: str,
    score: str,
    methodology: str,
) -> str:
    params = {
        "paper_id": paper_id,
        "task_id": task_id,
        "dataset_id": dataset_id,
        "model_name": MODEL_NAME,
        "harness": None,
        "best_metric": best_metric,
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
        paper_id=paper_id,
        task_id=task_id,
        dataset_id=dataset_id,
        model_name=MODEL_NAME,
        methodology=methodology,
        metrics={best_metric: score},
        best_metric=best_metric,
        is_open=True,
    )
    return "created"


def main() -> None:
    created = 0
    skipped = 0

    with db_manager.session_local() as session:
        paper_id = session.execute(
            text(
                "SELECT id FROM papers WHERE arxiv_id = :a AND is_latest_version LIMIT 1"
            ),
            {"a": BYTETrack_ARXIV},
        ).scalar_one()
        task_id = session.execute(
            text("SELECT id FROM tasks WHERE slug = :s"), {"s": TASK_SLUG}
        ).scalar_one()
        link_paper_task(session, paper_id, task_id)
        session.commit()

        service = EvaluationService(session)
        for spec in PAPER_EVALS + LEGACY_EVALS:
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
