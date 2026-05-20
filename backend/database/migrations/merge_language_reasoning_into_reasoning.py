"""
Merge the `language-reasoning` subtask into the top-level `reasoning` task.

Historically we had two separate ``Reasoning`` tasks: the top-level
``reasoning`` task (level 0, used for general CoT/RLVR-style papers) and a
``language-reasoning`` child of Language Modeling (level 1, holding the
classic NLP reasoning leaderboards such as BBH, ARC, HellaSwag, ...).

This migration unifies them onto the top-level ``reasoning`` task and
removes the child. All benchmark display links, leaderboard metric
triples, and evaluations are moved to the parent. Any stray
``paper_tasks`` or child tasks under ``language-reasoning`` are
reassigned before the row is deleted.

Idempotent: every move uses ``ON CONFLICT`` and the script is a no-op
once ``language-reasoning`` no longer exists.

Usage:
    uv run --env-file backend/keys.env python \\
        backend/database/migrations/merge_language_reasoning_into_reasoning.py
"""

from __future__ import annotations

import sys

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.services.evaluation_service import EvaluationService


SOURCE_SLUG = "language-reasoning"
TARGET_SLUG = "reasoning"


def _resolve_task_id(db, slug: str) -> int | None:
    row = db.execute(
        text("SELECT id FROM tasks WHERE slug = :slug"),
        {"slug": slug},
    ).first()
    return int(row[0]) if row else None


def _report_counts(db, task_id: int, label: str) -> None:
    benchmarks = db.execute(
        text("SELECT COUNT(*) FROM task_datasets WHERE task_id = :tid"),
        {"tid": task_id},
    ).scalar()
    metric_triples = db.execute(
        text("SELECT COUNT(*) FROM task_dataset_metrics WHERE task_id = :tid"),
        {"tid": task_id},
    ).scalar()
    evaluations = db.execute(
        text("SELECT COUNT(*) FROM evaluations WHERE task_id = :tid"),
        {"tid": task_id},
    ).scalar()
    paper_links = db.execute(
        text("SELECT COUNT(*) FROM paper_tasks WHERE task_id = :tid"),
        {"tid": task_id},
    ).scalar()
    print(
        f"  {label:<28} id={task_id:<5} "
        f"benchmarks={benchmarks:<4} metric_triples={metric_triples:<4} "
        f"evaluations={evaluations:<4} paper_links={paper_links}"
    )


