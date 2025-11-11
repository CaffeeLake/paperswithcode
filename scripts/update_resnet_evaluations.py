"""
Update ResNet evaluation results.

This script:
1. Removes the "ResNet ensemble (6 models, including two 152-layer)" evaluation
2. Adds a new "ResNet-152" evaluation with accuracy 79.57 on ImageNet-1k
"""

import sys
from backend.database.connection import db_manager
from backend.services.evaluation_service import EvaluationService
from backend.models.database import Evaluation

ARXIV_ID = "1512.03385"
PAPER_ID = 289
TASK_ID = 1  # Image Classification
DATASET_ID = 72  # ImageNet-1k


def main():
    """Update ResNet evaluations."""
    try:
        with db_manager.session_local() as db:
            service = EvaluationService(db)

            # Step 1: Find and delete the ensemble evaluation
            print("=" * 80)
            print("Step 1: Finding ensemble evaluation to delete")
            print("=" * 80)

            ensemble_eval = (
                db.query(Evaluation)
                .filter(
                    Evaluation.paper_id == PAPER_ID,
                    Evaluation.model_name
                    == "ResNet ensemble (6 models, including two 152-layer)",
                )
                .first()
            )

            if not ensemble_eval:
                print("⚠ Ensemble evaluation not found. Skipping deletion.")
            else:
                print(
                    f"Found ensemble evaluation: ID={ensemble_eval.id}, "
                    f"dataset_id={ensemble_eval.dataset_id}, "
                    f"metrics={ensemble_eval.metrics}"
                )
                print(f"Deleting evaluation ID {ensemble_eval.id}...")
                service.delete_evaluation(ensemble_eval.id)
                print("✓ Successfully deleted ensemble evaluation")

            # Step 2: Check if ResNet-152 evaluation already exists
            print("\n" + "=" * 80)
            print("Step 2: Checking for existing ResNet-152 evaluation")
            print("=" * 80)

            existing_eval = (
                db.query(Evaluation)
                .filter(
                    Evaluation.paper_id == PAPER_ID,
                    Evaluation.task_id == TASK_ID,
                    Evaluation.dataset_id == DATASET_ID,
                    Evaluation.model_name == "ResNet-152",
                )
                .first()
            )

            if existing_eval:
                print(
                    f"⚠ ResNet-152 evaluation already exists: ID={existing_eval.id}, "
                    f"metrics={existing_eval.metrics}"
                )
                print("Skipping creation.")
            else:
                # Step 3: Add new ResNet-152 evaluation
                print("\n" + "=" * 80)
                print("Step 3: Adding ResNet-152 evaluation")
                print("=" * 80)

                metrics = {"Accuracy": "79.57"}

                print("Creating evaluation:")
                print(f"  Paper ID: {PAPER_ID}")
                print(f"  Task ID: {TASK_ID}")
                print(f"  Dataset ID: {DATASET_ID}")
                print("  Model: ResNet-152")
                print(f"  Metrics: {metrics}")
                print("  Best Metric: Accuracy")

                new_evaluation = service.create_evaluation(
                    paper_id=PAPER_ID,
                    task_id=TASK_ID,
                    dataset_id=DATASET_ID,
                    model_name="ResNet-152",
                    metrics=metrics,
                    best_metric="Accuracy",
                )
                print(f"✓ Successfully created evaluation ID {new_evaluation.id}")

            # Step 4: Show final state
            print("\n" + "=" * 80)
            print("Step 4: Final evaluation state for ResNet paper")
            print("=" * 80)

            all_evals = (
                db.query(Evaluation)
                .filter(Evaluation.paper_id == PAPER_ID)
                .order_by(Evaluation.id)
                .all()
            )

            print(f"\nTotal evaluations: {len(all_evals)}")
            for eval_obj in all_evals:
                print(
                    f"  ID={eval_obj.id}: {eval_obj.model_name} "
                    f"(dataset_id={eval_obj.dataset_id}, task_id={eval_obj.task_id}, "
                    f"metrics={eval_obj.metrics})"
                )

            print("\n" + "=" * 80)
            print("SUCCESS: ResNet evaluations updated")
            print("=" * 80)

            return True

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
