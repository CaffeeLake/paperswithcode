"""
Script to remove duplicate evaluation results for a specific paper.

Duplicates are identified by:
- paper_id
- task_id
- dataset_id
- model_name
- best_metric

When duplicates are found, we keep the most complete one (based on metrics count and created_at).
"""

from collections import defaultdict
from backend.database.connection import db_manager
from backend.models.database import Evaluation as DBEvaluation
from backend.services.paper_service import PaperService
from backend.services.evaluation_service import EvaluationService


def find_duplicate_groups(evaluations):
    """Group evaluations by duplicate key.

    Two evaluations are considered duplicates if they have:
    - Same paper_id, task_id, dataset_id, best_metric
    - Same metrics values (same metric keys and values)

    Model name variations are allowed (e.g., "IN-22K" vs "ImageNet-22K")
    """
    groups = defaultdict(list)

    for eval_obj in evaluations:
        # Create a key for duplicate detection based on metrics content
        # Normalize metrics dict to a sorted tuple for comparison
        metrics_items = (
            sorted(eval_obj.metrics.items()) if eval_obj.metrics else tuple()
        )
        best_metric = eval_obj.best_metric or ""

        key = (
            eval_obj.paper_id,
            eval_obj.task_id,
            eval_obj.dataset_id,
            tuple(metrics_items),  # Use tuple of sorted items for comparison
            best_metric,
        )
        groups[key].append(eval_obj)

    # Return only groups with duplicates
    duplicates = {k: v for k, v in groups.items() if len(v) > 1}
    return duplicates


def select_best_evaluation(evaluations):
    """Select the best evaluation from a group of duplicates.

    Criteria (in order):
    1. Most metrics (most complete)
    2. Most recent created_at
    """

    def score(eval_obj):
        metrics_count = len(eval_obj.metrics) if eval_obj.metrics else 0
        # Higher score is better
        return (metrics_count, eval_obj.created_at)

    return max(evaluations, key=score)


def remove_duplicates_for_paper(arxiv_id: str, dry_run: bool = True):
    """Remove duplicate evaluations for a specific paper.

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
            print(f"Paper with ArXiv ID {arxiv_id} not found.")
            return

        paper_id = paper.id
        print(f"Found paper: {paper.title} (ID: {paper_id})")

        # Get all evaluations for this paper directly from database
        evaluations = (
            session.query(DBEvaluation).filter(DBEvaluation.paper_id == paper_id).all()
        )
        print(f"Total evaluations found: {len(evaluations)}")

        if len(evaluations) == 0:
            print("No evaluations found for this paper.")
            return

        # Find duplicate groups
        duplicate_groups = find_duplicate_groups(evaluations)

        if not duplicate_groups:
            print("No duplicate evaluations found.")
            return

        print(f"\nFound {len(duplicate_groups)} duplicate groups:")
        print("=" * 80)

        total_to_delete = 0

        for key, group in duplicate_groups.items():
            paper_id_key, task_id, dataset_id, metrics_items, best_metric = key

            # Reconstruct metrics dict from tuple
            metrics_dict = dict(metrics_items) if metrics_items else {}

            print("\nDuplicate group:")
            print(f"  Paper ID: {paper_id_key}")
            print(f"  Task ID: {task_id}")
            print(f"  Dataset ID: {dataset_id}")
            print(f"  Metrics: {metrics_dict}")
            print(f"  Best Metric: {best_metric or '(None)'}")
            print(f"  Count: {len(group)}")

            # Select the best evaluation to keep
            best_eval = select_best_evaluation(group)
            print(f"\n  Keeping evaluation ID {best_eval.id}:")
            print(f"    Metrics: {best_eval.metrics}")
            print(
                f"    Metrics count: {len(best_eval.metrics) if best_eval.metrics else 0}"
            )
            print(f"    Created at: {best_eval.created_at}")

            # Mark others for deletion
            to_delete = [e for e in group if e.id != best_eval.id]
            total_to_delete += len(to_delete)

            print(f"\n  Deleting {len(to_delete)} evaluation(s):")
            for eval_obj in to_delete:
                print(
                    f"    - ID {eval_obj.id}: metrics={eval_obj.metrics}, created_at={eval_obj.created_at}"
                )

            if not dry_run:
                # Delete the duplicates
                for eval_obj in to_delete:
                    db_eval = (
                        session.query(DBEvaluation)
                        .filter(DBEvaluation.id == eval_obj.id)
                        .first()
                    )
                    if db_eval:
                        session.delete(db_eval)
                        print(f"    ✓ Deleted evaluation ID {eval_obj.id}")

                session.commit()
                print("  ✓ Committed deletions for this group")

        print("\n" + "=" * 80)
        if dry_run:
            print(
                f"\nDRY RUN MODE: Would delete {total_to_delete} duplicate evaluation(s)"
            )
            print("Run with --no-dry-run to actually delete duplicates")
        else:
            print(f"\n✓ Successfully deleted {total_to_delete} duplicate evaluation(s)")

            # Recalculate ranks for affected leaderboards
            print("\nRecalculating ranks for affected leaderboards...")
            evaluation_service = EvaluationService(session)
            for key, group in duplicate_groups.items():
                paper_id_key, task_id, dataset_id, metrics_items, best_metric = key
                best_eval = select_best_evaluation(group)

                if best_eval.best_metric:
                    evaluation_service.recalculate_ranks(
                        task_id=best_eval.task_id,
                        dataset_id=best_eval.dataset_id,
                        metric_name=best_eval.best_metric,
                    )
                    print(
                        f"  ✓ Recalculated ranks for task {task_id}, dataset {dataset_id}, metric {best_eval.best_metric}"
                    )

    except Exception as e:
        session.rollback()
        print(f"Error: {str(e)}")
        import traceback

        traceback.print_exc()
    finally:
        session.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Remove duplicate evaluation results for a specific paper"
    )
    parser.add_argument(
        "arxiv_id",
        type=str,
        help="ArXiv ID of the paper (e.g., 2201.03545)",
    )
    parser.add_argument(
        "--no-dry-run",
        action="store_true",
        help="Actually delete duplicates (default is dry-run mode)",
    )

    args = parser.parse_args()

    dry_run = not args.no_dry_run

    remove_duplicates_for_paper(args.arxiv_id, dry_run=dry_run)
