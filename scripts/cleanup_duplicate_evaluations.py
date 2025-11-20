"""
Cleanup script for removing duplicate evaluation results for a paper.

This script:
1. Finds duplicate evaluation results (same paper_id, task_id, dataset_id, model_name)
2. Keeps the most recent one
3. Deletes the duplicates
4. Recalculates ranks for affected leaderboards
"""

import argparse
import logging
import sys
from collections import defaultdict
from pathlib import Path

from sqlalchemy.orm import Session

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.database.connection import db_manager
from backend.models.database import Evaluation as DBEvaluation, Paper as DBPaper
from backend.services.evaluation_service import EvaluationService

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_evaluations_for_paper(db: Session, arxiv_id: str) -> list[DBEvaluation]:
    """Get all evaluations for a paper."""
    paper = db.query(DBPaper).filter(DBPaper.arxiv_id == arxiv_id).first()
    if not paper:
        logger.error(f"Paper with ArXiv ID {arxiv_id} not found!")
        return []

    logger.info(f"Found paper: ID={paper.id}, Title: {paper.title}")

    evaluations = db.query(DBEvaluation).filter(DBEvaluation.paper_id == paper.id).all()

    logger.info(f"Found {len(evaluations)} evaluations for this paper")
    return evaluations


def find_duplicates(evaluations: list[DBEvaluation]) -> dict:
    """
    Find duplicate evaluations grouped by (paper_id, task_id, dataset_id, model_name).
    Also find duplicates by identical metrics (same task, dataset, and metric values).

    Returns:
        Dictionary mapping key to list of evaluation IDs
    """
    import json

    # First, group by exact model name match (original behavior)
    groups_by_model = defaultdict(list)
    groups_by_metrics = defaultdict(list)

    for eval_obj in evaluations:
        # Group by model name (exact duplicates)
        model_key = (
            eval_obj.paper_id,
            eval_obj.task_id,
            eval_obj.dataset_id,
            (eval_obj.model_name or "").strip(),
        )
        groups_by_model[model_key].append(eval_obj)

        # Group by identical metrics (same task, dataset, best_metric, and metric values)
        if eval_obj.metrics:
            metrics_str = json.dumps(eval_obj.metrics, sort_keys=True)
            metrics_key = (
                eval_obj.paper_id,
                eval_obj.task_id,
                eval_obj.dataset_id,
                eval_obj.best_metric or "",
                metrics_str,
            )
            groups_by_metrics[metrics_key].append(eval_obj)

    # Combine both types of duplicates
    duplicates = {}

    # Add exact model name duplicates
    for k, v in groups_by_model.items():
        if len(v) > 1:
            duplicates[k] = v

    # Add metrics-based duplicates (but exclude if already in model-based duplicates)
    for k, v in groups_by_metrics.items():
        if len(v) > 1:
            # Check if this group is already represented in model-based duplicates
            # If not, add it as a metrics-based duplicate
            paper_id, task_id, dataset_id, best_metric, metrics_str = k
            # Create a composite key for this group
            composite_key = (
                paper_id,
                task_id,
                dataset_id,
                f"metrics_match_{metrics_str}",
            )
            if composite_key not in duplicates:
                duplicates[composite_key] = v

    return duplicates


def choose_best_evaluation(evaluations: list[DBEvaluation]) -> DBEvaluation:
    """
    Choose the best evaluation from a list of duplicates.
    Priority:
    1. Most recent (by created_at or id)
    2. Has more metrics
    """
    # Sort by created_at (most recent first), then by id (fallback)
    return max(
        evaluations,
        key=lambda e: (
            e.created_at if e.created_at else e.id,
            len(e.metrics) if e.metrics else 0,
        ),
    )


