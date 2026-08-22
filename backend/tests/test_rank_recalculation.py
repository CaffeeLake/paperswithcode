"""
Test script for evaluation rank recalculation.

This script tests the automatic rank recalculation functionality by:
1. Creating test evaluations with different metric values
2. Verifying ranks are calculated correctly
3. Testing rank updates when evaluations are added/updated/deleted

Usage:
    uv run --env-file backend/keys.env python -m pytest backend/tests/test_rank_recalculation.py -v
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.services.evaluation_service import EvaluationService
from backend.config import get_settings


@pytest.fixture(scope="function")
def db_session():
    """
    Create a test database session.
    """
    settings = get_settings()
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    yield session
    session.close()


def test_rank_calculation_basic(db_session):
    """
    Test basic rank calculation for a simple leaderboard.
    """
    service = EvaluationService(db_session)

    # Create test evaluations (using existing paper, task, dataset IDs)
    # You'll need to adjust these IDs based on your database
    test_task_id = 1
    test_dataset_id = 1
    test_paper_id = 1

    # Create evaluations with different mAP scores
    eval1 = service.create_evaluation(
        paper_id=test_paper_id,
        task_id=test_task_id,
        dataset_id=test_dataset_id,
        model_name="Model A",
        metrics={"mAP": "60.5"},
        best_metric="mAP",
    )

    eval2 = service.create_evaluation(
        paper_id=test_paper_id,
        task_id=test_task_id,
        dataset_id=test_dataset_id,
        model_name="Model B",
        metrics={"mAP": "65.9"},
        best_metric="mAP",
    )

    eval3 = service.create_evaluation(
        paper_id=test_paper_id,
        task_id=test_task_id,
        dataset_id=test_dataset_id,
        model_name="Model C",
        metrics={"mAP": "63.2"},
        best_metric="mAP",
    )

    # Verify ranks
    # Model B (65.9) should be rank 1
    # Model C (63.2) should be rank 2
    # Model A (60.5) should be rank 3

    eval1_updated = service.get_evaluation(int(eval1.id))
    eval2_updated = service.get_evaluation(int(eval2.id))
    eval3_updated = service.get_evaluation(int(eval3.id))

    assert eval1_updated.best_rank == 3, (
        f"Model A should be rank 3, got {eval1_updated.best_rank}"
    )
    assert eval2_updated.best_rank == 1, (
        f"Model B should be rank 1, got {eval2_updated.best_rank}"
    )
    assert eval3_updated.best_rank == 2, (
        f"Model C should be rank 2, got {eval3_updated.best_rank}"
    )

    print("✓ Basic rank calculation test passed")

    # Cleanup
    service.delete_evaluation(int(eval1.id))
    service.delete_evaluation(int(eval2.id))
    service.delete_evaluation(int(eval3.id))


def test_rank_recalculation_on_update(db_session):
    """
    Test that ranks are recalculated when an evaluation is updated.
    """
    service = EvaluationService(db_session)

    test_task_id = 1
    test_dataset_id = 1
    test_paper_id = 1

    # Create evaluations
    eval1 = service.create_evaluation(
        paper_id=test_paper_id,
        task_id=test_task_id,
        dataset_id=test_dataset_id,
        model_name="Model X",
        metrics={"mAP": "60.0"},
        best_metric="mAP",
    )

    eval2 = service.create_evaluation(
        paper_id=test_paper_id,
        task_id=test_task_id,
        dataset_id=test_dataset_id,
        model_name="Model Y",
        metrics={"mAP": "62.0"},
        best_metric="mAP",
    )

    # Verify initial ranks
    eval1_v1 = service.get_evaluation(int(eval1.id))
    eval2_v1 = service.get_evaluation(int(eval2.id))
    assert eval1_v1.best_rank == 2
    assert eval2_v1.best_rank == 1

    service.update_evaluation(int(eval1.id), metrics={"mAP": "65.0"}, best_metric="mAP")

    # Verify ranks were recalculated
    eval1_v2 = service.get_evaluation(int(eval1.id))
    eval2_v2 = service.get_evaluation(int(eval2.id))

    assert eval1_v2.best_rank == 1, "Updated Model X should now be rank 1"
    assert eval2_v2.best_rank == 2, "Model Y should now be rank 2"

    print("✓ Rank recalculation on update test passed")

    # Cleanup
    service.delete_evaluation(int(eval1.id))
    service.delete_evaluation(int(eval2.id))


def test_rank_recalculation_on_delete(db_session):
    """
    Test that ranks are recalculated when an evaluation is deleted.
    """
    service = EvaluationService(db_session)

    test_task_id = 1
    test_dataset_id = 1
    test_paper_id = 1

    # Create evaluations
    eval1 = service.create_evaluation(
        paper_id=test_paper_id,
        task_id=test_task_id,
        dataset_id=test_dataset_id,
        model_name="Model P",
        metrics={"mAP": "55.0"},
        best_metric="mAP",
    )

    eval2 = service.create_evaluation(
        paper_id=test_paper_id,
        task_id=test_task_id,
        dataset_id=test_dataset_id,
        model_name="Model Q",
        metrics={"mAP": "60.0"},
        best_metric="mAP",
    )

    eval3 = service.create_evaluation(
        paper_id=test_paper_id,
        task_id=test_task_id,
        dataset_id=test_dataset_id,
        model_name="Model R",
        metrics={"mAP": "58.0"},
        best_metric="mAP",
    )

    # Verify initial ranks
    eval1_v1 = service.get_evaluation(int(eval1.id))
    eval2_v1 = service.get_evaluation(int(eval2.id))
    eval3_v1 = service.get_evaluation(int(eval3.id))

    assert eval1_v1.best_rank == 3
    assert eval2_v1.best_rank == 1
    assert eval3_v1.best_rank == 2

    # Delete the top-ranked evaluation
    service.delete_evaluation(int(eval2.id))

    # Verify remaining evaluations have updated ranks
    eval1_v2 = service.get_evaluation(int(eval1.id))
    eval3_v2 = service.get_evaluation(int(eval3.id))

    assert eval1_v2.best_rank == 2, "Model P should now be rank 2"
    assert eval3_v2.best_rank == 1, "Model R should now be rank 1"

    print("✓ Rank recalculation on delete test passed")

    # Cleanup
    service.delete_evaluation(int(eval1.id))
    service.delete_evaluation(int(eval3.id))


def test_separate_ranking_by_additional_data(db_session):
    """
    Test that evaluations with/without additional data are ranked separately.
    """
    service = EvaluationService(db_session)

    test_task_id = 1
    test_dataset_id = 1
    test_paper_id = 1

    # Create evaluations without additional data
    eval1_no_extra = service.create_evaluation(
        paper_id=test_paper_id,
        task_id=test_task_id,
        dataset_id=test_dataset_id,
        model_name="Model No Extra 1",
        metrics={"mAP": "60.0"},
        best_metric="mAP",
        uses_additional_data=False,
    )

    eval2_no_extra = service.create_evaluation(
        paper_id=test_paper_id,
        task_id=test_task_id,
        dataset_id=test_dataset_id,
        model_name="Model No Extra 2",
        metrics={"mAP": "62.0"},
        best_metric="mAP",
        uses_additional_data=False,
    )

    # Create evaluations with additional data
    eval1_extra = service.create_evaluation(
        paper_id=test_paper_id,
        task_id=test_task_id,
        dataset_id=test_dataset_id,
        model_name="Model Extra 1",
        metrics={"mAP": "65.0"},
        best_metric="mAP",
        uses_additional_data=True,
    )

    eval2_extra = service.create_evaluation(
        paper_id=test_paper_id,
        task_id=test_task_id,
        dataset_id=test_dataset_id,
        model_name="Model Extra 2",
        metrics={"mAP": "68.0"},
        best_metric="mAP",
        uses_additional_data=True,
    )

    # Verify ranks within each group
    eval1_no_extra_check = service.get_evaluation(int(eval1_no_extra.id))
    eval2_no_extra_check = service.get_evaluation(int(eval2_no_extra.id))
    eval1_extra_check = service.get_evaluation(int(eval1_extra.id))
    eval2_extra_check = service.get_evaluation(int(eval2_extra.id))

    # Within the no-extra-data group
    assert eval1_no_extra_check.best_rank == 2
    assert eval2_no_extra_check.best_rank == 1

    # Within the extra-data group
    assert eval1_extra_check.best_rank == 2
    assert eval2_extra_check.best_rank == 1

    print("✓ Separate ranking by additional data test passed")

    # Cleanup
    service.delete_evaluation(int(eval1_no_extra.id))
    service.delete_evaluation(int(eval2_no_extra.id))
    service.delete_evaluation(int(eval1_extra.id))
    service.delete_evaluation(int(eval2_extra.id))


def test_fps_rank_includes_secondary_metric_rows(db_session):
    """
    FPS rank should include mAP-primary rows that also report FPS, not only
    rows whose best_metric is FPS.
    """
    service = EvaluationService(db_session)

    test_task_id = 2
    test_dataset_id = 6
    test_paper_id = 7563

    slow_fps = service.create_evaluation(
        paper_id=test_paper_id,
        task_id=test_task_id,
        dataset_id=test_dataset_id,
        model_name="__rank_test_slow_fps__",
        metrics={"FPS": "1.0"},
        best_metric="FPS",
    )
    slow_rank_before = service.get_evaluation(int(slow_fps.id)).best_rank

    faster_map = service.create_evaluation(
        paper_id=test_paper_id,
        task_id=test_task_id,
        dataset_id=test_dataset_id,
        model_name="__rank_test_fast_map_fps__",
        metrics={"mAP": "1.0", "FPS": "99999"},
        best_metric="mAP",
    )

    slow_rank_after = service.get_evaluation(int(slow_fps.id)).best_rank
    assert slow_rank_after == slow_rank_before + 1, (
        f"Adding a faster mAP-primary row should push the FPS-primary row down by 1 "
        f"(before={slow_rank_before}, after={slow_rank_after})"
    )

    service.delete_evaluation(int(faster_map.id))
    service.delete_evaluation(int(slow_fps.id))


if __name__ == "__main__":
    # Run tests manually
    from backend.database.connection import get_database_session

    db = next(get_database_session())

    try:
        print("Running rank recalculation tests...\n")
        test_rank_calculation_basic(db)
        test_rank_recalculation_on_update(db)
        test_rank_recalculation_on_delete(db)
        test_separate_ranking_by_additional_data(db)
        test_fps_rank_includes_secondary_metric_rows(db)
        print("\n✓ All tests passed!")
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback

        traceback.print_exc()
    finally:
        db.close()
