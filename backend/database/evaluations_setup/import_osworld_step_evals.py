"""Import OSWorld step-budget evaluation rows from canonical paper tables.

Run after fix_osworld_benchmarks.py:

    uv run --env-file backend/keys.env \\
        python backend/database/evaluations_setup/import_osworld_step_evals.py
"""

from __future__ import annotations

import logging

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.database.evaluations_setup.evaluation_helpers import (
    get_or_create_evaluation,
)
from backend.services.evaluation_service import EvaluationService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TASK_SLUG = "computer-use-agents"
METRIC = "Success Rate"

FIFTY_STEP_SLUG = "osworld-50-steps"
HUNDRED_STEP_SLUG = "osworld-100-steps"
FIFTEEN_STEP_SLUG = "osworld-15-steps"

METH_50 = "OSWorld online evaluation, 50-step action budget. Source: {source}."
METH_100 = "OSWorld 361-task nogdrive subset, 100-step action budget. Source: {source}."
METH_15 = "OSWorld online evaluation, 15-step action budget. Source: {source}."

FIFTY_STEP_EVALS: list[dict] = [
    # Agent S3 paper (2510.02250) Table 1 — introduced models
    {
        "paper_id": 53144,
        "model_name": "Agent S3 w/ o3",
        "score": "60.6",
        "source": "arXiv 2510.02250 Table 1",
    },
    {
        "paper_id": 53144,
        "model_name": "Agent S3 w/ GPT-5 Mini",
        "score": "48.1",
        "source": "arXiv 2510.02250 Table 1",
    },
    {
        "paper_id": 53144,
        "model_name": "Agent S3 w/ GPT-5",
        "score": "61.1",
        "source": "arXiv 2510.02250 Table 1",
    },
    {
        "paper_id": 53144,
        "model_name": "Agent S3 w/ bBoN (N=10) w/ GPT-5 Mini",
        "score": "55.9",
        "source": "arXiv 2510.02250 Table 1",
    },
    # Agent S3 paper Table 1 — cited comparators on each method's paper
    {
        "paper_id": 47125,
        "model_name": "Agent S2 w/ Gemini 2.5 Pro",
        "score": "41.4",
        "source": "arXiv 2510.02250 Table 1 (Agent S2 baseline)",
    },
    {
        "paper_id": 47125,
        "model_name": "Agent S2 w/ GPT-5",
        "score": "46.3",
        "source": "arXiv 2510.02250 Table 1 (Agent S2 baseline)",
    },
    {
        "paper_id": 49038,
        "model_name": "JEDI-7B w/ o3",
        "score": "50.6",
        "source": "arXiv 2510.02250 Table 1",
    },
    {
        "paper_id": 51747,
        "model_name": "GTA1 (step-wise scaling) w/ o3",
        "score": "48.6",
        "source": "arXiv 2510.02250 Table 1",
    },
    {
        "paper_id": 52224,
        "model_name": "CoAct-1 (OAI CUA + o3 + o4-mini)",
        "score": "56.4",
        "source": "arXiv 2510.02250 Table 1",
    },
    # Agent S2 paper (2504.00906) Table 1 — 50-step column
    {
        "paper_id": 47125,
        "model_name": "OpenAI CUA",
        "score": "32.6",
        "source": "arXiv 2504.00906 Table 1",
        "is_open": False,
    },
    {
        "paper_id": 40043,
        "model_name": "Claude Computer Use w/ Claude-3.5-Sonnet",
        "score": "22.0",
        "source": "arXiv 2504.00906 Table 1",
        "is_open": False,
    },
    {
        "paper_id": 40043,
        "model_name": "Claude Computer Use w/ Claude-3.7-Sonnet",
        "score": "26.0",
        "source": "arXiv 2504.00906 Table 1",
        "is_open": False,
    },
    {
        "paper_id": 43067,
        "model_name": "UI-TARS-72B-SFT",
        "score": "18.8",
        "source": "arXiv 2504.00906 Table 1",
        "hf_model_url": "https://huggingface.co/ByteDance-Seed/UI-TARS-72B-SFT",
        "num_parameters": 73405560320,
    },
]

