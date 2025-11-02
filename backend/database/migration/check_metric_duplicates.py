#!/usr/bin/env python3
"""
Check for and report case-insensitive duplicate metrics.

This script helps identify metrics that are duplicates due to case sensitivity
(e.g., "score" vs "Score", "accuracy" vs "Accuracy").

Usage:
    uv run --env-file backend/keys.env python backend/database/migration/check_metric_duplicates.py
"""

from sqlalchemy import text
from backend.database.connection import DatabaseManager


def find_duplicate_metrics():
    """Find metrics that are case-insensitive duplicates."""
    db_manager = DatabaseManager()

    with db_manager.session_local() as db:
        query = text("""
            SELECT
                LOWER(name) AS metric_lower,
                COUNT(*) AS duplicate_count,
                STRING_AGG(name || ' (id: ' || id || ', used: ' ||
                    COALESCE((
                        SELECT COUNT(*)::text
                        FROM evaluations
                        WHERE best_metric = m.name
                    ), '0') ||
                    ')', ', ' ORDER BY id) AS versions,
                STRING_AGG(id::text, ', ' ORDER BY id) AS ids
            FROM metrics m
            GROUP BY LOWER(name)
            HAVING COUNT(*) > 1
            ORDER BY COUNT(*) DESC, LOWER(name)
        """)

        results = db.execute(query).fetchall()

        if not results:
            print("✓ No duplicate metrics found!")
            return True

        print(f"⚠ Found {len(results)} case-insensitive duplicate metric(s):\n")
        for row in results:
            print(f"  Metric: {row.metric_lower}")
            print(f"  Duplicates: {row.duplicate_count}")
            print(f"  Versions: {row.versions}")
            print(f"  IDs: {row.ids}")
            print()

        return False


def check_evaluation_metrics():
    """Check if any evaluations reference non-existent metrics."""
    db_manager = DatabaseManager()

    with db_manager.session_local() as db:
        query = text("""
            SELECT DISTINCT e.best_metric
            FROM evaluations e
            LEFT JOIN metrics m ON e.best_metric = m.name
            WHERE e.best_metric IS NOT NULL
              AND m.id IS NULL
            ORDER BY e.best_metric
        """)

        results = db.execute(query).fetchall()

        if not results:
            print("✓ All evaluation metrics exist in metrics table!")
            return True

        print(f"⚠ Found {len(results)} evaluation metric(s) not in metrics table:\n")
        for row in results:
            print(f"  - {row.best_metric}")
        print()

        return False


def main():
    """Run all checks."""
    print("=" * 60)
    print("Metric Duplicate Checker")
    print("=" * 60)
    print()

    print("=== Checking for Case-Insensitive Duplicates ===")
    no_duplicates = find_duplicate_metrics()
    print()

    print("=== Checking Evaluation Metric References ===")
    all_valid = check_evaluation_metrics()
    print()

    print("=" * 60)
    if no_duplicates and all_valid:
        print("✓ All checks passed!")
        return 0
    else:
        print("⚠ Some issues found (see above)")
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
