"""
Migration: Rename "Average WER" to "WER" in evaluations
Purpose: Standardize WER metric naming across the Open ASR Leaderboard
Date: 2025-10-22

This script:
1. Updates all evaluations with "Average WER" in metrics to use "WER" instead
2. Updates best_metric field from "Average WER" to "WER"
3. Removes the "Average WER" metric from the metrics table
4. Recalculates ranks for all affected leaderboards
"""

import logging
import sys
from pathlib import Path

from sqlalchemy.orm import Session

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.database.connection import db_manager
from backend.models.database import (
    Evaluation as DBEvaluation,
    Metric as DBMetric,
)
from backend.services.evaluation_service import EvaluationService

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def rename_average_wer_in_evaluations(db: Session) -> int:
    """
    Rename "Average WER" to "WER" in all evaluation metrics.

    Returns:
        Number of evaluations updated
    """
    logger.info("Finding evaluations with 'Average WER' metric...")

    # Find all evaluations that have "Average WER" in their metrics
    evaluations = db.query(DBEvaluation).all()

    updated_count = 0
    affected_leaderboards = set()

    for evaluation in evaluations:
        if evaluation.metrics and "Average WER" in evaluation.metrics:
            # Store the value
            avg_wer_value = evaluation.metrics["Average WER"]

            # Create a new dict with the updated key
            # This is necessary for SQLAlchemy to detect the change
            new_metrics = dict(evaluation.metrics)

            # If "WER" doesn't exist or if we're replacing it
            if "WER" not in new_metrics:
                new_metrics["WER"] = avg_wer_value

            # Remove "Average WER"
            del new_metrics["Average WER"]

            # Reassign to trigger SQLAlchemy's change detection
            evaluation.metrics = new_metrics

            # Update best_metric if it was "Average WER"
            if evaluation.best_metric == "Average WER":
                evaluation.best_metric = "WER"

            # Track this leaderboard for rank recalculation
            affected_leaderboards.add((evaluation.task_id, evaluation.dataset_id))

            updated_count += 1
            logger.info(
                f"Updated evaluation {evaluation.id}: "
                f"paper_id={evaluation.paper_id}, "
                f"task_id={evaluation.task_id}, "
                f"dataset_id={evaluation.dataset_id}, "
                f"WER={avg_wer_value}"
            )

    if updated_count > 0:
        db.commit()
        logger.info(f"✓ Updated {updated_count} evaluations")
    else:
        logger.info("No evaluations found with 'Average WER'")

    return updated_count, affected_leaderboards


def recalculate_affected_ranks(db: Session, leaderboards: set) -> int:
    """
    Recalculate ranks for all affected leaderboards.

    Args:
        leaderboards: Set of (task_id, dataset_id) tuples

    Returns:
        Number of leaderboards recalculated
    """
    logger.info(f"\nRecalculating ranks for {len(leaderboards)} leaderboards...")

    service = EvaluationService(db)
    recalculated_count = 0

    for task_id, dataset_id in leaderboards:
        try:
            updated = service.recalculate_ranks(task_id=task_id, dataset_id=dataset_id)
            logger.info(
                f"✓ Recalculated ranks for task {task_id}, dataset {dataset_id}: {updated} evaluations"
            )
            recalculated_count += 1
        except Exception as e:
            logger.error(
                f"✗ Failed to recalculate ranks for task {task_id}, dataset {dataset_id}: {e}"
            )

    return recalculated_count


def remove_average_wer_metric(db: Session) -> bool:
    """
    Remove the "Average WER" metric from the metrics table.

    Returns:
        True if removed, False if not found
    """
    logger.info("\nRemoving 'Average WER' metric from metrics table...")

    metric = db.query(DBMetric).filter(DBMetric.name == "Average WER").first()

    if metric:
        db.delete(metric)
        db.commit()
        logger.info("✓ Removed 'Average WER' metric")
        return True
    else:
        logger.info("'Average WER' metric not found in table")
        return False


def verify_wer_metric(db: Session) -> bool:
    """
    Verify that "WER" metric exists with correct direction.

    Returns:
        True if exists and correct, False otherwise
    """
    logger.info("\nVerifying 'WER' metric...")

    metric = db.query(DBMetric).filter(DBMetric.name == "WER").first()

    if not metric:
        logger.error("✗ 'WER' metric not found!")
        return False

    if metric.direction != "lower_is_better":
        logger.error(f"✗ 'WER' metric has wrong direction: {metric.direction}")
        return False

    logger.info(f"✓ 'WER' metric exists with correct direction: {metric.direction}")
    return True


def main():
    """Main migration function."""
    logger.info("=" * 80)
    logger.info("MIGRATION: Rename 'Average WER' to 'WER'")
    logger.info("=" * 80)

    session = db_manager.session_local()

    try:
        # Step 1: Verify WER metric exists
        if not verify_wer_metric(session):
            logger.error("\nMigration aborted: WER metric not properly configured")
            sys.exit(1)

        # Step 2: Rename "Average WER" to "WER" in evaluations
        updated_count, affected_leaderboards = rename_average_wer_in_evaluations(
            session
        )

        # Step 3: Recalculate ranks for affected leaderboards
        if affected_leaderboards:
            recalculated_count = recalculate_affected_ranks(
                session, affected_leaderboards
            )
            logger.info(f"\n✓ Recalculated {recalculated_count} leaderboards")

        # Step 4: Remove "Average WER" metric from metrics table
        remove_average_wer_metric(session)

        # Summary
        logger.info("\n" + "=" * 80)
        logger.info("MIGRATION SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Evaluations updated: {updated_count}")
        logger.info(f"Leaderboards recalculated: {len(affected_leaderboards)}")
        logger.info("=" * 80)
        logger.info("✅ MIGRATION COMPLETE")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"\n✗ Migration failed: {e}")
        import traceback

        traceback.print_exc()
        session.rollback()
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
