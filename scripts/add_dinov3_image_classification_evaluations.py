"""
Add missing DINOv3 image classification evaluation results.

This script adds evaluation results from Tables 7, 8, and 9 for datasets that exist
in the database, and reports which datasets are missing.
"""

import sys
from typing import Optional, List
from backend.database.connection import db_manager
from backend.services.evaluation_service import EvaluationService
from backend.services.leaderboard_metric_service import LeaderboardMetricService
from backend.models.database import Dataset as DBDataset, Evaluation as DBEvaluation
from backend.utils.dataset_utils import find_dataset_by_name

PAPER_ID = 52358  # DINOv3 paper ID
MODEL_NAME = "DINOv3 (7B)"
TASK_ID = 1  # Image Classification task

# Evaluation results to add (only for datasets that might exist)
# Note: ImageNet Val, ImageNet RealL, Hard Obj., iNat21, and Met (GAP) already exist
EVALUATION_RESULTS = [
    # Table 7: ImageNet variants (if they exist)
    {
        "dataset_names": ["ImageNet V2", "ImageNet-V2", "ImageNetV2"],
        "metrics": {"Top-1": "81.4"},
        "best_metric": "Top-1",
    },
    {
        "dataset_names": ["ImageNet-R", "ImageNet-Rendition-R", "Rendition R"],
        "metrics": {"Top-1": "91.1"},
        "best_metric": "Top-1",
    },
    {
        "dataset_names": ["ImageNet-Rendition-S", "ImageNet-Sketch", "Rendition S"],
        "metrics": {"Top-1": "71.3"},
        "best_metric": "Top-1",
    },
    {
        "dataset_names": ["ImageNet-A", "ImageNet-Adversarial"],
        "metrics": {"Top-1": "86.9"},
        "best_metric": "Top-1",
    },
    {
        "dataset_names": ["ImageNet-C", "ImageNet-Corruption"],
        "metrics": {"Top-1": "19.6"},
        "best_metric": "Top-1",
    },
    # Table 8: Finegrained classification
    {
        "dataset_names": ["Places", "Places365", "Places-365"],
        "metrics": {"Top-1": "70.0"},
        "best_metric": "Top-1",
    },
    {
        "dataset_names": ["iNaturalist 2018", "iNaturalist18", "iNat18", "iNat-2018"],
        "metrics": {"Top-1": "85.6"},
        "best_metric": "Top-1",
    },
    # Table 9: Instance recognition
    {
        "dataset_names": ["Oxford Buildings", "Oxford-Hard", "Oxford-H"],
        "metrics": {"mAP": "60.7"},
        "best_metric": "mAP",
    },
    {
        "dataset_names": ["Paris Buildings", "Paris-Hard", "Paris-H"],
        "metrics": {"mAP": "87.1"},
        "best_metric": "mAP",
    },
    {
        "dataset_names": ["AmsterTime", "Amsterdam"],
        "metrics": {"mAP": "56.5"},
        "best_metric": "mAP",
    },
]

# Datasets that are known to be missing (for reporting)
MISSING_DATASETS = [
    {
        "name": "ImageNet Val",
        "value": "88.4",
        "metric": "Top-1",
        "note": "Already exists as ImageNet-1k",
    },
    {"name": "ImageNet V2", "value": "81.4", "metric": "Top-1"},
    {
        "name": "ImageNet RealL",
        "value": "90.4",
        "metric": "Top-1",
        "note": "Already exists as ImageNet Real",
    },
    {"name": "Rendition R", "value": "91.1", "metric": "Top-1"},
    {"name": "Rendition S", "value": "71.3", "metric": "Top-1"},
    {"name": "Hard A", "value": "86.9", "metric": "Top-1"},
    {"name": "Hard C↓", "value": "19.6", "metric": "Top-1"},
    {
        "name": "Hard Obj.",
        "value": "79.0",
        "metric": "Top-1",
        "note": "Already exists as ObjectNet",
    },
    {
        "name": "Fine-S",
        "value": "93.0",
        "metric": "Top-1",
        "note": "Average over 12 datasets",
    },
    {"name": "Places", "value": "70.0", "metric": "Top-1"},
    {"name": "iNat18", "value": "85.6", "metric": "Top-1"},
    {
        "name": "iNat21",
        "value": "89.8",
        "metric": "Top-1",
        "note": "Already exists as iNaturalist 2021",
    },
    {"name": "Oxford-H", "value": "60.7", "metric": "mAP"},
    {"name": "Paris-H", "value": "87.1", "metric": "mAP"},
    {
        "name": "Met (GAP)",
        "value": "55.4",
        "metric": "GAP",
        "note": "Already exists as Met (Metropolitan Museum artworks)",
    },
    {"name": "AmsterTime", "value": "56.5", "metric": "mAP"},
]


