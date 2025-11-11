#!/usr/bin/env python3
"""
Find leaderboard results (evaluations) where the same dataset is used with different tasks.

This script identifies inconsistencies where evaluations for the same dataset
are associated with different tasks, which can lead to fragmented leaderboards.

Exception: Datasets that are legitimately linked to multiple tasks in the
task_datasets table (e.g., ImageNet for both image classification and generation).
"""

import sys
from collections import defaultdict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import Evaluation, Dataset, Task, TaskDataset


def find_dataset_task_inconsistencies(db: Session):
    """
    Find datasets that are used in evaluations with multiple different tasks.

    Returns:
        dict: Results with inconsistencies grouped by dataset
    """

    # Step 1: Get all unique (dataset_id, task_id) pairs from evaluations
    print("=" * 80)
    print("ANALYZING DATASET-TASK CONSISTENCY IN EVALUATIONS")
    print("=" * 80)
    print()

    # Query: For each dataset, find all unique tasks used in evaluations
    eval_dataset_tasks = db.execute(
        select(
            Evaluation.dataset_id,
            Evaluation.task_id,
            func.count(Evaluation.id).label("eval_count"),
        )
        .group_by(Evaluation.dataset_id, Evaluation.task_id)
        .order_by(Evaluation.dataset_id, Evaluation.task_id)
    ).all()

    # Group by dataset_id
    dataset_to_tasks = defaultdict(list)
    for dataset_id, task_id, eval_count in eval_dataset_tasks:
        dataset_to_tasks[dataset_id].append(
            {"task_id": task_id, "eval_count": eval_count}
        )

    # Step 2: Get datasets that are officially linked to multiple tasks
    # (These are exceptions - legitimate multi-task datasets)
    multi_task_datasets = db.execute(
        select(
            TaskDataset.dataset_id, func.count(TaskDataset.task_id).label("task_count")
        )
        .group_by(TaskDataset.dataset_id)
        .having(func.count(TaskDataset.task_id) > 1)
    ).all()

    legitimate_multi_task = {row.dataset_id for row in multi_task_datasets}

    print(
        f"Found {len(legitimate_multi_task)} datasets legitimately linked to multiple tasks"
    )
    print("(These will be marked as exceptions)")
    print()

    # Step 3: Find inconsistencies
    inconsistencies = []

    for dataset_id, tasks_info in dataset_to_tasks.items():
        if len(tasks_info) > 1:
            # This dataset is used with multiple tasks in evaluations

            # Get dataset details
            dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
            if not dataset:
                continue

            # Get task details for all tasks used
            task_details = []
            total_evals = 0
            for task_info in tasks_info:
                task = db.query(Task).filter(Task.id == task_info["task_id"]).first()
                if task:
                    task_details.append(
                        {
                            "task_id": task.id,
                            "task_name": task.name,
                            "task_slug": task.slug,
                            "eval_count": task_info["eval_count"],
                        }
                    )
                    total_evals += task_info["eval_count"]

            # Get officially linked tasks from task_datasets
            official_task_links = (
                db.query(TaskDataset).filter(TaskDataset.dataset_id == dataset_id).all()
            )
            official_task_ids = {link.task_id for link in official_task_links}

            inconsistencies.append(
                {
                    "dataset_id": dataset.id,
                    "dataset_name": dataset.name,
                    "dataset_slug": dataset.slug,
                    "is_legitimate_multi_task": dataset_id in legitimate_multi_task,
                    "tasks_in_evaluations": task_details,
                    "total_evaluations": total_evals,
                    "official_task_ids": official_task_ids,
                    "evaluation_task_ids": {t["task_id"] for t in task_details},
                }
            )

    return inconsistencies


