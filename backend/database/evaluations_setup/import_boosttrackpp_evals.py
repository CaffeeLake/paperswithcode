"""Import BoostTrack++ (2408.13003) evaluation rows on MOT17 and MOT20.

Scores from official GitHub README and paper Table 5 (MOT test sets, private detection).

Run:
    uv run --env-file backend/keys.env \\
        python backend/database/evaluations_setup/import_boosttrackpp_evals.py
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.models.database import Paper
from backend.services.arxiv_service import ArxivService
from backend.services.evaluation_service import EvaluationService
from backend.services.paper_service import PaperService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ARXIV_ID = "2408.13003"
TASK_SLUG = "object-tracking"
MODEL_NAME = "BoostTrack++"
GITHUB = "https://github.com/vukasin-stanojevic/BoostTrack"

EVALS = [
    {
        "dataset_slug": "mot17",
        "best_metric": "MOTA",
        "score": "80.7",
        "methodology": (
            "MOT17 test set, private detection protocol. Official GitHub README "
            "and paper Table 5 (HOTA 66.6, MOTA 80.7, IDF1 82.2)."
        ),
    },
    {
        "dataset_slug": "mot20",
        "best_metric": "MOTA",
        "score": "77.7",
        "methodology": (
            "MOT20 test set, private detection protocol. Official GitHub README "
            "and paper Table 5 (HOTA 66.4, MOTA 77.7, IDF1 82.0)."
        ),
    },
]


async def ensure_paper(session) -> Paper:
    existing = (
        session.query(Paper)
        .filter(Paper.arxiv_id == ARXIV_ID, Paper.is_latest_version.is_(True))
        .first()
    )
    if existing:
        return existing

    metadata = await ArxivService().get_paper_metadata(ARXIV_ID)
    if not metadata.success:
        raise RuntimeError(f"Failed to fetch arXiv metadata for {ARXIV_ID}")

    paper_id = PaperService(session).add_paper(
        {
            "arxiv_id": metadata.arxiv_id,
            "title": metadata.title,
            "abstract": metadata.abstract,
            "version": metadata.version,
            "date_published": metadata.published.date() if metadata.published else None,
            "primary_category": metadata.primary_category,
            "all_categories": metadata.categories,
            "is_latest_version": True,
        }
    )
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise RuntimeError(f"Failed to load newly created paper {paper_id}")
    logger.info("Indexed paper %s (id=%s)", ARXIV_ID, paper.id)
    return paper


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


async def main() -> None:
    created = skipped = 0
    with db_manager.session_local() as session:
        paper = await ensure_paper(session)
        task_id = session.execute(
            text("SELECT id FROM tasks WHERE slug = :s"), {"s": TASK_SLUG}
        ).scalar_one()
        link_paper_task(session, paper.id, task_id)
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
                paper_id=paper.id,
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
    asyncio.run(main())
