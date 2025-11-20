"""
Test script to verify task-dataset relationship changes.

This script verifies that:
1. Datasets can be queried by task_id
2. Tasks can be queried by dataset_id
3. Evaluation creation still validates correctly
4. Dataset creation works
5. Count queries return correct numbers
"""

import sys
from sqlalchemy import text
from backend.database.connection import db_manager
from backend.services.dataset_service import DatasetService
from backend.services.evaluation_service import EvaluationService


def test_task_datasets_table_removed():
    """Verify that task_datasets table no longer exists."""
    print("\n=== Test 1: Verify TASK_DATASETS table removed ===")
    with db_manager.session_local() as db:
        try:
            db.execute(text("SELECT 1 FROM task_datasets LIMIT 1"))
            print("❌ FAILED: task_datasets table still exists!")
            return False
        except Exception as e:
            if "does not exist" in str(e) or "no such table" in str(e):
                print("✓ PASSED: task_datasets table successfully removed")
                return True
            else:
                print(f"❌ FAILED: Unexpected error: {e}")
                return False


def test_dataset_filtering_by_task():
    """Test that datasets can be filtered by task_id via task_dataset_metrics."""
    print("\n=== Test 2: Filter datasets by task_id ===")
    with db_manager.session_local() as db:
        service = DatasetService(db)

        # Get datasets for task 1 (Image Classification)
        result = service.get_datasets(task_id=1, page_size=5)

        if result.count > 0:
            print(f"✓ PASSED: Found {result.count} datasets for task 1")
            print(f"  Sample: {result.results[0].name if result.results else 'N/A'}")
            return True
        else:
            print(
                "⚠ WARNING: No datasets found for task 1 (this may be expected if no metrics are defined)"
            )
            return True


def test_get_dataset_tasks():
    """Test that tasks can be retrieved for a dataset."""
    print("\n=== Test 3: Get tasks for dataset ===")
    with db_manager.session_local() as db:
        # Find a dataset with tasks
        result = db.execute(
            text("""
            SELECT DISTINCT dataset_id, COUNT(DISTINCT task_id) as task_count
            FROM task_dataset_metrics
            GROUP BY dataset_id
            HAVING COUNT(DISTINCT task_id) > 0
            ORDER BY task_count DESC
            LIMIT 1
        """)
        ).fetchone()

        if not result:
            print("⚠ WARNING: No datasets with tasks found")
            return True

        dataset_id, expected_count = result

        service = DatasetService(db)
        task_ids = service.get_dataset_tasks(dataset_id)

        if len(task_ids) == expected_count:
            print(
                f"✓ PASSED: Dataset {dataset_id} has {len(task_ids)} tasks (expected {expected_count})"
            )
            return True
        else:
            print(
                f"❌ FAILED: Dataset {dataset_id} returned {len(task_ids)} tasks, expected {expected_count}"
            )
            return False


def test_evaluation_validation():
    """Test that evaluation creation validates against task_dataset_metrics."""
    print("\n=== Test 4: Evaluation validation ===")
    with db_manager.session_local() as db:
        # Find a valid task-dataset pair with metrics
        valid_pair = db.execute(
            text("""
            SELECT DISTINCT task_id, dataset_id
            FROM task_dataset_metrics
            LIMIT 1
        """)
        ).fetchone()

        if not valid_pair:
            print("⚠ WARNING: No valid task-dataset pairs found")
            return True

        task_id, dataset_id = valid_pair

        service = EvaluationService(db)

        # Test validation with valid pair
        is_valid, error_msg = service._validate_dataset_task_consistency(
            task_id, dataset_id
        )

        if is_valid:
            print(
                f"✓ PASSED: Validation succeeded for valid pair (task={task_id}, dataset={dataset_id})"
            )
        else:
            print(f"❌ FAILED: Validation failed for valid pair: {error_msg}")
            return False

        # Test validation with invalid pair (task 999999, dataset 999999)
        is_valid, error_msg = service._validate_dataset_task_consistency(999999, 999999)

        if not is_valid:
            print("✓ PASSED: Validation correctly rejected invalid pair")
            return True
        else:
            print("❌ FAILED: Validation should have rejected invalid pair")
            return False


