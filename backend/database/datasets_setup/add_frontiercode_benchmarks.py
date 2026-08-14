"""Wire FrontierCode benchmarks into the Coding Agents task.

FrontierCode is Cognition's benchmark for measuring whether coding agents produce
mergeable, production-quality patches. Diamond is the headline 50-task hardest
subset reported by model vendors (e.g. Claude Opus 4.8 at 13.4% score).

Run:
    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/add_frontiercode_benchmarks.py
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import (
    Dataset as DBDataset,
)
from backend.models.database import (
    Paper as DBPaper,
)
from backend.models.database import (
    Task as DBTask,
)
from backend.services.external_resource_service import (
    ExternalResourceInput,
    ExternalResourceService,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

SOURCE_URL = "https://cognition.com/blog/frontier-code"
LEGACY_SOURCE_URL = "https://cognition.ai/blog/frontier-code"
LEADERBOARD_URL = "https://cognition.com/frontiercode"
SOURCE_TITLE = "Introducing FrontierCode"
SOURCE_DATE = date(2026, 6, 8)
SOURCE_AUTHORS = [
    "Eric Lu",
    "Ben Pan",
    "Deniz Birlikci",
    "Sam Lee",
    "Ray Wang",
    "Rohan Choudhury",
    "Fermi Ma",
    "TC Qin",
    "Carlo Baronio",
    "Silas Alberti",
]
SOURCE_ABSTRACT = (
    "FrontierCode is a coding-agent benchmark that measures whether models can "
    "produce mergeable, production-quality patches in real open-source "
    "repositories. Tasks were crafted by 20+ open-source maintainers and graded "
    "with an ensemble of unit tests, rubrics, and novel verifiers that assess "
    "correctness, test quality, scope discipline, style, and codebase standards. "
    "The benchmark reports pass rate and a weighted rubric score across three "
    "nested subsets: Extended (150 tasks), Main (100 hardest), and Diamond "
    "(50 hardest)."
)

TASK_SLUG = "coding-agents"
DATASETS = (
    {
        "name": "FrontierCode Main",
        "slug": "frontiercode-main",
        "short_description": "The current 100-task FrontierCode main benchmark.",
        "description": (
            "FrontierCode Main is the current 100-task benchmark for measuring "
            "whether coding agents produce mergeable, production-quality patches. "
            "FrontierCode 1.1 zeroes runs flagged for consulting solution-bearing "
            "internet sources."
        ),
        "homepage": LEADERBOARD_URL,
    },
    {
        "name": "FrontierCode Extended",
        "slug": "frontiercode-extended",
        "short_description": "The current 150-task FrontierCode extended benchmark.",
        "description": (
            "FrontierCode Extended is the current 150-task benchmark for measuring "
            "whether coding agents produce mergeable, production-quality patches. "
            "FrontierCode 1.1 zeroes runs flagged for consulting solution-bearing "
            "internet sources."
        ),
        "homepage": LEADERBOARD_URL,
    },
    {
        "name": "FrontierCode Diamond",
        "slug": "frontiercode-diamond",
        "short_description": (
            "Deprecated 50-task FrontierCode 1.0 subset measuring mergeable code quality."
        ),
        "description": (
            "FrontierCode Diamond is the deprecated hardest 50-task subset of "
            "FrontierCode 1.0. It is retained for historical results; FrontierCode "
            "1.1 reports the Main and Extended subsets instead."
        ),
        "homepage": SOURCE_URL,
    },
)
METRIC_NAMES = ("Score", "Pass Rate")


def _ensure_source_paper(session: Session) -> DBPaper:
    paper = (
        session.query(DBPaper)
        .filter(
            DBPaper.source == "external",
            DBPaper.source_url.in_((SOURCE_URL, LEGACY_SOURCE_URL)),
        )
        .one_or_none()
    )
    if paper is not None:
        paper.source_url = SOURCE_URL
        logger.info("Reusing external paper id=%s title=%r", paper.id, paper.title)
        return paper

    result = ExternalResourceService(session).add_external_resource(
        ExternalResourceInput(
            source_url=SOURCE_URL,
            title=SOURCE_TITLE,
            abstract=SOURCE_ABSTRACT,
            authors=SOURCE_AUTHORS,
            date_published=SOURCE_DATE,
        )
    )
    paper = session.query(DBPaper).filter(DBPaper.id == int(result.paper.id)).one()
    logger.info("Created external paper id=%s", paper.id)
    return paper


def _paper_url(paper: DBPaper) -> str:
    if paper.arxiv_id:
        return f"https://paperswithcode.co/paper/{paper.arxiv_id}"
    return f"https://paperswithcode.co/paper/{paper.id}"


def _get_task(session: Session) -> DBTask:
    task = session.query(DBTask).filter(DBTask.slug == TASK_SLUG).one_or_none()
    if task is None:
        raise RuntimeError(f"Task slug={TASK_SLUG!r} not found")
    return task


def _ensure_dataset(
    session: Session, paper: DBPaper, spec: dict[str, str]
) -> DBDataset:
    paper_url = _paper_url(paper)
    dataset = (
        session.query(DBDataset).filter(DBDataset.slug == spec["slug"]).one_or_none()
    )
    if dataset is None:
        dataset = DBDataset(
            name=spec["name"],
            slug=spec["slug"],
            full_name=spec["name"],
            description=spec["description"],
            short_description=spec["short_description"],
            homepage=spec["homepage"],
            paper_url=paper_url,
            introducing_paper_id=paper.id,
            introducing_paper_title=paper.title,
            introduced_year=SOURCE_DATE.year,
        )
        session.add(dataset)
        session.flush()
        logger.info("Created dataset %r (id=%s)", dataset.name, dataset.id)
        return dataset

    dataset.name = spec["name"]
    dataset.full_name = spec["name"]
    dataset.description = spec["description"]
    dataset.short_description = spec["short_description"]
    dataset.homepage = spec["homepage"]
    dataset.paper_url = paper_url
    dataset.introducing_paper_id = paper.id
    dataset.introducing_paper_title = paper.title
    dataset.introduced_year = dataset.introduced_year or SOURCE_DATE.year
    session.flush()
    logger.info("Updated dataset %r (id=%s)", dataset.name, dataset.id)
    return dataset


def _ensure_metric_id(session: Session, metric_name: str) -> int:
    row = session.execute(
        text("SELECT id FROM metrics WHERE name = :n"), {"n": metric_name}
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Metric {metric_name!r} not found")
    return int(row[0])


def _link_task_dataset(session: Session, task_id: int, dataset_id: int) -> None:
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


def _link_metric(
    session: Session, task_id: int, dataset_id: int, metric_id: int
) -> None:
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


def _tag_source_paper(session: Session, paper_id: int, task_id: int) -> None:
    session.execute(
        text(
            """
            INSERT INTO paper_tasks (paper_id, task_id, source)
            VALUES (:paper_id, :task_id, 'manual')
            ON CONFLICT DO NOTHING
            """
        ),
        {"paper_id": paper_id, "task_id": task_id},
    )


def main() -> None:
    with db_manager.session_local() as session:
        paper = _ensure_source_paper(session)
        task = _get_task(session)
        datasets = [_ensure_dataset(session, paper, spec) for spec in DATASETS]
        metric_ids = {name: _ensure_metric_id(session, name) for name in METRIC_NAMES}
        for dataset in datasets:
            _link_task_dataset(session, task.id, dataset.id)
            if dataset.slug != "frontiercode-diamond":
                session.execute(
                    text(
                        "UPDATE task_datasets SET supports_harness = TRUE "
                        "WHERE task_id = :task_id AND dataset_id = :dataset_id"
                    ),
                    {"task_id": task.id, "dataset_id": dataset.id},
                )
            for metric_name, metric_id in metric_ids.items():
                if dataset.slug == "frontiercode-diamond" and metric_name != "Score":
                    continue
                _link_metric(session, task.id, dataset.id, metric_id)
        _tag_source_paper(session, paper.id, task.id)
        session.commit()
        logger.info(
            "FrontierCode ready: dataset_ids=%s task_id=%s paper_url=%s",
            [dataset.id for dataset in datasets],
            task.id,
            _paper_url(paper),
        )


if __name__ == "__main__":
    main()
