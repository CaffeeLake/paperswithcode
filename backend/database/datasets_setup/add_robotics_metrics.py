#!/usr/bin/env python3
"""Phase 2 robotics metrics: wire Success Rate and Push-T coverage leaderboards.

Ensures every benchmark linked to the Robotics task has a Success Rate
leaderboard in ``task_dataset_metrics``. Push-T also gets Target Area
Coverage, the primary sim metric reported by Diffusion Policy (PLAN_ROBOTICS
labels this "Position error"; papers report max target-area coverage / IoU).

Run:

    uv run --env-file backend/keys.env \\
        python backend/database/datasets_setup/add_robotics_metrics.py
"""

from __future__ import annotations

import logging

from sqlalchemy import text

from backend.database.connection import db_manager

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ROBOTICS_TASK_SLUG = "robotics"
SUCCESS_RATE_METRIC = "Success Rate"
TARGET_AREA_COVERAGE_METRIC = "Target Area Coverage"
PUSH_T_SLUG = "push-t"

# Import-time aliases (Average Success → Success Rate) are handled in add-evals;
# no separate DB metric row is created for Average Success.


def ensure_metric(
    session,
    name: str,
    direction: str,
    full_name: str,
    scale: str,
    description: str,
) -> int:
    row = session.execute(
        text("SELECT id FROM metrics WHERE name = :name"),
        {"name": name},
    ).first()
    if row:
        return int(row[0])

    metric_id = session.execute(
        text(
            """
            INSERT INTO metrics (name, direction, full_name, scale, description)
            VALUES (:name, :direction, :full_name, :scale, :description)
            RETURNING id
            """
        ),
        {
            "name": name,
            "direction": direction,
            "full_name": full_name,
            "scale": scale,
            "description": description,
        },
    ).scalar_one()
    logger.info("Created metric %r (id=%s)", name, metric_id)
    return int(metric_id)


def wire_metric(session, task_id: int, dataset_id: int, metric_id: int) -> None:
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
    session = db_manager.session_local()
    try:
        robotics_task_id = session.execute(
            text("SELECT id FROM tasks WHERE slug = :slug"),
            {"slug": ROBOTICS_TASK_SLUG},
        ).scalar_one()

        success_rate_id = ensure_metric(
            session,
            SUCCESS_RATE_METRIC,
            "higher_is_better",
            "Success Rate",
            "0-100",
            "Fraction of episodes or tasks completed successfully.",
        )
        coverage_id = ensure_metric(
            session,
            TARGET_AREA_COVERAGE_METRIC,
            "higher_is_better",
            "Target Area Coverage",
            "0-1",
            (
                "Maximum target-area coverage (IoU) achieved during a Push-T "
                "episode; primary sim metric in Diffusion Policy."
            ),
        )

        robotics_datasets = session.execute(
            text(
                """
                SELECT d.id, d.slug, d.name
                FROM datasets d
                JOIN task_datasets td ON td.dataset_id = d.id
                WHERE td.task_id = :task_id
                ORDER BY d.name
                """
            ),
            {"task_id": robotics_task_id},
        ).fetchall()

        success_linked = 0
        coverage_linked = 0
        for dataset_id, slug, name in robotics_datasets:
            wire_metric(session, robotics_task_id, int(dataset_id), success_rate_id)
            success_linked += 1
            if slug == PUSH_T_SLUG:
                wire_metric(session, robotics_task_id, int(dataset_id), coverage_id)
                coverage_linked += 1
                logger.info(
                    "Linked %s + %s to %r",
                    SUCCESS_RATE_METRIC,
                    TARGET_AREA_COVERAGE_METRIC,
                    name,
                )

        session.commit()
        logger.info(
            "Robotics metrics ready: Success Rate on %s benchmarks, %s on Push-T",
            success_linked,
            TARGET_AREA_COVERAGE_METRIC if coverage_linked else "not linked",
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
