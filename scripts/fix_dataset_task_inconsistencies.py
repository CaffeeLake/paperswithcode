#!/usr/bin/env python3
"""
Fix dataset-task inconsistencies in evaluations.

This script identifies evaluations that use incorrect tasks for their datasets
and provides options to fix them by updating to the correct task.
"""

import sys
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import Evaluation, Dataset, Task, TaskDataset, Paper


def get_evaluation_details(db: Session, dataset_id: int):
    """Get detailed information about all evaluations for a dataset."""

    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        return None

    # Get officially linked tasks
    official_task_links = (
        db.query(TaskDataset).filter(TaskDataset.dataset_id == dataset_id).all()
    )
    official_task_ids = {link.task_id for link in official_task_links}

    # Get all evaluations for this dataset
    evaluations = db.query(Evaluation).filter(Evaluation.dataset_id == dataset_id).all()

    # Group by task
    task_groups = {}
    for eval in evaluations:
        if eval.task_id not in task_groups:
            task = db.query(Task).filter(Task.id == eval.task_id).first()
            task_groups[eval.task_id] = {
                "task": task,
                "is_official": eval.task_id in official_task_ids,
                "evaluations": [],
            }

        paper = db.query(Paper).filter(Paper.id == eval.paper_id).first()
        task_groups[eval.task_id]["evaluations"].append(
            {
                "eval_id": eval.id,
                "paper_id": eval.paper_id,
                "arxiv_id": paper.arxiv_id if paper else None,
                "paper_title": paper.title if paper else None,
                "model_name": eval.model_name,
                "metrics": eval.metrics,
                "created_at": eval.created_at,
            }
        )

    return {
        "dataset": dataset,
        "official_task_ids": official_task_ids,
        "task_groups": task_groups,
    }


def print_dataset_report(db: Session, dataset_id: int):
    """Print a detailed report for a specific dataset."""

    details = get_evaluation_details(db, dataset_id)
    if not details:
        print(f"Dataset ID {dataset_id} not found")
        return

    dataset = details["dataset"]
    print("=" * 80)
    print(f"Dataset: {dataset.name}")
    print(f"Slug: {dataset.slug}")
    print(f"ID: {dataset.id}")
    print(f"URL: https://paperswithcode.co/dataset/{dataset.slug}")
    print("=" * 80)
    print()

    # Show official tasks
    if details["official_task_ids"]:
        print("✓ Officially linked tasks:")
        for task_id in details["official_task_ids"]:
            task = db.query(Task).filter(Task.id == task_id).first()
            if task:
                print(f"  - {task.name} (ID: {task_id})")
        print()

    # Show evaluations grouped by task
    print("Evaluations by task:")
    print()

    for task_id, group in sorted(details["task_groups"].items()):
        task = group["task"]
        is_official = group["is_official"]
        evals = group["evaluations"]

        status = "✓ CORRECT" if is_official else "✗ INCORRECT"
        print(f"{status} - {task.name} (ID: {task_id}) - {len(evals)} evaluation(s)")
        print()

        for i, eval_info in enumerate(evals, 1):
            print(f"  {i}. Evaluation ID: {eval_info['eval_id']}")
            print(f"     Paper: {eval_info['arxiv_id']}")
            print(f"     Title: {eval_info['paper_title'][:80]}...")
            print(f"     Model: {eval_info['model_name']}")
            print(f"     Metrics: {eval_info['metrics']}")
            print(f"     Created: {eval_info['created_at']}")
            print()

    print("-" * 80)
    print()


