"""
Add DINOv3 Depth Estimation Evaluation Results

This script adds missing evaluation results for DINOv3 on depth estimation benchmarks
from Table 12 of the DINOv3 paper (arxiv: 2508.10104).

The results show DINOv3 performance on:
- NYUv2: ARel 4.3% (0.043), δ₁ 98.0% (0.980)
- KITTI: ARel 7.3% (0.073), δ₁ 96.7% (0.967)
- ETH3D: ARel 5.4% (0.054), δ₁ 97.5% (0.975)
- ScanNet: ARel 4.4% (0.044), δ₁ 98.1% (0.981)
- DIODE: ARel 25.6% (0.256), δ₁ 82.2% (0.822)

Note: Values are stored as decimals (0.043, 0.980) to match the standard format
used by other depth estimation models, even though the paper reports them as percentages.
"""

import sys
from typing import Dict, List
from backend.database.connection import db_manager
from backend.services.evaluation_service import EvaluationService
from backend.services.paper_service import PaperService
from backend.services.dataset_service import DatasetService
from backend.services.leaderboard_metric_service import LeaderboardMetricService
from backend.database.evaluations_setup.evaluation_helpers import (
    get_or_create_evaluation,
)
from backend.models.api import DatasetCreateRequest
from sqlalchemy.orm import Session

ARXIV_ID = "2508.10104"
TASK_ID = 16  # Depth estimation task ID

# Evaluation results from Table 12
# Note: The paper reports these as percentages (4.3%, 98.0%), but we store them
# as decimals (0.043, 0.980) to match the standard format used by other models.
EVALUATION_RESULTS = [
    {
        "dataset_name": "NYUv2",
        "dataset_id": 76,
        "metrics": {"AbsRel": "0.043", "delta1": "0.980"},
        "best_metric": "delta1",  # Higher is better
    },
    {
        "dataset_name": "KITTI",
        "dataset_id": 75,
        "metrics": {"AbsRel": "0.073", "delta1": "0.967"},
        "best_metric": "delta1",
    },
    {
        "dataset_name": "ETH3D",
        "dataset_id": 218,
        "metrics": {"AbsRel": "0.054", "delta1": "0.975"},
        "best_metric": "delta1",
    },
    {
        "dataset_name": "ScanNet",
        "dataset_id": None,  # Will be created if doesn't exist
        "metrics": {"AbsRel": "0.044", "delta1": "0.981"},
        "best_metric": "delta1",
    },
    {
        "dataset_name": "DIODE",
        "dataset_id": 240,
        "metrics": {"AbsRel": "0.256", "delta1": "0.822"},
        "best_metric": "delta1",
    },
]

MODEL_NAME = "DINOv3"


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


def get_or_create_scannet_dataset(db: Session, task_id: int) -> int:
    """Get or create ScanNet dataset."""
    print("Checking for ScanNet dataset...")

    dataset_service = DatasetService(db)

    # Try to find existing ScanNet dataset
    datasets = dataset_service.get_datasets(search="ScanNet", page_size=10)
    for dataset in datasets.results:
        if "scannet" in dataset.name.lower():
            print(f"✓ Found existing dataset: '{dataset.name}' (ID={dataset.id})")
            return dataset.id

    # Create ScanNet dataset if not found
    print("  Creating ScanNet dataset...")
    dataset_request = DatasetCreateRequest(
        name="ScanNet",
        full_name="ScanNet: Richly-annotated 3D Reconstructions of Indoor Scenes",
        description="Large-scale RGB-D video dataset containing 2.5M views in 1513 scenes with 3D camera poses, surface reconstructions, and instance-level semantic segmentations. Used for depth estimation evaluation.",
        url="http://www.scan-net.org/",
        task_ids=[task_id],
    )

    dataset = dataset_service.create_dataset(dataset_request)
    print(f"✓ Created dataset: '{dataset.name}' (ID={dataset.id})")
    return dataset.id


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
    print("Add DINOv3 Depth Estimation Evaluation Results")
    print("=" * 80)
    print()

    try:
        with db_manager.session_local() as db:
            # Step 1: Get paper ID
            print("Step 1: Looking up DINOv3 paper...")
            print("-" * 80)
            paper_id = get_paper_id(db, ARXIV_ID)
            print()

            # Step 2: Handle ScanNet dataset
            print("Step 2: Checking datasets...")
            print("-" * 80)
            for result in EVALUATION_RESULTS:
                if result["dataset_id"] is None:
                    result["dataset_id"] = get_or_create_scannet_dataset(db, TASK_ID)
            print()

            # Step 3: Register metrics for each dataset
            print("Step 3: Registering metrics for leaderboards...")
            print("-" * 80)
            metric_names = ["AbsRel", "delta1"]
            for result in EVALUATION_RESULTS:
                dataset_id = result["dataset_id"]
                dataset_name = result["dataset_name"]
                print(f"  {dataset_name} (ID: {dataset_id}):")
                register_metrics_if_needed(db, TASK_ID, dataset_id, metric_names)
            print()

            # Step 4: Process evaluation results
            print("Step 4: Processing evaluation results...")
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
                    f"[{i}/{len(EVALUATION_RESULTS)}] {dataset_name}: {best_metric}={metrics[best_metric]}"
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
            print("Step 5: Committing changes to database...")
            print("-" * 80)
            db.commit()
            print("✓ All changes committed successfully")
            print()

            # Step 6: Generate summary report
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
                        [f"{k}={v}" for k, v in eval_info["metrics"].items()]
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
