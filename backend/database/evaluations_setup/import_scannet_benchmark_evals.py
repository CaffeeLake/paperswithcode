#!/usr/bin/env python3
"""Import ScanNet benchmark eval rows from CSV into PostgreSQL.

Reads data/scannet_benchmark_evals_to_add.csv produced by
export_scannet_benchmark_evals.py. Scores sourced only from the official
kaldir benchmark are stored with external=true and external_source_url set
to the benchmark result_details page.

Run:

    uv run --env-file backend/keys.env \\
        python backend/database/evaluations_setup/import_scannet_benchmark_evals.py
"""

from __future__ import annotations

import asyncio
import csv
import logging
from pathlib import Path

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.database.evaluations_setup.evaluation_helpers import (
    get_or_create_evaluation,
)
from backend.models.database import (
    Author,
    Evaluation as DBEvaluation,
    Paper,
    PaperAuthor,
)
from backend.services.arxiv_service import ArxivService
from backend.services.evaluation_service import EvaluationService
from backend.services.paper_service import PaperService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
CSV_PATH = REPO_ROOT / "data" / "scannet_benchmark_evals_to_add.csv"


async def ensure_arxiv_paper(session, arxiv_id: str) -> Paper:
    existing = (
        session.query(Paper)
        .filter(Paper.arxiv_id == arxiv_id, Paper.is_latest_version.is_(True))
        .first()
    )
    if existing:
        return existing

    metadata = await ArxivService().get_paper_metadata(arxiv_id)
    if not metadata.success:
        raise RuntimeError(
            f"Failed to fetch arXiv metadata for {arxiv_id}: {metadata.error_message}"
        )

    paper_service = PaperService(session)
    paper_id = paper_service.add_paper(
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
    if not paper_id:
        existing = (
            session.query(Paper)
            .filter(Paper.arxiv_id == arxiv_id, Paper.is_latest_version.is_(True))
            .first()
        )
        if existing:
            return existing
        raise RuntimeError(f"Failed to create paper row for {arxiv_id}")

    paper = session.get(Paper, paper_id)
    if paper is None:
        raise RuntimeError(f"Created paper {paper_id} but could not reload it")

    if metadata.authors:
        for order, author_name in enumerate(metadata.authors, start=1):
            author = session.query(Author).filter(Author.name == author_name).first()
            if not author:
                author = Author(name=author_name)
                session.add(author)
                session.flush()
            session.add(
                PaperAuthor(paper_id=paper.id, author_id=author.id, author_order=order)
            )
        session.flush()

    logger.info("Imported paper %s (id=%s)", arxiv_id, paper.id)
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


def load_csv_rows() -> list[dict[str, str]]:
    with CSV_PATH.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def find_existing_for_update(
    session,
    paper_id: int,
    task_id: int,
    dataset_id: int,
    existing_model_name: str,
    best_metric: str,
) -> DBEvaluation | None:
    return (
        session.query(DBEvaluation)
        .filter(
            DBEvaluation.paper_id == paper_id,
            DBEvaluation.task_id == task_id,
            DBEvaluation.dataset_id == dataset_id,
            DBEvaluation.model_name == existing_model_name,
            DBEvaluation.best_metric == best_metric,
        )
        .first()
    )


def score_str(value: str | float) -> str:
    numeric = float(value)
    if numeric.is_integer():
        return str(int(numeric))
    return f"{numeric:g}"


async def main() -> None:
    rows = load_csv_rows()
    session = db_manager.session_local()
    created = 0
    updated = 0
    skipped = 0
    papers_imported = 0

    try:
        for row in rows:
            action = row["action"].strip()
            if action not in {"add", "update"}:
                logger.info(
                    "Skipping unsupported action %r for %s", action, row["method_name"]
                )
                skipped += 1
                continue

            arxiv_id = row["arxiv_id"].strip()
            task_id = int(row["task_id"])
            dataset_id = int(row["dataset_id"])
            best_metric = row["best_metric"].strip()
            model_name = row["model_name"].strip()
            score = score_str(row["score"])
            source_url = row["external_source_url"].strip()
            is_open = row.get("is_open", "true").strip().lower() == "true"
            methodology = row.get("methodology", "").strip()

            paper_id = row.get("paper_id", "").strip()
            if paper_id:
                paper = session.get(Paper, int(paper_id))
                if paper is None:
                    paper = await ensure_arxiv_paper(session, arxiv_id)
                    papers_imported += 1
            else:
                paper = await ensure_arxiv_paper(session, arxiv_id)
                papers_imported += 1

            link_paper_task(session, paper.id, task_id)

            if action == "update":
                existing_model_name = (
                    row.get("existing_model_name", "").strip() or model_name
                )
                existing = find_existing_for_update(
                    session,
                    paper.id,
                    task_id,
                    dataset_id,
                    existing_model_name,
                    best_metric,
                )
                if existing is None:
                    logger.warning(
                        "No existing eval for update: %s / %s / %s — creating instead",
                        arxiv_id,
                        row["board"],
                        existing_model_name,
                    )
                    action = "add"
                else:
                    service = EvaluationService(session)
                    service.update_evaluation(
                        existing.id,
                        model_name=model_name,
                        methodology=methodology,
                        metrics={best_metric: score},
                        best_metric=best_metric,
                        is_open=is_open,
                        external_source_url=source_url,
                        source_url=source_url,
                        source_url_set=True,
                    )
                    updated += 1
                    logger.info(
                        "Updated %s / %s / %s -> %s %s",
                        arxiv_id,
                        row["board"],
                        existing_model_name,
                        score,
                        best_metric,
                    )
                    continue

            existed = (
                session.query(DBEvaluation)
                .filter(
                    DBEvaluation.paper_id == paper.id,
                    DBEvaluation.task_id == task_id,
                    DBEvaluation.dataset_id == dataset_id,
                    DBEvaluation.model_name == model_name,
                    DBEvaluation.best_metric == best_metric,
                )
                .first()
            )
            get_or_create_evaluation(
                session,
                paper_id=paper.id,
                task_id=task_id,
                dataset_id=dataset_id,
                model_name=model_name,
                methodology=methodology,
                metrics={best_metric: score},
                best_metric=best_metric,
                external_source_url=source_url,
                source_url=source_url,
                is_open=is_open,
            )
            if existed:
                skipped += 1
                logger.info(
                    "Skipped existing %s / %s / %s",
                    arxiv_id,
                    row["board"],
                    model_name,
                )
            else:
                created += 1
                logger.info(
                    "Created %s / %s / %s = %s %s (external source)",
                    arxiv_id,
                    row["board"],
                    model_name,
                    score,
                    best_metric,
                )

        session.commit()
        logger.info(
            "Done: %s created, %s updated, %s skipped, %s papers imported",
            created,
            updated,
            skipped,
            papers_imported,
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    asyncio.run(main())
