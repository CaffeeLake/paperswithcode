#!/usr/bin/env python3
"""Import legacy PwC PubLayNet val eval rows for document-layout-analysis.

Legacy source: data/legacy_pwc_data/evaluation-tables.json
Leaderboard slug: document-layout-analysis-on-publaynet-val

DocLayNet has no rows in the legacy evaluation-tables dump (dataset post-dates
most legacy leaderboard curation). This script only backfills PubLayNet.

Run:
    uv run --env-file backend/keys.env \\
        python backend/database/evaluations_setup/import_publaynet_legacy_evals.py
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import ijson
from sqlalchemy import text

from backend.database.connection import db_manager
from backend.database.evaluations_setup.analyze_legacy_top_ranked_gaps import (
    extract_arxiv_id,
    walk_leaderboards,
)
from backend.models.database import Evaluation as DBEvaluation, Paper
from backend.services.arxiv_service import ArxivService
from backend.services.evaluation_service import EvaluationService
from backend.services.paper_service import PaperService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TASK_SLUG = "document-layout-analysis"
DATASET_SLUG = "publaynet"
LEGACY_PATH = Path("data/legacy_pwc_data/evaluation-tables.json")
SOTA_SLUG = "document-layout-analysis-on-publaynet-val"
BEST_METRIC = "mAP"
SOURCE_NOTE = (
    "PubLayNet validation split; mean per-class AP (legacy Overall) from legacy "
    f"PwC evaluation-tables.json ({SOTA_SLUG}). Stored as mAP on this leaderboard."
)


def load_legacy_rows() -> list[dict]:
    with LEGACY_PATH.open("rb") as f:
        for item in ijson.items(f, "item"):
            for slug, _, ds in walk_leaderboards(item, item.get("task", "")):
                if slug == SOTA_SLUG:
                    return ds.get("sota", {}).get("rows", [])
    raise RuntimeError(f"Leaderboard {SOTA_SLUG!r} not found in legacy data")


def to_leaderboard_score(raw: str) -> str:
    value = float(raw.strip())
    if value <= 1.0:
        scaled = value * 100
        return str(int(scaled)) if scaled.is_integer() else f"{scaled:g}"
    return raw.strip()


def link_map_metric(session, task_id: int, dataset_id: int) -> None:
    metric_id = session.execute(
        text("SELECT id FROM metrics WHERE name = :n"), {"n": BEST_METRIC}
    ).scalar_one()
    session.execute(
        text(
            """
            INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
            VALUES (:task_id, :dataset_id, :metric_id)
            ON CONFLICT DO NOTHING
            """
        ),
        {"task_id": task_id, "dataset_id": dataset_id, "metric_id": metric_id},
    )


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
        raise RuntimeError(f"Failed to fetch arXiv metadata for {arxiv_id}")

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
    logger.info("Indexed paper %s (id=%s)", arxiv_id, paper.id)
    return paper


async def main() -> None:
    legacy_rows = load_legacy_rows()
    logger.info("Loaded %s legacy rows from %s", len(legacy_rows), SOTA_SLUG)

    session = db_manager.session_local()
    created = 0
    skipped = 0
    no_arxiv = 0
    no_overall = 0

    try:
        task_id = session.execute(
            text("SELECT id FROM tasks WHERE slug = :s"), {"s": TASK_SLUG}
        ).scalar_one()
        dataset_id = session.execute(
            text("SELECT id FROM datasets WHERE slug = :s"), {"s": DATASET_SLUG}
        ).scalar_one()
        link_map_metric(session, task_id, dataset_id)
        session.commit()

        service = EvaluationService(session)
        linked_papers: set[int] = set()

        for row in legacy_rows:
            model_name = (row.get("model_name") or "").strip()
            metrics = row.get("metrics") or {}
            overall_raw = metrics.get("Overall")
            if not overall_raw or not str(overall_raw).strip():
                no_overall += 1
                logger.info("Skip %r — no Overall metric", model_name)
                continue

            arxiv_id = extract_arxiv_id(row.get("paper_url"))
            if not arxiv_id:
                no_arxiv += 1
                logger.info(
                    "Skip %r — no arXiv id (%s)", model_name, row.get("paper_url")
                )
                continue

            session.rollback()
            paper = await ensure_arxiv_paper(session, arxiv_id)
            if paper.id not in linked_papers:
                link_paper_task(session, paper.id, task_id)
                session.commit()
                linked_papers.add(paper.id)

            exists = (
                session.query(DBEvaluation)
                .filter(
                    DBEvaluation.paper_id == paper.id,
                    DBEvaluation.task_id == task_id,
                    DBEvaluation.dataset_id == dataset_id,
                    DBEvaluation.model_name == model_name,
                    DBEvaluation.best_metric == BEST_METRIC,
                )
                .first()
            )
            if exists:
                skipped += 1
                logger.info("Skip existing %s / %s", arxiv_id, model_name)
                continue

            score = to_leaderboard_score(str(overall_raw))
            methodology = f"{SOURCE_NOTE} Source: arXiv {arxiv_id}."
            service.create_evaluation(
                paper_id=paper.id,
                task_id=task_id,
                dataset_id=dataset_id,
                model_name=model_name,
                methodology=methodology,
                metrics={BEST_METRIC: score},
                best_metric=BEST_METRIC,
                external_source_url=f"https://arxiv.org/abs/{arxiv_id}",
                is_open=True,
            )
            created += 1
            logger.info(
                "Created %s / %s / %s = %s", arxiv_id, model_name, BEST_METRIC, score
            )

        logger.info(
            "Done: created=%s skipped=%s no_arxiv=%s no_overall=%s papers_tagged=%s",
            created,
            skipped,
            no_arxiv,
            no_overall,
            len(linked_papers),
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    asyncio.run(main())