def print_report(inconsistencies):
    """Print a detailed report of inconsistencies."""

    if not inconsistencies:
        print("✓ No inconsistencies found!")
        print("All datasets use consistent tasks across evaluations.")
        return

    # Sort by total evaluations (descending) to prioritize high-impact issues
    inconsistencies.sort(key=lambda x: x["total_evaluations"], reverse=True)

    # Separate legitimate multi-task datasets from true inconsistencies
    legitimate = [inc for inc in inconsistencies if inc["is_legitimate_multi_task"]]
    problematic = [
        inc for inc in inconsistencies if not inc["is_legitimate_multi_task"]
    ]

    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total datasets with multiple tasks in evaluations: {len(inconsistencies)}")
    print(f"  - Legitimate multi-task datasets: {len(legitimate)}")
    print(f"  - Problematic inconsistencies: {len(problematic)}")
    print()

    if problematic:
        print("=" * 80)
        print("PROBLEMATIC INCONSISTENCIES")
        print("=" * 80)
        print("These datasets should use a consistent task across all evaluations:")
        print()

        for i, inc in enumerate(problematic, 1):
            print(f"{i}. Dataset: {inc['dataset_name']}")
            print(f"   Slug: {inc['dataset_slug']}")
            print(f"   Dataset ID: {inc['dataset_id']}")
            print(f"   Total evaluations: {inc['total_evaluations']}")
            print(f"   URL: https://paperswithcode.co/dataset/{inc['dataset_slug']}")
            print()
            print("   Tasks used in evaluations:")
            for task in sorted(
                inc["tasks_in_evaluations"], key=lambda x: x["eval_count"], reverse=True
            ):
                print(
                    f"     - {task['task_name']} (ID: {task['task_id']}) - {task['eval_count']} evaluations"
                )
            print()

            if inc["official_task_ids"]:
                official_tasks = (
                    db.query(Task).filter(Task.id.in_(inc["official_task_ids"])).all()
                )
                print("   Officially linked to tasks:")
                for task in official_tasks:
                    print(f"     - {task.name} (ID: {task.id})")
            else:
                print("   ⚠ Not officially linked to any tasks in task_datasets table!")
            print()
            print("-" * 80)
            print()

    if legitimate:
        print("=" * 80)
        print("LEGITIMATE MULTI-TASK DATASETS (Exceptions)")
        print("=" * 80)
        print("These datasets are intentionally linked to multiple tasks:")
        print()

        for i, inc in enumerate(legitimate, 1):
            print(f"{i}. Dataset: {inc['dataset_name']} (ID: {inc['dataset_id']})")
            print("   Tasks used:")
            for task in inc["tasks_in_evaluations"]:
                print(f"     - {task['task_name']} - {task['eval_count']} evaluations")
            print()


def generate_sql_queries(inconsistencies):
    """Generate SQL queries to view problematic evaluations."""

    problematic = [
        inc for inc in inconsistencies if not inc["is_legitimate_multi_task"]
    ]

    if not problematic:
        return

    print("=" * 80)
    print("SQL QUERIES TO INVESTIGATE EVALUATIONS")
    print("=" * 80)
    print()

    for inc in problematic[:5]:  # Show queries for top 5
        print(f"-- {inc['dataset_name']} (ID: {inc['dataset_id']})")
        print("SELECT ")
        print("  e.id as eval_id,")
        print("  p.arxiv_id,")
        print("  p.title,")
        print("  t.name as task_name,")
        print("  t.id as task_id,")
        print("  e.model_name,")
        print("  e.metrics")
        print("FROM evaluations e")
        print("JOIN papers p ON e.paper_id = p.id")
        print("JOIN tasks t ON e.task_id = t.id")
        print(f"WHERE e.dataset_id = {inc['dataset_id']}")
        print("ORDER BY t.id, e.created_at DESC")
        print("LIMIT 20;")
        print()


if __name__ == "__main__":
    with db_manager.session_local() as db:
        inconsistencies = find_dataset_task_inconsistencies(db)
        print_report(inconsistencies)
        print()
        generate_sql_queries(inconsistencies)

        # Exit with error code if there are problematic inconsistencies
        problematic_count = sum(
            1 for inc in inconsistencies if not inc["is_legitimate_multi_task"]
        )
        if problematic_count > 0:
            print()
            print(f"⚠ Found {problematic_count} datasets with inconsistent task usage")
            sys.exit(1)
        else:
            print()
            print("✓ All clear!")
            sys.exit(0)
