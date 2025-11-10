#!/usr/bin/env python3
"""
Fix best_metric for Depth Anything V2 evaluations.

The ViT-G models on KITTI and NYUv2 have AbsRel as best_metric, but should
have delta1 (higher is better) to be consistent with other models and the paper.
"""

import sys
from backend.database.connection import db_manager
from backend.services.evaluation_service import EvaluationService

# Evaluation IDs to fix (ViT-G on KITTI and NYUv2)
EVALUATIONS_TO_FIX = [
    (484, "Depth Anything V2 (ViT-G)", "KITTI"),
    (485, "Depth Anything V2 (ViT-G)", "NYUv2"),
]


def main():
    """Fix best_metric for specified evaluations."""
    db = db_manager.session_local()
    try:
        evaluation_service = EvaluationService(db)

        print("=" * 80)
        print("Fixing best_metric for Depth Anything V2 ViT-G evaluations")
        print("=" * 80)
        print()

        for eval_id, model_name, dataset_name in EVALUATIONS_TO_FIX:
            print(f"Evaluation ID {eval_id}: {model_name} on {dataset_name}")

            # Get current evaluation
            eval_obj = evaluation_service.get_evaluation(eval_id)
            print(f"  Current best_metric: {eval_obj.best_metric}")
            print(f"  Metrics: {eval_obj.metrics}")

            # Update to delta1
            evaluation_service.update_evaluation(
                evaluation_id=eval_id, best_metric="delta1"
            )

            print("  ✓ Updated best_metric to: delta1")
            print()

        print("=" * 80)
        print("✓ Successfully updated all evaluations")
        print("=" * 80)

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
