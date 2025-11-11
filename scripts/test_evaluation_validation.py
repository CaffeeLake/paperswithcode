#!/usr/bin/env python3
"""
Test dataset-task validation in evaluation creation.

This script tests that the new validation prevents creating evaluations
with incorrect task-dataset combinations.
"""

import sys
from backend.database.connection import db_manager
from backend.services.evaluation_service import EvaluationService


def test_validation():
    """Test the dataset-task consistency validation."""

    print("=" * 80)
    print("TESTING DATASET-TASK CONSISTENCY VALIDATION")
    print("=" * 80)
    print()

    with db_manager.session_local() as db:
        service = EvaluationService(db)

        # Test case 1: Try to create evaluation with LVBench (ID: 58) and Vision-Language Models (ID: 8)
        # This should FAIL because LVBench is linked to Video-Language Models (ID: 9)
        print("Test 1: Attempting to create evaluation with incorrect task")
        print("  Dataset: LVBench (ID: 58)")
        print("  Task: Vision-Language Models (ID: 8) [INCORRECT]")
        print("  Expected official task: Video-Language Models (ID: 9)")
        print()

        try:
            is_valid, error = service._validate_dataset_task_consistency(
                task_id=8, dataset_id=58
            )
            if not is_valid:
                print("  ✓ VALIDATION BLOCKED CORRECTLY")
                print(f"  Error message: {error}")
            else:
                print("  ✗ VALIDATION FAILED - Should have blocked this!")
                return False
        except Exception as e:
            print(f"  ✗ UNEXPECTED ERROR: {e}")
            return False

        print()
        print("-" * 80)
        print()

        # Test case 2: Try with correct task
        print("Test 2: Creating evaluation with CORRECT task")
        print("  Dataset: LVBench (ID: 58)")
        print("  Task: Video-Language Models (ID: 9) [CORRECT]")
        print()

        try:
            is_valid, error = service._validate_dataset_task_consistency(
                task_id=9, dataset_id=58
            )
            if is_valid:
                print("  ✓ VALIDATION PASSED CORRECTLY")
            else:
                print(
                    f"  ✗ VALIDATION FAILED - Should have allowed this! Error: {error}"
                )
                return False
        except Exception as e:
            print(f"  ✗ UNEXPECTED ERROR: {e}")
            return False

        print()
        print("-" * 80)
        print()

        # Test case 3: Test with OCRBench
        print(
            "Test 3: Attempting to create evaluation with incorrect task for OCRBench"
        )
        print("  Dataset: OCRBench (ID: 155)")
        print("  Task: Vision-Language Models (ID: 8) [INCORRECT]")
        print("  Expected official task: OCR (ID: 4)")
        print()

        try:
            is_valid, error = service._validate_dataset_task_consistency(
                task_id=8, dataset_id=155
            )
            if not is_valid:
                print("  ✓ VALIDATION BLOCKED CORRECTLY")
                print(f"  Error message: {error}")
            else:
                print("  ✗ VALIDATION FAILED - Should have blocked this!")
                return False
        except Exception as e:
            print(f"  ✗ UNEXPECTED ERROR: {e}")
            return False

        print()
        print("-" * 80)
        print()

        # Test case 4: Test with correct task for OCRBench
        print("Test 4: Creating evaluation with CORRECT task for OCRBench")
        print("  Dataset: OCRBench (ID: 155)")
        print("  Task: OCR (ID: 4) [CORRECT]")
        print()

        try:
            is_valid, error = service._validate_dataset_task_consistency(
                task_id=4, dataset_id=155
            )
            if is_valid:
                print("  ✓ VALIDATION PASSED CORRECTLY")
            else:
                print(
                    f"  ✗ VALIDATION FAILED - Should have allowed this! Error: {error}"
                )
                return False
        except Exception as e:
            print(f"  ✗ UNEXPECTED ERROR: {e}")
            return False

        print()
        print("-" * 80)
        print()

        # Test case 5: Test with multi-task dataset (ETH3D - ID: 218)
        print("Test 5: Multi-task dataset (ETH3D)")
        print("  Dataset: ETH3D (ID: 218)")
        print(
            "  This dataset is linked to multiple tasks (Depth estimation, 3D Understanding)"
        )
        print()

        # Should allow Depth estimation (ID: 16)
        try:
            is_valid, error = service._validate_dataset_task_consistency(
                task_id=16, dataset_id=218
            )
            if is_valid:
                print("  ✓ VALIDATION PASSED for Depth estimation")
            else:
                print(f"  ✗ VALIDATION FAILED - Should allow this task! Error: {error}")
                return False
        except Exception as e:
            print(f"  ✗ UNEXPECTED ERROR: {e}")
            return False

        # Should allow 3D Understanding (ID: 263)
        try:
            is_valid, error = service._validate_dataset_task_consistency(
                task_id=263, dataset_id=218
            )
            if is_valid:
                print("  ✓ VALIDATION PASSED for 3D Understanding")
            else:
                print(f"  ✗ VALIDATION FAILED - Should allow this task! Error: {error}")
                return False
        except Exception as e:
            print(f"  ✗ UNEXPECTED ERROR: {e}")
            return False

        # Should NOT allow a different task (e.g., OCR - ID: 4)
        try:
            is_valid, error = service._validate_dataset_task_consistency(
                task_id=4, dataset_id=218
            )
            if not is_valid:
                print("  ✓ VALIDATION BLOCKED incorrect task for multi-task dataset")
                print(f"  Error message: {error}")
            else:
                print("  ✗ VALIDATION FAILED - Should have blocked this!")
                return False
        except Exception as e:
            print(f"  ✗ UNEXPECTED ERROR: {e}")
            return False

        print()
        print("=" * 80)
        print("ALL TESTS PASSED ✓")
        print("=" * 80)
        print()
        print(
            "The validation is working correctly and will prevent future inconsistencies!"
        )

        return True


if __name__ == "__main__":
    success = test_validation()
    sys.exit(0 if success else 1)
