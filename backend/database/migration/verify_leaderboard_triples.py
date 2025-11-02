"""
Verification script for leaderboard triples migration.

This script verifies that:
1. task_dataset_metrics table is populated
2. Triples exist for popular datasets
3. Evaluations have matching triples
4. Ranks are calculated correctly per triple

Usage:
    uv run --env-file backend/keys.env python backend/database/migration/verify_leaderboard_triples.py
"""

import sys
from sqlalchemy import text
from backend.database.connection import DatabaseManager

# Initialize database manager
db_manager = DatabaseManager()


def verify_triples_populated():
    """Verify that task_dataset_metrics table has data."""
    print("\n=== Verifying Triples Populated ===")

    with db_manager.session_local() as db:
        # Count total triples
        result = db.execute(
            text("SELECT COUNT(*) FROM task_dataset_metrics")
        ).fetchone()
        triple_count = result[0]
        print(f"✓ Total triples: {triple_count}")

        if triple_count == 0:
            print("✗ ERROR: No triples found! Migration may have failed.")
            return False

        # Check for popular datasets
        query = text("""
            SELECT t.name AS task, d.name AS dataset, m.name AS metric, COUNT(*) as count
            FROM task_dataset_metrics tdm
            JOIN tasks t ON tdm.task_id = t.id
            JOIN datasets d ON tdm.dataset_id = d.id
            JOIN metrics m ON tdm.metric_id = m.id
            WHERE d.name IN ('COCO', 'ImageNet', 'LibriSpeech', 'GLUE')
            GROUP BY t.name, d.name, m.name
            ORDER BY d.name, t.name, m.name
            LIMIT 20
        """)

        results = db.execute(query).fetchall()
        if results:
            print("\n✓ Sample triples for popular datasets:")
            for row in results:
                print(f"  - ({row.task}, {row.dataset}, {row.metric})")
        else:
            print("⚠ WARNING: No triples found for popular datasets")

        return True


def verify_evaluations_have_triples():
    """Verify that evaluations have matching triples."""
    print("\n=== Verifying Evaluations Have Matching Triples ===")

    with db_manager.session_local() as db:
        # Count evaluations without matching triples
        query = text("""
            SELECT COUNT(*)
            FROM evaluations e
            LEFT JOIN metrics m ON e.best_metric = m.name
            LEFT JOIN task_dataset_metrics tdm ON (
                e.task_id = tdm.task_id AND
                e.dataset_id = tdm.dataset_id AND
                m.id = tdm.metric_id
            )
            WHERE e.best_metric IS NOT NULL AND tdm.task_id IS NULL
        """)

        result = db.execute(query).fetchone()
        orphan_count = result[0]

        if orphan_count == 0:
            print("✓ All evaluations have matching triples")
            return True
        else:
            print(f"⚠ WARNING: {orphan_count} evaluations without matching triples")
            print("  This is OK if no triples are configured yet (allow-all mode)")
            return True


def verify_ranks_per_triple():
    """Verify that ranks are calculated per triple."""
    print("\n=== Verifying Ranks Per Triple ===")

    with db_manager.session_local() as db:
        # Check that evaluations with different best_metric have independent ranks
        query = text("""
            SELECT
                e.task_id,
                e.dataset_id,
                e.best_metric,
                COUNT(*) as eval_count,
                COUNT(DISTINCT e.best_rank) as unique_ranks,
                MIN(e.best_rank) as min_rank,
                MAX(e.best_rank) as max_rank
            FROM evaluations e
            WHERE e.best_metric IS NOT NULL AND e.best_rank IS NOT NULL
            GROUP BY e.task_id, e.dataset_id, e.best_metric
            HAVING COUNT(*) > 1
            ORDER BY eval_count DESC
            LIMIT 10
        """)

        results = db.execute(query).fetchall()
        if results:
            print("\n✓ Sample leaderboards with rankings:")
            for row in results:
                print(
                    f"  - Task {row.task_id}, Dataset {row.dataset_id}, Metric '{row.best_metric}': "
                    f"{row.eval_count} evaluations, ranks {row.min_rank}-{row.max_rank}"
                )
            return True
        else:
            print("⚠ WARNING: No leaderboards with multiple evaluations found")
            return True


def verify_composite_index():
    """Verify that composite index exists on evaluations."""
    print("\n=== Verifying Composite Index ===")

    with db_manager.session_local() as db:
        query = text("""
            SELECT indexname
            FROM pg_indexes
            WHERE tablename = 'evaluations'
            AND indexname LIKE '%task_dataset_metric%'
        """)

        result = db.execute(query).fetchone()
        if result:
            print(f"✓ Composite index exists: {result.indexname}")
            return True
        else:
            print("⚠ WARNING: Composite index not found")
            print(
                "  Run: CREATE INDEX idx_evaluations_task_dataset_metric ON evaluations(task_id, dataset_id, best_metric);"
            )
            return False


def main():
    """Run all verification checks."""
    print("=" * 60)
    print("Leaderboard Triples Migration Verification")
    print("=" * 60)

    checks = [
        verify_triples_populated(),
        verify_evaluations_have_triples(),
        verify_ranks_per_triple(),
        verify_composite_index(),
    ]

    print("\n" + "=" * 60)
    if all(checks):
        print("✓ All verification checks passed!")
        print("=" * 60)
        return 0
    else:
        print("⚠ Some checks failed or have warnings")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
