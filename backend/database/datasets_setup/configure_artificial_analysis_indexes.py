"""Move the Intelligence Index to Language Modeling and add the Agentic Index.

The Intelligence Index is a general language-model composite, so it belongs on
Language Modeling. Artificial Analysis also publishes a dedicated Agentic Index
(GDPval-AA v2 and τ³-Banking), which stays on Agents.

Run:
    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/configure_artificial_analysis_indexes.py
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import (
    Dataset as DBDataset,
    Paper as DBPaper,
    Task as DBTask,
)
from backend.services.artificial_analysis_sync_service import (
    AGENTIC_INDEX,
    INTELLIGENCE_INDEX,
    METRIC_NAME,
)
from backend.services.evaluation_service import EvaluationService

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

SOURCE_PAPER_ID = 83492
AGENTS_SLUG = "agents"
LANGUAGE_MODELING_SLUG = "language-modeling"
AGENTIC_NAME = "Artificial Analysis Agentic Index"
AGENTIC_URL = "https://artificialanalysis.ai/models/capabilities/agentic"
AGENTIC_HOMEPAGE = "https://artificialanalysis.ai/methodology/capability-indices"
AGENTIC_DESCRIPTION = (
    "Composite Artificial Analysis benchmark index for agentic workflows, "
    "averaging GDPval-AA v2 and τ³-Banking to measure tool use, planning, "
    "autonomy, and complex problem solving."
)
AGENTIC_SHORT_DESCRIPTION = (
    "Composite Artificial Analysis index for agentic workflows, combining "
    "GDPval-AA v2 and τ³-Banking."
)


def _paper_url(paper: DBPaper) -> str:
    if paper.arxiv_id:
        return f"https://paperswithcode.co/paper/{paper.arxiv_id}"
    return f"https://paperswithcode.co/paper/{paper.id}"


def _get_task(session: Session, slug: str) -> DBTask:
    task = session.query(DBTask).filter(DBTask.slug == slug).one_or_none()
    if task is None:
        raise RuntimeError(f"Task slug={slug!r} not found")
    return task


def _get_metric_id(session: Session) -> int:
    row = session.execute(
        text("SELECT id FROM metrics WHERE name = :n"), {"n": METRIC_NAME}
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Metric {METRIC_NAME!r} not found")
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


def _unlink_task_dataset(session: Session, task_id: int, dataset_id: int) -> None:
    session.execute(
        text(
            """
            DELETE FROM task_dataset_metrics
            WHERE task_id = :task_id AND dataset_id = :dataset_id
            """
        ),
        {"task_id": task_id, "dataset_id": dataset_id},
    )
    session.execute(
        text(
            """
            DELETE FROM task_datasets
            WHERE task_id = :task_id AND dataset_id = :dataset_id
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
            ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'
            """
        ),
        {"paper_id": paper_id, "task_id": task_id},
    )


def _ensure_agentic_dataset(session: Session, paper: DBPaper) -> DBDataset:
    dataset = (
        session.query(DBDataset)
        .filter(DBDataset.slug == AGENTIC_INDEX.dataset_slug)
        .one_or_none()
    )
    paper_url = _paper_url(paper)
    if dataset is None:
        dataset = DBDataset(
            name=AGENTIC_NAME,
            slug=AGENTIC_INDEX.dataset_slug,
            full_name=AGENTIC_NAME,
            description=AGENTIC_DESCRIPTION,
            short_description=AGENTIC_SHORT_DESCRIPTION,
            url=AGENTIC_URL,
            homepage=AGENTIC_HOMEPAGE,
            paper_url=paper_url,
            introducing_paper_id=paper.id,
            introducing_paper_title=paper.title,
            introduced_year=2026,
        )
        session.add(dataset)
        session.flush()
        logger.info("Created dataset %r (id=%s)", dataset.name, dataset.id)
        return dataset

    dataset.name = AGENTIC_NAME
    dataset.full_name = AGENTIC_NAME
    dataset.description = AGENTIC_DESCRIPTION
    dataset.short_description = AGENTIC_SHORT_DESCRIPTION
    dataset.url = AGENTIC_URL
    dataset.homepage = AGENTIC_HOMEPAGE
    dataset.paper_url = paper_url
    dataset.introducing_paper_id = paper.id
    dataset.introducing_paper_title = paper.title
    dataset.introduced_year = dataset.introduced_year or 2026
    session.flush()
    logger.info("Updated dataset %r (id=%s)", dataset.name, dataset.id)
    return dataset


def _move_intelligence_index(
    session: Session,
    *,
    dataset_id: int,
    agents_id: int,
    language_id: int,
    metric_id: int,
) -> None:
    _link_task_dataset(session, language_id, dataset_id)
    _link_metric(session, language_id, dataset_id, metric_id)
    moved = session.execute(
        text(
            """
            UPDATE evaluations
            SET task_id = :new_task_id, updated_at = NOW()
            WHERE task_id = :old_task_id
              AND dataset_id = :dataset_id
            RETURNING id
            """
        ),
        {
            "new_task_id": language_id,
            "old_task_id": agents_id,
            "dataset_id": dataset_id,
        },
    ).fetchall()
    logger.info(
        "Moved %s Intelligence Index evaluations to language-modeling", len(moved)
    )
    session.execute(
        text(
            """
            INSERT INTO paper_tasks (paper_id, task_id, source)
            SELECT DISTINCT paper_id, :new_task_id, 'auto'
            FROM evaluations
            WHERE task_id = :new_task_id AND dataset_id = :dataset_id
            ON CONFLICT (paper_id, task_id) DO NOTHING
            """
        ),
        {"new_task_id": language_id, "dataset_id": dataset_id},
    )
    _unlink_task_dataset(session, agents_id, dataset_id)
    EvaluationService(session).recalculate_ranks(
        language_id, dataset_id, metric_name=METRIC_NAME, commit=False
    )


def main() -> None:
    with db_manager.session_local() as session:
        paper = session.get(DBPaper, SOURCE_PAPER_ID)
        if paper is None:
            raise RuntimeError(f"Source paper id={SOURCE_PAPER_ID} not found")
        agents = _get_task(session, AGENTS_SLUG)
        language = _get_task(session, LANGUAGE_MODELING_SLUG)
        intelligence = (
            session.query(DBDataset)
            .filter(DBDataset.slug == INTELLIGENCE_INDEX.dataset_slug)
            .one_or_none()
        )
        if intelligence is None:
            raise RuntimeError(
                f"Dataset slug={INTELLIGENCE_INDEX.dataset_slug!r} not found"
            )
        metric_id = _get_metric_id(session)
        _move_intelligence_index(
            session,
            dataset_id=intelligence.id,
            agents_id=agents.id,
            language_id=language.id,
            metric_id=metric_id,
        )
        _tag_source_paper(session, paper.id, language.id)
        agentic = _ensure_agentic_dataset(session, paper)
        _link_task_dataset(session, agents.id, agentic.id)
        _link_metric(session, agents.id, agentic.id, metric_id)
        _tag_source_paper(session, paper.id, agents.id)
        session.commit()
        logger.info(
            "Artificial Analysis indexes ready: intelligence=%s agentic=%s",
            intelligence.id,
            agentic.id,
        )


if __name__ == "__main__":
    main()