HUNDRED_STEP_EVALS: list[dict] = [
    {
        "paper_id": 53144,
        "model_name": "Agent S3 w/ GPT-5",
        "score": "62.6",
        "source": "arXiv 2510.02250 Table 1",
    },
    {
        "paper_id": 53144,
        "model_name": "Agent S3 w/ bBoN (N=10) w/ GPT-5",
        "score": "69.9",
        "source": "arXiv 2510.02250 Table 1",
    },
    {
        "paper_id": 53144,
        "model_name": "Agent S3 w/ bBoN (N=10) w/ GPT-5 Mini",
        "score": "60.2",
        "source": "arXiv 2510.02250 Table 1",
    },
    {
        "paper_id": 52224,
        "model_name": "CoAct-1 (OAI CUA + o3 + o4-mini)",
        "score": "59.9",
        "source": "arXiv 2510.02250 Table 1",
    },
    {
        "paper_id": 51747,
        "model_name": "GTA1 (step-wise scaling) w/ o3",
        "score": "53.1",
        "source": "arXiv 2510.02250 Table 1",
    },
    {
        "paper_id": 49038,
        "model_name": "JEDI-7B w/ o3",
        "score": "51.0",
        "source": "arXiv 2510.02250 Table 1",
    },
    {
        "paper_id": 47125,
        "model_name": "Agent S2 w/ GPT-5",
        "score": "48.8",
        "source": "arXiv 2510.02250 Table 1",
    },
]

# Open-weight checkpoints with public HF releases. Checked before closed-vendor
# heuristics so rows like "JEDI-7B w/ o3" stay open (open 7B model + API planner).
_OPEN_WEIGHT_MARKERS = ("ui-tars", "jedi-7b")

# Proprietary API / unreleased frontier backbones (add-evals closed-source rules).
_CLOSED_VENDOR_MARKERS = (
    "gpt-",
    "gpt-4o",
    "gpt-5",
    "claude",
    "gemini",
    "openai cua",
    "computer use",
    " o3",
    "o3 ",
    "w/ o3",
    "o4-mini",
    "coact-1",
    "gta1",
    "oai cua",
)


def determine_is_open(model_name: str) -> bool:
    lower = model_name.lower()
    if any(marker in lower for marker in _OPEN_WEIGHT_MARKERS):
        return True
    if any(marker in lower for marker in _CLOSED_VENDOR_MARKERS):
        return False
    return True


FIFTEEN_STEP_EVALS: list[dict] = [
    {
        "paper_id": 47125,
        "model_name": "OpenAI CUA",
        "score": "19.7",
        "source": "arXiv 2504.00906 Table 1",
        "is_open": False,
    },
    {
        "paper_id": 40043,
        "model_name": "Claude Computer Use w/ Claude-3.5-Sonnet",
        "score": "14.9",
        "source": "arXiv 2504.00906 Table 1",
        "is_open": False,
    },
    {
        "paper_id": 40043,
        "model_name": "Claude Computer Use w/ Claude-3.7-Sonnet",
        "score": "15.5",
        "source": "arXiv 2504.00906 Table 1",
        "is_open": False,
    },
    {
        "paper_id": 43067,
        "model_name": "UI-TARS-72B-SFT",
        "score": "18.7",
        "source": "arXiv 2504.00906 Table 1",
        "hf_model_url": "https://huggingface.co/ByteDance-Seed/UI-TARS-72B-SFT",
        "num_parameters": 73405560320,
    },
    {
        "paper_id": 47125,
        "model_name": "Agent S2 w/ Claude-3.5-Sonnet",
        "score": "24.5",
        "source": "arXiv 2504.00906 Table 1",
    },
    {
        "paper_id": 47125,
        "model_name": "Agent S2 w/ Claude-3.7-Sonnet",
        "score": "27.0",
        "source": "arXiv 2504.00906 Table 1",
    },
]


def _dataset_id(session, slug: str) -> int:
    return session.execute(
        text("SELECT id FROM datasets WHERE slug = :slug"),
        {"slug": slug},
    ).scalar_one()


def _task_id(session) -> int:
    return session.execute(
        text("SELECT id FROM tasks WHERE slug = :slug"),
        {"slug": TASK_SLUG},
    ).scalar_one()


