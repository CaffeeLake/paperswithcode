"""
Consolidate duplicate 'accuracy' and 'Accuracy' metrics into a single canonical form.

Problem:
    The database contains two variants of the accuracy metric:
    - 'Accuracy' (ID: 18) - used in 62 evaluations
    - 'accuracy' (ID: 39) - used in 60 evaluations

Solution:
    1. Update all evaluations.best_metric fields from 'accuracy' to 'Accuracy'
    2. Update all evaluations.metrics JSONB fields to rename 'accuracy' keys to 'Accuracy'
    3. Delete the duplicate 'accuracy' metric (ID: 39) from the metrics table

Usage:
    # Dry run (preview changes)
    python backend/database/migration/consolidate_accuracy_metric.py --dry-run

    # Execute migration
    python backend/database/migration/consolidate_accuracy_metric.py
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import argparse
import logging
from sqlalchemy import text

from backend.database.connection import DatabaseManager

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

db_manager = DatabaseManager()


def check_current_state(session):
    """Check and report current state of accuracy metrics."""

    logger.info("=" * 80)
    logger.info("CURRENT STATE")
    logger.info("=" * 80)

    # Check metrics table
    result = session.execute(
        text("""
        SELECT name, id, full_name
        FROM metrics
        WHERE LOWER(name) = 'accuracy'
        ORDER BY name
    """)
    )
    metrics = result.fetchall()
    logger.info(f"\nMetrics table: {len(metrics)} accuracy variant(s)")
    for metric in metrics:
        logger.info(f"  - '{metric[0]}' (ID: {metric[1]}, Full: {metric[2]})")

    # Check evaluations.best_metric
    for variant in ["accuracy", "Accuracy"]:
        result = session.execute(
            text("""
            SELECT COUNT(*)
            FROM evaluations
            WHERE best_metric = :variant
        """),
            {"variant": variant},
        )
        count = result.fetchone()[0]
        logger.info(f"\nEvaluations with best_metric = '{variant}': {count}")

    # Check evaluations.metrics JSONB
    for variant in ["accuracy", "Accuracy"]:
        result = session.execute(
            text("""
            SELECT COUNT(*)
            FROM evaluations
            WHERE metrics ? :variant
        """),
            {"variant": variant},
        )
        count = result.fetchone()[0]
        logger.info(f"Evaluations with '{variant}' in metrics: {count}")

    logger.info("=" * 80)


def consolidate_accuracy_metrics(dry_run=True):
    """
    Consolidate duplicate accuracy metrics.

    Args:
        dry_run: If True, only preview changes without committing
    """

    session = db_manager.session_local()

    try:
        # Check current state
        check_current_state(session)

        logger.info("\n" + "=" * 80)
        if dry_run:
            logger.info("DRY RUN MODE - No changes will be committed")
        else:
            logger.info("EXECUTING MIGRATION")
        logger.info("=" * 80)

        # Step 1: Update evaluations.best_metric
        logger.info("\n1. Updating evaluations.best_metric field...")
        result = session.execute(
            text("""
            UPDATE evaluations
            SET best_metric = 'Accuracy'
            WHERE best_metric = 'accuracy'
        """)
        )
        best_metric_updated = result.rowcount
        logger.info(f"   Updated {best_metric_updated} evaluation(s)")

        # Step 2: Update evaluations.metrics JSONB
        logger.info("\n2. Updating evaluations.metrics JSONB field...")

        # First, get the count of evaluations that need updating
        result = session.execute(
            text("""
            SELECT COUNT(*)
            FROM evaluations
            WHERE metrics ? 'accuracy'
        """)
        )
        metrics_to_update = result.fetchone()[0]
        logger.info(
            f"   Found {metrics_to_update} evaluation(s) with 'accuracy' in metrics"
        )

        # Update the JSONB field (rename key from 'accuracy' to 'Accuracy')
        result = session.execute(
            text("""
            UPDATE evaluations
            SET metrics = metrics - 'accuracy' || jsonb_build_object('Accuracy', metrics->'accuracy')
            WHERE metrics ? 'accuracy'
        """)
        )
        metrics_updated = result.rowcount
        logger.info(f"   Updated {metrics_updated} evaluation(s)")

        # Step 3: Delete duplicate metric from metrics table
        logger.info("\n3. Deleting duplicate 'accuracy' metric from metrics table...")
        result = session.execute(
            text("""
            DELETE FROM metrics
            WHERE name = 'accuracy' AND id = 39
        """)
        )
        metrics_deleted = result.rowcount
        logger.info(f"   Deleted {metrics_deleted} metric(s)")

        if dry_run:
            logger.info("\n" + "=" * 80)
            logger.info("DRY RUN - Rolling back all changes")
            logger.info("=" * 80)
            session.rollback()

            logger.info("\nSummary of changes that WOULD be made:")
            logger.info(f"  - best_metric fields updated: {best_metric_updated}")
            logger.info(f"  - metrics JSONB fields updated: {metrics_updated}")
            logger.info(f"  - duplicate metrics deleted: {metrics_deleted}")
        else:
            logger.info("\n" + "=" * 80)
            logger.info("COMMITTING CHANGES")
            logger.info("=" * 80)
            session.commit()

            logger.info("\nSummary of changes made:")
            logger.info(f"  - best_metric fields updated: {best_metric_updated}")
            logger.info(f"  - metrics JSONB fields updated: {metrics_updated}")
            logger.info(f"  - duplicate metrics deleted: {metrics_deleted}")

            # Verify the changes
            logger.info("\n" + "=" * 80)
            logger.info("VERIFICATION")
            logger.info("=" * 80)

            # Check metrics table
            result = session.execute(
                text("""
                SELECT name, id, full_name
                FROM metrics
                WHERE LOWER(name) = 'accuracy'
                ORDER BY name
            """)
            )
            metrics = result.fetchall()
            logger.info(f"\nMetrics table: {len(metrics)} accuracy variant(s)")
            for metric in metrics:
                logger.info(f"  - '{metric[0]}' (ID: {metric[1]})")

            # Check evaluations with lowercase accuracy
            result = session.execute(
                text("""
                SELECT COUNT(*)
                FROM evaluations
                WHERE best_metric = 'accuracy'
            """)
            )
            lowercase_best = result.fetchone()[0]

            result = session.execute(
                text("""
                SELECT COUNT(*)
                FROM evaluations
                WHERE metrics ? 'accuracy'
            """)
            )
            lowercase_metrics = result.fetchone()[0]

            # Check evaluations with capitalized Accuracy
            result = session.execute(
                text("""
                SELECT COUNT(*)
                FROM evaluations
                WHERE best_metric = 'Accuracy'
            """)
            )
            capitalized_best = result.fetchone()[0]

            result = session.execute(
                text("""
                SELECT COUNT(*)
                FROM evaluations
                WHERE metrics ? 'Accuracy'
            """)
            )
            capitalized_metrics = result.fetchone()[0]

            logger.info("\nEvaluations with lowercase 'accuracy':")
            logger.info(f"  - best_metric: {lowercase_best}")
            logger.info(f"  - metrics JSONB: {lowercase_metrics}")

            logger.info("\nEvaluations with capitalized 'Accuracy':")
            logger.info(f"  - best_metric: {capitalized_best}")
            logger.info(f"  - metrics JSONB: {capitalized_metrics}")

            # Verify success
            if lowercase_best == 0 and lowercase_metrics == 0 and len(metrics) == 1:
                logger.info("\n" + "=" * 80)
                logger.info("✅ MIGRATION SUCCESSFUL!")
                logger.info("=" * 80)
                logger.info("All accuracy metrics have been consolidated to 'Accuracy'")
                return True
            else:
                logger.error("\n" + "=" * 80)
                logger.error("⚠️  VERIFICATION FAILED")
                logger.error("=" * 80)
                if lowercase_best > 0 or lowercase_metrics > 0:
                    logger.error(
                        f"Still found lowercase 'accuracy' in {lowercase_best + lowercase_metrics} record(s)"
                    )
                if len(metrics) != 1:
                    logger.error(f"Expected 1 accuracy metric, found {len(metrics)}")
                return False

        return True

    except Exception as e:
        logger.error(f"\n✗ Error during migration: {e}")
        import traceback

        traceback.print_exc()
        session.rollback()
        return False
    finally:
        session.close()


def main():
    """Main function to run the migration."""

    parser = argparse.ArgumentParser(
        description="Consolidate duplicate accuracy metrics in the database"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without committing (default: False)",
    )

    args = parser.parse_args()

    logger.info("\n" + "=" * 80)
    logger.info("CONSOLIDATE ACCURACY METRICS MIGRATION")
    logger.info("=" * 80)
    logger.info(
        "This script will consolidate 'accuracy' and 'Accuracy' into 'Accuracy'"
    )
    logger.info("=" * 80 + "\n")

    success = consolidate_accuracy_metrics(dry_run=args.dry_run)

    if success and not args.dry_run:
        logger.info("\n✅ Migration completed successfully!")
        logger.info("The database now has a single canonical 'Accuracy' metric.")
    elif args.dry_run:
        logger.info("\n✓ Dry run completed. Run without --dry-run to apply changes.")
    else:
        logger.error("\n✗ Migration failed. Check the logs above for details.")
        sys.exit(1)


if __name__ == "__main__":
    main()
