"""
Script to remove all evaluations for a specific paper (by ArXiv ID).

Usage:
    uv run --env-file backend/keys.env python remove_evaluations_for_paper.py 2201.03545
"""

import sys
import logging
from backend.database.connection import db_manager
from backend.services.paper_service import PaperService
from backend.services.evaluation_service import EvaluationService
from backend.models.database import Evaluation as DBEvaluation

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def remove_evaluations_for_paper(arxiv_id: str, dry_run: bool = False):
    """Remove all evaluations for a specific paper.

    Args:
        arxiv_id: ArXiv ID of the paper
        dry_run: If True, only print what would be deleted without making changes
    """
    session = db_manager.session_local()

    try:
        # Get paper by ArXiv ID
        paper_service = PaperService(session)
        paper = paper_service.get_paper_by_arxiv_id(arxiv_id)

        if not paper:
            logger.error(f"Paper with ArXiv ID {arxiv_id} not found.")
            return

        paper_id = paper.id
        logger.info(f"Found paper: {paper.title} (ID: {paper_id})")

        # Get all evaluations for this paper
        evaluations = (
            session.query(DBEvaluation).filter(DBEvaluation.paper_id == paper_id).all()
        )

        logger.info(f"Total evaluations found: {len(evaluations)}")

        if len(evaluations) == 0:
            logger.info("No evaluations found for this paper.")
            return

        # Show what will be deleted
        logger.info("\nEvaluations to be deleted:")
        logger.info("=" * 80)
        for eval_obj in evaluations:
            logger.info(
                f"  ID {eval_obj.id}: "
                f"Task={eval_obj.task_id}, "
                f"Dataset={eval_obj.dataset_id}, "
                f"Metrics={eval_obj.metrics}, "
                f"Best Metric={eval_obj.best_metric}"
            )

        if dry_run:
            logger.info(
                f"\nDRY RUN MODE: Would delete {len(evaluations)} evaluation(s)"
            )
            return

        # Delete evaluations using the service (which handles rank recalculation)
        evaluation_service = EvaluationService(session)
        deleted_count = 0

        for eval_obj in evaluations:
            try:
                evaluation_service.delete_evaluation(eval_obj.id)
                deleted_count += 1
                logger.info(f"✓ Deleted evaluation ID {eval_obj.id}")
            except Exception as e:
                logger.error(f"✗ Failed to delete evaluation ID {eval_obj.id}: {e}")

        logger.info(f"\n✓ Successfully deleted {deleted_count} evaluation(s)")

    except Exception as e:
        logger.error(f"Error: {e}")
        session.rollback()
    finally:
        session.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python remove_evaluations_for_paper.py <arxiv_id> [--dry-run]")
        sys.exit(1)

    arxiv_id = sys.argv[1]
    dry_run = "--dry-run" in sys.argv or "-d" in sys.argv

    if dry_run:
        logger.info("Running in DRY RUN mode - no changes will be made")

    remove_evaluations_for_paper(arxiv_id, dry_run=dry_run)
