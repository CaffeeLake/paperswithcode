"""
Migration: Standardize "accuracy" to "Accuracy" (capitalized) across all evaluations
Purpose: Ensure consistent metric naming - all accuracy metrics should be capitalized
Date: 2025-01-XX

This script:
1. Updates all evaluations with lowercase "accuracy" in metrics to use "Accuracy" instead
2. Updates best_metric field from "accuracy" to "Accuracy"
3. Recalculates ranks for all affected leaderboards
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
)
from backend.services.evaluation_service import EvaluationService

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def standardize_accuracy_to_capitalized(db: Session) -> tuple[int, set]:
    """
    Rename lowercase "accuracy" to capitalized "Accuracy" in all evaluation metrics.

    Args:
        db: Database session

    Returns:
        Tuple of (updated_count, affected_leaderboards)
    """
    logger.info("Finding evaluations with lowercase 'accuracy' metric...")

    # Find all evaluations that have lowercase "accuracy" in metrics
    evaluations = (
        db.query(DBEvaluation).filter(DBEvaluation.metrics.has_key("accuracy")).all()
    )

    logger.info(
        f"Found {len(evaluations)} evaluations with lowercase 'accuracy' metric"
    )

    updated_count = 0
    affected_leaderboards = set()

    for evaluation in evaluations:
        if evaluation.metrics and "accuracy" in evaluation.metrics:
            # Store the value
            accuracy_value = evaluation.metrics["accuracy"]

            # Create a new dict with the updated key
            # This is necessary for SQLAlchemy to detect the change
            new_metrics = dict(evaluation.metrics)

            # If "Accuracy" doesn't exist, add it
            if "Accuracy" not in new_metrics:
                new_metrics["Accuracy"] = accuracy_value
            else:
                # If Accuracy already exists, keep the existing value (don't overwrite)
                logger.warning(
                    f"Evaluation {evaluation.id} already has 'Accuracy' metric, keeping existing value"
                )

            # Remove lowercase "accuracy"
            del new_metrics["accuracy"]

            # Reassign to trigger SQLAlchemy's change detection
            evaluation.metrics = new_metrics

            # Update best_metric if it was lowercase "accuracy"
            if evaluation.best_metric == "accuracy":
                evaluation.best_metric = "Accuracy"

            # Track this leaderboard for rank recalculation
            affected_leaderboards.add((evaluation.task_id, evaluation.dataset_id))

            updated_count += 1
            logger.info(
                f"Updated evaluation {evaluation.id}: "
                f"paper_id={evaluation.paper_id}, "
                f"task_id={evaluation.task_id}, "
                f"dataset_id={evaluation.dataset_id}, "
                f"Accuracy={accuracy_value}"
            )

    if updated_count > 0:
        db.commit()
        logger.info(f"✓ Updated {updated_count} evaluations")
    else:
        logger.info("No evaluations found with lowercase 'accuracy' metric")

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


def main():
    """Main migration function."""
    logger.info("=" * 80)
    logger.info("MIGRATION: Standardize 'accuracy' to 'Accuracy' (capitalized)")
    logger.info("=" * 80)

    session = db_manager.session_local()

    try:
        # Standardize "accuracy" to "Accuracy" in all evaluations
        updated_count, affected_leaderboards = standardize_accuracy_to_capitalized(
            session
        )

        # Recalculate ranks for affected leaderboards
        if affected_leaderboards:
            recalculated_count = recalculate_affected_ranks(
                session, affected_leaderboards
            )
            logger.info(f"\n✓ Recalculated {recalculated_count} leaderboards")

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
