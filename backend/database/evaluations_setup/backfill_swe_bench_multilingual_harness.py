"""Backfill harness values on SWE-Bench Multilingual coding-agents rows.

Run after enable_swe_bench_multilingual_harness.sql:

    uv run --env-file backend/keys.env \
        python backend/database/evaluations_setup/backfill_swe_bench_multilingual_harness.py
"""

from __future__ import annotations

import logging
import re

from sqlalchemy import select

from backend.database.connection import db_manager
from backend.models.database import Dataset, Evaluation, Task, TaskDataset
from backend.services.evaluation_service import EvaluationService

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

TASK_SLUG = "coding-agents"
MULTILINGUAL_SLUG = "swe-bench-multilingual"
VERIFIED_SLUG = "swe-bench-verified"

# Normalize source spellings to the values already used on SWE-Bench Verified.
HARNESS_ALIASES = {
    "mini-swe-agent": "MiniSWE-Agent",
    "miniswe-agent": "MiniSWE-Agent",
    "swe-agent": "SWE-Agent",
    "openhands": "OpenHands",
}


def normalize_harness(value: str) -> str:
    key = value.strip().lower()
    return HARNESS_ALIASES.get(key, value.strip())


def split_model_harness(model_name: str) -> tuple[str, str] | None:
    match = re.match(r"^(.*) \(([^)]+)\)$", model_name)
    if not match:
        return None
    base, suffix = match.group(1), match.group(2)
    if suffix.lower() == "non-thinking":
        return None
    return base, normalize_harness(suffix)


def main() -> None:
    with db_manager.session_local() as session:
        task = session.execute(select(Task).where(Task.slug == TASK_SLUG)).scalar_one()
        multilingual = session.execute(
            select(Dataset).where(Dataset.slug == MULTILINGUAL_SLUG)
        ).scalar_one()
        verified = session.execute(
            select(Dataset).where(Dataset.slug == VERIFIED_SLUG)
        ).scalar_one()

        task_dataset = session.execute(
            select(TaskDataset).where(
                TaskDataset.task_id == task.id,
                TaskDataset.dataset_id == multilingual.id,
            )
        ).scalar_one()
        if not task_dataset.supports_harness:
            task_dataset.supports_harness = True
            logger.info("Enabled supports_harness for SWE-Bench Multilingual.")

        verified_rows = (
            session.execute(
                select(Evaluation).where(
                    Evaluation.task_id == task.id,
                    Evaluation.dataset_id == verified.id,
                )
            )
            .scalars()
            .all()
        )
        verified_harness = {
            (row.paper_id, row.model_name): row.harness for row in verified_rows
        }

        multilingual_rows = (
            session.execute(
                select(Evaluation).where(
                    Evaluation.task_id == task.id,
                    Evaluation.dataset_id == multilingual.id,
                )
            )
            .scalars()
            .all()
        )

        service = EvaluationService(session)
        updated = 0
        for row in multilingual_rows:
            model_name = row.model_name or ""
            harness = row.harness

            split = split_model_harness(model_name)
            if split:
                model_name, harness = split
            elif not harness:
                harness = verified_harness.get((row.paper_id, model_name))
                if not harness:
                    harness = "Not reported"

            if row.model_name == model_name and row.harness == harness:
                continue

            service.update_evaluation(
                int(row.id),
                model_name=model_name,
                harness=harness,
                harness_set=True,
            )
            updated += 1
            logger.info(
                "Updated eval %s: model_name=%r harness=%r",
                row.id,
                model_name,
                harness,
            )

        session.commit()
        logger.info("Updated %s SWE-Bench Multilingual evaluation rows.", updated)


if __name__ == "__main__":
    main()
