"""
Move the CountBench benchmark from `Object counting` to `Image Understanding`.

`Object counting` is a hidden, single-benchmark task that only hosts CountBench.
We want CountBench to live under the broader `Image Understanding` task instead.
After moving CountBench (its task-dataset link, the `Accuracy` leaderboard
metric, all evaluation rows, and any `paper_tasks` links pointing at the source
task), we delete the now-empty `Object counting` task.

Idempotent: every move uses ``ON CONFLICT`` and the script is a no-op once
the source task no longer exists.

Usage:
    uv run --env-file backend/keys.env python \\
        backend/database/migrations/move_countbench_to_image_understanding.py
"""

from __future__ import annotations

import sys

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.services.evaluation_service import EvaluationService


SOURCE_TASK_SLUG = "object-counting"
TARGET_TASK_SLUG = "image-understanding"
DATASET_SLUG = "countbench"


def _resolve_task_id(db, slug: str) -> int | None:
    row = db.execute(
        text("SELECT id FROM tasks WHERE slug = :slug"),
        {"slug": slug},
    ).first()
    return int(row[0]) if row else None


def _resolve_dataset_id(db, slug: str) -> int | None:
    row = db.execute(
        text("SELECT id FROM datasets WHERE slug = :slug"),
        {"slug": slug},
    ).first()
    return int(row[0]) if row else None


def _report_task_counts(db, task_id: int, label: str) -> None:
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
    children = db.execute(
        text("SELECT COUNT(*) FROM tasks WHERE parent_id = :tid"),
        {"tid": task_id},
    ).scalar()
    print(
        f"  {label:<32} id={task_id:<5} "
        f"benchmarks={benchmarks:<4} metric_triples={metric_triples:<4} "
        f"evaluations={evaluations:<4} paper_links={paper_links:<5} "
        f"children={children}"
    )


