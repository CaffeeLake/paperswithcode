"""
Consolidate ImageNet-1k evaluation metrics to "Top-1".

This script updates all ImageNet-1k evaluation results to use "Top-1" as the metric name
instead of "Accuracy" or "Top-1 Accuracy", since all results are top-1 accuracy.
"""

import sys
from backend.database.connection import db_manager
from backend.services.evaluation_service import EvaluationService
from backend.services.leaderboard_metric_service import LeaderboardMetricService
from backend.models.database import Evaluation, Dataset, Metric

DATASET_ID = 72  # ImageNet-1k dataset ID
NEW_METRIC_NAME = "Top-1"


def ensure_top1_metric(db):
    """Ensure Top-1 metric exists in the database."""
    metric = db.query(Metric).filter(Metric.name == NEW_METRIC_NAME).first()

    if not metric:
        print(f"Creating metric: {NEW_METRIC_NAME}")
        metric = Metric(
            name=NEW_METRIC_NAME,
            full_name="Top-1 Accuracy",
            direction="higher_is_better",
            description="Top-1 accuracy (single best prediction)",
        )
        db.add(metric)
        db.commit()
        db.refresh(metric)
        print(f"✓ Created metric: {NEW_METRIC_NAME} (ID: {metric.id})")
    else:
        print(f"✓ Metric '{NEW_METRIC_NAME}' already exists (ID: {metric.id})")

    return metric


def get_imagenet_task_id(db):
    """Get the task ID for ImageNet-1k evaluations."""
    # Get a sample evaluation to find the task ID
    sample_eval = (
        db.query(Evaluation).filter(Evaluation.dataset_id == DATASET_ID).first()
    )
    if sample_eval:
        return sample_eval.task_id
    return None


def consolidate_imagenet_metrics():
    """Consolidate ImageNet-1k evaluation metrics to Top-1."""
    db = db_manager.session_local()
    try:
        # Verify dataset exists
        imagenet = db.query(Dataset).filter(Dataset.id == DATASET_ID).first()
        if not imagenet:
            print(f"✗ ImageNet-1k dataset (ID {DATASET_ID}) not found")
            return False

        print(f"Found ImageNet-1k dataset: {imagenet.name} (ID: {imagenet.id})")
        print()

        # Get all evaluations for ImageNet-1k
        evaluations = (
            db.query(Evaluation).filter(Evaluation.dataset_id == DATASET_ID).all()
        )

        print(f"Found {len(evaluations)} evaluations to update:")
        print("-" * 80)

        evaluation_service = EvaluationService(db)
        task_id = get_imagenet_task_id(db)

        updated_count = 0
        for eval_obj in evaluations:
            old_metrics = eval_obj.metrics.copy()
            old_best_metric = eval_obj.best_metric

            # Determine the value to use for Top-1
            top1_value = None
            if "Top-1 Accuracy" in old_metrics:
                top1_value = old_metrics["Top-1 Accuracy"]
            elif "Accuracy" in old_metrics:
                top1_value = old_metrics["Accuracy"]

            if not top1_value:
                print(
                    f"  Evaluation ID {eval_obj.id}: No Accuracy or Top-1 Accuracy metric found, skipping"
                )
                print(f"    Current metrics: {old_metrics}")
                continue

            # Update metrics to use Top-1
            new_metrics = {"Top-1": top1_value}

            print(f"  Evaluation ID {eval_obj.id} (Model: {eval_obj.model_name}):")
            print(f"    Old metrics: {old_metrics}")
            print(f"    Old best_metric: {old_best_metric}")
            print(f"    New metrics: {new_metrics}")
            print("    New best_metric: Top-1")

            # Update the evaluation
            evaluation_service.update_evaluation(
                evaluation_id=eval_obj.id,
                metrics=new_metrics,
                best_metric="Top-1",
            )

            print("    ✓ Updated successfully")
            print()
            updated_count += 1

        # Register Top-1 metric for ImageNet-1k leaderboard if needed
        if task_id:
            print("Registering Top-1 metric for ImageNet-1k leaderboard...")
            metric_service = LeaderboardMetricService(db)
            allowed_metrics = metric_service.get_allowed_metrics_for_leaderboard(
                task_id, DATASET_ID
            )

            if NEW_METRIC_NAME not in allowed_metrics:
                try:
                    metric_service.add_metric_to_leaderboard(
                        task_id, DATASET_ID, NEW_METRIC_NAME
                    )
                    print("✓ Registered Top-1 metric for ImageNet-1k leaderboard")
                except ValueError as e:
                    if "already linked" in str(e):
                        print("✓ Top-1 metric already registered")
                    else:
                        print(f"⚠ Could not register metric: {e}")
            else:
                print("✓ Top-1 metric already registered")
            print()

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
    print("Consolidate ImageNet-1k Evaluation Metrics")
    print("=" * 80)
    print()

    try:
        success = consolidate_imagenet_metrics()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"Failed to consolidate metrics: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
