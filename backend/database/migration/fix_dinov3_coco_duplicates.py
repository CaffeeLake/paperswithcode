"""
Check and fix duplicate evaluation results for DINOv3 paper on COCO val2017.

This script:
1. Finds the DINOv3 paper (arxiv_id: 2508.10104)
2. Finds COCO val2017 dataset
3. Checks for duplicate evaluations (same paper_id, task_id, dataset_id, model_name)
4. Removes duplicates, keeping the most recent one
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import logging
from sqlalchemy import text
from collections import defaultdict

from backend.database.connection import DatabaseManager
from backend.services.paper_service import PaperService
from backend.services.evaluation_service import EvaluationService

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

db_manager = DatabaseManager()

ARXIV_ID = "2508.10104"
DATASET_NAME = "COCO val2017"


def find_duplicates(session):
    """Find duplicate evaluations for DINOv3 paper on COCO val2017."""

    # Get paper_id
    paper_service = PaperService(session)
    try:
        paper = paper_service.get_paper_by_arxiv_id(ARXIV_ID)
        paper_id = int(paper.id)
        logger.info(f"Found paper: {paper.title} (ID: {paper_id})")
    except Exception as e:
        logger.error(f"Paper not found: {e}")
        return None, None, []

    # Get dataset_id for COCO val2017
    result = session.execute(
        text("""
        SELECT id, name FROM datasets
        WHERE name = :name OR slug = :slug
        LIMIT 1
        """),
        {"name": DATASET_NAME, "slug": "coco-val2017"},
    )
    dataset_row = result.fetchone()
    if not dataset_row:
        logger.error(f"Dataset '{DATASET_NAME}' not found")
        return paper_id, None, []

    dataset_id = dataset_row[0]
    logger.info(f"Found dataset: {dataset_row[1]} (ID: {dataset_id})")

    # Get all evaluations for this paper on this dataset
    result = session.execute(
        text("""
        SELECT
            e.id,
            e.paper_id,
            e.task_id,
            e.dataset_id,
            e.model_name,
            e.metrics,
            e.best_metric,
            e.best_rank,
            e.created_at,
            t.name as task_name
        FROM evaluations e
        JOIN tasks t ON e.task_id = t.id
        WHERE e.paper_id = :paper_id AND e.dataset_id = :dataset_id
        ORDER BY e.created_at DESC
        """),
        {"paper_id": paper_id, "dataset_id": dataset_id},
    )

    evaluations = result.fetchall()
    logger.info(
        f"\nFound {len(evaluations)} evaluation(s) for this paper on {DATASET_NAME}"
    )

    # Show all evaluations
    logger.info("\nAll evaluations found:")
    for eval_row in evaluations:
        logger.info(
            f"  ID: {eval_row[0]}, Task: {eval_row[9]} (ID: {eval_row[2]}), "
            f"Model: {eval_row[4]}, Metrics: {eval_row[5]}, "
            f"Best Metric: {eval_row[6]}, Best Rank: {eval_row[7]}, "
            f"Created: {eval_row[8]}"
        )

    # Group by (task_id, model_name) to find duplicates (exact match)
    groups_exact = defaultdict(list)
    for eval_row in evaluations:
        key = (eval_row[2], eval_row[4])  # (task_id, model_name)
        groups_exact[key].append(
            {
                "id": eval_row[0],
                "paper_id": eval_row[1],
                "task_id": eval_row[2],
                "dataset_id": eval_row[3],
                "model_name": eval_row[4],
                "metrics": eval_row[5],
                "best_metric": eval_row[6],
                "best_rank": eval_row[7],
                "created_at": eval_row[8],
                "task_name": eval_row[9],
            }
        )

    # Also check for case-insensitive model name duplicates
    groups_ci = defaultdict(list)
    for eval_row in evaluations:
        key = (
            eval_row[2],
            eval_row[4].lower() if eval_row[4] else None,
        )  # (task_id, model_name_lower)
        groups_ci[key].append(
            {
                "id": eval_row[0],
                "paper_id": eval_row[1],
                "task_id": eval_row[2],
                "dataset_id": eval_row[3],
                "model_name": eval_row[4],
                "metrics": eval_row[5],
                "best_metric": eval_row[6],
                "best_rank": eval_row[7],
                "created_at": eval_row[8],
                "task_name": eval_row[9],
            }
        )

    # Find duplicates (groups with more than 1 evaluation)
    duplicates = []

    # Check exact matches first
    for key, evals in groups_exact.items():
        if len(evals) > 1:
            duplicates.append(
                {
                    "task_id": key[0],
                    "model_name": key[1],
                    "evaluations": evals,
                    "type": "exact_match",
                }
            )

    # Check case-insensitive matches (but skip if already found as exact match)
    for key, evals in groups_ci.items():
        if len(evals) > 1:
            # Check if this is already in duplicates (exact match)
            already_found = any(
                d["task_id"] == key[0] and d["model_name"].lower() == key[1]
                for d in duplicates
            )
            if not already_found:
                duplicates.append(
                    {
                        "task_id": key[0],
                        "model_name": key[1],  # Use original case from first eval
                        "evaluations": evals,
                        "type": "case_insensitive_match",
                    }
                )

    return paper_id, dataset_id, duplicates


def fix_duplicates(session, paper_id, dataset_id, duplicates, dry_run=True):
    """Fix duplicate evaluations by keeping the most recent one."""

    if not duplicates:
        logger.info("No duplicates found!")
        return 0

    logger.info(f"\nFound {len(duplicates)} duplicate group(s):")
    for dup in duplicates:
        logger.info(f"  Task ID {dup['task_id']}, Model: {dup['model_name']}")
        logger.info(f"    {len(dup['evaluations'])} duplicate evaluation(s)")
        for eval_obj in dup["evaluations"]:
            logger.info(
                f"      ID: {eval_obj['id']}, Created: {eval_obj['created_at']}, "
                f"Metrics: {eval_obj['metrics']}, Best Rank: {eval_obj['best_rank']}"
            )

    if dry_run:
        logger.info("\n" + "=" * 80)
        logger.info("DRY RUN MODE - No changes will be committed")
        logger.info("=" * 80)
        return 0

    logger.info("\n" + "=" * 80)
    logger.info("FIXING DUPLICATES")
    logger.info("=" * 80)

    deleted_count = 0
    affected_leaderboards = set()

    for dup in duplicates:
        # Sort by created_at (most recent first)
        evals = sorted(dup["evaluations"], key=lambda x: x["created_at"], reverse=True)

        # Keep the first (most recent), delete the rest
        keep_eval = evals[0]
        delete_evals = evals[1:]

        logger.info(
            f"\nKeeping evaluation ID {keep_eval['id']} (created: {keep_eval['created_at']})"
        )
        logger.info(f"Deleting {len(delete_evals)} duplicate(s):")

        for eval_obj in delete_evals:
            logger.info(f"  - ID {eval_obj['id']} (created: {eval_obj['created_at']})")
            affected_leaderboards.add((eval_obj["task_id"], eval_obj["dataset_id"]))

            # Delete the evaluation
            session.execute(
                text("DELETE FROM evaluations WHERE id = :eval_id"),
                {"eval_id": eval_obj["id"]},
            )
            deleted_count += 1

    session.commit()
    logger.info(f"\nDeleted {deleted_count} duplicate evaluation(s)")

    # Recalculate ranks for affected leaderboards
    if affected_leaderboards:
        logger.info("\nRecalculating ranks for affected leaderboards...")
        evaluation_service = EvaluationService(session)
        recalculated_count = 0

        for task_id, ds_id in affected_leaderboards:
            try:
                evaluation_service.recalculate_ranks(
                    task_id=task_id,
                    dataset_id=ds_id,
                )
                recalculated_count += 1
            except Exception as e:
                logger.warning(
                    f"Failed to recalculate ranks for task_id={task_id}, dataset_id={ds_id}: {e}"
                )

        logger.info(f"Recalculated ranks for {recalculated_count} leaderboard(s)")

    return deleted_count


def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Check and fix duplicate evaluations for DINOv3 paper on COCO val2017"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without committing (default: False)",
    )

    args = parser.parse_args()

    session = db_manager.session_local()

    try:
        logger.info("=" * 80)
        logger.info("CHECKING FOR DUPLICATE EVALUATIONS")
        logger.info("=" * 80)
        logger.info(f"Paper ArXiv ID: {ARXIV_ID}")
        logger.info(f"Dataset: {DATASET_NAME}")
        logger.info("=" * 80 + "\n")

        paper_id, dataset_id, duplicates = find_duplicates(session)

        if paper_id is None:
            logger.error("Could not find paper or dataset")
            return

        deleted_count = fix_duplicates(
            session, paper_id, dataset_id, duplicates, dry_run=args.dry_run
        )

        if args.dry_run:
            logger.info(
                "\n✓ Dry run completed. Run without --dry-run to apply changes."
            )
        else:
            logger.info("\n✅ Duplicate removal completed successfully!")
            logger.info(f"Removed {deleted_count} duplicate evaluation(s)")

    except Exception as e:
        logger.error(f"\n✗ Error: {e}")
        import traceback

        traceback.print_exc()
        session.rollback()
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
