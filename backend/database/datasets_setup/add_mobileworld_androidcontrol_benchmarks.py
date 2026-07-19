"""Add MobileWorld and AndroidControl to the Computer Use Agents task.

Run:
    uv run --env-file backend/keys.env \\
        python backend/database/datasets_setup/add_mobileworld_androidcontrol_benchmarks.py
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import (
    Dataset as DBDataset,
    Paper as DBPaper,
    Task as DBTask,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

TASK_SLUG = "computer-use-agents"

BENCHMARKS: list[dict] = [
    {
        "slug": "mobileworld",
        "name": "MobileWorld",
        "arxiv_id": "2512.19432",
        "introduced_date": date(2025, 12, 22),
        "homepage": "https://tongyi-mai.github.io/MobileWorld/",
        "hf_url": "https://huggingface.co/datasets/Tongyi-MAI/MobileWorld",
        "github": "https://github.com/Tongyi-MAI/MobileWorld",
        "short_description": (
            "Online mobile GUI agent benchmark with agent-user interaction and MCP tasks."
        ),
        "description": (
            "MobileWorld is an online benchmark for autonomous mobile agents with 201 tasks "
            "across 20 applications. It extends AndroidWorld-style deterministic evaluation "
            "with long-horizon cross-app workflows, agent-user interaction tasks, and "
            "Model Context Protocol (MCP)-augmented hybrid tool use. Results are reported "
            "as task success rate."
        ),
        "metric_name": "Success Rate",
    },
    {
        "slug": "androidcontrol",
        "name": "AndroidControl",
        "arxiv_id": "2406.03679",
        "introduced_date": date(2024, 6, 6),
        "homepage": "https://github.com/google-research/google-research/tree/master/android_control",
        "hf_url": "https://huggingface.co/datasets/google/android-control",
        "github": "https://github.com/google-research/google-research/tree/master/android_control",
        "short_description": (
            "Large-scale Android GUI control dataset for static action prediction."
        ),
        "description": (
            "AndroidControl contains 15,283 human demonstrations across 833 Android apps "
            "with high-level goals and low-level step instructions, screenshots, and "
            "accessibility trees. It is widely used for offline static GUI understanding "
            "and action prediction; papers report overall accuracy on held-out test steps."
        ),
        "metric_name": "Accuracy",
    },
]


def _get_task(session: Session) -> DBTask:
    task = session.query(DBTask).filter(DBTask.slug == TASK_SLUG).one_or_none()
    if task is None:
        raise RuntimeError(f"Task slug={TASK_SLUG!r} not found")
    return task


def _get_paper(session: Session, arxiv_id: str) -> DBPaper:
    paper = (
        session.query(DBPaper)
        .filter(DBPaper.arxiv_id == arxiv_id, DBPaper.is_latest_version)
        .one_or_none()
    )
    if paper is None:
        raise RuntimeError(f"Paper arxiv_id={arxiv_id!r} not found")
    return paper


def _paper_url(paper: DBPaper) -> str:
    return f"https://paperswithcode.co/paper/{paper.arxiv_id}"


def _ensure_dataset(session: Session, spec: dict, paper: DBPaper) -> DBDataset:
    dataset = (
        session.query(DBDataset).filter(DBDataset.slug == spec["slug"]).one_or_none()
    )
    paper_url = _paper_url(paper)
    if dataset is None:
        dataset = DBDataset(
            name=spec["name"],
            slug=spec["slug"],
            full_name=paper.title,
            description=spec["description"],
            short_description=spec["short_description"],
            url=spec["github"],
            homepage=spec["homepage"],
            hf_url=spec["hf_url"],
            paper_url=paper_url,
            introducing_paper_id=paper.id,
            introducing_paper_title=paper.title,
            introduced_year=spec["introduced_date"].year,
        )
        session.add(dataset)
        session.flush()
        logger.info("Created dataset %r (id=%s)", dataset.name, dataset.id)
    else:
        dataset.full_name = paper.title
        dataset.description = spec["description"]
        dataset.short_description = spec["short_description"]
        dataset.url = spec["github"]
        dataset.homepage = spec["homepage"]
        dataset.hf_url = spec["hf_url"]
        dataset.paper_url = paper_url
        dataset.introducing_paper_id = paper.id
        dataset.introducing_paper_title = paper.title
        dataset.introduced_year = (
            dataset.introduced_year or spec["introduced_date"].year
        )
        session.flush()
        logger.info("Updated dataset %r (id=%s)", dataset.name, dataset.id)
    return dataset


def _get_metric_id(session: Session, metric_name: str) -> int:
    row = session.execute(
        text("SELECT id FROM metrics WHERE name = :n"), {"n": metric_name}
    ).one()
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
        task = _get_task(session)
        for spec in BENCHMARKS:
            paper = _get_paper(session, spec["arxiv_id"])
            dataset = _ensure_dataset(session, spec, paper)
            metric_id = _get_metric_id(session, spec["metric_name"])
            _link_task_dataset(session, task.id, dataset.id)
            _link_metric(session, task.id, dataset.id, metric_id)
            _tag_source_paper(session, paper.id, task.id)
            logger.info(
                "%s ready: dataset_id=%s metric=%s paper_url=%s",
                spec["name"],
                dataset.id,
                spec["metric_name"],
                _paper_url(paper),
            )
        session.commit()


if __name__ == "__main__":
    main()
