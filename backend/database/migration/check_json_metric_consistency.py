#!/usr/bin/env python3
"""
Check for inconsistent metric capitalization in evaluations JSON.

This script identifies cases where the best_metric field doesn't match
the capitalization of the keys in the metrics JSON field.

Usage:
    uv run --env-file backend/keys.env python backend/database/migration/check_json_metric_consistency.py
"""

import json
from sqlalchemy import text
from backend.database.connection import DatabaseManager


def check_json_consistency():
    """Check if best_metric matches the JSON keys."""
    db_manager = DatabaseManager()

    with db_manager.session_local() as db:
        # Get all evaluations with best_metric
        query = text("""
            SELECT
                id,
                model_name,
                best_metric,
                metrics::text as metrics_text,
                dataset_id
            FROM evaluations
            WHERE best_metric IS NOT NULL
            ORDER BY id
        """)

        results = db.execute(query).fetchall()

        inconsistencies = []

        for row in results:
            try:
                metrics_dict = json.loads(row.metrics_text)

                # Check if best_metric exists in the JSON with exact capitalization
                if row.best_metric not in metrics_dict:
                    # Check if it exists with different capitalization
                    json_keys = list(metrics_dict.keys())
                    matching_keys = [
                        k for k in json_keys if k.lower() == row.best_metric.lower()
                    ]

                    if matching_keys:
                        inconsistencies.append(
                            {
                                "id": row.id,
                                "model_name": row.model_name,
                                "best_metric": row.best_metric,
                                "json_keys": json_keys,
                                "dataset_id": row.dataset_id,
                            }
                        )
            except json.JSONDecodeError:
                print(f"⚠ Warning: Invalid JSON for evaluation {row.id}")

        if not inconsistencies:
            print("✓ All evaluations have consistent metric capitalization!")
            return True

        print(
            f"⚠ Found {len(inconsistencies)} evaluation(s) with inconsistent capitalization:\n"
        )
        for inc in inconsistencies[:10]:  # Show first 10
            print(
                f"  Eval ID {inc['id']} (dataset {inc['dataset_id']}): {inc['model_name']}"
            )
            print(f"    best_metric: '{inc['best_metric']}'")
            print(f"    JSON keys: {inc['json_keys']}")
            print()

        if len(inconsistencies) > 10:
            print(f"  ... and {len(inconsistencies) - 10} more")

        return False


def main():
    """Run consistency check."""
    print("=" * 60)
    print("Evaluation Metrics JSON Consistency Checker")
    print("=" * 60)
    print()

    is_consistent = check_json_consistency()

    print("=" * 60)
    if is_consistent:
        print("✓ All checks passed!")
        return 0
    else:
        print("⚠ Inconsistencies found (see above)")
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
