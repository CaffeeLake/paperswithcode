"""
Add DINOv3 ImageNet Variant Evaluation Results

This script adds evaluation results for DINOv3 on ImageNet variant datasets
from Table 7 of the DINOv3 paper (arxiv: 2508.10104).

The results show DINOv3 (ViT 7B/16) performance on:
- ImageNet V2: 81.4 (Top-1 accuracy)
- ImageNet-R: 91.1 (Top-1 accuracy)
- ImageNet-S: 71.3 (Top-1 accuracy)
- ImageNet-Hard: Note - The table shows ImageNet-A (86.9), ImageNet-C (19.6),
  and ImageNet-O (79.0) separately, but we'll add ImageNet-Hard if applicable.
"""

import sys
from typing import Dict, List
from backend.database.connection import db_manager
from backend.services.evaluation_service import EvaluationService
from backend.services.paper_service import PaperService
from backend.services.leaderboard_metric_service import LeaderboardMetricService
from backend.database.evaluations_setup.evaluation_helpers import (
    get_or_create_evaluation,
)
from backend.models.database import Metric
from sqlalchemy.orm import Session

ARXIV_ID = "2508.10104"
TASK_ID = 1  # Image Classification task ID
PAPER_ID = 52358  # DINOv3 paper ID

# Dataset IDs we just added
DATASET_IDS = {
    "ImageNet V2": 278,
    "ImageNet-R": 279,
    "ImageNet-S": 280,
    "ImageNet-Hard": 281,
}

# Evaluation results from Table 7 (DINOv3 ViT 7B/16)
# Note: The paper reports these as percentages (81.4%, 91.1%, etc.)
EVALUATION_RESULTS = [
    {
        "dataset_name": "ImageNet V2",
        "dataset_id": DATASET_IDS["ImageNet V2"],
        "metrics": {"Top-1": "81.4"},
        "best_metric": "Top-1",
    },
    {
        "dataset_name": "ImageNet-R",
        "dataset_id": DATASET_IDS["ImageNet-R"],
        "metrics": {"Top-1": "91.1"},
        "best_metric": "Top-1",
    },
    {
        "dataset_name": "ImageNet-S",
        "dataset_id": DATASET_IDS["ImageNet-S"],
        "metrics": {"Top-1": "71.3"},
        "best_metric": "Top-1",
    },
    # Note: ImageNet-Hard in the table shows ImageNet-A (86.9), ImageNet-C (19.6),
    # and ImageNet-O (79.0) separately. We'll skip ImageNet-Hard for now since
    # it's a meta-dataset and the table shows separate results for A, C, O.
]

MODEL_NAME = "DINOv3"


def ensure_top1_metric(db: Session):
    """Ensure Top-1 metric exists in the database."""
    metric = db.query(Metric).filter(Metric.name == "Top-1").first()

    if not metric:
        print("Creating metric: Top-1")
        metric = Metric(
            name="Top-1",
            full_name="Top-1 Accuracy",
            direction="higher_is_better",
            description="Top-1 accuracy (single best prediction)",
        )
        db.add(metric)
        db.commit()
        db.refresh(metric)
        print(f"✓ Created metric: Top-1 (ID: {metric.id})")
    else:
        print(f"✓ Metric 'Top-1' already exists (ID: {metric.id})")

    return metric


def get_paper_id(db: Session, arxiv_id: str) -> int:
    """Get paper ID by ArXiv ID."""
    print(f"Looking up paper with ArXiv ID: {arxiv_id}...")

    paper_service = PaperService(db)
    try:
        paper = paper_service.get_paper_by_arxiv_id(arxiv_id)
        print(f"✓ Found paper: '{paper.title}' (ID={paper.id})")
        return int(paper.id)
    except Exception as e:
        print(f"✗ Error finding paper: {e}")
        raise


def verify_dataset(db: Session, dataset_id: int, dataset_name: str) -> bool:
    """Verify dataset exists."""
    from backend.models.database import Dataset

    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if dataset:
        print(f"  ✓ Found dataset: '{dataset.name}' (ID={dataset.id})")
        return True
    else:
        print(f"  ✗ Dataset not found: {dataset_name} (ID={dataset_id})")
        return False


def register_metrics_if_needed(
    db: Session, task_id: int, dataset_id: int, metric_names: List[str]
):
    """Register metrics for a leaderboard if not already registered."""
    metric_service = LeaderboardMetricService(db)
    allowed_metrics = metric_service.get_allowed_metrics_for_leaderboard(
        task_id, dataset_id
    )

    metrics_to_add = [m for m in metric_names if m not in allowed_metrics]

    if metrics_to_add:
        print(f"  Registering metrics: {', '.join(metrics_to_add)}")
        for metric_name in metrics_to_add:
            try:
                metric_service.add_metric_to_leaderboard(
                    task_id, dataset_id, metric_name
                )
                print(f"    ✓ Registered {metric_name}")
            except ValueError as e:
                if "already linked" in str(e):
                    print(f"    ✓ {metric_name} already registered")
                else:
                    print(f"    ⚠ Could not register {metric_name}: {e}")
    else:
        print("  ✓ All metrics already registered")


