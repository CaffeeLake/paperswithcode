"""Import FrontierSWE leaderboard rows as external evaluations on model paper pages.

Fetches mean@5 leaderboard data from https://www.frontierswe.com/ and attaches
each model's FrontierSWE score to its introducing paper with external=true.

Run:
    uv run --env-file backend/keys.env \
        python backend/database/evaluations_setup/import_frontierswe_external_evals.py
"""

from __future__ import annotations

import json
import logging
import re
import urllib.request
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import Evaluation as DBEvaluation, Task as DBTask
from backend.services.evaluation_service import EvaluationService

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

FRONTIERSWE_SOURCE_URL = "https://www.frontierswe.com/"
TASK_SLUG = "coding-agents"
DATASET_SLUG = "frontierswe"
RANK_METRIC = "Average Rank"
DOMINANCE_METRIC = "Dominance"

# FrontierSWE model label -> local paper id for the evaluated release.
MODEL_PAPER_IDS: dict[str, int] = {
    "Claude Fable 5": 98110,
    "Claude Opus 4.8": 97913,
    "GLM-5.2": 98456,
    "GPT-5.5": 97922,
    "Claude Opus 4.7": 97914,
    "Claude Opus 4.6": 97916,
    "GPT-5.4": 97924,
    "Composer 2.5": 57059,
    "Gemini 3.1 Pro": 97943,
    "GLM-5.1": 83636,
    "DeepSeek V4 Pro": 98780,
    "Kimi K2.6": 82965,
    "Kimi K2.5": 55657,
    "Qwen3.6-Plus": 83277,
}

# Closed-source API models on FrontierSWE (no public weights for the evaluated row).
CLOSED_MODELS = {
    "Claude Fable 5",
    "Claude Opus 4.8",
    "Claude Opus 4.7",
    "Claude Opus 4.6",
    "GPT-5.5",
    "GPT-5.4",
    "Gemini 3.1 Pro",
    "Composer 2.5",
    "Qwen3.6-Plus",
}


@dataclass
class LeaderboardEntry:
    model: str
    harness: str
    overall: float
    dominance: float
    implementation: float
    performance: float
    research: float


def fetch_leaderboard_entries() -> list[LeaderboardEntry]:
    with urllib.request.urlopen(FRONTIERSWE_SOURCE_URL, timeout=60) as resp:
        html = resp.read().decode()

    scripts = re.findall(r"self\.__next_f\.push\(\[1,\"(.*?)\"\]\)", html)
    for script in scripts:
        if "entries" not in script or "Claude Fable" not in script:
            continue
        script = script.replace('\\"', '"')
        start = script.index('{"entries":')
        depth = 0
        for i, ch in enumerate(script[start:], start=start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    payload = json.loads(script[start : i + 1])
                    rows = payload["entries"]["mean"]
                    return [
                        LeaderboardEntry(
                            model=row["model"],
                            harness=row["harness"],
                            overall=float(row["overall"]),
                            dominance=float(row["dominance"]),
                            implementation=float(row["implementation"]),
                            performance=float(row["performance"]),
                            research=float(row["research"]),
                        )
                        for row in rows
                    ]

    raise RuntimeError("Could not parse FrontierSWE leaderboard from homepage HTML")


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
            f"Dataset {DATASET_SLUG!r} not found; run add_frontierswe_benchmark.py first"
        )
    return int(task.id), int(row[0])


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
            "source_url": FRONTIERSWE_SOURCE_URL,
        },
    ).rowcount
    session.flush()
    return deleted or 0


def _format_score(value: float) -> str:
    rounded = round(value, 2)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.2f}"


def import_rows(
    session: Session, task_id: int, dataset_id: int
) -> tuple[int, list[str]]:
    entries = fetch_leaderboard_entries()
    skipped: list[str] = []
    created = 0

    for entry in entries:
        paper_id = MODEL_PAPER_IDS.get(entry.model)
        if paper_id is None:
            skipped.append(f"{entry.model}: no paper mapping")
            continue

        dominance_pct = round(entry.dominance * 100, 2)
        methodology = (
            f"FrontierSWE mean@5 leaderboard (independent source). "
            f"Average rank {entry.overall:.2f} across 17 tasks; "
            f"dominance {dominance_pct:g}%; "
            f"implementation rank {entry.implementation:.2f}, "
            f"performance rank {entry.performance:.2f}, "
            f"research rank {entry.research:.2f}. "
            f"Harness: {entry.harness}."
        )
        if entry.model == "Composer 2.5":
            methodology += (
                " FrontierSWE label is Composer 2.5; attached to the Composer 2 "
                "technical report paper as the closest local release page."
            )

        existing = session.execute(
            text(
                """
                SELECT id FROM evaluations
                WHERE paper_id = :paper_id
                  AND task_id = :task_id
                  AND dataset_id = :dataset_id
                  AND model_name = :model_name
                  AND COALESCE(harness, '') = :harness
                  AND best_metric = :best_metric
                """
            ),
            {
                "paper_id": paper_id,
                "task_id": task_id,
                "dataset_id": dataset_id,
                "model_name": entry.model,
                "harness": entry.harness,
                "best_metric": RANK_METRIC,
            },
        ).first()
        if existing:
            skipped.append(f"{entry.model}: duplicate row already exists")
            continue

        session.add(
            DBEvaluation(
                paper_id=paper_id,
                task_id=task_id,
                dataset_id=dataset_id,
                model_name=entry.model,
                harness=entry.harness,
                methodology=methodology,
                metrics={
                    RANK_METRIC: _format_score(entry.overall),
                    DOMINANCE_METRIC: _format_score(dominance_pct),
                },
                best_metric=RANK_METRIC,
                external_source_url=FRONTIERSWE_SOURCE_URL,
                source_url=FRONTIERSWE_SOURCE_URL,
                external=True,
                is_open=entry.model not in CLOSED_MODELS,
            )
        )
        created += 1

    session.flush()

    eval_service = EvaluationService(session)
    eval_service.recalculate_ranks(task_id, dataset_id, metric_name=RANK_METRIC)
    eval_service.recalculate_ranks(task_id, dataset_id, metric_name=DOMINANCE_METRIC)

    return created, skipped


def main() -> None:
    with db_manager.session_local() as session:
        task_id, dataset_id = _get_task_and_dataset(session)
        deleted = _delete_existing_rows(session, task_id, dataset_id)
        created, skipped = import_rows(session, task_id, dataset_id)
        session.commit()
        logger.info("Deleted %d prior FrontierSWE rows", deleted)
        logger.info("Created %d FrontierSWE external evaluation rows", created)
        if skipped:
            logger.info("Skipped %d rows:", len(skipped))
            for line in skipped:
                logger.info("  - %s", line)


if __name__ == "__main__":
    main()