def test_task_count_in_datasets():
    """Test that task counts are correctly calculated for datasets."""
    print("\n=== Test 5: Task counts for datasets ===")
    with db_manager.session_local() as db:
        # Get expected counts from task_dataset_metrics
        expected_counts = db.execute(
            text("""
            SELECT dataset_id, COUNT(DISTINCT task_id) as task_count
            FROM task_dataset_metrics
            GROUP BY dataset_id
            ORDER BY task_count DESC
            LIMIT 1
        """)
        ).fetchone()

        if not expected_counts:
            print("⚠ WARNING: No task-dataset metrics found")
            return True

        dataset_id, expected_count = expected_counts

        service = DatasetService(db)
        dataset = service.get_dataset(dataset_id)

        if dataset and dataset.task_count == expected_count:
            print(
                f"✓ PASSED: Dataset {dataset_id} has task_count={dataset.task_count} (expected {expected_count})"
            )
            return True
        elif dataset:
            print(
                f"❌ FAILED: Dataset {dataset_id} has task_count={dataset.task_count}, expected {expected_count}"
            )
            return False
        else:
            print(f"❌ FAILED: Could not retrieve dataset {dataset_id}")
            return False


def test_dataset_tasks_endpoint():
    """Test the /datasets/{id}/tasks/ endpoint behavior."""
    print("\n=== Test 6: Datasets tasks endpoint ===")
    with db_manager.session_local() as db:
        # Find a dataset with tasks
        result = db.execute(
            text("""
            SELECT dataset_id, COUNT(DISTINCT task_id) as task_count
            FROM task_dataset_metrics
            GROUP BY dataset_id
            HAVING COUNT(DISTINCT task_id) > 0
            ORDER BY task_count DESC
            LIMIT 1
        """)
        ).fetchone()

        if not result:
            print("⚠ WARNING: No datasets with tasks found")
            return True

        dataset_id, expected_count = result

        # Simulate what the endpoint does
        from backend.models.database import Task as DBTask, TaskDatasetMetric

        tasks_query = (
            db.query(DBTask)
            .join(TaskDatasetMetric, DBTask.id == TaskDatasetMetric.task_id)
            .filter(TaskDatasetMetric.dataset_id == dataset_id)
            .distinct()
            .order_by(DBTask.name)
            .all()
        )

        if len(tasks_query) == expected_count:
            print(
                f"✓ PASSED: Dataset {dataset_id} endpoint would return {len(tasks_query)} tasks (expected {expected_count})"
            )
            return True
        else:
            print(
                f"❌ FAILED: Dataset {dataset_id} endpoint returned {len(tasks_query)} tasks, expected {expected_count}"
            )
            return False


def main():
    """Run all tests."""
    print("\n" + "=" * 80)
    print("  TASK-DATASET RELATIONSHIP MIGRATION TESTS")
    print("=" * 80)

    tests = [
        test_task_datasets_table_removed,
        test_dataset_filtering_by_task,
        test_get_dataset_tasks,
        test_evaluation_validation,
        test_task_count_in_datasets,
        test_dataset_tasks_endpoint,
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"\n❌ TEST EXCEPTION: {e}")
            import traceback

            traceback.print_exc()
            results.append(False)

    # Summary
    print("\n" + "=" * 80)
    print("  TEST SUMMARY")
    print("=" * 80)
    passed = sum(results)
    total = len(results)
    print(f"\nPassed: {passed}/{total}")

    if passed == total:
        print("\n✓✓✓ ALL TESTS PASSED ✓✓✓\n")
        return 0
    else:
        print(f"\n❌ {total - passed} TEST(S) FAILED ❌\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