def move() -> int:
    with db_manager.session_local() as db:
        target_id = _resolve_task_id(db, TARGET_TASK_SLUG)
        if target_id is None:
            print(f"Target task '{TARGET_TASK_SLUG}' not found; aborting.")
            return 1

        source_id = _resolve_task_id(db, SOURCE_TASK_SLUG)
        if source_id is None:
            print(
                f"Source task '{SOURCE_TASK_SLUG}' not found; nothing to move."
                " Assuming a previous run already completed."
            )
            print("\nCurrent state:")
            _report_task_counts(db, target_id, f"{TARGET_TASK_SLUG} (target)")
            return 0

        if source_id == target_id:
            print(
                f"Source and target resolve to the same task id ({source_id});"
                " aborting."
            )
            return 1

        dataset_id = _resolve_dataset_id(db, DATASET_SLUG)
        if dataset_id is None:
            print(f"Dataset '{DATASET_SLUG}' not found; aborting.")
            return 1

        print("Before move:")
        _report_task_counts(db, source_id, f"{SOURCE_TASK_SLUG} (source)")
        _report_task_counts(db, target_id, f"{TARGET_TASK_SLUG} (target)")

        # Capture (dataset, metric) leaderboards we'll need to re-rank after
        # moving evaluations to the target task. Scoped to CountBench only.
        affected = db.execute(
            text(
                """
                SELECT DISTINCT dataset_id, best_metric
                FROM evaluations
                WHERE task_id = :sid
                  AND dataset_id = :did
                  AND best_metric IS NOT NULL
                """
            ),
            {"sid": source_id, "did": dataset_id},
        ).all()
        affected_leaderboards = [(int(r[0]), r[1]) for r in affected]
        print(
            f"\nAffected (dataset, metric) leaderboards to re-rank after move:"
            f" {len(affected_leaderboards)}"
        )

        print("\nMoving CountBench task_datasets link...")
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
                WHERE td.task_id = :sid AND td.dataset_id = :did
                ON CONFLICT (task_id, dataset_id) DO UPDATE
                SET supports_harness =
                        EXCLUDED.supports_harness OR task_datasets.supports_harness,
                    featured_rank =
                        COALESCE(task_datasets.featured_rank, EXCLUDED.featured_rank),
                    updated_at = NOW()
                """
            ),
            {"sid": source_id, "tid": target_id, "did": dataset_id},
        )
        deleted_td = db.execute(
            text(
                "DELETE FROM task_datasets WHERE task_id = :sid AND dataset_id = :did"
            ),
            {"sid": source_id, "did": dataset_id},
        ).rowcount
        print(f"  Deleted {deleted_td} task_datasets rows from source.")

        print("Moving CountBench task_dataset_metrics...")
        db.execute(
            text(
                """
                INSERT INTO task_dataset_metrics
                    (task_id, dataset_id, metric_id, created_at)
                SELECT :tid, tdm.dataset_id, tdm.metric_id, tdm.created_at
                FROM task_dataset_metrics tdm
                WHERE tdm.task_id = :sid AND tdm.dataset_id = :did
                ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING
                """
            ),
            {"sid": source_id, "tid": target_id, "did": dataset_id},
        )
        deleted_tdm = db.execute(
            text(
                "DELETE FROM task_dataset_metrics "
                "WHERE task_id = :sid AND dataset_id = :did"
            ),
            {"sid": source_id, "did": dataset_id},
        ).rowcount
        print(f"  Deleted {deleted_tdm} task_dataset_metrics rows from source.")

        print("Moving CountBench evaluations...")
        updated_evals = db.execute(
            text(
                """
                UPDATE evaluations
                SET task_id = :tid, updated_at = NOW()
                WHERE task_id = :sid AND dataset_id = :did
                """
            ),
            {"sid": source_id, "tid": target_id, "did": dataset_id},
        ).rowcount
        print(f"  Updated {updated_evals} evaluations rows to target task.")

        # Move any remaining paper_tasks links pointing at the source task to
        # the target. The source task is being deleted, so every paper_tasks
        # row attached to it must either be reassigned to the target or
        # dropped. Reassigning preserves the broader "this paper is about
        # Image Understanding" relationship that previously rolled up under
        # `Object counting`.
        print("Moving paper_tasks from source to target...")
        db.execute(
            text(
                """
                INSERT INTO paper_tasks (paper_id, task_id, source)
                SELECT paper_id, :tid, source
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

        # Reparent any child tasks under source to target. There should be
        # none for `Object counting`, but keep this guard so the script
        # remains safe if the taxonomy changes before the migration runs.
        reparented = db.execute(
            text(
                """
                UPDATE tasks SET parent_id = :tid, updated_at = NOW()
                WHERE parent_id = :sid
                """
            ),
            {"sid": source_id, "tid": target_id},
        ).rowcount
        if reparented:
            print(f"  Reparented {reparented} child tasks under source.")

        # Hard guard: only delete the source task once nothing references it.
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
                    f"referencing source task id {source_id}; aborting "
                    "before deleting the task row."
                )

        print("Deleting source task row...")
        db.execute(
            text("DELETE FROM tasks WHERE id = :sid"),
            {"sid": source_id},
        )

        db.commit()
        print("Committed move transaction.")

        if affected_leaderboards:
            print(
                f"\nRecalculating ranks for {len(affected_leaderboards)} "
                "(target, dataset, metric) leaderboards..."
            )
            service = EvaluationService(db)
            for did, metric_name in affected_leaderboards:
                updated = service.recalculate_ranks(
                    task_id=target_id,
                    dataset_id=did,
                    metric_name=metric_name,
                )
                print(
                    f"  dataset={did:<5} metric={metric_name!s:<30}"
                    f" rows_updated={updated}"
                )

        print("\nAfter move:")
        _report_task_counts(db, target_id, f"{TARGET_TASK_SLUG} (target)")
        still_there = _resolve_task_id(db, SOURCE_TASK_SLUG)
        if still_there is not None:
            raise RuntimeError(
                f"Source task '{SOURCE_TASK_SLUG}' still present after move"
                f" (id={still_there})"
            )
        print(f"  {SOURCE_TASK_SLUG} (source)         gone")

    return 0


def main() -> int:
    print("=" * 70)
    print("Move `CountBench` from `object-counting` to `image-understanding`")
    print("=" * 70)
    return move()


if __name__ == "__main__":
    sys.exit(main())
