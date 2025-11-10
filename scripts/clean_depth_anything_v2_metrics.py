#!/usr/bin/env python3
"""
Update Depth Anything V2 evaluations to only include AbsRel and delta1 metrics.

Removes extra metrics like RMSE, log10, delta2, delta3, RMSE log from
depth estimation evaluations. Keeps Accuracy for DA-2K and mIoU for segmentation.
"""

import sys
from backend.database.connection import db_manager
from backend.services.evaluation_service import EvaluationService
from backend.models.database import Evaluation, Dataset
from sqlalchemy import select

PAPER_ID = 32904  # Depth Anything V2
TASK_ID_DEPTH = 16  # Depth estimation


def main():
    """Update evaluations to only include AbsRel and delta1."""
    db = db_manager.session_local()
    try:
        evaluation_service = EvaluationService(db)

        # Get all depth estimation evaluations for this paper
        evals = db.execute(
            select(Evaluation, Dataset.name)
            .join(Dataset, Evaluation.dataset_id == Dataset.id)
            .where(Evaluation.paper_id == PAPER_ID)
            .where(Evaluation.task_id == TASK_ID_DEPTH)
            .order_by(Evaluation.id)
        ).all()

        print("=" * 100)
        print(
            "Updating Depth Anything V2 evaluations to only include AbsRel and delta1"
        )
        print("=" * 100)
        print()

        updated_count = 0
        skipped_count = 0

        for eval_obj, dataset_name in evals:
            current_metrics = eval_obj.metrics.copy()

            # Determine which metrics to keep
            if dataset_name == "DA-2K":
                # Keep Accuracy for DA-2K benchmark
                metrics_to_keep = {
                    k: v for k, v in current_metrics.items() if k == "Accuracy"
                }
                if len(metrics_to_keep) == len(current_metrics):
                    print(
                        f"⊙ Skipping {eval_obj.model_name} on {dataset_name} (already correct)"
                    )
                    skipped_count += 1
                    continue
            else:
                # Keep only AbsRel and delta1 for depth estimation
                metrics_to_keep = {
                    k: v
                    for k, v in current_metrics.items()
                    if k in ["AbsRel", "delta1"]
                }

                # If no AbsRel or delta1, skip (shouldn't happen but be safe)
                if not metrics_to_keep:
                    print(
                        f"⚠ Skipping {eval_obj.model_name} on {dataset_name} (no AbsRel/delta1 found)"
                    )
                    skipped_count += 1
                    continue

            # Check if update is needed
            if metrics_to_keep == current_metrics:
                print(
                    f"⊙ Skipping {eval_obj.model_name} on {dataset_name} (already correct)"
                )
                skipped_count += 1
                continue

            # Update the evaluation
            print(f"Updating ID {eval_obj.id}: {eval_obj.model_name} on {dataset_name}")
            print(f"  Before: {current_metrics}")
            print(f"  After:  {metrics_to_keep}")

            evaluation_service.update_evaluation(
                evaluation_id=eval_obj.id, metrics=metrics_to_keep
            )

            print("  ✓ Updated successfully")
            print()
            updated_count += 1

        print("=" * 100)
        print("SUMMARY")
        print("=" * 100)
        print(f"Updated: {updated_count} evaluations")
        print(f"Skipped: {skipped_count} evaluations (already correct)")
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
