"""
Run the Language Modeling subtasks migration and recalculate leaderboard ranks.

This script applies `add_language_modeling_subtasks.sql` and then walks every
`(task_id, dataset_id, best_metric)` triple touched by the move and asks the
evaluation service to recalculate `best_rank` so the new child-task
leaderboards stay correct.

Idempotent: the SQL uses `ON CONFLICT` and only rewrites rows that still live
on the parent Language Modeling task. Re-running the script after a successful
migration is a no-op for the SQL step and recalculates ranks for the (now)
child-task leaderboards based on the same dataset slug list.

Usage:
    uv run --env-file backend/keys.env python \
        backend/database/migrations/run_add_language_modeling_subtasks.py
"""

from pathlib import Path
import sys

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.services.evaluation_service import EvaluationService


SQL_FILE = Path(__file__).parent / "add_language_modeling_subtasks.sql"


SUBTASK_SLUGS = (
    "world-knowledge",
    "long-context",
    "instruction-following",
    "math",
    "language-reasoning",
    "coding",
    "safety-and-grounding",
    "classic-language-modeling",
)


def apply_sql_migration() -> None:
    """Run the multi-statement SQL file via the raw psycopg2 connection.

    SQLAlchemy's `exec_driver_sql` parameter handling rejects some PL/pgSQL
    blocks in the file, so we reach for the underlying DBAPI connection,
    which executes the script as a single text payload.
    """
    print(f"Applying SQL migration: {SQL_FILE.name}")
    sql = SQL_FILE.read_text()
    raw = db_manager.engine.raw_connection()
    try:
        with raw.cursor() as cur:
            cur.execute(sql)
        raw.commit()
    finally:
        raw.close()
    print("SQL migration committed.")


def recalculate_subtask_ranks() -> None:
    """Recalculate ranks for every (child_task, dataset, best_metric) triple."""

    with db_manager.session_local() as db:
        rows = db.execute(
            text(
                """
                SELECT DISTINCT e.task_id, e.dataset_id, e.best_metric
                FROM evaluations e
                JOIN tasks t ON t.id = e.task_id
                WHERE t.slug = ANY(:slugs)
                  AND e.best_metric IS NOT NULL
                """
            ),
            {"slugs": list(SUBTASK_SLUGS)},
        ).all()

        if not rows:
            print("No subtask evaluations found; nothing to rank.")
            return

        print(
            f"Recalculating ranks for {len(rows)} (task, dataset, metric) leaderboards..."
        )
        service = EvaluationService(db)
        for task_id, dataset_id, best_metric in rows:
            updated = service.recalculate_ranks(
                task_id=task_id,
                dataset_id=dataset_id,
                metric_name=best_metric,
            )
            print(
                f"  task={task_id:<5} dataset={dataset_id:<5} metric={best_metric!s:<25} rows_updated={updated}"
            )


def report_state() -> None:
    with db_manager.session_local() as db:
        parent = db.execute(
            text("SELECT id, name FROM tasks WHERE slug = 'language-modeling'")
        ).first()
        if not parent:
            print("Language Modeling task missing; aborting.")
            return

        children = db.execute(
            text(
                """
                SELECT t.slug, t.name, t.id,
                       (SELECT COUNT(*) FROM task_datasets td WHERE td.task_id = t.id) AS benchmarks,
                       (SELECT COUNT(*) FROM evaluations e WHERE e.task_id = t.id) AS evaluations
                FROM tasks t
                WHERE t.parent_id = :parent_id
                ORDER BY t.name
                """
            ),
            {"parent_id": parent.id},
        ).all()

        print("\nLanguage Modeling subtasks now in the database:")
        print(f"  Parent task: id={parent.id} name='{parent.name}'")
        for row in children:
            print(
                f"    - {row.slug:<28} (id={row.id})"
                f" benchmarks={row.benchmarks:<3} evaluations={row.evaluations}"
            )

        leftover_benchmarks = db.execute(
            text("SELECT COUNT(*) FROM task_datasets WHERE task_id = :p"),
            {"p": parent.id},
        ).scalar()
        leftover_evals = db.execute(
            text("SELECT COUNT(*) FROM evaluations WHERE task_id = :p"),
            {"p": parent.id},
        ).scalar()
        print(
            f"\nParent residual: benchmarks={leftover_benchmarks} evaluations={leftover_evals}"
        )


def main() -> int:
    print("=" * 70)
    print("Language Modeling Subtasks Migration")
    print("=" * 70)

    apply_sql_migration()
    recalculate_subtask_ranks()
    report_state()

    print("\nMigration complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
