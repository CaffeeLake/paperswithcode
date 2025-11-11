"""
Cleanup script for paper 2505.09388 evaluation results.

This script:
1. Deletes duplicate evaluation results (keeping the best one)
2. Replaces "score" with "Accuracy" for scores on 0-100 scale
3. Removes evaluation results using "Elo" metric
4. Recalculates ranks for affected leaderboards
"""

import logging
import sys
from collections import defaultdict
from pathlib import Path

from sqlalchemy.orm import Session

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

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

ARXIV_ID = "2505.09388"


def is_score_0_100_scale(score_value: str) -> bool:
    """
    Check if a score value is on a 0-100 scale.

    Conservative approach: Only convert scores >= 20 to avoid accidentally
    converting scores on 0-10 scale (like WritingBench, AlignBench).
    Scores < 20 are likely on a different scale and should be kept as "score".
    """
    try:
        value = float(score_value)
        # Check if value is between 0 and 100
        if not (0 <= value <= 100):
            return False

        # Be conservative: values < 20 might be on 0-10 scale
        # Only convert scores >= 20 to avoid false positives
        return value >= 20
    except (ValueError, TypeError):
        return False


def get_evaluations_for_paper(db: Session, arxiv_id: str) -> list[DBEvaluation]:
    """Get all evaluations for a paper."""
    paper = db.query(DBPaper).filter(DBPaper.arxiv_id == arxiv_id).first()
    if not paper:
        logger.error(f"Paper with ArXiv ID {arxiv_id} not found!")
        return []

    logger.info(f"Found paper: ID={paper.id}, Title={paper.title}")

    evaluations = db.query(DBEvaluation).filter(DBEvaluation.paper_id == paper.id).all()

    logger.info(f"Found {len(evaluations)} evaluations for this paper")
    return evaluations


def find_duplicates(evaluations: list[DBEvaluation]) -> dict:
    """
    Find duplicate evaluations grouped by (paper_id, task_id, dataset_id, model_name).

    Returns:
        Dictionary mapping (paper_id, task_id, dataset_id, model_name) to list of evaluation IDs
    """
    groups = defaultdict(list)

    for eval_obj in evaluations:
        key = (
            eval_obj.paper_id,
            eval_obj.task_id,
            eval_obj.dataset_id,
            eval_obj.model_name or "",
        )
        groups[key].append(eval_obj)

    # Filter to only groups with duplicates
    duplicates = {k: v for k, v in groups.items() if len(v) > 1}

    return duplicates


def choose_best_evaluation(evaluations: list[DBEvaluation]) -> DBEvaluation:
    """
    Choose the best evaluation from a list of duplicates.
    Priority:
    1. Has "Accuracy" metric
    2. Has "score" metric (will be converted to Accuracy)
    3. Most recent
    """
    # Prefer evaluations with "Accuracy" metric
    accuracy_evals = [e for e in evaluations if e.metrics and "Accuracy" in e.metrics]
    if accuracy_evals:
        return accuracy_evals[0]

    # Then prefer evaluations with "score" metric
    score_evals = [e for e in evaluations if e.metrics and "score" in e.metrics]
    if score_evals:
        return score_evals[0]

    # Otherwise, return the most recent
    return max(evaluations, key=lambda e: e.created_at or e.id)


