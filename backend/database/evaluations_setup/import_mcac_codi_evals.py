#!/usr/bin/env python3
"""Import MCAC few-shot evals from CoDi Table III (arXiv:2512.20153)."""

from __future__ import annotations

import asyncio
import json
import logging

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.models.database import Author, Paper, PaperAuthor
from backend.services.arxiv_service import ArxivService
from backend.services.evaluation_service import EvaluationService
from backend.services.paper_service import PaperService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TASK_ID = 340
MCAC_SLUG = "mcac"
CODI_ARXIV = "2512.20153"
SOURCE = "CoDi Table III few-shot MCAC (test split); arXiv:2512.20153"
EXTERNAL_SOURCE = f"https://arxiv.org/abs/{CODI_ARXIV}"

# (paper_arxiv, model_name, metric, score, note)
ROWS = [
    ("2309.04820", "ABC123", "MAE", 9.52, "MCAC test split"),
    ("2309.04820", "ABC123", "RMSE", 17.64, "MCAC test split"),
    ("2104.08391", "FamNet", "MAE", 26.40, "MCAC test split"),
    ("2104.08391", "FamNet", "RMSE", 45.52, "MCAC test split"),
    ("2203.08354", "BMNet+", "MAE", 17.29, "MCAC test split"),
    ("2203.08354", "BMNet+", "RMSE", 29.83, "MCAC test split"),
    ("2409.18686", "GeCo", "MAE", 19.91, "MCAC test split"),
    ("2409.18686", "GeCo", "RMSE", 33.25, "MCAC test split"),
    ("2208.13721", "CounTR", "MAE", 16.12, "MCAC test split"),
    ("2208.13721", "CounTR", "RMSE", 29.28, "MCAC test split"),
    ("2211.08217", "LOCA", "MAE", 10.91, "MCAC test split"),
    ("2211.08217", "LOCA", "RMSE", 22.04, "MCAC test split"),
    ("2511.08048", "GeCo2", "MAE", 7.93, "MCAC test split"),
    ("2511.08048", "GeCo2", "RMSE", 17.05, "MCAC test split"),
    (CODI_ARXIV, "CoDi", "MAE", 5.26, "MCAC test split"),
    (CODI_ARXIV, "CoDi", "RMSE", 16.31, "MCAC test split"),
]


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

    logger.info("Imported arXiv paper %s (id=%s)", arxiv_id, paper.id)
    return paper


def link_paper_task(session, paper_id: int) -> None:
    session.execute(
        text(
            """
            INSERT INTO paper_tasks (paper_id, task_id, source)
            VALUES (:p, :t, 'manual')
            ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'
            """
        ),
        {"p": paper_id, "t": TASK_ID},
    )


def resolve_dataset_id(session) -> int:
    row = session.execute(
        text("SELECT id FROM datasets WHERE slug = :s"), {"s": MCAC_SLUG}
    ).first()
    if not row:
        raise RuntimeError(f"Missing dataset slug={MCAC_SLUG!r}")
    return int(row[0])


def normalize_legacy_rows(session, dataset_id: int) -> None:
    """Align older MCAC rows with single-metric leaderboard shape."""
    legacy = (
        session.execute(
            text(
                """
            SELECT id, model_name, best_metric, metrics
            FROM evaluations
            WHERE task_id = :t AND dataset_id = :d
              AND model_name IN ('ABC123', 'GeCo2 (3-shot)')
            """
            ),
            {"t": TASK_ID, "d": dataset_id},
        )
        .mappings()
        .all()
    )
    for row in legacy:
        metric = row["best_metric"]
        metrics = row["metrics"] or {}
        if len(metrics) <= 1:
            continue
        session.execute(
            text(
                """
                UPDATE evaluations
                SET metrics = CAST(:metrics AS jsonb)
                WHERE id = :id
                """
            ),
            {"id": row["id"], "metrics": json.dumps({metric: metrics[metric]})},
        )
        if row["model_name"] == "GeCo2 (3-shot)":
            session.execute(
                text("UPDATE evaluations SET model_name = 'GeCo2' WHERE id = :id"),
                {"id": row["id"]},
            )


async def main() -> None:
    session = db_manager.session_local()
    created = skipped = 0
    paper_cache: dict[str, Paper] = {}
    try:
        dataset_id = resolve_dataset_id(session)
        normalize_legacy_rows(session, dataset_id)
        svc = EvaluationService(session)

        for paper_arxiv, model_name, metric, score, note in ROWS:
            if paper_arxiv not in paper_cache:
                paper = await ensure_arxiv_paper(session, paper_arxiv)
                paper_cache[paper_arxiv] = paper
                link_paper_task(session, paper.id)
            else:
                paper = paper_cache[paper_arxiv]

            params = {
                "paper_id": paper.id,
                "task_id": TASK_ID,
                "dataset_id": dataset_id,
                "model_name": model_name,
                "best_metric": metric,
            }
            existing = session.execute(
                text(
                    """
                    SELECT id FROM evaluations
                    WHERE paper_id=:paper_id AND task_id=:task_id AND dataset_id=:dataset_id
                      AND model_name=:model_name
                      AND COALESCE(harness, '') = ''
                      AND best_metric=:best_metric
                    """
                ),
                params,
            ).first()
            if existing:
                skipped += 1
                continue

            external_source = None if paper_arxiv == CODI_ARXIV else EXTERNAL_SOURCE
            svc.create_evaluation(
                paper_id=paper.id,
                task_id=TASK_ID,
                dataset_id=dataset_id,
                model_name=model_name,
                methodology=f"{note}. {SOURCE}.",
                metrics={metric: score},
                best_metric=metric,
                external_source_url=external_source,
                is_open=True,
            )
            created += 1

        for metric in ("MAE", "RMSE"):
            svc.recalculate_ranks(TASK_ID, dataset_id, metric_name=metric)

        session.commit()
        print(f"created={created} skipped={skipped}")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    asyncio.run(main())