def fix_evaluations(
    db: Session,
    dataset_id: int,
    from_task_id: int,
    to_task_id: int,
    dry_run: bool = True,
):
    """
    Update evaluations for a dataset from one task to another.

    Args:
        db: Database session
        dataset_id: Dataset ID
        from_task_id: Current (incorrect) task ID
        to_task_id: Target (correct) task ID
        dry_run: If True, only show what would be changed
    """

    evaluations = (
        db.query(Evaluation)
        .filter(Evaluation.dataset_id == dataset_id, Evaluation.task_id == from_task_id)
        .all()
    )

    if not evaluations:
        print(
            f"No evaluations found with dataset_id={dataset_id} and task_id={from_task_id}"
        )
        return 0

    from_task = db.query(Task).filter(Task.id == from_task_id).first()
    to_task = db.query(Task).filter(Task.id == to_task_id).first()
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()

    print(
        f"{'[DRY RUN] ' if dry_run else ''}Updating {len(evaluations)} evaluation(s):"
    )
    print(f"  Dataset: {dataset.name}")
    print(f"  From task: {from_task.name} (ID: {from_task_id})")
    print(f"  To task: {to_task.name} (ID: {to_task_id})")
    print()

    for i, eval in enumerate(evaluations, 1):
        paper = db.query(Paper).filter(Paper.id == eval.paper_id).first()
        print(
            f"  {i}. Eval ID {eval.id} - Paper: {paper.arxiv_id if paper else 'Unknown'}"
        )

    if not dry_run:
        for eval in evaluations:
            eval.task_id = to_task_id
        db.commit()
        print()
        print(f"✓ Successfully updated {len(evaluations)} evaluation(s)")
    else:
        print()
        print("(Dry run - no changes made)")

    return len(evaluations)


if __name__ == "__main__":
    # Problematic datasets found:
    # 1. OCRBench (ID: 155) - Move 3 evals from Vision-Language Models (8) to OCR (4)
    # 2. LVBench (ID: 58) - Move 1 eval from Vision-Language Models (8) to Video-Language Models (9)
    # 3. LIBERO (ID: 108) - Move 1 eval from Vision-Language Models (8) to Robotics (11)

    with db_manager.session_local() as db:
        print("=" * 80)
        print("DATASET-TASK INCONSISTENCY DETAILS")
        print("=" * 80)
        print()

        # Print detailed reports for each problematic dataset
        for dataset_id in [155, 58, 108]:
            print_dataset_report(db, dataset_id)

        print()
        print("=" * 80)
        print("RECOMMENDED FIXES")
        print("=" * 80)
        print()
        print("To fix these inconsistencies, run the following commands:")
        print()
        print("# Fix OCRBench (move 3 evals from Vision-Language to OCR)")
        print(
            "python scripts/fix_dataset_task_inconsistencies.py --fix --dataset 155 --from-task 8 --to-task 4"
        )
        print()
        print("# Fix LVBench (move 1 eval from Vision-Language to Video-Language)")
        print(
            "python scripts/fix_dataset_task_inconsistencies.py --fix --dataset 58 --from-task 8 --to-task 9"
        )
        print()
        print("# Fix LIBERO (move 1 eval from Vision-Language to Robotics)")
        print(
            "python scripts/fix_dataset_task_inconsistencies.py --fix --dataset 108 --from-task 8 --to-task 11"
        )
        print()
        print("=" * 80)

        # Command-line interface for fixing
        if len(sys.argv) > 1 and "--fix" in sys.argv:
            try:
                import argparse

                parser = argparse.ArgumentParser()
                parser.add_argument("--fix", action="store_true", help="Apply fixes")
                parser.add_argument(
                    "--dataset", type=int, required=True, help="Dataset ID"
                )
                parser.add_argument(
                    "--from-task", type=int, required=True, help="Current task ID"
                )
                parser.add_argument(
                    "--to-task", type=int, required=True, help="Target task ID"
                )
                parser.add_argument(
                    "--dry-run", action="store_true", help="Dry run (no changes)"
                )

                args = parser.parse_args()

                print()
                print("=" * 80)
                print("APPLYING FIX")
                print("=" * 80)
                print()

                count = fix_evaluations(
                    db, args.dataset, args.from_task, args.to_task, dry_run=args.dry_run
                )

                if not args.dry_run and count > 0:
                    print()
                    print("✓ Fix applied successfully!")
                    print()
                    print("Verifying...")
                    print()
                    print_dataset_report(db, args.dataset)
            except Exception as e:
                print(f"Error: {e}")
                sys.exit(1)