def cleanup_evaluations(db: Session, arxiv_id: str) -> dict:
    """
    Clean up evaluations for a paper.

    Returns:
        Dictionary with cleanup statistics
    """
    stats = {
        "deleted_elo": 0,
        "updated_score_to_accuracy": 0,
        "deleted_duplicates": 0,
        "affected_leaderboards": set(),
    }

    service = EvaluationService(db)
    evaluations = get_evaluations_for_paper(db, arxiv_id)

    if not evaluations:
        return stats

    # Step 1: Delete evaluations with "Elo" metric
    logger.info("\n" + "=" * 80)
    logger.info("Step 1: Deleting evaluations with 'Elo' metric")
    logger.info("=" * 80)

    elo_evaluations = [
        e
        for e in evaluations
        if e.metrics and ("Elo" in e.metrics or e.best_metric == "Elo")
    ]

    for eval_obj in elo_evaluations:
        logger.info(
            f"Deleting evaluation {eval_obj.id}: "
            f"task_id={eval_obj.task_id}, dataset_id={eval_obj.dataset_id}, "
            f"model={eval_obj.model_name}, metrics={eval_obj.metrics}"
        )
        service.delete_evaluation(eval_obj.id)
        stats["deleted_elo"] += 1
        stats["affected_leaderboards"].add((eval_obj.task_id, eval_obj.dataset_id))

    # Refresh evaluations list after deletions
    evaluations = get_evaluations_for_paper(db, arxiv_id)

    # Step 2: Update "score" to "Accuracy" for 0-100 scale scores
    logger.info("\n" + "=" * 80)
    logger.info("Step 2: Updating 'score' to 'Accuracy' for 0-100 scale scores")
    logger.info("=" * 80)

    for eval_obj in evaluations:
        if eval_obj.metrics and "score" in eval_obj.metrics:
            score_value = eval_obj.metrics["score"]

            if is_score_0_100_scale(score_value):
                # Create new metrics dict
                new_metrics = dict(eval_obj.metrics)

                # Add Accuracy if it doesn't exist
                if "Accuracy" not in new_metrics:
                    new_metrics["Accuracy"] = score_value

                # Remove score
                del new_metrics["score"]

                # Update evaluation
                eval_obj.metrics = new_metrics

                # Update best_metric if it was "score"
                if eval_obj.best_metric == "score":
                    eval_obj.best_metric = "Accuracy"

                logger.info(
                    f"Updated evaluation {eval_obj.id}: "
                    f"score={score_value} -> Accuracy={score_value}"
                )
                stats["updated_score_to_accuracy"] += 1
                stats["affected_leaderboards"].add(
                    (eval_obj.task_id, eval_obj.dataset_id)
                )

    if stats["updated_score_to_accuracy"] > 0:
        db.commit()
        logger.info(f"✓ Updated {stats['updated_score_to_accuracy']} evaluations")

    # Refresh evaluations list after updates
    evaluations = get_evaluations_for_paper(db, arxiv_id)

    # Step 3: Remove duplicates
    logger.info("\n" + "=" * 80)
    logger.info("Step 3: Removing duplicate evaluations")
    logger.info("=" * 80)

    duplicates = find_duplicates(evaluations)
    logger.info(f"Found {len(duplicates)} groups with duplicates")

    for key, dup_evals in duplicates.items():
        paper_id, task_id, dataset_id, model_name = key
        logger.info(
            f"\nDuplicate group: task_id={task_id}, dataset_id={dataset_id}, "
            f"model={model_name}, count={len(dup_evals)}"
        )

        # Choose the best evaluation to keep
        keep_eval = choose_best_evaluation(dup_evals)
        delete_evals = [e for e in dup_evals if e.id != keep_eval.id]

        logger.info(f"  Keeping evaluation {keep_eval.id}")
        for delete_eval in delete_evals:
            logger.info(
                f"  Deleting evaluation {delete_eval.id}: "
                f"metrics={delete_eval.metrics}, best_metric={delete_eval.best_metric}"
            )
            service.delete_evaluation(delete_eval.id)
            stats["deleted_duplicates"] += 1
            stats["affected_leaderboards"].add(
                (delete_eval.task_id, delete_eval.dataset_id)
            )

    return stats


def recalculate_affected_ranks(db: Session, leaderboards: set) -> int:
    """Recalculate ranks for all affected leaderboards."""
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
    logger.info("=" * 80)
    logger.info(f"CLEANUP: Evaluation results for paper {ARXIV_ID}")
    logger.info("=" * 80)

    session = db_manager.session_local()

    try:
        # Perform cleanup
        stats = cleanup_evaluations(session, ARXIV_ID)

        # Recalculate ranks for affected leaderboards
        if stats["affected_leaderboards"]:
            recalculated_count = recalculate_affected_ranks(
                session, stats["affected_leaderboards"]
            )
            logger.info(f"\n✓ Recalculated {recalculated_count} leaderboards")

        # Summary
        logger.info("\n" + "=" * 80)
        logger.info("CLEANUP SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Evaluations with 'Elo' metric deleted: {stats['deleted_elo']}")
        logger.info(
            f"Evaluations updated ('score' -> 'Accuracy'): "
            f"{stats['updated_score_to_accuracy']}"
        )
        logger.info(f"Duplicate evaluations deleted: {stats['deleted_duplicates']}")
        logger.info(f"Leaderboards affected: {len(stats['affected_leaderboards'])}")
        logger.info("=" * 80)
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
