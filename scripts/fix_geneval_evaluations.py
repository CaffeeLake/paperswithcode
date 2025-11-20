"""
Fix GenEval evaluations to ensure they all appear on the benchmark page.

Issues:
1. Evaluation 729 is on task 8 but should be on task 19 (Image generation)
2. Two different metric names: "Overall (GenEval)" vs "GenEval Score"
3. Need to consolidate metrics or ensure both show on benchmark page

Solution:
1. Move evaluation 729 to task 19
2. Update evaluation 729 to use "GenEval Score" metric (or consolidate metrics)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.database.connection import db_manager
from backend.models.database import (
    Evaluation as DBEvaluation,
    Metric as DBMetric,
    TaskDataset,
)
from backend.services.evaluation_service import EvaluationService


def main():
    """Fix GenEval evaluations."""
    with db_manager.session_local() as db:
        # 1. Check current state
        print("1. Checking current GenEval evaluations...")
        evals = db.query(DBEvaluation).filter(DBEvaluation.dataset_id == 340).all()
        print(f"   Found {len(evals)} evaluations for GenEval dataset")

        for eval in evals:
            print(
                f"   Evaluation {eval.id}: Task {eval.task_id}, Metric: {eval.best_metric}"
            )

        # 2. Ensure GenEval is linked to task 19 (Image generation)
        print("\n2. Ensuring GenEval is linked to task 19...")
        link_19 = (
            db.query(TaskDataset)
            .filter(TaskDataset.task_id == 19, TaskDataset.dataset_id == 340)
            .first()
        )
        if not link_19:
            link_19 = TaskDataset(task_id=19, dataset_id=340)
            db.add(link_19)
            db.commit()
            print("   ✓ Linked GenEval to task 19")
        else:
            print("   ✓ GenEval already linked to task 19")

        # 3. Check if we should remove link to task 8
        print("\n3. Checking task 8 link...")
        link_8 = (
            db.query(TaskDataset)
            .filter(TaskDataset.task_id == 8, TaskDataset.dataset_id == 340)
            .first()
        )
        if link_8:
            # Check if there are any evaluations on task 8
            evals_task_8 = (
                db.query(DBEvaluation)
                .filter(DBEvaluation.task_id == 8, DBEvaluation.dataset_id == 340)
                .all()
            )
            if evals_task_8:
                print(f"   ⚠ Found {len(evals_task_8)} evaluations on task 8")
                print("   Moving evaluation 729 to task 19...")
                eval_729 = db.query(DBEvaluation).filter(DBEvaluation.id == 729).first()
                if eval_729:
                    eval_729.task_id = 19
                    db.commit()
                    print("   ✓ Moved evaluation 729 to task 19")

                # Now remove the task 8 link
                db.delete(link_8)
                db.commit()
                print("   ✓ Removed GenEval link to task 8")
            else:
                print("   ✓ No evaluations on task 8, removing link...")
                db.delete(link_8)
                db.commit()
                print("   ✓ Removed GenEval link to task 8")
        else:
            print("   ✓ GenEval not linked to task 8")

        # 4. Consolidate metrics - update "Overall (GenEval)" to "GenEval Score"
        print("\n4. Consolidating metrics...")
        eval_729 = db.query(DBEvaluation).filter(DBEvaluation.id == 729).first()
        if eval_729 and eval_729.best_metric == "Overall (GenEval)":
            # Check if "GenEval Score" metric exists
            geneval_score_metric = (
                db.query(DBMetric).filter(DBMetric.name == "GenEval Score").first()
            )
            if geneval_score_metric:
                # Update evaluation to use "GenEval Score"
                old_metrics = (
                    eval_729.metrics
                    if isinstance(eval_729.metrics, dict)
                    else eval_729.metrics
                )
                if isinstance(old_metrics, str):
                    import json

                    old_metrics = json.loads(old_metrics)

                # Get the value from "Overall (GenEval)"
                old_value = old_metrics.get("Overall (GenEval)")
                if old_value:
                    eval_729.metrics = {"GenEval Score": old_value}
                    eval_729.best_metric = "GenEval Score"
                    db.commit()
                    print("   ✓ Updated evaluation 729 to use 'GenEval Score'")
                else:
                    print("   ⚠ Could not find value for 'Overall (GenEval)'")
            else:
                print("   ⚠ 'GenEval Score' metric not found")
        else:
            print("   ✓ Evaluation 729 already uses correct metric")

        # 5. Recalculate ranks for both evaluations
        print("\n5. Recalculating ranks...")
        evaluation_service = EvaluationService(db)
        evaluation_service.recalculate_ranks(
            task_id=19, dataset_id=340, metric_name="GenEval Score"
        )
        print("   ✓ Ranks recalculated")

        # 6. Verify final state
        print("\n6. Final state:")
        evals = db.query(DBEvaluation).filter(DBEvaluation.dataset_id == 340).all()
        for eval in evals:
            print(
                f"   Evaluation {eval.id}: Task {eval.task_id}, "
                f"Metric: {eval.best_metric}, Rank: {eval.best_rank}"
            )

        print("\n✅ All fixes completed!")


if __name__ == "__main__":
    main()
