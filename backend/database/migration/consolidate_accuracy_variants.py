"""
Consolidate "Accuracy (TTA)" and "Accuracy (mean)" metrics to "Accuracy".

Problem:
    The database contains variants of the accuracy metric:
    - "Accuracy (TTA)" - Test-Time Augmentation variant
    - "Accuracy (mean)" - Mean accuracy variant
    - "Accuracy" - Standard accuracy metric

Solution:
    1. Update all evaluations.best_metric fields from variants to "Accuracy"
    2. Update all evaluations.metrics JSONB fields to rename variant keys to "Accuracy"
    3. Handle cases where "Accuracy" already exists (keep the variant value)
    4. Recalculate ranks for affected leaderboards
    5. Delete the unused variant metrics from the metrics table

Usage:
    # Dry run (preview changes)
    uv run --env-file backend/keys.env python backend/database/migration/consolidate_accuracy_variants.py --dry-run

    # Execute migration
    uv run --env-file backend/keys.env python backend/database/migration/consolidate_accuracy_variants.py
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import argparse
import logging
from sqlalchemy import text

from backend.database.connection import DatabaseManager
from backend.services.evaluation_service import EvaluationService

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

db_manager = DatabaseManager()

# Variants to consolidate
VARIANTS = ["Accuracy (TTA)", "Accuracy (mean)"]
TARGET_METRIC = "Accuracy"


def check_current_state(session):
    """Check and report current state of accuracy metrics."""

    logger.info("=" * 80)
    logger.info("CURRENT STATE")
    logger.info("=" * 80)

    # Check metrics table
    result = session.execute(
        text("""
        SELECT name, id, full_name, direction
        FROM metrics
        WHERE name IN (:variant1, :variant2, :target)
        ORDER BY name
    """),
        {"variant1": VARIANTS[0], "variant2": VARIANTS[1], "target": TARGET_METRIC},
    )
    metrics = result.fetchall()
    logger.info(f"\nMetrics table: {len(metrics)} accuracy-related metric(s)")
    for metric in metrics:
        logger.info(
            f"  - '{metric[0]}' (ID: {metric[1]}, Full: {metric[2]}, Direction: {metric[3]})"
        )

    # Check evaluations.best_metric
    for variant in VARIANTS + [TARGET_METRIC]:
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
    for variant in VARIANTS + [TARGET_METRIC]:
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

    # Check for evaluations that have both a variant and Accuracy
    for variant in VARIANTS:
        result = session.execute(
            text("""
            SELECT COUNT(*)
            FROM evaluations
            WHERE metrics ? :variant AND metrics ? :target
        """),
            {"variant": variant, "target": TARGET_METRIC},
        )
        count = result.fetchone()[0]
        if count > 0:
            logger.warning(
                f"Found {count} evaluation(s) with both '{variant}' and '{TARGET_METRIC}'"
            )

    logger.info("=" * 80)


def consolidate_accuracy_variants(dry_run=True):
    """
    Consolidate accuracy variant metrics to "Accuracy".

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

        # Track affected leaderboards for rank recalculation
        affected_leaderboards = set()

        # Step 1: Update evaluations.best_metric
        logger.info("\n1. Updating evaluations.best_metric field...")
        for variant in VARIANTS:
            # Get affected leaderboards before update
            result = session.execute(
                text("""
                SELECT DISTINCT task_id, dataset_id
                FROM evaluations
                WHERE best_metric = :variant
            """),
                {"variant": variant},
            )
            for row in result:
                affected_leaderboards.add((row[0], row[1]))

            result = session.execute(
                text("""
                UPDATE evaluations
                SET best_metric = :target
                WHERE best_metric = :variant
            """),
                {"target": TARGET_METRIC, "variant": variant},
            )
            updated = result.rowcount
            logger.info(
                f"   Updated {updated} evaluation(s) with best_metric = '{variant}'"
            )

        # Step 2: Update evaluations.metrics JSONB
        logger.info("\n2. Updating evaluations.metrics JSONB field...")

        for variant in VARIANTS:
            # Get count of evaluations that need updating
            result = session.execute(
                text("""
                SELECT COUNT(*)
                FROM evaluations
                WHERE metrics ? :variant
            """),
                {"variant": variant},
            )
            metrics_to_update = result.fetchone()[0]
            logger.info(
                f"   Found {metrics_to_update} evaluation(s) with '{variant}' in metrics"
            )

            # Get affected leaderboards
            result = session.execute(
                text("""
                SELECT DISTINCT task_id, dataset_id
                FROM evaluations
                WHERE metrics ? :variant
            """),
                {"variant": variant},
            )
            for row in result:
                affected_leaderboards.add((row[0], row[1]))

            # Handle two cases:
            # Case 1: Evaluation has variant but not Accuracy - simple rename
            # Case 2: Evaluation has both variant and Accuracy - remove variant, keep Accuracy
            logger.info(f"   Processing evaluations with '{variant}'...")

            # Case 1: Simple rename (no existing Accuracy)
            result = session.execute(
                text("""
                UPDATE evaluations
                SET metrics = metrics - :variant || jsonb_build_object(:target, metrics->:variant)
                WHERE metrics ? :variant AND NOT (metrics ? :target)
            """),
                {"variant": variant, "target": TARGET_METRIC},
            )
            case1_updated = result.rowcount
            logger.info(f"     Case 1 (simple rename): {case1_updated} evaluation(s)")

            # Case 2: Remove variant, keep existing Accuracy
            result = session.execute(
                text("""
                UPDATE evaluations
                SET metrics = metrics - :variant
                WHERE metrics ? :variant AND metrics ? :target
            """),
                {"variant": variant, "target": TARGET_METRIC},
            )
            case2_updated = result.rowcount
            logger.info(
                f"     Case 2 (remove variant, keep Accuracy): {case2_updated} evaluation(s)"
            )

        # Step 3: Delete variant metrics from metrics table
        logger.info("\n3. Deleting variant metrics from metrics table...")
        for variant in VARIANTS:
            result = session.execute(
                text("""
                DELETE FROM metrics
                WHERE name = :variant
            """),
                {"variant": variant},
            )
            deleted = result.rowcount
            logger.info(f"   Deleted {deleted} metric(s) named '{variant}'")

        if dry_run:
            logger.info("\n" + "=" * 80)
            logger.info("DRY RUN - Rolling back all changes")
            logger.info("=" * 80)
            session.rollback()

            logger.info("\nSummary of changes that WOULD be made:")
            logger.info(f"  - Affected leaderboards: {len(affected_leaderboards)}")
            logger.info(f"  - Variant metrics deleted: {len(VARIANTS)}")
        else:
            logger.info("\n" + "=" * 80)
            logger.info("COMMITTING CHANGES")
            logger.info("=" * 80)
            session.commit()

            logger.info("\nSummary of changes made:")
            logger.info(f"  - Affected leaderboards: {len(affected_leaderboards)}")
            logger.info(f"  - Variant metrics deleted: {len(VARIANTS)}")

            # Step 4: Recalculate ranks for affected leaderboards
            logger.info("\n4. Recalculating ranks for affected leaderboards...")
            evaluation_service = EvaluationService(session)
            recalculated_count = 0

            for task_id, dataset_id in affected_leaderboards:
                try:
                    evaluation_service.recalculate_ranks(
                        task_id=task_id,
                        dataset_id=dataset_id,
                        metric_name=TARGET_METRIC,
                    )
                    recalculated_count += 1
                except Exception as e:
                    logger.warning(
                        f"   Failed to recalculate ranks for task_id={task_id}, dataset_id={dataset_id}: {e}"
                    )

            logger.info(
                f"   Recalculated ranks for {recalculated_count} leaderboard(s)"
            )

            # Verify the changes
            logger.info("\n" + "=" * 80)
            logger.info("VERIFICATION")
            logger.info("=" * 80)

            # Check metrics table
            result = session.execute(
                text("""
                SELECT name, id, full_name
                FROM metrics
                WHERE name IN (:variant1, :variant2, :target)
                ORDER BY name
            """),
                {
                    "variant1": VARIANTS[0],
                    "variant2": VARIANTS[1],
                    "target": TARGET_METRIC,
                },
            )
            metrics = result.fetchall()
            logger.info(f"\nMetrics table: {len(metrics)} accuracy-related metric(s)")
            for metric in metrics:
                logger.info(f"  - '{metric[0]}' (ID: {metric[1]})")

            # Check evaluations with variants
            variant_best = 0
            variant_metrics = 0
            for variant in VARIANTS:
                result = session.execute(
                    text("""
                    SELECT COUNT(*)
                    FROM evaluations
                    WHERE best_metric = :variant
                """),
                    {"variant": variant},
                )
                variant_best += result.fetchone()[0]

                result = session.execute(
                    text("""
                    SELECT COUNT(*)
                    FROM evaluations
                    WHERE metrics ? :variant
                """),
                    {"variant": variant},
                )
                variant_metrics += result.fetchone()[0]

            # Check evaluations with target Accuracy
            result = session.execute(
                text("""
                SELECT COUNT(*)
                FROM evaluations
                WHERE best_metric = :target
            """),
                {"target": TARGET_METRIC},
            )
            target_best = result.fetchone()[0]

            result = session.execute(
                text("""
                SELECT COUNT(*)
                FROM evaluations
                WHERE metrics ? :target
            """),
                {"target": TARGET_METRIC},
            )
            target_metrics = result.fetchone()[0]

            logger.info("\nEvaluations with variant metrics:")
            logger.info(f"  - best_metric: {variant_best}")
            logger.info(f"  - metrics JSONB: {variant_metrics}")

            logger.info(f"\nEvaluations with '{TARGET_METRIC}':")
            logger.info(f"  - best_metric: {target_best}")
            logger.info(f"  - metrics JSONB: {target_metrics}")

            # Verify success
            variant_metrics_in_table = [m for m in metrics if m[0] in VARIANTS]
            if (
                variant_best == 0
                and variant_metrics == 0
                and len(variant_metrics_in_table) == 0
            ):
                logger.info("\n" + "=" * 80)
                logger.info("✅ MIGRATION SUCCESSFUL!")
                logger.info("=" * 80)
                logger.info(
                    f"All accuracy variants have been consolidated to '{TARGET_METRIC}'"
                )
                return True
            else:
                logger.error("\n" + "=" * 80)
                logger.error("⚠️  VERIFICATION FAILED")
                logger.error("=" * 80)
                if variant_best > 0 or variant_metrics > 0:
                    logger.error(
                        f"Still found variant metrics in {variant_best + variant_metrics} record(s)"
                    )
                if len(variant_metrics_in_table) > 0:
                    logger.error(
                        f"Still found {len(variant_metrics_in_table)} variant metric(s) in metrics table"
                    )
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
        description="Consolidate accuracy variant metrics to 'Accuracy'"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without committing (default: False)",
    )

    args = parser.parse_args()

    logger.info("\n" + "=" * 80)
    logger.info("CONSOLIDATE ACCURACY VARIANTS MIGRATION")
    logger.info("=" * 80)
    logger.info(
        f"This script will consolidate '{VARIANTS[0]}' and '{VARIANTS[1]}' to '{TARGET_METRIC}'"
    )
    logger.info("=" * 80 + "\n")

    success = consolidate_accuracy_variants(dry_run=args.dry_run)

    if success and not args.dry_run:
        logger.info("\n✅ Migration completed successfully!")
        logger.info(
            f"The database now uses '{TARGET_METRIC}' for all accuracy metrics."
        )
    elif args.dry_run:
        logger.info("\n✓ Dry run completed. Run without --dry-run to apply changes.")
    else:
        logger.error("\n✗ Migration failed. Check the logs above for details.")
        sys.exit(1)


if __name__ == "__main__":
    main()
