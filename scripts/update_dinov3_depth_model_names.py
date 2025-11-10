"""
Update model_name for DINOv3 depth estimation evaluations.

This script updates the model_name for all depth estimation evaluation results
to "DINOv3 + Depth Anything V2" to reflect that these results combine DINOv3
with Depth Anything V2 as mentioned in Table 12 of the DINOv3 paper.
"""

import sys
from backend.database.connection import db_manager
from backend.services.evaluation_service import EvaluationService
from backend.models.database import Evaluation

PAPER_ID = 52358  # DINOv3 paper ID
TASK_ID = 16  # Depth estimation task ID
NEW_MODEL_NAME = "DINOv3 + Depth Anything V2"


def update_depth_evaluation_model_names():
    """Update model_name for all depth estimation evaluations."""
    db = db_manager.session_local()
    try:
        evaluation_service = EvaluationService(db)

        # Find all depth estimation evaluations for DINOv3
        evaluations = (
            db.query(Evaluation)
            .filter(Evaluation.paper_id == PAPER_ID, Evaluation.task_id == TASK_ID)
            .all()
        )

        print(f"Found {len(evaluations)} depth estimation evaluations to update:")
        print("-" * 80)

        updated_count = 0
        for eval_obj in evaluations:
            old_name = eval_obj.model_name
            dataset_id = eval_obj.dataset_id

            print(f"  Evaluation ID {eval_obj.id} (Dataset ID {dataset_id}):")
            print(f"    Old model_name: {old_name}")
            print(f"    New model_name: {NEW_MODEL_NAME}")

            # Update the evaluation
            evaluation_service.update_evaluation(
                evaluation_id=eval_obj.id, model_name=NEW_MODEL_NAME
            )

            print("    ✓ Updated successfully")
            print()
            updated_count += 1

        print("=" * 80)
        print(f"✓ Successfully updated {updated_count} evaluations")
        print("=" * 80)

        return True

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback

        traceback.print_exc()
        db.rollback()
        return False
    finally:
        db.close()


def main():
    """Main entry point."""
    print("=" * 80)
    print("Update DINOv3 Depth Estimation Model Names")
    print("=" * 80)
    print()

    try:
        success = update_depth_evaluation_model_names()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"Failed to update model names: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
