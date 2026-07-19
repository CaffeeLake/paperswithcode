"""Import Odysseys leaderboard rows as external evaluations on model paper pages.

Scores come from the Odysseys project page (arxiv 2604.24964) and are attached
to each evaluated model's introducing paper with external=true. Wrapper agents
that drive a backbone model through a separate framework are excluded.

Run:
    uv run --env-file backend/keys.env \
        python backend/database/evaluations_setup/import_odysseys_external_evals.py
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import Evaluation as DBEvaluation, Paper, Task as DBTask
from backend.services.evaluation_service import EvaluationService
from backend.services.external_resource_service import (
    ExternalResourceInput,
    ExternalResourceService,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

ODYSSEYS_SOURCE_URL = "https://paperswithcode.co/paper/2604.24964"
TASK_SLUG = "computer-use-agents"
DATASET_SLUG = "odysseys"
BEST_METRIC = "Success Rate"

# Wrapper / framework agents that reuse a backbone model — excluded per user request.
EXCLUDED_MODELS = {
    "WebWright (GPT-5.4)",
    "BrowserCode (Opus 4.7)",
    "MACU (Qwen-3.6-27B)",
}

GEMINI_35_FLASH_PAPER = {
    "source_url": "https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-5/",
    "title": "Gemini 3.5: frontier intelligence with action",
    "abstract": (
        "Google introduces the Gemini 3.5 model family, starting with Gemini 3.5 "
        "Flash — a frontier agentic and coding model optimized for multi-step "
        "workflows and long-horizon tasks at high speed."
    ),
    "date_published": date(2026, 5, 19),
}


@dataclass(frozen=True)
class OdysseysRow:
    model_name: str
    paper_id: int | None
    perfect: float
    rubric_avg: float
    judge: float | None
    avg_steps: float
    traj_eff: float
    is_open: bool
    hf_model_url: str | None = None
    num_parameters: int | None = None


# Reproduced from https://odysseys-website.pages.dev/js/data.js (CUA rows only).
EVAL_ROWS: list[OdysseysRow] = [
    OdysseysRow(
        model_name="Claude Opus 4.6",
        paper_id=97916,
        perfect=44.5,
        rubric_avg=68.9,
        judge=37.0,
        avg_steps=81.3,
        traj_eff=1.06,
        is_open=False,
    ),
    OdysseysRow(
        model_name="Gemini 3.5 Flash",
        paper_id=None,
        perfect=48.0,
        rubric_avg=64.65,
        judge=None,
        avg_steps=80.61,
        traj_eff=1.1561,
        is_open=False,
    ),
    OdysseysRow(
        model_name="GPT-5.4",
        paper_id=97924,
        perfect=33.5,
        rubric_avg=55.4,
        judge=21.5,
        avg_steps=64.4,
        traj_eff=1.15,
        is_open=False,
    ),
    OdysseysRow(
        model_name="Claude Sonnet 4.6",
        paper_id=97925,
        perfect=31.0,
        rubric_avg=49.8,
        judge=25.0,
        avg_steps=80.4,
        traj_eff=0.79,
        is_open=False,
    ),
    OdysseysRow(
        model_name="GPT-5.4 Mini",
        paper_id=97924,
        perfect=10.5,
        rubric_avg=38.4,
        judge=15.5,
        avg_steps=41.7,
        traj_eff=1.12,
        is_open=False,
    ),
    OdysseysRow(
        model_name="Qwen-3.5-VL-9B",
        paper_id=83017,
        perfect=13.5,
        rubric_avg=42.6,
        judge=18.0,
        avg_steps=78.3,
        traj_eff=0.75,
        is_open=True,
        num_parameters=9_000_000_000,
    ),
    OdysseysRow(
        model_name="Qwen-3.5-VL-4B",
        paper_id=83017,
        perfect=10.7,
        rubric_avg=42.9,
        judge=18.3,
        avg_steps=86.4,
        traj_eff=0.69,
        is_open=True,
        num_parameters=4_000_000_000,
    ),
    OdysseysRow(
        model_name="Qwen-3.5-VL-35B-A3B",
        paper_id=83017,
        perfect=6.5,
        rubric_avg=28.5,
        judge=9.5,
        avg_steps=86.1,
        traj_eff=0.42,
        is_open=True,
        num_parameters=35_000_000_000,
    ),
    OdysseysRow(
        model_name="UI-TARS-1.5-7B",
        paper_id=43067,
        perfect=1.0,
        rubric_avg=10.0,
        judge=2.0,
        avg_steps=76.6,
        traj_eff=0.23,
        is_open=True,
        hf_model_url="https://huggingface.co/ByteDance-Seed/UI-TARS-1.5-7B",
        num_parameters=7_000_000_000,
    ),
]


def _get_task_and_dataset(session: Session) -> tuple[int, int]:
    task = session.query(DBTask).filter(DBTask.slug == TASK_SLUG).one_or_none()
    if task is None:
        raise RuntimeError(f"Task {TASK_SLUG!r} not found")
    row = session.execute(
        text("SELECT id FROM datasets WHERE slug = :slug"),
        {"slug": DATASET_SLUG},
    ).fetchone()
    if row is None:
        raise RuntimeError(
            f"Dataset {DATASET_SLUG!r} not found; run add_odysseys_benchmark.py first"
        )
    return int(task.id), int(row[0])


def _ensure_external_paper(session: Session, spec: dict) -> Paper:
    existing = (
        session.query(Paper)
        .filter(
            Paper.source == "external",
            Paper.source_url == spec["source_url"],
        )
        .first()
    )
    if existing:
        return existing

    result = ExternalResourceService(session).add_external_resource(
        ExternalResourceInput(
            source_url=spec["source_url"],
            title=spec["title"],
            abstract=spec["abstract"],
            date_published=spec.get("date_published"),
        )
    )
    paper = session.query(Paper).filter(Paper.id == int(result.paper.id)).one()
    logger.info("Created external paper %r (id=%s)", spec["title"], paper.id)
    return paper


def _resolve_paper_id(session: Session, row: OdysseysRow) -> int | None:
    if row.model_name == "Gemini 3.5 Flash":
        return _ensure_external_paper(session, GEMINI_35_FLASH_PAPER).id
    return row.paper_id


def _format_score(value: float) -> str:
    rounded = round(value, 1)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.1f}"


def _methodology(row: OdysseysRow) -> str:
    parts = [
        "Odysseys perfect rubric rate from the project leaderboard "
        "(2604.24964). CUA agent via OSWorld with a 100-step budget.",
        f"Rubric average {_format_score(row.rubric_avg)}%.",
        f"Avg. steps {_format_score(row.avg_steps)}.",
        f"Trajectory efficiency {_format_score(row.traj_eff)}.",
    ]
    if row.judge is not None:
        parts.append(f"O-M2W judge {_format_score(row.judge)}%.")
    if row.model_name == "Qwen-3.5-VL-35B-A3B":
        parts.append("35B total parameters (3B active MoE).")
    return " ".join(parts)


def _delete_existing_rows(session: Session, task_id: int, dataset_id: int) -> int:
    deleted = session.execute(
        text(
            """
            DELETE FROM evaluations
            WHERE task_id = :task_id
              AND dataset_id = :dataset_id
              AND source_url = :source_url
            """
        ),
        {
            "task_id": task_id,
            "dataset_id": dataset_id,
            "source_url": ODYSSEYS_SOURCE_URL,
        },
    ).rowcount
    session.flush()
    return deleted or 0


def import_rows(
    session: Session, task_id: int, dataset_id: int
) -> tuple[int, list[str]]:
    skipped: list[str] = []
    created = 0

    for row in EVAL_ROWS:
        if row.model_name in EXCLUDED_MODELS:
            skipped.append(f"{row.model_name}: wrapper agent (excluded)")
            continue

        paper_id = _resolve_paper_id(session, row)
        if paper_id is None:
            skipped.append(f"{row.model_name}: no local paper row")
            continue

        existing = session.execute(
            text(
                """
                SELECT id FROM evaluations
                WHERE paper_id = :paper_id
                  AND task_id = :task_id
                  AND dataset_id = :dataset_id
                  AND model_name = :model_name
                  AND COALESCE(harness, '') = ''
                  AND best_metric = :best_metric
                  AND source_url = :source_url
                """
            ),
            {
                "paper_id": paper_id,
                "task_id": task_id,
                "dataset_id": dataset_id,
                "model_name": row.model_name,
                "best_metric": BEST_METRIC,
                "source_url": ODYSSEYS_SOURCE_URL,
            },
        ).first()
        if existing:
            skipped.append(f"{row.model_name}: duplicate row already exists")
            continue

        session.add(
            DBEvaluation(
                paper_id=paper_id,
                task_id=task_id,
                dataset_id=dataset_id,
                model_name=row.model_name,
                methodology=_methodology(row),
                metrics={BEST_METRIC: _format_score(row.perfect)},
                best_metric=BEST_METRIC,
                external_source_url=ODYSSEYS_SOURCE_URL,
                source_url=ODYSSEYS_SOURCE_URL,
                external=True,
                is_open=row.is_open,
                hf_model_url=row.hf_model_url,
                num_parameters=row.num_parameters,
            )
        )
        created += 1

    session.flush()
    EvaluationService(session).recalculate_ranks(
        task_id, dataset_id, metric_name=BEST_METRIC
    )
    return created, skipped


def main() -> None:
    with db_manager.session_local() as session:
        task_id, dataset_id = _get_task_and_dataset(session)
        deleted = _delete_existing_rows(session, task_id, dataset_id)
        created, skipped = import_rows(session, task_id, dataset_id)
        session.commit()
        logger.info("Deleted %d prior Odysseys external rows", deleted)
        logger.info("Created %d Odysseys external evaluation rows", created)
        if skipped:
            logger.info("Skipped %d rows:", len(skipped))
            for line in skipped:
                logger.info("  - %s", line)


if __name__ == "__main__":
    main()
