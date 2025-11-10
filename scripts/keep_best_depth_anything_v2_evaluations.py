#!/usr/bin/env python3
"""
Keep only the best evaluation result per dataset for Depth Anything V2.

For each dataset, identifies the best performing model based on best_metric
and removes all other model variants.
"""

import sys
from backend.database.connection import db_manager
from backend.services.evaluation_service import EvaluationService
from backend.models.database import Evaluation, Dataset
from sqlalchemy import select

PAPER_ID = 32904  # Depth Anything V2
TASK_ID_DEPTH = 16  # Depth estimation


def find_best_evaluation(evaluations):
    """Find the best evaluation based on best_metric value."""
    if not evaluations:
        return None

    # Get the first evaluation to determine best_metric
    first_eval = evaluations[0]
    best_metric = first_eval.best_metric

    # Determine if higher or lower is better
    # For depth estimation: delta1 and Accuracy are higher-is-better
    # AbsRel is lower-is-better, but we use best_metric which should be delta1 or Accuracy
    higher_is_better = best_metric in ["delta1", "Accuracy"]

    best_eval = None
    best_value = None

    for eval_obj in evaluations:
        if best_metric not in eval_obj.metrics:
            continue

        value = float(eval_obj.metrics[best_metric])

        if best_value is None:
            best_value = value
            best_eval = eval_obj
        elif higher_is_better and value > best_value:
            best_value = value
            best_eval = eval_obj
        elif not higher_is_better and value < best_value:
            best_value = value
            best_eval = eval_obj

    return best_eval


def main():
    """Keep only best evaluation per dataset."""
    db = db_manager.session_local()
    try:
        evaluation_service = EvaluationService(db)

        # Get all depth estimation evaluations for this paper
        evals = db.execute(
            select(Evaluation, Dataset.name)
            .join(Dataset, Evaluation.dataset_id == Dataset.id)
            .where(Evaluation.paper_id == PAPER_ID)
            .where(Evaluation.task_id == TASK_ID_DEPTH)
            .order_by(Dataset.name, Evaluation.model_name)
        ).all()

        print("=" * 100)
        print("Keeping only best evaluation per dataset for Depth Anything V2")
        print("=" * 100)
        print()

        # Group by dataset
        datasets = {}
        for eval_obj, dataset_name in evals:
            if dataset_name not in datasets:
                datasets[dataset_name] = []
            datasets[dataset_name].append(eval_obj)

        kept_count = 0
        deleted_count = 0

        for dataset_name in sorted(datasets.keys()):
            models = datasets[dataset_name]

            if len(models) == 1:
                print(f"⊙ {dataset_name}: Only 1 evaluation, keeping it")
                kept_count += 1
                continue

            # Find best evaluation
            best_eval = find_best_evaluation(models)

            if not best_eval:
                print(f"⚠ {dataset_name}: Could not determine best evaluation")
                continue

            print(f"{dataset_name}:")
            print(f"  Keeping: ID {best_eval.id} - {best_eval.model_name}")
            print(
                f"    {best_eval.best_metric}={best_eval.metrics.get(best_eval.best_metric)}"
            )

            # Delete all others
            to_delete = [e for e in models if e.id != best_eval.id]
            print(f"  Deleting {len(to_delete)} other evaluations:")

            for eval_obj in to_delete:
                print(
                    f"    - ID {eval_obj.id}: {eval_obj.model_name} ({eval_obj.best_metric}={eval_obj.metrics.get(eval_obj.best_metric)})"
                )
                evaluation_service.delete_evaluation(eval_obj.id)
                deleted_count += 1

            kept_count += 1
            print()

        print("=" * 100)
        print("SUMMARY")
        print("=" * 100)
        print(f"Kept: {kept_count} evaluations (best per dataset)")
        print(f"Deleted: {deleted_count} evaluations")
        print("=" * 100)

        return True

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