def merge() -> int:
    with db_manager.session_local() as db:
        source_id = _resolve_task_id(db, SOURCE_SLUG)
        target_id = _resolve_task_id(db, TARGET_SLUG)

        if target_id is None:
            print(f"Target task '{TARGET_SLUG}' not found; aborting.")
            return 1

        if source_id is None:
            print(
                f"Source task '{SOURCE_SLUG}' not found; nothing to merge."
                " Assuming a previous run already completed."
            )
            print("\nCurrent state:")
            _report_counts(db, target_id, f"{TARGET_SLUG} (target)")
            return 0

        if source_id == target_id:
            print(
                f"Source and target resolve to the same task id ({source_id});"
                " aborting."
            )
            return 1

        print("Before merge:")
        _report_counts(db, source_id, f"{SOURCE_SLUG} (source)")
        _report_counts(db, target_id, f"{TARGET_SLUG} (target)")

        affected = db.execute(
            text(
                """
                SELECT DISTINCT dataset_id, best_metric
                FROM evaluations
                WHERE task_id = :sid AND best_metric IS NOT NULL
                """
            ),
            {"sid": source_id},
        ).all()
        affected_leaderboards = [(int(r[0]), r[1]) for r in affected]
        print(
            f"\nAffected (dataset, metric) leaderboards to re-rank after move:"
            f" {len(affected_leaderboards)}"
        )

        print("\nMoving task_datasets...")
        db.execute(
            text(
                """
                INSERT INTO task_datasets
                    (task_id, dataset_id, featured_rank, supports_harness,
                     created_at, updated_at)
                SELECT
                    :tid,
                    td.dataset_id,
                    td.featured_rank,
                    td.supports_harness,
                    td.created_at,
                    NOW()
                FROM task_datasets td
                WHERE td.task_id = :sid
                ON CONFLICT (task_id, dataset_id) DO UPDATE
                SET supports_harness =
                        EXCLUDED.supports_harness OR task_datasets.supports_harness,
                    featured_rank =
                        COALESCE(task_datasets.featured_rank, EXCLUDED.featured_rank),
                    updated_at = NOW()
                """
            ),
            {"sid": source_id, "tid": target_id},
        )
        deleted_td = db.execute(
            text("DELETE FROM task_datasets WHERE task_id = :sid"),
            {"sid": source_id},
        ).rowcount
        print(f"  Deleted {deleted_td} task_datasets rows from source.")

        print("Moving task_dataset_metrics...")
        db.execute(
            text(
                """
                INSERT INTO task_dataset_metrics
                    (task_id, dataset_id, metric_id, created_at)
                SELECT :tid, tdm.dataset_id, tdm.metric_id, tdm.created_at
                FROM task_dataset_metrics tdm
                WHERE tdm.task_id = :sid
                ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING
                """
            ),
            {"sid": source_id, "tid": target_id},
        )
        deleted_tdm = db.execute(
            text("DELETE FROM task_dataset_metrics WHERE task_id = :sid"),
            {"sid": source_id},
        ).rowcount
        print(f"  Deleted {deleted_tdm} task_dataset_metrics rows from source.")

        print("Moving evaluations...")
        updated_evals = db.execute(
            text(
                """
                UPDATE evaluations
                SET task_id = :tid, updated_at = NOW()
                WHERE task_id = :sid
                """
            ),
            {"sid": source_id, "tid": target_id},
        ).rowcount
        print(f"  Updated {updated_evals} evaluations rows to target task.")

        print("Moving paper_tasks (if any)...")
        db.execute(
            text(
                """
                INSERT INTO paper_tasks (paper_id, task_id)
                SELECT paper_id, :tid
                FROM paper_tasks
                WHERE task_id = :sid
                ON CONFLICT (paper_id, task_id) DO NOTHING
                """
            ),
            {"sid": source_id, "tid": target_id},
        )
        deleted_pt = db.execute(
            text("DELETE FROM paper_tasks WHERE task_id = :sid"),
            {"sid": source_id},
        ).rowcount
        print(f"  Deleted {deleted_pt} paper_tasks rows from source.")

        print("Reparenting any child tasks under source to target...")
        reparented = db.execute(
            text(
                """
                UPDATE tasks SET parent_id = :tid, updated_at = NOW()
                WHERE parent_id = :sid
                """
            ),
            {"sid": source_id, "tid": target_id},
        ).rowcount
        print(f"  Reparented {reparented} child tasks.")

        print("Deleting source task row...")
        db.execute(
            text("DELETE FROM tasks WHERE id = :sid"),
            {"sid": source_id},
        )

        for table, column in (
            ("task_datasets", "task_id"),
            ("task_dataset_metrics", "task_id"),
            ("evaluations", "task_id"),
            ("paper_tasks", "task_id"),
            ("tasks", "parent_id"),
        ):
            leftover = db.execute(
                text(f"SELECT COUNT(*) FROM {table} WHERE {column} = :sid"),
                {"sid": source_id},
            ).scalar()
            if leftover:
                raise RuntimeError(
                    f"Found {leftover} leftover rows in {table}.{column} "
                    f"referencing source task id {source_id}"
                )

        db.commit()
        print("Committed merge transaction.")

        if affected_leaderboards:
            print(
                f"\nRecalculating ranks for {len(affected_leaderboards)} "
                "(target, dataset, metric) leaderboards..."
            )
            service = EvaluationService(db)
            for dataset_id, metric_name in affected_leaderboards:
                updated = service.recalculate_ranks(
                    task_id=target_id,
                    dataset_id=dataset_id,
                    metric_name=metric_name,
                )
                print(
                    f"  dataset={dataset_id:<5} metric={metric_name!s:<30}"
                    f" rows_updated={updated}"
                )

        print("\nAfter merge:")
        _report_counts(db, target_id, f"{TARGET_SLUG} (target)")
        still_there = _resolve_task_id(db, SOURCE_SLUG)
        if still_there is not None:
            raise RuntimeError(
                f"Source task '{SOURCE_SLUG}' still present after merge"
                f" (id={still_there})"
            )
        print(f"  {SOURCE_SLUG} (source)        gone")

    return 0


def main() -> int:
    print("=" * 70)
    print("Merge `language-reasoning` into `reasoning`")
    print("=" * 70)
    return merge()


if __name__ == "__main__":
    sys.exit(main())