def create_or_update_evaluation(
    db: Session,
    paper_id: int,
    task_id: int,
    dataset_id: int,
    metrics: Dict[str, str],
    best_metric: str,
    model_name: str,
) -> bool:
    """
    Create or update an evaluation entry for a model result.
    Uses get_or_create_evaluation which merges metrics if evaluation already exists.

    Returns:
        True if successful, False otherwise
    """
    try:
        # Use the helper function that merges metrics for existing evaluations
        evaluation = get_or_create_evaluation(
            db=db,
            paper_id=paper_id,
            task_id=task_id,
            dataset_id=dataset_id,
            model_name=model_name,
            metrics=metrics,
            best_metric=best_metric,
            merge_metrics=True,  # Merge with existing metrics if evaluation exists
        )

        # Recalculate ranks after creating/updating
        evaluation_service = EvaluationService(db)
        evaluation_service.recalculate_ranks(
            task_id=task_id,
            dataset_id=dataset_id,
            metric_name=best_metric,
        )

        print(f"  ✓ Created/updated evaluation ID: {evaluation.id}")
        return True
    except Exception as e:
        print(f"  ✗ Error creating/updating evaluation: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Main execution function."""
    print("=" * 80)
    print("Add DINOv3 ImageNet Variant Evaluation Results")
    print("=" * 80)
    print()

    try:
        with db_manager.session_local() as db:
            # Step 1: Ensure Top-1 metric exists
            print("Step 1: Ensuring Top-1 metric exists...")
            print("-" * 80)
            ensure_top1_metric(db)
            print()

            # Step 2: Get paper ID
            print("Step 2: Looking up DINOv3 paper...")
            print("-" * 80)
            paper_id = get_paper_id(db, ARXIV_ID)
            print()

            # Step 3: Verify datasets exist
            print("Step 3: Verifying datasets...")
            print("-" * 80)
            for result in EVALUATION_RESULTS:
                verify_dataset(db, result["dataset_id"], result["dataset_name"])
            print()

            # Step 4: Register metrics for each dataset
            print("Step 4: Registering metrics for leaderboards...")
            print("-" * 80)
            metric_names = ["Top-1"]
            for result in EVALUATION_RESULTS:
                dataset_id = result["dataset_id"]
                dataset_name = result["dataset_name"]
                print(f"  {dataset_name} (ID: {dataset_id}):")
                register_metrics_if_needed(db, TASK_ID, dataset_id, metric_names)
            print()

            # Step 5: Process evaluation results
            print("Step 5: Processing evaluation results...")
            print("-" * 80)
            print(f"Total datasets to process: {len(EVALUATION_RESULTS)}")
            print()

            created_evaluations = []
            failed_evaluations = []

            for i, result in enumerate(EVALUATION_RESULTS, 1):
                dataset_name = result["dataset_name"]
                dataset_id = result["dataset_id"]
                metrics = result["metrics"]
                best_metric = result["best_metric"]

                print(
                    f"[{i}/{len(EVALUATION_RESULTS)}] {dataset_name}: {best_metric}={metrics[best_metric]}%"
                )

                # Create or update evaluation
                if create_or_update_evaluation(
                    db, paper_id, TASK_ID, dataset_id, metrics, best_metric, MODEL_NAME
                ):
                    created_evaluations.append(
                        {
                            "dataset": dataset_name,
                            "metrics": metrics,
                            "best_metric": best_metric,
                        }
                    )
                else:
                    failed_evaluations.append(
                        {"dataset": dataset_name, "reason": "Creation failed"}
                    )

                print()

            # Commit all changes
            print("Step 6: Committing changes to database...")
            print("-" * 80)
            db.commit()
            print("✓ All changes committed successfully")
            print()

            # Step 7: Generate summary report
            print("=" * 80)
            print("SUMMARY REPORT")
            print("=" * 80)
            print()

            print(f"Total datasets processed: {len(EVALUATION_RESULTS)}")
            print(f"Evaluations created successfully: {len(created_evaluations)}")
            print(f"Failed evaluations: {len(failed_evaluations)}")
            print()

            if created_evaluations:
                print("✓ Successfully Created Evaluations:")
                print("-" * 80)
                for eval_info in created_evaluations:
                    metrics_str = ", ".join(
                        [f"{k}={v}%" for k, v in eval_info["metrics"].items()]
                    )
                    print(
                        f"  • {eval_info['dataset']}: {metrics_str} (best: {eval_info['best_metric']})"
                    )
                print()

            if failed_evaluations:
                print("⚠ Failed Evaluations:")
                print("-" * 80)
                for fail_info in failed_evaluations:
                    print(f"  • {fail_info['dataset']}: {fail_info['reason']}")
                print()

            print("=" * 80)
            print("✓ Script completed successfully!")
            print("=" * 80)

            return 0

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