def _import_rows(
    session,
    *,
    task_id: int,
    dataset_id: int,
    rows: list[dict],
    methodology_template: str,
) -> int:
    added = 0
    for row in rows:
        source = row["source"]
        kwargs = {
            "paper_id": row["paper_id"],
            "task_id": task_id,
            "dataset_id": dataset_id,
            "model_name": row["model_name"],
            "metrics": {METRIC: row["score"]},
            "best_metric": METRIC,
            "methodology": methodology_template.format(source=source),
            "is_open": row.get("is_open", determine_is_open(row["model_name"])),
        }
        if row.get("hf_model_url"):
            kwargs["hf_model_url"] = row["hf_model_url"]
        if row.get("num_parameters"):
            kwargs["num_parameters"] = row["num_parameters"]

        before = session.execute(
            text(
                """
                SELECT id FROM evaluations
                WHERE paper_id = :paper_id
                  AND task_id = :task_id
                  AND dataset_id = :dataset_id
                  AND model_name = :model_name
                  AND best_metric = :best_metric
                """
            ),
            {
                "paper_id": row["paper_id"],
                "task_id": task_id,
                "dataset_id": dataset_id,
                "model_name": row["model_name"],
                "best_metric": METRIC,
            },
        ).first()
        get_or_create_evaluation(session, **kwargs)
        after = session.execute(
            text(
                """
                SELECT id FROM evaluations
                WHERE paper_id = :paper_id
                  AND task_id = :task_id
                  AND dataset_id = :dataset_id
                  AND model_name = :model_name
                  AND best_metric = :best_metric
                """
            ),
            {
                "paper_id": row["paper_id"],
                "task_id": task_id,
                "dataset_id": dataset_id,
                "model_name": row["model_name"],
                "best_metric": METRIC,
            },
        ).first()
        if before is None and after is not None:
            added += 1
            logger.info("Added %s -> %s", row["model_name"], row["score"])
        else:
            logger.info("Updated/kept %s -> %s", row["model_name"], row["score"])
    return added


def _patch_is_open_flags(session, dataset_ids: list[int]) -> int:
    """Ensure is_open matches model_name for every row on step-budget leaderboards."""
    rows = session.execute(
        text(
            "SELECT id, model_name, is_open FROM evaluations WHERE dataset_id = ANY(:ids)"
        ),
        {"ids": dataset_ids},
    ).all()
    patched = 0
    for eval_id, model_name, current in rows:
        expected = determine_is_open(model_name)
        if current != expected:
            session.execute(
                text(
                    """
                    UPDATE evaluations
                    SET is_open = :is_open, updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                    """
                ),
                {"id": eval_id, "is_open": expected},
            )
            patched += 1
            logger.info(
                "is_open %s -> %s for %r (id=%s)",
                current,
                expected,
                model_name,
                eval_id,
            )
    return patched


def main() -> None:
    session = db_manager.session_local()
    try:
        task_id = _task_id(session)
        fifty_id = _dataset_id(session, FIFTY_STEP_SLUG)
        hundred_id = _dataset_id(session, HUNDRED_STEP_SLUG)
        fifteen_id = _dataset_id(session, FIFTEEN_STEP_SLUG)

        added_50 = _import_rows(
            session,
            task_id=task_id,
            dataset_id=fifty_id,
            rows=FIFTY_STEP_EVALS,
            methodology_template=METH_50,
        )
        added_100 = _import_rows(
            session,
            task_id=task_id,
            dataset_id=hundred_id,
            rows=HUNDRED_STEP_EVALS,
            methodology_template=METH_100,
        )
        added_15 = _import_rows(
            session,
            task_id=task_id,
            dataset_id=fifteen_id,
            rows=FIFTEEN_STEP_EVALS,
            methodology_template=METH_15,
        )

        patched = _patch_is_open_flags(session, [fifty_id, hundred_id, fifteen_id])
        logger.info("Patched is_open on %s evaluation rows", patched)

        service = EvaluationService(session)
        for dataset_id in (fifty_id, hundred_id, fifteen_id):
            service.recalculate_ranks(task_id, dataset_id, metric_name=METRIC)

        session.commit()
        logger.info(
            "Import complete: +%s (50-step), +%s (100-step), +%s (15-step)",
            added_50,
            added_100,
            added_15,
        )
        for slug, dataset_id in (
            (FIFTY_STEP_SLUG, fifty_id),
            (HUNDRED_STEP_SLUG, hundred_id),
            (FIFTEEN_STEP_SLUG, fifteen_id),
        ):
            count = session.execute(
                text("SELECT COUNT(*) FROM evaluations WHERE dataset_id = :d"),
                {"d": dataset_id},
            ).scalar_one()
            logger.info("%s: %s total evaluations", slug, count)
    finally:
        session.close()


if __name__ == "__main__":
    main()
