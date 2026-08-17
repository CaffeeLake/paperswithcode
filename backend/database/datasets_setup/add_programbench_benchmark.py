"""Wire ProgramBench into the Coding Agents task.

ProgramBench evaluates whether coding agents can rebuild full software projects
from a compiled binary and documentation alone. The introducing paper is
arxiv:2605.03546.

Run:
    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/add_programbench_benchmark.py
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.database.papers_setup.add_missing_dataset_papers import fetch_and_add_paper
from backend.models.database import (
    Dataset as DBDataset,
)
from backend.models.database import (
    Evaluation as DBEvaluation,
)
from backend.models.database import (
    Metric as DBMetric,
)
from backend.models.database import (
    Paper as DBPaper,
)
from backend.models.database import (
    Task as DBTask,
)
from backend.services.arxiv_service import ArxivService
from backend.services.evaluation_service import EvaluationService
from backend.services.paper_service import PaperService

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

PROGRAMBENCH_ARXIV_ID = "2605.03546"
TASK_SLUG = "coding-agents"
DATASET_NAME = "ProgramBench"
DATASET_SLUG = "programbench"
DATASET_FULL_NAME = "ProgramBench"
DATASET_HOMEPAGE = "https://programbench.com/"
DATASET_GITHUB = "https://github.com/facebookresearch/ProgramBench"
PAPER_URL = f"https://paperswithcode.co/paper/{PROGRAMBENCH_ARXIV_ID}"

DATASET_DESCRIPTION = (
    "ProgramBench measures whether software engineering agents can architect and "
    "implement a complete codebase from scratch given only a compiled binary and "
    "its documentation. Agents choose the language, design abstractions, write "
    "source code, and produce a build script; solutions pass only if all "
    "agent-driven fuzzing behavioral tests match the reference executable. The "
    "benchmark spans 200 tasks from compact CLI tools to large systems such as "
    "FFmpeg, SQLite, and the PHP interpreter."
)
DATASET_SHORT_DESCRIPTION = (
    "200-task benchmark for rebuilding programs from binaries and docs only."
)

PRIMARY_METRIC_NAME = "Resolved"
ALMOST_RESOLVED_METRIC_NAME = "Almost Resolved"
AVERAGE_PASS_RATE_METRIC_NAME = "Average Test Pass Rate"
METRICS = {
    PRIMARY_METRIC_NAME: {
        "full_name": "Fully Resolved Programs",
        "description": (
            "Percentage of ProgramBench tasks whose reconstructed program passes "
            "every hidden behavioral test. This is ProgramBench's primary metric."
        ),
    },
    ALMOST_RESOLVED_METRIC_NAME: {
        "full_name": "Almost Resolved Programs",
        "description": (
            "Percentage of ProgramBench tasks whose reconstructed program passes "
            "at least 95% of hidden behavioral tests."
        ),
    },
    AVERAGE_PASS_RATE_METRIC_NAME: {
        "full_name": "Average Hidden-Test Pass Rate",
        "description": (
            "Average percentage of hidden behavioral tests passed across the "
            "evaluated ProgramBench tasks. This diagnostic is not the primary "
            "fully-resolved metric."
        ),
    },
}

ANTHROPIC_VARIANT_NAME = "ProgramBench Golden 166 (5 Episodes)"
ANTHROPIC_VARIANT_SLUG = "programbench-golden-166-five-episodes"
ANTHROPIC_VARIANT_SOURCE_URL = "https://www.anthropic.com/claude-opus-5-system-card"
ANTHROPIC_VARIANT_DESCRIPTION = (
    "Anthropic's ProgramBench protocol excludes 34 tasks whose reference binary "
    "scores below 0.9 on the hidden test suite, leaving 166 golden tasks. Each "
    "model continues the same codebase across five episodes with a fresh context "
    "budget of up to 1M tokens per episode. Results are average hidden-test pass "
    "rates and are not comparable to ProgramBench's fully-resolved percentage."
)


async def _ensure_paper(session: Session) -> DBPaper:
    paper = (
        session.query(DBPaper)
        .filter(
            DBPaper.arxiv_id == PROGRAMBENCH_ARXIV_ID,
            DBPaper.is_latest_version,
        )
        .one_or_none()
    )
    if paper is not None:
        logger.info("Reusing paper id=%s title=%r", paper.id, paper.title)
        return paper

    arxiv_service = ArxivService()
    paper_service = PaperService(session)
    paper = await fetch_and_add_paper(
        arxiv_service, paper_service, PROGRAMBENCH_ARXIV_ID
    )
    if paper is None:
        raise RuntimeError(
            f"Failed to import ProgramBench paper {PROGRAMBENCH_ARXIV_ID}"
        )
    return paper


def _get_task(session: Session) -> DBTask:
    task = session.query(DBTask).filter(DBTask.slug == TASK_SLUG).one_or_none()
    if task is None:
        raise RuntimeError(f"Task slug={TASK_SLUG!r} not found")
    return task


def _ensure_dataset(session: Session, paper: DBPaper) -> DBDataset:
    dataset = (
        session.query(DBDataset).filter(DBDataset.slug == DATASET_SLUG).one_or_none()
    )
    if dataset is None:
        dataset = DBDataset(
            name=DATASET_NAME,
            slug=DATASET_SLUG,
            full_name=DATASET_FULL_NAME,
            description=DATASET_DESCRIPTION,
            short_description=DATASET_SHORT_DESCRIPTION,
            url=DATASET_GITHUB,
            homepage=DATASET_HOMEPAGE,
            paper_url=PAPER_URL,
            introducing_paper_id=paper.id,
            introducing_paper_title=paper.title,
            introduced_year=2026,
        )
        session.add(dataset)
        session.flush()
        logger.info("Created dataset %r (id=%s)", dataset.name, dataset.id)
        return dataset

    dataset.full_name = DATASET_FULL_NAME
    dataset.description = DATASET_DESCRIPTION
    dataset.short_description = DATASET_SHORT_DESCRIPTION
    dataset.url = DATASET_GITHUB
    dataset.homepage = DATASET_HOMEPAGE
    dataset.paper_url = PAPER_URL
    dataset.introducing_paper_id = paper.id
    dataset.introducing_paper_title = paper.title
    dataset.introduced_year = dataset.introduced_year or 2026
    session.flush()
    logger.info("Updated dataset %r (id=%s)", dataset.name, dataset.id)
    return dataset


def _ensure_metrics(session: Session) -> dict[str, int]:
    metric_ids: dict[str, int] = {}
    for name, metadata in METRICS.items():
        metric = session.query(DBMetric).filter(DBMetric.name == name).one_or_none()
        if metric is None:
            metric = DBMetric(
                name=name,
                direction="higher_is_better",
                scale="0-100",
            )
            session.add(metric)
        metric.full_name = metadata["full_name"]
        metric.direction = "higher_is_better"
        metric.scale = "0-100"
        metric.description = metadata["description"]
        session.flush()
        metric_ids[name] = metric.id
    return metric_ids


def _ensure_anthropic_variant(
    session: Session, parent: DBDataset, source_paper: DBPaper
) -> DBDataset:
    dataset = (
        session.query(DBDataset)
        .filter(DBDataset.slug == ANTHROPIC_VARIANT_SLUG)
        .one_or_none()
    )
    if dataset is None:
        dataset = DBDataset(name=ANTHROPIC_VARIANT_NAME, slug=ANTHROPIC_VARIANT_SLUG)
        session.add(dataset)
    dataset.name = ANTHROPIC_VARIANT_NAME
    dataset.full_name = ANTHROPIC_VARIANT_NAME
    dataset.description = ANTHROPIC_VARIANT_DESCRIPTION
    dataset.short_description = (
        "Anthropic's 166-task ProgramBench protocol with five sequential episodes."
    )
    dataset.url = ANTHROPIC_VARIANT_SOURCE_URL
    dataset.homepage = ANTHROPIC_VARIANT_SOURCE_URL
    dataset.parent_dataset_id = parent.id
    dataset.variant_type = "variant"
    dataset.split_name = "Golden 166 / 5 episodes"
    dataset.introducing_paper_id = source_paper.id
    dataset.introducing_paper_title = source_paper.title
    dataset.paper_url = f"https://paperswithcode.co/paper/{source_paper.id}"
    dataset.introduced_year = 2026
    session.flush()
    return dataset


def _migrate_evaluations(
    session: Session, main_dataset_id: int, variant_dataset_id: int
) -> None:
    episode_five = (
        session.query(DBEvaluation)
        .filter(
            DBEvaluation.dataset_id == main_dataset_id,
            DBEvaluation.model_name == "Claude Opus 5 (episode 5)",
            DBEvaluation.external_source_url == ANTHROPIC_VARIANT_SOURCE_URL,
        )
        .one_or_none()
    )
    if episode_five is not None:
        value = (episode_five.metrics or {}).get(
            AVERAGE_PASS_RATE_METRIC_NAME,
            (episode_five.metrics or {}).get("Accuracy"),
        )
        if value is None:
            raise RuntimeError("Anthropic ProgramBench row has no pass-rate value")
        episode_five.dataset_id = variant_dataset_id
        episode_five.metrics = {AVERAGE_PASS_RATE_METRIC_NAME: value}
        episode_five.best_metric = AVERAGE_PASS_RATE_METRIC_NAME
        session.flush()

    manual_rows = (
        session.query(DBEvaluation)
        .filter(
            DBEvaluation.dataset_id == main_dataset_id,
            DBEvaluation.best_metric == "Accuracy",
            ~DBEvaluation.methodology.like(
                "Managed by the Papers with Code ProgramBench live sync.%"
            ),
        )
        .all()
    )
    for row in manual_rows:
        value = (row.metrics or {}).get("Accuracy")
        if value is None:
            raise RuntimeError(f"ProgramBench evaluation {row.id} has no Accuracy")
        row.metrics = {AVERAGE_PASS_RATE_METRIC_NAME: value}
        row.best_metric = AVERAGE_PASS_RATE_METRIC_NAME


def _link_task_dataset(session: Session, task_id: int, dataset_id: int) -> None:
    session.execute(
        text(
            """
            INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
            VALUES (:task_id, :dataset_id, TRUE)
            ON CONFLICT (task_id, dataset_id) DO UPDATE
            SET supports_harness = EXCLUDED.supports_harness
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
        paper = asyncio.run(_ensure_paper(session))
        task = _get_task(session)
        dataset = _ensure_dataset(session, paper)
        metric_ids = _ensure_metrics(session)
        opus_paper = (
            session.query(DBPaper)
            .filter(
                DBPaper.source == "external",
                DBPaper.source_url == "https://www.anthropic.com/news/claude-opus-5",
                DBPaper.is_latest_version,
            )
            .one()
        )
        variant = _ensure_anthropic_variant(session, dataset, opus_paper)
        _link_task_dataset(session, task.id, dataset.id)
        _link_task_dataset(session, task.id, variant.id)
        for metric_id in metric_ids.values():
            _link_metric(session, task.id, dataset.id, metric_id)
        _link_metric(
            session,
            task.id,
            variant.id,
            metric_ids[AVERAGE_PASS_RATE_METRIC_NAME],
        )
        _migrate_evaluations(session, dataset.id, variant.id)
        session.flush()
        rank_service = EvaluationService(session)
        rank_service.recalculate_ranks(
            task.id,
            dataset.id,
            metric_name=AVERAGE_PASS_RATE_METRIC_NAME,
            commit=False,
        )
        rank_service.recalculate_ranks(
            task.id,
            variant.id,
            metric_name=AVERAGE_PASS_RATE_METRIC_NAME,
            commit=False,
        )
        accuracy_id = session.execute(
            text("SELECT id FROM metrics WHERE name = 'Accuracy'")
        ).scalar_one()
        session.execute(
            text(
                """
                DELETE FROM task_dataset_metrics
                WHERE task_id = :task_id
                  AND dataset_id = :dataset_id
                  AND metric_id = :metric_id
                """
            ),
            {
                "task_id": task.id,
                "dataset_id": dataset.id,
                "metric_id": accuracy_id,
            },
        )
        _tag_source_paper(session, paper.id, task.id)
        _tag_source_paper(session, opus_paper.id, task.id)
        session.commit()
        logger.info(
            "ProgramBench ready: dataset_id=%s variant_id=%s task_id=%s paper_url=%s",
            dataset.id,
            variant.id,
            task.id,
            PAPER_URL,
        )


if __name__ == "__main__":
    main()
