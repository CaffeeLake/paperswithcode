"""
Migration script to populate TASK_DATASET_METRICS from evaluations.

This script identifies task-dataset pairs that have evaluations but no metrics
defined in TASK_DATASET_METRICS, and adds default metrics for them based on
the metrics used in existing evaluations.
"""

import sys
from sqlalchemy import text
from backend.database.connection import db_manager


def analyze_data():
    """Analyze the current state of task-dataset relationships."""
    with db_manager.session_local() as db:
        print("=" * 80)
        print("MIGRATION ANALYSIS: TASK_DATASETS → TASK_DATASET_METRICS")
        print("=" * 80)

        # Count task-dataset links
        td_count = db.execute(text("SELECT COUNT(*) FROM task_datasets")).scalar()
        print(f"\n1. TASK_DATASETS entries: {td_count}")

        # Count task-dataset-metric links
        tdm_count = db.execute(
            text("SELECT COUNT(*) FROM task_dataset_metrics")
        ).scalar()
        print(f"2. TASK_DATASET_METRICS entries: {tdm_count}")

        # Count evaluations
        eval_count = db.execute(text("SELECT COUNT(*) FROM evaluations")).scalar()
        print(f"3. Total evaluations: {eval_count}")

        # Count unique task-dataset pairs in evaluations
        eval_pairs = db.execute(
            text("SELECT COUNT(DISTINCT (task_id, dataset_id)) FROM evaluations")
        ).scalar()
        print(f"4. Unique (task, dataset) pairs in evaluations: {eval_pairs}")

        # Count task-dataset pairs with evaluations but no metrics
        missing_metrics = db.execute(
            text("""
            SELECT COUNT(DISTINCT (e.task_id, e.dataset_id))
            FROM evaluations e
            WHERE NOT EXISTS (
                SELECT 1 FROM task_dataset_metrics tdm
                WHERE tdm.task_id = e.task_id AND tdm.dataset_id = e.dataset_id
            )
        """)
        ).scalar()
        print(f"5. Evaluation pairs WITHOUT metrics: {missing_metrics}")

        # Count orphaned task-datasets (no evaluations, no metrics)
        orphaned = db.execute(
            text("""
            SELECT COUNT(*)
            FROM task_datasets td
            WHERE NOT EXISTS (
                SELECT 1 FROM evaluations e
                WHERE e.task_id = td.task_id AND e.dataset_id = td.dataset_id
            )
            AND NOT EXISTS (
                SELECT 1 FROM task_dataset_metrics tdm
                WHERE tdm.task_id = td.task_id AND tdm.dataset_id = td.dataset_id
            )
        """)
        ).scalar()
        print(f"6. Orphaned TASK_DATASETS (no evals, no metrics): {orphaned}")

        print("\n" + "=" * 80)
        print("MIGRATION PLAN:")
        print("=" * 80)
        print(
            f"- Add metrics for {missing_metrics} task-dataset pairs with evaluations"
        )
        print(f"- Ignore {orphaned} orphaned task-dataset links (will be deleted)")
        print("=" * 80 + "\n")


