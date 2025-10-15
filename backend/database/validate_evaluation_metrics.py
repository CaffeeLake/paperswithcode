"""
Data validation script for evaluation metrics.

This script checks for and fixes common data inconsistencies in the evaluations table,
particularly metric naming inconsistencies that can cause display issues.
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Dict, List
import sys
import os

# Add backend to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.config import get_settings


def get_database_connection():
    """Get a psycopg2 database connection."""
    settings = get_settings()
    # Parse the database URL to extract connection parameters
    # URL format: postgresql://user:password@host:port/database
    url = settings.database_url.replace("postgresql://", "")
    user_pass, host_port_db = url.split("@")
    user, password = user_pass.split(":")
    host_port, database = host_port_db.split("/")
    host, port = host_port.split(":") if ":" in host_port else (host_port, "5432")

    return psycopg2.connect(
        host=host, port=port, database=database, user=user, password=password
    )


def get_all_metric_keys(cursor) -> List[str]:
    """Get all unique metric keys used in evaluations."""
    cursor.execute("""
        SELECT DISTINCT jsonb_object_keys(metrics) as metric_name
        FROM evaluations
        ORDER BY metric_name
    """)
    return [row["metric_name"] for row in cursor.fetchall()]


def find_metric_inconsistencies(cursor) -> Dict[str, List[str]]:
    """
    Find potential metric naming inconsistencies.

    Returns a dictionary mapping standardized names to their variations.
    """
    metric_keys = get_all_metric_keys(cursor)

    inconsistencies = {}

    # Known inconsistencies to check for
    # Format: {standard_name: [variations]}
    known_variations = {
        "box AP": ["box mAP", "box_ap", "box_map", "bbox AP", "bbox mAP"],
        "AP": ["mAP", "mean AP"],
        "AP50": ["AP@50", "AP@0.5", "AP_50"],
        "AP75": ["AP@75", "AP@0.75", "AP_75"],
    }

    for standard_name, variations in known_variations.items():
        found_variations = [v for v in variations if v in metric_keys]
        if found_variations:
            inconsistencies[standard_name] = found_variations

    return inconsistencies


def standardize_metric_names(cursor, dry_run=True) -> int:
    """
    Standardize metric names across all evaluations.

    Args:
        cursor: Database cursor
        dry_run: If True, only report what would be changed

    Returns:
        Number of evaluations updated
    """
    inconsistencies = find_metric_inconsistencies(cursor)

    if not inconsistencies:
        print("✓ No metric naming inconsistencies found!")
        return 0

    print("\nFound metric naming inconsistencies:")
    for standard_name, variations in inconsistencies.items():
        print(f"  {standard_name}: {', '.join(variations)}")

    total_updated = 0

    for standard_name, variations in inconsistencies.items():
        for variation in variations:
            # Count how many would be affected
            cursor.execute(
                """
                SELECT COUNT(*) as count
                FROM evaluations
                WHERE metrics ? %s
            """,
                (variation,),
            )
            count = cursor.fetchone()["count"]

            if count > 0:
                print(f"\n  {variation} → {standard_name}: {count} evaluation(s)")

                if not dry_run:
                    # Update the metric name
                    cursor.execute(
                        """
                        UPDATE evaluations
                        SET metrics = jsonb_set(
                            jsonb_set(metrics, %s, metrics->%s),
                            %s, 'null'::jsonb
                        ) - %s
                        WHERE metrics ? %s
                    """,
                        (
                            f"{{{standard_name}}}",  # New key path
                            variation,  # Old key to copy from
                            f"{{{variation}}}",  # Path to remove
                            variation,  # Key to remove
                            variation,  # Filter condition
                        ),
                    )
                    total_updated += count
                    print(f"    ✓ Updated {count} evaluation(s)")

    return total_updated


def validate_best_metrics(cursor, dry_run=True) -> int:
    """
    Ensure all evaluations have a best_metric set.

    Args:
        cursor: Database cursor
        dry_run: If True, only report what would be changed

    Returns:
        Number of evaluations updated
    """
    # Find evaluations without best_metric
    cursor.execute("""
        SELECT id, model_name, metrics
        FROM evaluations
        WHERE best_metric IS NULL
        LIMIT 10
    """)

    missing_best_metric = cursor.fetchall()

    if not missing_best_metric:
        print("\n✓ All evaluations have best_metric set!")
        return 0

    print(f"\nFound {len(missing_best_metric)} evaluations without best_metric set")

    total_updated = 0

    for eval_row in missing_best_metric:
        eval_id = eval_row["id"]
        model_name = eval_row["model_name"]
        metrics = eval_row["metrics"]

        # Determine best metric based on available metrics
        # Priority: box AP > AP > any other metric
        if "box AP" in metrics:
            best_metric = "box AP"
        elif "AP" in metrics:
            best_metric = "AP"
        else:
            # Use the first metric key
            best_metric = next(iter(metrics.keys())) if metrics else None

        if best_metric:
            print(f"  Evaluation {eval_id} ({model_name}): best_metric = {best_metric}")

            if not dry_run:
                cursor.execute(
                    """
                    UPDATE evaluations
                    SET best_metric = %s
                    WHERE id = %s
                """,
                    (best_metric, eval_id),
                )
                total_updated += 1

    return total_updated


def main():
    """Main validation and cleanup function."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate and fix evaluation metric inconsistencies"
    )
    parser.add_argument(
        "--fix", action="store_true", help="Actually fix issues (default is dry-run)"
    )
    args = parser.parse_args()

    dry_run = not args.fix

    print("=" * 60)
    print("Evaluation Metrics Validation")
    print("=" * 60)

    if dry_run:
        print("\n⚠️  DRY RUN MODE - No changes will be made")
        print("Use --fix to actually apply changes\n")
    else:
        print("\n⚠️  FIXING MODE - Changes will be applied\n")

    try:
        conn = get_database_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # Run validations
        print("\n1. Checking for metric naming inconsistencies...")
        updated_metrics = standardize_metric_names(cursor, dry_run=dry_run)

        print("\n2. Checking for missing best_metric values...")
        updated_best_metrics = validate_best_metrics(cursor, dry_run=dry_run)

        # Commit changes if not dry run
        if not dry_run:
            conn.commit()
            print("\n✓ All changes committed to database")

        # Summary
        print("\n" + "=" * 60)
        print("Summary:")
        print(f"  Metric names standardized: {updated_metrics}")
        print(f"  Best metrics set: {updated_best_metrics}")
        print("=" * 60)

        cursor.close()
        conn.close()

        if dry_run and (updated_metrics > 0 or updated_best_metrics > 0):
            print("\n💡 Run with --fix to apply these changes")
            return 1

        return 0

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
