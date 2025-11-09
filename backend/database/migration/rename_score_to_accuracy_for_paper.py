"""
Migration: Rename "score" to "Accuracy" for paper 2509.17765
Purpose: Standardize metric naming for Qwen3-Omni Technical Report
Date: 2025-01-XX

This script:
1. Updates all evaluations for paper 2509.17765 with "score" in metrics to use "Accuracy" instead
2. Updates best_metric field from "score" to "Accuracy"
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
    Paper as DBPaper,
)
from backend.services.evaluation_service import EvaluationService

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

ARXIV_ID = "2509.17765"


def rename_score_to_accuracy_for_paper(db: Session, arxiv_id: str) -> tuple[int, set]:
    """
    Rename "score" to "Accuracy" in evaluation metrics for a specific paper.

    Args:
        db: Database session
        arxiv_id: ArXiv ID of the paper

    Returns:
        Tuple of (updated_count, affected_leaderboards)
    """
    logger.info(f"Finding paper with ArXiv ID: {arxiv_id}")

    # Find the paper
    paper = db.query(DBPaper).filter(DBPaper.arxiv_id == arxiv_id).first()
    if not paper:
        logger.error(f"Paper with ArXiv ID {arxiv_id} not found!")
        return 0, set()

    logger.info(f"Found paper: ID={paper.id}, Title={paper.title}")

    # Find all evaluations for this paper that have "score" in metrics
    evaluations = (
        db.query(DBEvaluation)
        .filter(DBEvaluation.paper_id == paper.id)
        .filter(DBEvaluation.metrics.has_key("score"))
        .all()
    )

    logger.info(f"Found {len(evaluations)} evaluations with 'score' metric")

    updated_count = 0
    affected_leaderboards = set()

    for evaluation in evaluations:
        if evaluation.metrics and "score" in evaluation.metrics:
            # Store the value
            score_value = evaluation.metrics["score"]

            # Create a new dict with the updated key
            # This is necessary for SQLAlchemy to detect the change
            new_metrics = dict(evaluation.metrics)

            # If "Accuracy" doesn't exist or if we're replacing it
            if "Accuracy" not in new_metrics:
                new_metrics["Accuracy"] = score_value
            else:
                # If Accuracy already exists, keep the existing value
                logger.warning(
                    f"Evaluation {evaluation.id} already has 'Accuracy' metric, keeping existing value"
                )

            # Remove "score"
            del new_metrics["score"]

            # Reassign to trigger SQLAlchemy's change detection
            evaluation.metrics = new_metrics

            # Update best_metric if it was "score"
            if evaluation.best_metric == "score":
                evaluation.best_metric = "Accuracy"

            # Track this leaderboard for rank recalculation
            affected_leaderboards.add((evaluation.task_id, evaluation.dataset_id))

            updated_count += 1
            logger.info(
                f"Updated evaluation {evaluation.id}: "
                f"paper_id={evaluation.paper_id}, "
                f"task_id={evaluation.task_id}, "
                f"dataset_id={evaluation.dataset_id}, "
                f"Accuracy={score_value}"
            )

    if updated_count > 0:
        db.commit()
        logger.info(f"✓ Updated {updated_count} evaluations")
    else:
        logger.info("No evaluations found with 'score' metric")

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
    logger.info(f"MIGRATION: Rename 'score' to 'Accuracy' for paper {ARXIV_ID}")
    logger.info("=" * 80)

    session = db_manager.session_local()

    try:
        # Rename "score" to "accuracy" in evaluations
        updated_count, affected_leaderboards = rename_score_to_accuracy_for_paper(
            session, ARXIV_ID
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