def cleanup_evaluations(db: Session, arxiv_id: str, dry_run: bool = False) -> dict:
    """
    Clean up duplicate evaluations for a paper.

    Args:
        db: Database session
        arxiv_id: ArXiv ID of the paper
        dry_run: If True, only show what would be deleted without actually deleting

    Returns:
        Dictionary with cleanup statistics
    """
    stats = {
        "deleted_duplicates": 0,
        "affected_leaderboards": set(),
        "duplicates_found": 0,
    }

    service = EvaluationService(db)
    evaluations = get_evaluations_for_paper(db, arxiv_id)

    if not evaluations:
        logger.info("No evaluations found for this paper")
        return stats

    # Find duplicates
    logger.info("\n" + "=" * 80)
    logger.info("Finding duplicate evaluations...")
    logger.info("=" * 80)

    duplicates = find_duplicates(evaluations)
    stats["duplicates_found"] = len(duplicates)

    if not duplicates:
        logger.info("No duplicates found!")
        return stats

    logger.info(f"Found {len(duplicates)} groups with duplicates")

    # Remove duplicates
    for key, dup_evals in duplicates.items():
        paper_id, task_id, dataset_id, model_name = key
        logger.info(
            f"\nDuplicate group: task_id={task_id}, dataset_id={dataset_id}, "
            f"model='{model_name}', count={len(dup_evals)}"
        )

        # Choose the best evaluation to keep
        keep_eval = choose_best_evaluation(dup_evals)
        delete_evals = [e for e in dup_evals if e.id != keep_eval.id]

        logger.info(
            f"  Keeping evaluation {keep_eval.id} (created_at: {keep_eval.created_at})"
        )
        logger.info(f"    Metrics: {keep_eval.metrics}")

        for delete_eval in delete_evals:
            logger.info(
                f"  {'[DRY RUN] Would delete' if dry_run else 'Deleting'} evaluation {delete_eval.id} (created_at: {delete_eval.created_at})"
            )
            logger.info(f"    Metrics: {delete_eval.metrics}")
            if not dry_run:
                service.delete_evaluation(delete_eval.id)
                stats["deleted_duplicates"] += 1
                stats["affected_leaderboards"].add(
                    (delete_eval.task_id, delete_eval.dataset_id)
                )
            else:
                stats["deleted_duplicates"] += 1
                stats["affected_leaderboards"].add(
                    (delete_eval.task_id, delete_eval.dataset_id)
                )

    return stats


def recalculate_affected_ranks(db: Session, leaderboards: set) -> int:
    """Recalculate ranks for all affected leaderboards."""
    if not leaderboards:
        return 0

    logger.info("\n" + "=" * 80)
    logger.info(f"Recalculating ranks for {len(leaderboards)} leaderboards...")
    logger.info("=" * 80)

    service = EvaluationService(db)
    recalculated_count = 0

    for task_id, dataset_id in leaderboards:
        try:
            updated = service.recalculate_ranks(task_id=task_id, dataset_id=dataset_id)
            logger.info(
                f"✓ Recalculated ranks for task {task_id}, dataset {dataset_id}: "
                f"{updated} evaluations updated"
            )
            recalculated_count += 1
        except Exception as e:
            logger.error(
                f"✗ Failed to recalculate ranks for task {task_id}, dataset {dataset_id}: {e}"
            )

    return recalculated_count


def main():
    """Main cleanup function."""
    parser = argparse.ArgumentParser(
        description="Remove duplicate evaluation results for a paper"
    )
    parser.add_argument(
        "--arxiv_id",
        type=str,
        required=True,
        help="ArXiv ID of the paper to clean up",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting",
    )
    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info(
        f"CLEANUP: Duplicate evaluation results for paper {args.arxiv_id}"
        + (" (DRY RUN)" if args.dry_run else "")
    )
    logger.info("=" * 80)

    session = db_manager.session_local()

    try:
        # Perform cleanup
        stats = cleanup_evaluations(session, args.arxiv_id, dry_run=args.dry_run)

        # Recalculate ranks for affected leaderboards
        if stats["affected_leaderboards"] and not args.dry_run:
            recalculated_count = recalculate_affected_ranks(
                session, stats["affected_leaderboards"]
            )
            logger.info(f"\n✓ Recalculated {recalculated_count} leaderboards")

        # Summary
        logger.info("\n" + "=" * 80)
        logger.info("CLEANUP SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Duplicate groups found: {stats['duplicates_found']}")
        logger.info(
            f"Evaluations {'that would be' if args.dry_run else ''} deleted: "
            f"{stats['deleted_duplicates']}"
        )
        logger.info(f"Leaderboards affected: {len(stats['affected_leaderboards'])}")
        logger.info("=" * 80)
        if args.dry_run:
            logger.info("⚠️  DRY RUN COMPLETE - No changes made")
        else:
            logger.info("✅ CLEANUP COMPLETE")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"\n✗ Cleanup failed: {e}")
        import traceback

        traceback.print_exc()
        session.rollback()
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
