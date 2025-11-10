"""
Fix DINOv3 Depth Estimation Scale Issue

The DINOv3 depth estimation results were stored with percentage values (4.3, 7.3)
instead of decimal values (0.043, 0.073) to match the standard format used by
other depth estimation models.

This script:
1. Finds all DINOv3 depth estimation evaluations
2. Converts AbsRel values from percentage to decimal (divide by 100)
3. Converts delta1 values from percentage to decimal (divide by 100)
4. Updates the evaluations in the database
"""

import sys
from backend.database.connection import db_manager
from backend.services.evaluation_service import EvaluationService
from sqlalchemy import text
from sqlalchemy.orm import Session

ARXIV_ID = "2508.10104"
TASK_ID = 16  # Depth estimation task ID


def fix_evaluation_scale(
    db: Session, evaluation_id: int, current_metrics: dict
) -> dict:
    """Convert percentage metrics to decimal format."""
    fixed_metrics = current_metrics.copy()

    # Fix AbsRel: convert from percentage (4.3) to decimal (0.043)
    if "AbsRel" in fixed_metrics:
        try:
            absrel_value = float(fixed_metrics["AbsRel"])
            # If value is > 1, it's likely a percentage and needs conversion
            if absrel_value > 1.0:
                old_value = fixed_metrics["AbsRel"]
                fixed_metrics["AbsRel"] = f"{absrel_value / 100:.4f}".rstrip(
                    "0"
                ).rstrip(".")
                print(f"    AbsRel: {old_value} → {fixed_metrics['AbsRel']}")
        except (ValueError, TypeError):
            print(f"    ⚠ Could not convert AbsRel: {fixed_metrics['AbsRel']}")

    # Fix delta1: convert from percentage (98.0) to decimal (0.980)
    if "delta1" in fixed_metrics:
        try:
            delta1_value = float(fixed_metrics["delta1"])
            # If value is > 1, it's likely a percentage and needs conversion
            if delta1_value > 1.0:
                fixed_metrics["delta1"] = f"{delta1_value / 100:.4f}".rstrip(
                    "0"
                ).rstrip(".")
                print(
                    f"    delta1: {current_metrics['delta1']} → {fixed_metrics['delta1']}"
                )
        except (ValueError, TypeError):
            print(f"    ⚠ Could not convert delta1: {fixed_metrics['delta1']}")

    return fixed_metrics


def main():
    """Main execution function."""
    print("=" * 80)
    print("Fix DINOv3 Depth Estimation Scale Issue")
    print("=" * 80)
    print()

    try:
        with db_manager.session_local() as db:
            # Find all DINOv3 depth estimation evaluations
            print("Step 1: Finding DINOv3 depth estimation evaluations...")
            print("-" * 80)

            result = db.execute(
                text("""
                SELECT e.id, e.model_name, d.name as dataset_name, e.metrics
                FROM evaluations e
                JOIN datasets d ON e.dataset_id = d.id
                JOIN papers p ON e.paper_id = p.id
                WHERE p.arxiv_id = :arxiv_id
                AND e.task_id = :task_id
                ORDER BY d.name
            """),
                {"arxiv_id": ARXIV_ID, "task_id": TASK_ID},
            )

            evaluations = list(result)

            if not evaluations:
                print("✗ No DINOv3 depth estimation evaluations found.")
                return 1

            print(f"✓ Found {len(evaluations)} evaluation(s)")
            print()

            # Step 2: Fix each evaluation
            print("Step 2: Fixing evaluation scales...")
            print("-" * 80)

            evaluation_service = EvaluationService(db)
            fixed_count = 0

            for eval_row in evaluations:
                eval_id = eval_row.id
                model_name = eval_row.model_name
                dataset_name = eval_row.dataset_name
                current_metrics = eval_row.metrics

                print(
                    f"\n[{fixed_count + 1}/{len(evaluations)}] {dataset_name} ({model_name}):"
                )
                print(f"    Current metrics: {current_metrics}")

                # Fix the metrics
                fixed_metrics = fix_evaluation_scale(db, eval_id, current_metrics)

                # Check if metrics changed
                if fixed_metrics != current_metrics:
                    # Determine best_metric (should be delta1)
                    best_metric = (
                        "delta1"
                        if "delta1" in fixed_metrics
                        else list(fixed_metrics.keys())[0]
                    )

                    # Update the evaluation using the service
                    try:
                        evaluation_service.update_evaluation(
                            evaluation_id=eval_id,
                            metrics=fixed_metrics,
                            best_metric=best_metric,
                        )
                        print(f"    ✓ Updated evaluation ID {eval_id}")
                        fixed_count += 1
                    except Exception as e:
                        print(f"    ✗ Error updating evaluation {eval_id}: {e}")
                else:
                    print("    ✓ No changes needed (already in correct format)")

            # Step 3: Recalculate ranks
            print("\nStep 3: Recalculating ranks...")
            print("-" * 80)

            # Get unique dataset IDs
            dataset_ids = set()
            for eval_row in evaluations:
                result = db.execute(
                    text("SELECT dataset_id FROM evaluations WHERE id = :id"),
                    {"id": eval_row.id},
                ).fetchone()
                if result:
                    dataset_ids.add(result.dataset_id)

            for dataset_id in dataset_ids:
                print(f"  Recalculating ranks for dataset ID {dataset_id}...")
                try:
                    evaluation_service.recalculate_ranks(
                        task_id=TASK_ID,
                        dataset_id=dataset_id,
                        metric_name="delta1",
                    )
                    print("    ✓ Ranks recalculated")
                except Exception as e:
                    print(f"    ⚠ Error recalculating ranks: {e}")

            # Commit changes
            print("\nStep 4: Committing changes...")
            print("-" * 80)
            db.commit()
            print("✓ All changes committed successfully")
            print()

            # Summary
            print("=" * 80)
            print("SUMMARY")
            print("=" * 80)
            print(f"Total evaluations found: {len(evaluations)}")
            print(f"Evaluations fixed: {fixed_count}")
            print(f"Evaluations unchanged: {len(evaluations) - fixed_count}")
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
