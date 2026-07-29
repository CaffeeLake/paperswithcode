#!/usr/bin/env python3
"""Add Recommendation / CTR / Ranking task coverage and seed leaderboards.

Run with:

    uv run --env-file backend/keys.env \
        python backend/database/tasks_setup/add_recommendation_ctr_ranking_coverage.py

The import is intentionally protocol-specific.  A benchmark name such as
"MovieLens" or "Criteo" is not enough: every dataset row below names the split,
candidate set, or preprocessing family it represents.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.database.tasks_setup.recommendation_coverage_data import (
    BENCHMARKS,
    EVALS,
    EXTERNAL_SOURCES,
    LEDGER,
    MAJOR_PAPER_TASKS,
    METRICS,
    RECENT_PAPER_TASKS,
    SOURCE_ARXIV,
    TASKS,
)
from backend.models.database import Author, Paper, PaperAuthor
from backend.services.arxiv_service import ArxivService
from backend.services.evaluation_service import EvaluationService
from backend.services.paper_service import PaperService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

LEDGER_PATH = Path("data/curation/recommendation_ctr_ranking_ledger.json")


async def ensure_arxiv_paper(
    session, arxiv_id: str, *, required: bool = True
) -> Paper | None:
    existing = (
        session.query(Paper)
        .filter(Paper.arxiv_id == arxiv_id, Paper.is_latest_version.is_(True))
        .first()
    )
    if existing:
        return existing

    metadata = await ArxivService().get_paper_metadata(arxiv_id)
    if not metadata.success:
        message = (
            f"Failed to fetch arXiv metadata for {arxiv_id}: {metadata.error_message}"
        )
        if required:
            raise RuntimeError(message)
        logger.warning(message)
        return None

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
    return paper


def ensure_external_paper(session, key: str) -> Paper:
    spec = EXTERNAL_SOURCES[key]
    row = (
        session.query(Paper)
        .filter(Paper.source == "external", Paper.source_url == spec["source_url"])
        .first()
    )
    if row:
        row.title = spec["title"]
        row.abstract = spec["abstract"]
        row.date_published = spec["date_published"]
        session.flush()
        return row

    paper = Paper(
        title=spec["title"],
        abstract=spec["abstract"],
        source="external",
        source_url=spec["source_url"],
        arxiv_id=None,
        version="v1",
        is_latest_version=True,
        date_published=spec["date_published"],
    )
    session.add(paper)
    session.flush()
    return paper


def paper_url_for(paper: Paper) -> str:
    if paper.arxiv_id:
        return f"https://paperswithcode.co/paper/{paper.arxiv_id}"
    return f"https://paperswithcode.co/paper/{paper.id}"


def ensure_task(session, spec: dict[str, Any]) -> int:
    row = session.execute(
        text(
            """
            INSERT INTO tasks (
                name, slug, description, keywords, area_id, parent_id, level,
                image_url, image_credit, useful_leaderboards
            )
            VALUES (
                :name, :slug, :description, :keywords,
                (SELECT id FROM areas WHERE name = :area LIMIT 1),
                CASE WHEN :parent IS NULL THEN NULL
                     ELSE (SELECT id FROM tasks WHERE slug = :parent LIMIT 1) END,
                CASE WHEN :parent IS NULL THEN 0
                     ELSE (SELECT level + 1 FROM tasks WHERE slug = :parent LIMIT 1) END,
                NULL, :image_credit, NULL
            )
            ON CONFLICT (slug) DO UPDATE SET
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                keywords = EXCLUDED.keywords,
                area_id = EXCLUDED.area_id,
                parent_id = EXCLUDED.parent_id,
                level = EXCLUDED.level,
                image_url = NULL,
                image_credit = EXCLUDED.image_credit,
                useful_leaderboards = EXCLUDED.useful_leaderboards,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id
            """
        ),
        {
            "name": spec["name"],
            "slug": spec["slug"],
            "description": spec["description"],
            "keywords": spec["keywords"],
            "area": spec["area"],
            "parent": spec["parent"],
            "image_credit": "[Papers with Code curation](/tasks/recommendation-systems)",
        },
    ).scalar_one()
    return int(row)


def ensure_metric(session, spec: tuple[str, str, str, str]) -> int:
    name, direction, scale, description = spec
    row = session.execute(
        text("SELECT id FROM metrics WHERE name = :name"),
        {"name": name},
    ).fetchone()
    if row:
        return int(row.id)
    return int(
        session.execute(
            text(
                """
                INSERT INTO metrics (name, full_name, direction, scale, description)
                VALUES (:name, :name, :direction, :scale, :description)
                RETURNING id
                """
            ),
            {
                "name": name,
                "direction": direction,
                "scale": scale,
                "description": description,
            },
        ).scalar_one()
    )


def task_id(session, slug: str) -> int:
    return int(
        session.execute(
            text("SELECT id FROM tasks WHERE slug = :slug"),
            {"slug": slug},
        ).scalar_one()
    )


def link_paper_to_task(session, paper_id: int, task_slug: str) -> None:
    session.execute(
        text(
            """
            INSERT INTO paper_tasks (paper_id, task_id, source)
            SELECT :paper_id, id, 'manual' FROM tasks WHERE slug = :slug
            ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'
            """
        ),
        {"paper_id": paper_id, "slug": task_slug},
    )


def ensure_dataset(session, spec: dict[str, Any], source_paper: Paper) -> int:
    row = session.execute(
        text("SELECT id FROM datasets WHERE slug = :slug"),
        {"slug": spec["slug"]},
    ).fetchone()
    if row:
        dataset_id = int(row.id)
    else:
        dataset_id = int(
            session.execute(
                text(
                    """
                    INSERT INTO datasets (
                        name, slug, description, short_description, homepage,
                        introduced_date, introduced_year, paper_url,
                        introducing_paper_id, introducing_paper_title
                    )
                    VALUES (
                        :name, :slug, :description, :short_description, :homepage,
                        :introduced_date, :introduced_year, :paper_url,
                        :introducing_paper_id, :introducing_paper_title
                    )
                    RETURNING id
                    """
                ),
                {
                    "name": spec["name"],
                    "slug": spec["slug"],
                    "description": spec["description"],
                    "short_description": spec["short_description"],
                    "homepage": spec["homepage"],
                    "introduced_date": spec["introduced_date"],
                    "introduced_year": spec["introduced_date"].year,
                    "paper_url": paper_url_for(source_paper),
                    "introducing_paper_id": source_paper.id,
                    "introducing_paper_title": source_paper.title,
                },
            ).scalar_one()
        )

    session.execute(
        text(
            """
            UPDATE datasets
            SET name = :name,
                description = :description,
                short_description = :short_description,
                homepage = :homepage,
                introduced_date = COALESCE(introduced_date, :introduced_date),
                introduced_year = COALESCE(introduced_year, :introduced_year),
                paper_url = :paper_url,
                introducing_paper_id = :introducing_paper_id,
                introducing_paper_title = :introducing_paper_title,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
            """
        ),
        {
            "id": dataset_id,
            "name": spec["name"],
            "description": spec["description"],
            "short_description": spec["short_description"],
            "homepage": spec["homepage"],
            "introduced_date": spec["introduced_date"],
            "introduced_year": spec["introduced_date"].year,
            "paper_url": paper_url_for(source_paper),
            "introducing_paper_id": source_paper.id,
            "introducing_paper_title": source_paper.title,
        },
    )
    return dataset_id


def wire_benchmark(
    session,
    dataset_id: int,
    task_slug_value: str,
    metric_names: list[str],
    metric_ids: dict[str, int],
) -> None:
    target_task_id = task_id(session, task_slug_value)
    session.execute(
        text(
            """
            INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
            VALUES (:task_id, :dataset_id, FALSE)
            ON CONFLICT (task_id, dataset_id) DO UPDATE
            SET supports_harness = FALSE, updated_at = CURRENT_TIMESTAMP
            """
        ),
        {"task_id": target_task_id, "dataset_id": dataset_id},
    )
    for metric_name in metric_names:
        session.execute(
            text(
                """
                INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
                VALUES (:task_id, :dataset_id, :metric_id)
                ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING
                """
            ),
            {
                "task_id": target_task_id,
                "dataset_id": dataset_id,
                "metric_id": metric_ids[metric_name],
            },
        )


def existing_evaluation_id(
    session,
    paper_id: int,
    task_id_value: int,
    dataset_id: int,
    model_name: str,
    metric: str,
) -> int | None:
    row = session.execute(
        text(
            """
            SELECT id FROM evaluations
            WHERE paper_id = :paper_id
              AND task_id = :task_id
              AND dataset_id = :dataset_id
              AND model_name = :model_name
              AND COALESCE(harness, '') = ''
              AND best_metric = :metric
            LIMIT 1
            """
        ),
        {
            "paper_id": paper_id,
            "task_id": task_id_value,
            "dataset_id": dataset_id,
            "model_name": model_name,
            "metric": metric,
        },
    ).fetchone()
    if not row:
        return None
    return int(row.id)


def update_existing_evaluation(
    session,
    evaluation_id: int,
    metrics: dict[str, str],
    methodology: str,
    source_url: str,
) -> None:
    session.execute(
        text(
            """
            UPDATE evaluations
            SET metrics = CAST(:metrics AS jsonb),
                methodology = :methodology,
                external_source_url = :source_url,
                source_url = :source_url,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :evaluation_id
            """
        ),
        {
            "evaluation_id": evaluation_id,
            "metrics": json.dumps(metrics),
            "methodology": methodology,
            "source_url": source_url,
        },
    )


async def resolve_benchmark_sources(session) -> dict[str, Paper]:
    source_papers: dict[str, Paper] = {}
    for key, arxiv_id in SOURCE_ARXIV.items():
        paper = await ensure_arxiv_paper(session, arxiv_id)
        if paper is None:
            raise RuntimeError(f"Missing required source paper for {key}: {arxiv_id}")
        source_papers[key] = paper
    for key in EXTERNAL_SOURCES:
        source_papers[key] = ensure_external_paper(session, key)
    return source_papers


async def main() -> None:
    session = db_manager.session_local()
    try:
        for task in TASKS:
            ensure_task(session, task)
        session.commit()

        metric_ids = {spec[0]: ensure_metric(session, spec) for spec in METRICS}
        source_papers = await resolve_benchmark_sources(session)

        for spec in BENCHMARKS:
            source_key = spec.get("source_key") or spec.get("external_source_key")
            source_paper = source_papers[source_key]
            dataset_id = ensure_dataset(session, spec, source_paper)
            for slug in spec["task_slugs"]:
                wire_benchmark(session, dataset_id, slug, spec["metrics"], metric_ids)
                link_paper_to_task(session, int(source_paper.id), slug)
            link_paper_to_task(session, int(source_paper.id), "recommendation-systems")
        session.commit()

        for arxiv_id, task_slugs in MAJOR_PAPER_TASKS.items():
            paper = await ensure_arxiv_paper(session, arxiv_id, required=False)
            if paper is None:
                continue
            link_paper_to_task(session, int(paper.id), "recommendation-systems")
            for slug in task_slugs:
                link_paper_to_task(session, int(paper.id), slug)
        session.commit()

        for arxiv_id, task_slugs in RECENT_PAPER_TASKS.items():
            paper = await ensure_arxiv_paper(session, arxiv_id, required=False)
            if paper is None:
                continue
            link_paper_to_task(session, int(paper.id), "recommendation-systems")
            for slug in task_slugs:
                if slug != "recommendation-systems":
                    link_paper_to_task(session, int(paper.id), slug)
        session.commit()

        eval_service = EvaluationService(session)
        added = 0
        affected_leaderboards: set[tuple[int, int, str]] = set()
        skipped_missing_paper = []
        for spec in EVALS:
            paper = await ensure_arxiv_paper(
                session, spec["paper_arxiv"], required=False
            )
            if paper is None:
                skipped_missing_paper.append(spec)
                continue
            target_task_id = task_id(session, spec["task_slug"])
            dataset_id = int(
                session.execute(
                    text("SELECT id FROM datasets WHERE slug = :slug"),
                    {"slug": spec["dataset_slug"]},
                ).scalar_one()
            )
            link_paper_to_task(session, int(paper.id), "recommendation-systems")
            link_paper_to_task(session, int(paper.id), spec["task_slug"])
            metrics = {spec["metric"]: spec["score"]}
            metrics.update(spec.get("extra") or {})
            affected_leaderboards.add((target_task_id, dataset_id, spec["metric"]))
            existing_id = existing_evaluation_id(
                session,
                int(paper.id),
                target_task_id,
                dataset_id,
                spec["model_name"],
                spec["metric"],
            )
            if existing_id:
                update_existing_evaluation(
                    session,
                    existing_id,
                    metrics,
                    spec["methodology"],
                    paper_url_for(paper),
                )
                continue
            eval_service.create_evaluation(
                paper_id=int(paper.id),
                task_id=target_task_id,
                dataset_id=dataset_id,
                model_name=spec["model_name"],
                methodology=spec["methodology"],
                metrics=metrics,
                best_metric=spec["metric"],
                external_source_url=paper_url_for(paper),
                is_open=True,
            )
            added += 1
        session.commit()

        for target_task_id, dataset_id, metric in affected_leaderboards:
            eval_service.recalculate_ranks(
                target_task_id, dataset_id, metric_name=metric
            )

        LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        ledger = {**LEDGER, "skipped_missing_paper": skipped_missing_paper}
        LEDGER_PATH.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n")

        logger.info(
            "Recommendation coverage added successfully; eval rows added=%s", added
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    asyncio.run(main())