def migrate_evaluation_metrics():
    """
    For each (task, dataset) pair with evaluations but no metrics,
    add the metrics that are actually used in those evaluations.
    """
    with db_manager.session_local() as db:
        print("Step 1: Identifying task-dataset pairs needing metrics...\n")

        # Get all task-dataset pairs from evaluations that don't have metrics
        result = db.execute(
            text("""
            SELECT DISTINCT
                e.task_id,
                e.dataset_id,
                t.name as task_name,
                d.name as dataset_name
            FROM evaluations e
            JOIN tasks t ON t.id = e.task_id
            JOIN datasets d ON d.id = e.dataset_id
            WHERE NOT EXISTS (
                SELECT 1 FROM task_dataset_metrics tdm
                WHERE tdm.task_id = e.task_id AND tdm.dataset_id = e.dataset_id
            )
            ORDER BY e.task_id, e.dataset_id
        """)
        ).fetchall()

        pairs_to_process = [(row[0], row[1], row[2], row[3]) for row in result]
        print(f"Found {len(pairs_to_process)} task-dataset pairs needing metrics\n")

        if not pairs_to_process:
            print("No migration needed - all evaluation pairs have metrics defined!")
            return

        print("Step 2: Extracting metrics from evaluations...\n")

        total_metrics_added = 0

        for task_id, dataset_id, task_name, dataset_name in pairs_to_process:
            # Get all unique metrics used in evaluations for this task-dataset pair
            metrics_result = db.execute(
                text("""
                SELECT DISTINCT
                    e.best_metric,
                    COUNT(*) as usage_count
                FROM evaluations e
                WHERE e.task_id = :task_id
                    AND e.dataset_id = :dataset_id
                    AND e.best_metric IS NOT NULL
                GROUP BY e.best_metric
                ORDER BY usage_count DESC
            """),
                {"task_id": task_id, "dataset_id": dataset_id},
            ).fetchall()

            if not metrics_result:
                print(
                    f"  Warning: No metrics found for task {task_id} ({task_name[:40]}) - dataset {dataset_id} ({dataset_name[:40]})"
                )
                continue

            # Add each metric to task_dataset_metrics
            for metric_name, usage_count in metrics_result:
                # First, ensure the metric exists in the metrics table
                metric_result = db.execute(
                    text("""
                    SELECT id FROM metrics WHERE name = :name
                """),
                    {"name": metric_name},
                ).fetchone()

                if not metric_result:
                    print(
                        f"  Warning: Metric '{metric_name}' not found in metrics table, skipping..."
                    )
                    continue

                metric_id = metric_result[0]

                # Check if this triple already exists
                exists = db.execute(
                    text("""
                    SELECT 1 FROM task_dataset_metrics
                    WHERE task_id = :task_id
                        AND dataset_id = :dataset_id
                        AND metric_id = :metric_id
                """),
                    {
                        "task_id": task_id,
                        "dataset_id": dataset_id,
                        "metric_id": metric_id,
                    },
                ).fetchone()

                if exists:
                    continue

                # Insert the metric
                db.execute(
                    text("""
                    INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id, created_at)
                    VALUES (:task_id, :dataset_id, :metric_id, NOW())
                """),
                    {
                        "task_id": task_id,
                        "dataset_id": dataset_id,
                        "metric_id": metric_id,
                    },
                )

                total_metrics_added += 1

            print(
                f"  ✓ Task {task_id}: {task_name[:40]:40} | Dataset {dataset_id}: {dataset_name[:40]:40} | Added {len(metrics_result)} metrics"
            )

        # Commit all changes
        db.commit()

        print("\nStep 3: Migration complete!")
        print(f"  Total metrics added: {total_metrics_added}")
        print(f"  Pairs processed: {len(pairs_to_process)}")


def verify_migration():
    """Verify that all evaluations now have corresponding metrics defined."""
    with db_manager.session_local() as db:
        print("\n" + "=" * 80)
        print("VERIFICATION")
        print("=" * 80 + "\n")

        # Check for evaluations without metrics
        missing = db.execute(
            text("""
            SELECT COUNT(DISTINCT (e.task_id, e.dataset_id))
            FROM evaluations e
            WHERE NOT EXISTS (
                SELECT 1 FROM task_dataset_metrics tdm
                WHERE tdm.task_id = e.task_id AND tdm.dataset_id = e.dataset_id
            )
        """)
        ).scalar()

        if missing > 0:
            print(f"❌ FAILED: {missing} evaluation pairs still without metrics!")
            return False
        else:
            print("✓ SUCCESS: All evaluation pairs now have metrics defined")

        # Get updated counts
        tdm_count = db.execute(
            text("SELECT COUNT(*) FROM task_dataset_metrics")
        ).scalar()
        print(f"✓ Total TASK_DATASET_METRICS entries: {tdm_count}")

        # Check unique task-dataset pairs
        unique_pairs = db.execute(
            text("""
            SELECT COUNT(DISTINCT (task_id, dataset_id)) FROM task_dataset_metrics
        """)
        ).scalar()
        print(f"✓ Unique (task, dataset) pairs with metrics: {unique_pairs}")

        print("\n" + "=" * 80)
        print("READY TO REMOVE TASK_DATASETS TABLE")
        print("=" * 80 + "\n")

        return True


def main():
    """Run the migration."""
    print("\n")
    print("█" * 80)
    print("  TASK_DATASETS → TASK_DATASET_METRICS MIGRATION")
    print("█" * 80)
    print("\n")

    # Step 1: Analyze current state
    analyze_data()

    # Step 2: Confirm migration
    response = input("Proceed with migration? (yes/no): ").strip().lower()
    if response != "yes":
        print("\nMigration cancelled.")
        return 1

    print("\n")

    # Step 3: Perform migration
    try:
        migrate_evaluation_metrics()
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback

        traceback.print_exc()
        return 1

    # Step 4: Verify results
    if not verify_migration():
        return 1

    print("✓ Migration completed successfully!")
    print("\nNext steps:")
    print("1. Update code to use TASK_DATASET_METRICS instead of TASK_DATASETS")
    print("2. Test all API endpoints")
    print("3. Drop the TASK_DATASETS table\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
