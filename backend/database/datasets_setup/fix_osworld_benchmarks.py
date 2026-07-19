"""Fix OSWorld benchmark hierarchy, metrics, featured ranks, and eval placement.

- Links step-budget variants (15 / 50 / 100 steps) under parent OSWorld
- Normalizes Success Rate metric casing on step-budget leaderboards
- Moves misplaced 15-step Agent S rows off the 50-step leaderboard
- Sets featured benchmark order on Computer Use Agents

Run:
    uv run --env-file backend/keys.env \\
        python backend/database/datasets_setup/fix_osworld_benchmarks.py
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import Dataset as DBDataset
from backend.services.evaluation_service import EvaluationService

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

TASK_SLUG = "computer-use-agents"
METRIC_NAME = "Success Rate"
PARENT_SLUG = "osworld"
INTRODUCING_PAPER_ID = 30246
INTRODUCING_PAPER_TITLE = (
    "OSWorld: Benchmarking Multimodal Agents for Open-Ended Tasks in "
    "Real Computer Environments"
)
PAPER_URL = "https://paperswithcode.co/paper/2404.07972"
HOMEPAGE = "https://os-world.github.io/"
HF_URL = "https://huggingface.co/datasets/xlangai/windows_osworld"

PARENT_DESCRIPTION = (
    "OSWorld is a benchmark of 369 computer tasks involving real web and desktop "
    "apps in open domains, OS file I/O, and workflows spanning multiple applications. "
    "Results are reported on separate leaderboards by step budget (15, 50, or 100 "
    "max steps). OSWorld-Verified is a separate stabilized re-release with its own "
    "leaderboard."
)

STEP_VARIANTS: list[dict[str, str]] = [
    {
        "slug": "osworld-15-steps",
        "name": "OSWorld (15 steps)",
        "split_name": "15 steps",
        "description": (
            "OSWorld online evaluation with a 15-step action budget on the standard "
            "369-task Ubuntu benchmark. Common for quick-scaling and grounding ablations."
        ),
    },
    {
        "slug": "osworld-50-steps",
        "name": "OSWorld (50 steps)",
        "split_name": "50 steps",
        "description": (
            "OSWorld online evaluation with a 50-step action budget on the standard "
            "369-task Ubuntu benchmark. The most commonly reported step budget in "
            "2024–2025 computer-use agent papers."
        ),
    },
    {
        "slug": "osworld-100-steps",
        "name": "OSWorld (100 steps)",
        "split_name": "100 steps",
        "description": (
            "OSWorld online evaluation with a 100-step action budget on the 361-task "
            "nogdrive subset used in recent scaling papers (eight multi-app Google "
            "Drive tasks excluded)."
        ),
    },
]

# OSWorld step-budget slugs — featured_rank is intentionally left NULL so the
# task page orders benchmarks by leaderboard entry count (paper_count).
OSWORLD_STEP_SLUGS = (
    "osworld",
    "osworld-verified",
    "osworld-15-steps",
    "osworld-50-steps",
    "osworld-100-steps",
)

# UI-TARS 15-step row currently lives on generic `osworld`.
MOVE_UI_TARS_15_STEP_EVAL_ID = 11346

# JEDI 51.0% is the 100-step number in Agent S3 Table 1; 50-step is imported separately.
MOVE_TO_100_STEP_EVAL_IDS = [796]


def _get_task_id(session: Session) -> int:
    return session.execute(
        text("SELECT id FROM tasks WHERE slug = :slug"),
        {"slug": TASK_SLUG},
    ).scalar_one()


def _get_metric_id(session: Session) -> int:
    return session.execute(
        text("SELECT id FROM metrics WHERE name = :n"),
        {"n": METRIC_NAME},
    ).scalar_one()


def _ensure_parent(session: Session) -> DBDataset:
    parent = (
        session.query(DBDataset).filter(DBDataset.slug == PARENT_SLUG).one_or_none()
    )
    if parent is None:
        raise RuntimeError(f"Parent dataset {PARENT_SLUG!r} not found")

    parent.full_name = INTRODUCING_PAPER_TITLE
    parent.description = PARENT_DESCRIPTION
    parent.short_description = (
        "Real computer-environment tasks; see step-budget leaderboards for rankings."
    )
    parent.homepage = HOMEPAGE
    parent.hf_url = HF_URL
    parent.introducing_paper_id = INTRODUCING_PAPER_ID
    parent.introducing_paper_title = INTRODUCING_PAPER_TITLE
    parent.paper_url = PAPER_URL
    parent.introduced_year = 2024
    parent.parent_dataset_id = None
    parent.variant_type = None
    parent.split_name = None
    session.flush()
    logger.info("Updated parent dataset %r (id=%s)", parent.name, parent.id)
    return parent


def _ensure_step_variant(
    session: Session,
    parent: DBDataset,
    *,
    slug: str,
    name: str,
    split_name: str,
    description: str,
) -> DBDataset:
    dataset = session.query(DBDataset).filter(DBDataset.slug == slug).one_or_none()
    if dataset is None:
        dataset = DBDataset(
            name=name,
            slug=slug,
            full_name=INTRODUCING_PAPER_TITLE,
            description=description,
            short_description=description.split(".")[0] + ".",
            homepage=parent.homepage,
            hf_url=parent.hf_url,
            paper_url=parent.paper_url,
            introducing_paper_id=parent.introducing_paper_id,
            introducing_paper_title=parent.introducing_paper_title,
            introduced_year=parent.introduced_year,
            parent_dataset_id=parent.id,
            variant_type="split",
            split_name=split_name,
        )
        session.add(dataset)
        session.flush()
        logger.info("Created step variant %r (id=%s)", dataset.name, dataset.id)
        return dataset

    dataset.name = name
    dataset.description = description
    dataset.short_description = description.split(".")[0] + "."
    dataset.full_name = INTRODUCING_PAPER_TITLE
    dataset.parent_dataset_id = parent.id
    dataset.variant_type = "split"
    dataset.split_name = split_name
    dataset.homepage = parent.homepage
    dataset.hf_url = parent.hf_url
    dataset.paper_url = parent.paper_url
    dataset.introducing_paper_id = parent.introducing_paper_id
    dataset.introducing_paper_title = parent.introducing_paper_title
    dataset.introduced_year = parent.introduced_year
    session.flush()
    logger.info("Updated step variant %r (id=%s)", dataset.name, dataset.id)
    return dataset


def _ensure_task_links(
    session: Session, task_id: int, dataset_id: int, metric_id: int
) -> None:
    session.execute(
        text(
            "INSERT INTO task_datasets (task_id, dataset_id, supports_harness) "
            "VALUES (:t, :d, FALSE) ON CONFLICT (task_id, dataset_id) DO NOTHING"
        ),
        {"t": task_id, "d": dataset_id},
    )
    session.execute(
        text(
            "INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id) "
            "VALUES (:t, :d, :m) ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING"
        ),
        {"t": task_id, "d": dataset_id, "m": metric_id},
    )


def _normalize_metric_casing(session: Session, dataset_ids: list[int]) -> int:
    result = session.execute(
        text(
            """
            UPDATE evaluations
            SET metrics = (metrics - 'Success rate') || jsonb_build_object(
                    'Success Rate',
                    trim(metrics->>'Success rate')
                ),
                best_metric = CASE
                    WHEN best_metric = 'Success rate' THEN 'Success Rate'
                    ELSE best_metric
                END,
                updated_at = CURRENT_TIMESTAMP
            WHERE dataset_id = ANY(:dataset_ids)
              AND metrics ? 'Success rate'
            """
        ),
        {"dataset_ids": dataset_ids},
    )
    return result.rowcount or 0


def _fix_existing_50_step_rows(session: Session, service: EvaluationService) -> None:
    fixes = [
        {
            "id": 60,
            "model_name": "Agent S3 w/ bBoN (N=10) w/ GPT-5",
            "methodology": (
                "OSWorld 361-task nogdrive subset, 50-step budget. Behavior Best-of-N "
                "(N=10) over Agent S3 rollouts. Source: arXiv 2510.02250 Table 1."
            ),
        },
        {
            "id": 61,
            "methodology": (
                "OSWorld 369-task benchmark, 50-step budget, screenshot-only. "
                "Source: arXiv 2504.00906 Table 1."
            ),
        },
        {
            "id": 62,
            "methodology": (
                "OSWorld 369-task benchmark, 50-step budget, screenshot-only. "
                "Source: arXiv 2504.00906 Table 1."
            ),
        },
        {
            "id": 11347,
            "methodology": (
                "Screenshot-only OSWorld online evaluation, 50-step budget, averaged "
                "over 3 runs. UI-TARS-DPO variant. Source: arXiv 2501.12326 Table 9."
            ),
        },
    ]
    for row in fixes:
        eval_id = row.pop("id")
        service.update_evaluation(evaluation_id=eval_id, **row)


def _move_evaluations(
    session: Session,
    service: EvaluationService,
    *,
    eval_ids: list[int],
    dataset_id: int,
    methodology_suffix: str,
) -> None:
    for eval_id in eval_ids:
        existing = session.execute(
            text("SELECT methodology FROM evaluations WHERE id = :id"),
            {"id": eval_id},
        ).scalar_one_or_none()
        methodology = existing or ""
        if methodology_suffix not in methodology:
            methodology = (
                f"{methodology.strip()} {methodology_suffix}".strip()
                if methodology
                else methodology_suffix
            )
        service.update_evaluation(
            evaluation_id=eval_id,
            dataset_id=dataset_id,
            best_metric=METRIC_NAME,
            methodology=methodology,
        )
        logger.info("Moved evaluation %s -> dataset_id=%s", eval_id, dataset_id)


def _clear_osworld_featured_ranks(session: Session, task_id: int) -> None:
    session.execute(
        text(
            """
            UPDATE task_datasets td
            SET featured_rank = NULL,
                updated_at = CURRENT_TIMESTAMP
            FROM datasets d
            WHERE td.dataset_id = d.id
              AND td.task_id = :task_id
              AND d.slug = ANY(:slugs)
            """
        ),
        {"task_id": task_id, "slugs": list(OSWORLD_STEP_SLUGS)},
    )


def main() -> None:
    session = db_manager.session_local()
    try:
        task_id = _get_task_id(session)
        metric_id = _get_metric_id(session)
        parent = _ensure_parent(session)

        step_datasets: dict[str, DBDataset] = {}
        for spec in STEP_VARIANTS:
            dataset = _ensure_step_variant(session, parent, **spec)
            _ensure_task_links(session, task_id, dataset.id, metric_id)
            step_datasets[spec["slug"]] = dataset

        _ensure_task_links(session, task_id, parent.id, metric_id)
        _clear_osworld_featured_ranks(session, task_id)
        session.commit()

        service = EvaluationService(session)
        step_ids = [d.id for d in step_datasets.values()]
        fixed = _normalize_metric_casing(session, step_ids)
        logger.info("Normalized Success rate -> Success Rate on %s rows", fixed)

        _fix_existing_50_step_rows(session, service)
        _move_evaluations(
            session,
            service,
            eval_ids=[63, 64],
            dataset_id=step_datasets["osworld-15-steps"].id,
            methodology_suffix="15-step budget. Source: arXiv 2504.00906 Table 1.",
        )
        _move_evaluations(
            session,
            service,
            eval_ids=[MOVE_UI_TARS_15_STEP_EVAL_ID],
            dataset_id=step_datasets["osworld-15-steps"].id,
            methodology_suffix="15-step budget. Source: arXiv 2501.12326 Table 9.",
        )
        _move_evaluations(
            session,
            service,
            eval_ids=MOVE_TO_100_STEP_EVAL_IDS,
            dataset_id=step_datasets["osworld-100-steps"].id,
            methodology_suffix="100-step budget. Source: arXiv 2510.02250 Table 1.",
        )

        for slug, dataset in step_datasets.items():
            service.recalculate_ranks(task_id, dataset.id, metric_name=METRIC_NAME)
            count = session.execute(
                text("SELECT COUNT(*) FROM evaluations WHERE dataset_id = :d"),
                {"d": dataset.id},
            ).scalar_one()
            logger.info("%s: %s evaluations", slug, count)

        session.commit()
        logger.info("OSWorld benchmark fix complete.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
