"""Add the first curated Graph Machine Learning benchmark surface.

This script implements PLAN_GRAPH_ML.md through the benchmark batches:

- OGB core node/link/graph property prediction.
- Classic citation and heterophily node classification leaderboards.
- Benchmarking GNNs and LRGB graph datasets.
- MoleculeNet molecular property prediction tasks.
- Knowledge graph completion and Temporal Graph Benchmark rows.
- A small, conservative seed of graph eval rows from legacy PwC data.

Run:
    uv run --env-file backend/keys.env \\
        python backend/database/datasets_setup/add_graph_ml_coverage.py
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.database.datasets_setup.graph_ml_benchmarks import BENCHMARKS
from backend.database.datasets_setup.graph_ml_coverage_data import (
    CORE_PAPER_TASKS,
    EVAL_SPECS,
    FB15K237_SOURCE_URL,
    METRIC_SPECS,
    SOURCE_PAPERS,
    TASK_SLUGS,
)
from backend.models.database import (
    Dataset as DBDataset,
    Paper as DBPaper,
    Task as DBTask,
)
from backend.services.arxiv_service import ArxivService
from backend.services.evaluation_service import EvaluationService
from backend.services.external_resource_service import (
    ExternalResourceInput,
    ExternalResourceService,
)
from backend.services.paper_service import PaperService

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def ensure_arxiv_paper(session: Session, arxiv_id: str) -> DBPaper:
    paper = (
        session.query(DBPaper)
        .filter(DBPaper.arxiv_id == arxiv_id, DBPaper.is_latest_version.is_(True))
        .first()
    )
    if paper is not None:
        return paper

    metadata = await ArxivService().get_paper_metadata(arxiv_id)
    if not metadata.success:
        raise RuntimeError(
            f"Failed to fetch arXiv metadata for {arxiv_id}: {metadata.error_message}"
        )

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
    if paper_id is None:
        paper = (
            session.query(DBPaper)
            .filter(DBPaper.arxiv_id == arxiv_id, DBPaper.is_latest_version.is_(True))
            .one()
        )
    else:
        paper = session.get(DBPaper, int(paper_id))
    if paper is None:
        raise RuntimeError(f"Failed to load paper for arXiv {arxiv_id}")
    logger.info("Imported paper %s (id=%s)", arxiv_id, paper.id)
    return paper


def ensure_fb15k237_source_paper(session: Session) -> DBPaper:
    paper = (
        session.query(DBPaper)
        .filter(DBPaper.source == "external", DBPaper.source_url == FB15K237_SOURCE_URL)
        .one_or_none()
    )
    if paper is not None:
        return paper

    result = ExternalResourceService(session).add_external_resource(
        ExternalResourceInput(
            source_url=FB15K237_SOURCE_URL,
            title="Knowledge Base Completion Using Embeddings and Rules",
            abstract=(
                "This paper studies knowledge base completion with embeddings "
                "and logical rules, and introduces the FB15k-237 filtered "
                "Freebase benchmark used to reduce inverse-relation leakage."
            ),
            authors=["Kristina Toutanova", "Danqi Chen"],
            date_published=date(2015, 7, 31),
        )
    )
    paper = session.query(DBPaper).filter(DBPaper.id == int(result.paper.id)).one()
    logger.info("Created external FB15k-237 source paper id=%s", paper.id)
    return paper


def paper_url(paper: DBPaper) -> str:
    if paper.arxiv_id:
        return f"https://paperswithcode.co/paper/{paper.arxiv_id}"
    return f"https://paperswithcode.co/paper/{paper.id}"


def get_task(session: Session, slug: str) -> DBTask:
    task = session.query(DBTask).filter(DBTask.slug == slug).one_or_none()
    if task is None:
        raise RuntimeError(
            f"Task slug={slug!r} not found. Apply "
            "backend/database/migrations/add_graph_machine_learning_task.sql first."
        )
    return task


def ensure_metric(session: Session, spec: dict[str, Any]) -> int:
    row = session.execute(
        text("SELECT id FROM metrics WHERE name = :name"), {"name": spec["name"]}
    ).fetchone()
    if row:
        return int(row[0])

    metric_id = session.execute(
        text(
            """
            INSERT INTO metrics (name, direction, full_name, scale, description)
            VALUES (:name, :direction, :full_name, :scale, :description)
            RETURNING id
            """
        ),
        spec,
    ).scalar_one()
    logger.info("Created metric %s (id=%s)", spec["name"], metric_id)
    return int(metric_id)


def metric_id(session: Session, name: str) -> int:
    row = session.execute(
        text("SELECT id FROM metrics WHERE name = :name"), {"name": name}
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Metric {name!r} not found")
    return int(row[0])


def ensure_dataset(
    session: Session,
    spec: dict[str, Any],
    source_paper: DBPaper,
) -> DBDataset:
    native_url = paper_url(source_paper)
    dataset = (
        session.query(DBDataset).filter(DBDataset.slug == spec["slug"]).one_or_none()
    )
    if dataset is None:
        dataset = DBDataset(
            name=spec["name"],
            slug=spec["slug"],
            full_name=spec["full_name"],
            description=spec["description"],
            short_description=spec["short_description"],
            url=spec["url"],
            homepage=spec["homepage"],
            paper_url=native_url,
            introducing_paper_id=source_paper.id,
            introducing_paper_title=source_paper.title,
            introduced_year=spec["introduced_year"],
        )
        session.add(dataset)
        session.flush()
        logger.info("Created dataset %s (id=%s)", dataset.name, dataset.id)
        return dataset

    dataset.name = spec["name"]
    dataset.full_name = spec["full_name"]
    dataset.description = spec["description"]
    dataset.short_description = spec["short_description"]
    dataset.url = spec["url"]
    dataset.homepage = spec["homepage"]
    dataset.paper_url = native_url
    dataset.introducing_paper_id = source_paper.id
    dataset.introducing_paper_title = source_paper.title
    dataset.introduced_year = dataset.introduced_year or spec["introduced_year"]
    session.flush()
    logger.info("Updated dataset %s (id=%s)", dataset.name, dataset.id)
    return dataset


def link_task_dataset(session: Session, task_id: int, dataset_id: int) -> None:
    session.execute(
        text(
            """
            INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
            VALUES (:task_id, :dataset_id, FALSE)
            ON CONFLICT (task_id, dataset_id) DO NOTHING
            """
        ),
        {"task_id": task_id, "dataset_id": dataset_id},
    )


def link_metric(
    session: Session,
    task_id: int,
    dataset_id: int,
    metric_id_value: int,
) -> None:
    session.execute(
        text(
            """
            INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
            VALUES (:task_id, :dataset_id, :metric_id)
            ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING
            """
        ),
        {
            "task_id": task_id,
            "dataset_id": dataset_id,
            "metric_id": metric_id_value,
        },
    )


def tag_source_paper(session: Session, paper_id: int, task_id: int) -> None:
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


async def resolve_source_paper(
    session: Session,
    spec: dict[str, Any],
    source_cache: dict[str, DBPaper],
) -> DBPaper:
    if spec.get("external_source") == "fb15k-237":
        if "fb15k-237" not in source_cache:
            source_cache["fb15k-237"] = ensure_fb15k237_source_paper(session)
        return source_cache["fb15k-237"]

    source_key = spec["source_key"]
    if source_key not in source_cache:
        source_cache[source_key] = await ensure_arxiv_paper(
            session, SOURCE_PAPERS[source_key]
        )
    return source_cache[source_key]


def create_or_skip_eval(
    session: Session,
    spec: dict[str, Any],
    paper: DBPaper,
) -> bool:
    task = get_task(session, spec["task_slug"])
    dataset = (
        session.query(DBDataset)
        .filter(DBDataset.slug == spec["dataset_slug"])
        .one_or_none()
    )
    if dataset is None:
        raise RuntimeError(f"Dataset slug={spec['dataset_slug']!r} not found")

    exists = session.execute(
        text(
            """
            SELECT id
            FROM evaluations
            WHERE paper_id = :paper_id
              AND task_id = :task_id
              AND dataset_id = :dataset_id
              AND model_name = :model_name
              AND COALESCE(harness, '') = ''
              AND best_metric = :best_metric
            LIMIT 1
            """
        ),
        {
            "paper_id": paper.id,
            "task_id": task.id,
            "dataset_id": dataset.id,
            "model_name": spec["model_name"],
            "best_metric": spec["metric"],
        },
    ).fetchone()
    if exists:
        logger.info(
            "Evaluation already exists: paper=%s dataset=%s model=%s metric=%s",
            paper.arxiv_id or paper.id,
            dataset.slug,
            spec["model_name"],
            spec["metric"],
        )
        return False

    tag_source_paper(session, paper.id, task.id)

    EvaluationService(session).create_evaluation(
        paper_id=paper.id,
        task_id=task.id,
        dataset_id=dataset.id,
        model_name=spec["model_name"],
        methodology=spec["methodology"],
        metrics={spec["metric"]: spec["score"]},
        best_metric=spec["metric"],
        uses_additional_data=spec.get("uses_additional_data", False),
        is_open=True,
        source_url=paper_url(paper),
        num_parameters=spec.get("num_parameters"),
    )
    logger.info(
        "Created eval: %s / %s / %s=%s",
        dataset.slug,
        spec["model_name"],
        spec["metric"],
        spec["score"],
    )
    return True


async def main() -> None:
    with db_manager.session_local() as session:
        for slug in TASK_SLUGS:
            get_task(session, slug)

        for spec in METRIC_SPECS:
            ensure_metric(session, spec)

        source_cache: dict[str, DBPaper] = {}
        tasks = {slug: get_task(session, slug) for slug in TASK_SLUGS}
        metric_ids: dict[str, int] = {}
        created_or_updated = 0

        for spec in BENCHMARKS:
            source_paper = await resolve_source_paper(session, spec, source_cache)
            dataset = ensure_dataset(session, spec, source_paper)
            created_or_updated += 1

            for task_slug, metric_name in spec["task_metrics"]:
                task = tasks[task_slug]
                link_task_dataset(session, task.id, dataset.id)
                if metric_name not in metric_ids:
                    metric_ids[metric_name] = metric_id(session, metric_name)
                link_metric(session, task.id, dataset.id, metric_ids[metric_name])
                tag_source_paper(session, source_paper.id, task.id)

            logger.info(
                "Ready benchmark %s: metrics=%s source=%s",
                dataset.slug,
                spec["task_metrics"],
                dataset.paper_url,
            )

        # Attach the benchmark source papers to the top-level family as well.
        graph_task = tasks["graph-machine-learning"]
        for paper in source_cache.values():
            tag_source_paper(session, paper.id, graph_task.id)

        for arxiv_id, task_slugs in CORE_PAPER_TASKS.items():
            paper = await ensure_arxiv_paper(session, arxiv_id)
            for task_slug in task_slugs:
                tag_source_paper(session, paper.id, tasks[task_slug].id)

        logger.info("Benchmarks created/updated: %s", created_or_updated)

        eval_created = 0
        for spec in EVAL_SPECS:
            paper = await ensure_arxiv_paper(session, spec["paper_arxiv"])
            if create_or_skip_eval(session, spec, paper):
                eval_created += 1

        session.commit()

        logger.info("Evaluation rows created: %s", eval_created)

        rows = session.execute(
            text(
                """
                SELECT t.slug AS task_slug, COUNT(td.dataset_id) AS benchmarks
                FROM tasks t
                LEFT JOIN task_datasets td ON td.task_id = t.id
                WHERE t.slug = ANY(:slugs)
                GROUP BY t.slug
                ORDER BY t.slug
                """
            ),
            {"slugs": TASK_SLUGS},
        ).mappings()
        for row in rows:
            logger.info("%s benchmarks=%s", row["task_slug"], row["benchmarks"])


if __name__ == "__main__":
    asyncio.run(main())
