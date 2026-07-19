"""Add the six D4RL AntMaze v2 offline-RL leaderboards.

The v2 registrations remain canonical D4RL environments. Minari's migrated
AntMaze datasets use a different namespace and version, so they are not merged
into these leaderboards.

Run:
    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/add_d4rl_antmaze_v2_benchmarks.py
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import Dataset, Paper, Task

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TASK_ID = 364
TASK_SLUG = "offline-reinforcement-learning"
SOURCE_ARXIV_ID = "2004.07219"
SOURCE_URL = f"https://paperswithcode.co/paper/{SOURCE_ARXIV_ID}"
HOMEPAGE = "https://github.com/Farama-Foundation/D4RL"
METRIC_NAME = "Normalized Score"

BENCHMARKS = [
    ("umaze", "U-maze", "fixed start and fixed goal", 700),
    ("umaze-diverse", "U-maze", "random starts and random goals", 700),
    (
        "medium-play",
        "medium maze",
        "hand-picked starts and hand-picked commanded goals",
        1000,
    ),
    ("medium-diverse", "medium maze", "random starts and random goals", 1000),
    (
        "large-play",
        "large maze",
        "hand-picked starts and hand-picked commanded goals",
        1000,
    ),
    ("large-diverse", "large maze", "random starts and random goals", 1000),
]


def get_task(session: Session) -> Task:
    task = session.query(Task).filter(Task.slug == TASK_SLUG).one_or_none()
    if task is None:
        raise RuntimeError(f"Task {TASK_SLUG!r} not found")
    if task.id != TASK_ID:
        raise RuntimeError(f"Task {TASK_SLUG!r} has id={task.id}, expected {TASK_ID}")
    return task


def get_source_paper(session: Session) -> Paper:
    paper = (
        session.query(Paper)
        .filter(Paper.arxiv_id == SOURCE_ARXIV_ID, Paper.is_latest_version)
        .one_or_none()
    )
    if paper is None:
        raise RuntimeError(f"Latest source paper {SOURCE_ARXIV_ID} not found")
    return paper


def description(variant: str, layout: str, collection: str, horizon: int) -> str:
    env_id = f"antmaze-{variant}-v2"
    return (
        f"D4RL {env_id} evaluates offline MuJoCo Ant navigation in the {layout} "
        f"using the fixed v2 dataset collected with {collection}. The v2 "
        "evaluation convention resamples the target goal on every rollout. "
        "Reaching the goal is a terminal success; a rollout that instead reaches "
        f"the {horizon}-step TimeLimit is a timeout truncation, kept distinct from "
        "a terminal transition. This leaderboard uses D4RL Normalized Score for "
        "the exact v2 offline-only protocol and excludes v0/v1 results and all "
        "offline-to-online fine-tuning."
    )


def ensure_dataset(
    session: Session,
    paper: Paper,
    variant: str,
    layout: str,
    collection: str,
    horizon: int,
) -> Dataset:
    env_id = f"antmaze-{variant}-v2"
    name = f"D4RL AntMaze-{variant}-v2"
    slug = f"d4rl-antmaze-{variant}-v2"
    matches = (
        session.query(Dataset)
        .filter((Dataset.slug == slug) | (Dataset.name == name))
        .all()
    )
    if len(matches) > 1:
        raise RuntimeError(f"Ambiguous dataset rows for {name!r}/{slug!r}")

    if matches:
        dataset = matches[0]
        if dataset.slug != slug or dataset.name != name:
            raise RuntimeError(
                f"Conflicting dataset id={dataset.id}: "
                f"name={dataset.name!r}, slug={dataset.slug!r}"
            )
        logger.info("Repairing %s (id=%s)", env_id, dataset.id)
    else:
        dataset = Dataset(name=name, slug=slug)
        session.add(dataset)
        session.flush()
        logger.info("Created %s (id=%s)", env_id, dataset.id)

    dataset.full_name = name
    dataset.description = description(variant, layout, collection, horizon)
    dataset.short_description = (
        f"D4RL {env_id} offline Ant navigation with per-rollout v2 evaluation goals."
    )
    dataset.url = HOMEPAGE
    dataset.homepage = HOMEPAGE
    dataset.paper_url = SOURCE_URL
    dataset.introducing_paper_id = paper.id
    dataset.introducing_paper_title = paper.title
    dataset.introduced_year = 2020
    session.flush()
    return dataset


def wire_benchmark(session: Session, task_id: int, dataset_id: int) -> None:
    metric_id = session.execute(
        text("SELECT id FROM metrics WHERE name = :name"), {"name": METRIC_NAME}
    ).scalar_one()
    session.execute(
        text(
            """
            INSERT INTO task_datasets (
                task_id, dataset_id, featured_rank, supports_harness
            )
            VALUES (:task_id, :dataset_id, NULL, FALSE)
            ON CONFLICT (task_id, dataset_id) DO UPDATE
            SET featured_rank = NULL, supports_harness = FALSE
            """
        ),
        {"task_id": task_id, "dataset_id": dataset_id},
    )
    session.execute(
        text(
            """
            DELETE FROM task_dataset_metrics
            WHERE task_id = :task_id AND dataset_id = :dataset_id
              AND metric_id <> :metric_id
            """
        ),
        {"task_id": task_id, "dataset_id": dataset_id, "metric_id": metric_id},
    )
    session.execute(
        text(
            """
            INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
            VALUES (:task_id, :dataset_id, :metric_id)
            ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING
            """
        ),
        {"task_id": task_id, "dataset_id": dataset_id, "metric_id": metric_id},
    )


def main() -> None:
    with db_manager.session_local() as session:
        task = get_task(session)
        paper = get_source_paper(session)
        session.execute(
            text(
                """
                INSERT INTO paper_tasks (paper_id, task_id, source)
                VALUES (:paper_id, :task_id, 'manual')
                ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'
                """
            ),
            {"paper_id": paper.id, "task_id": task.id},
        )

        datasets = []
        for spec in BENCHMARKS:
            dataset = ensure_dataset(session, paper, *spec)
            wire_benchmark(session, task.id, dataset.id)
            datasets.append(dataset)

        session.commit()
        for dataset in datasets:
            logger.info(
                "Ready: id=%s slug=%s source=%s metric=%s",
                dataset.id,
                dataset.slug,
                dataset.paper_url,
                METRIC_NAME,
            )


if __name__ == "__main__":
    main()
