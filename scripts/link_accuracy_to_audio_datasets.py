"""
Link the "Accuracy" metric to all Audio Classification datasets.

This script queries all datasets linked to the Audio Classification task (ID: 259)
and links the "Accuracy" metric to each dataset via the API endpoint.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from sqlalchemy import and_
from backend.database.connection import DatabaseManager
from backend.models.database import (
    Dataset as DBDataset,
    DatasetMetric as DBDatasetMetric,
    Metric as DBMetric,
    TaskDataset,
)

# Configuration
API_BASE_URL = "http://localhost:8000/api/v1"
TASK_ID = 259  # Audio Classification
METRIC_NAME = "Accuracy"

db_manager = DatabaseManager()


def get_audio_classification_datasets(session):
    """
    Query all datasets linked to the Audio Classification task.

    Returns:
        List of tuples: (dataset_id, dataset_name, dataset_slug)
    """
    # Query datasets linked to Audio Classification via task_datasets junction table
    datasets = (
        session.query(DBDataset.id, DBDataset.name, DBDataset.slug)
        .join(TaskDataset, DBDataset.id == TaskDataset.dataset_id)
        .filter(TaskDataset.task_id == TASK_ID)
        .order_by(DBDataset.name)
        .all()
    )

    return [(d.id, d.name, d.slug) for d in datasets]


def check_metric_already_linked(session, dataset_id, metric_name):
    """
    Check if a metric is already linked to a dataset.

    Args:
        session: Database session
        dataset_id: Dataset ID
        metric_name: Metric name (e.g., "Accuracy")

    Returns:
        Boolean indicating if the metric is already linked
    """
    # Get the metric ID for the given metric name
    metric = session.query(DBMetric).filter(DBMetric.name == metric_name).first()

    if not metric:
        return False

    # Check if link exists in dataset_metrics junction table
    link = (
        session.query(DBDatasetMetric)
        .filter(
            and_(
                DBDatasetMetric.dataset_id == dataset_id,
                DBDatasetMetric.metric_id == metric.id,
            )
        )
        .first()
    )

    return link is not None


def link_metric_via_api(dataset_id, metric_name):
    """
    Link a metric to a dataset via the API.

    Args:
        dataset_id: Dataset ID
        metric_name: Metric name (e.g., "Accuracy")

    Returns:
        Dictionary with status and response information
    """
    url = f"{API_BASE_URL}/datasets/{dataset_id}/metrics"
    payload = {"metric_name": metric_name}

    try:
        response = requests.post(url, json=payload, timeout=10)

        return {
            "status_code": response.status_code,
            "success": response.status_code in [200, 201],
            "response": response.json()
            if response.status_code in [200, 201]
            else response.text,
        }
    except requests.exceptions.RequestException as e:
        return {
            "status_code": 0,
            "success": False,
            "response": str(e),
        }


def main():
    """Main function to link Accuracy metric to audio classification datasets."""
    print("=" * 80)
    print("LINKING ACCURACY METRIC TO AUDIO CLASSIFICATION DATASETS")
    print("=" * 80)
    print(f"Task ID: {TASK_ID} (Audio Classification)")
    print(f"Metric: {METRIC_NAME}")
    print(f"API Endpoint: {API_BASE_URL}/datasets/{{dataset_id}}/metrics")
    print("=" * 80)
    print()

    # Statistics
    total_datasets = 0
    already_linked = 0
    newly_linked = 0
    failed_links = 0

    session = db_manager.session_local()

    try:
        # Step 1: Get all audio classification datasets
        print("Step 1: Querying Audio Classification datasets...")
        datasets = get_audio_classification_datasets(session)
        total_datasets = len(datasets)
        print(f"Found {total_datasets} datasets linked to Audio Classification task\n")

        if total_datasets == 0:
            print("⚠ No datasets found for Audio Classification task")
            return 0

        # Step 2: Check each dataset and link metric if needed
        print("Step 2: Checking and linking Accuracy metric...\n")

        for dataset_id, dataset_name, dataset_slug in datasets:
            print(
                f"[{total_datasets - failed_links - newly_linked - already_linked}] {dataset_name}"
            )
            print(f"    ID: {dataset_id}, Slug: {dataset_slug}")

            # Check if metric is already linked
            is_linked = check_metric_already_linked(session, dataset_id, METRIC_NAME)

            if is_linked:
                already_linked += 1
                print("    ✓ Accuracy metric already linked")
            else:
                # Link metric via API
                print("    → Linking Accuracy metric...")
                result = link_metric_via_api(dataset_id, METRIC_NAME)

                if result["success"]:
                    newly_linked += 1
                    print("    ✓ Successfully linked Accuracy metric")
                else:
                    failed_links += 1
                    print(
                        f"    ✗ Failed to link metric (Status: {result['status_code']})"
                    )
                    print(f"    Error: {result['response']}")

            print()

        # Step 3: Summary
        print("=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Total datasets: {total_datasets}")
        print(f"Already linked: {already_linked}")
        print(f"Newly linked: {newly_linked}")
        print(f"Failed: {failed_links}")
        print("=" * 80)

        if failed_links > 0:
            print("\n⚠ Some datasets failed to link. Check errors above.")
            return 1
        elif newly_linked > 0:
            print(
                f"\n✓ Successfully linked Accuracy metric to {newly_linked} dataset(s)"
            )
            return 0
        else:
            print("\n✓ All datasets already had Accuracy metric linked")
            return 0

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback

        traceback.print_exc()
        return 1

    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