def find_dataset_by_variations(db, name_variations: List[str]) -> Optional[DBDataset]:
    """Try to find a dataset using multiple name variations."""
    for name in name_variations:
        # Try exact match
        dataset = db.query(DBDataset).filter(DBDataset.name.ilike(name)).first()
        if dataset:
            return dataset
        # Try partial match in name
        dataset = db.query(DBDataset).filter(DBDataset.name.ilike(f"%{name}%")).first()
        if dataset:
            return dataset
        # Try partial match in full_name
        dataset = (
            db.query(DBDataset).filter(DBDataset.full_name.ilike(f"%{name}%")).first()
        )
        if dataset:
            return dataset
        # Use utility function
        dataset = find_dataset_by_name(db, name)
        if dataset:
            return dataset
    return None


def check_existing_evaluation(
    db, paper_id: int, task_id: int, dataset_id: int, model_name: str
) -> bool:
    """Check if evaluation already exists."""
    existing = (
        db.query(DBEvaluation)
        .filter(
            DBEvaluation.paper_id == paper_id,
            DBEvaluation.task_id == task_id,
            DBEvaluation.dataset_id == dataset_id,
            DBEvaluation.model_name == model_name,
        )
        .first()
    )
    return existing is not None


def add_evaluation_results():
    """Add missing evaluation results."""
    db = db_manager.session_local()
    try:
        evaluation_service = EvaluationService(db)
        metric_service = LeaderboardMetricService(db)

        print("=" * 80)
        print("Adding DINOv3 Image Classification Evaluation Results")
        print("=" * 80)
        print(f"Paper ID: {PAPER_ID}")
        print(f"Model: {MODEL_NAME}")
        print(f"Task ID: {TASK_ID} (Image Classification)")
        print()

        added_count = 0
        skipped_count = 0
        not_found_datasets = []

        # Process each evaluation result
        for eval_data in EVALUATION_RESULTS:
            dataset_names = eval_data["dataset_names"]
            metrics = eval_data["metrics"]
            best_metric = eval_data["best_metric"]

            # Try to find the dataset
            dataset = find_dataset_by_variations(db, dataset_names)

            if not dataset:
                print(f"✗ Dataset not found: {dataset_names[0]}")
                not_found_datasets.append(dataset_names[0])
                continue

            # Check if evaluation already exists
            if check_existing_evaluation(db, PAPER_ID, TASK_ID, dataset.id, MODEL_NAME):
                print(f"⊙ Skipping (already exists): {dataset.name} (ID: {dataset.id})")
                skipped_count += 1
                continue

            # Register metrics if needed
            metric_names = list(metrics.keys())
            for metric_name in metric_names:
                try:
                    allowed_metrics = (
                        metric_service.get_allowed_metrics_for_leaderboard(
                            TASK_ID, dataset.id
                        )
                    )
                    if metric_name not in allowed_metrics:
                        metric_service.add_metric_to_leaderboard(
                            TASK_ID, dataset.id, metric_name
                        )
                except Exception:
                    # Metric might already be registered, continue
                    pass

            # Validate metrics
            is_valid, error_message = metric_service.validate_metrics_for_leaderboard(
                TASK_ID, dataset.id, metric_names, best_metric
            )

            if not is_valid:
                print(f"✗ Invalid metrics for {dataset.name}: {error_message}")
                not_found_datasets.append(
                    f"{dataset_names[0]} (metric validation failed)"
                )
                continue

            # Add evaluation
            try:
                evaluation = evaluation_service.create_evaluation(
                    paper_id=PAPER_ID,
                    task_id=TASK_ID,
                    dataset_id=dataset.id,
                    metrics=metrics,
                    best_metric=best_metric,
                    model_name=MODEL_NAME,
                )
                print(f"✓ Added: {dataset.name} (ID: {dataset.id})")
                print(f"  Metrics: {metrics}")
                print(f"  Evaluation ID: {evaluation.id}")
                added_count += 1
            except Exception as e:
                print(f"✗ Error adding evaluation for {dataset.name}: {e}")
                not_found_datasets.append(f"{dataset_names[0]} (error: {str(e)})")

        print()
        print("=" * 80)
        print("Summary")
        print("=" * 80)
        print(f"Added: {added_count}")
        print(f"Skipped (already exists): {skipped_count}")
        print(f"Not found: {len(not_found_datasets)}")
        print()

        # Report missing datasets
        print("Missing datasets (not in database):")
        for ds_info in MISSING_DATASETS:
            if "note" in ds_info:
                print(
                    f"  - {ds_info['name']}: {ds_info['value']} ({ds_info['metric']}) - {ds_info['note']}"
                )
            else:
                print(
                    f"  - {ds_info['name']}: {ds_info['value']} ({ds_info['metric']})"
                )

        if not_found_datasets:
            print()
            print("Datasets searched but not found:")
            for ds in set(not_found_datasets):
                print(f"  - {ds}")

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
    success = add_evaluation_results()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
