"""
Migrate AP and mAP@[.5,.95] metrics to mAP.

AP (Average Precision) and mAP (mean Average Precision) are essentially the same metric.
This script:
1. Migrates all evaluations using AP to use mAP
2. Migrates all evaluations using mAP@[.5,.95] to use mAP
3. Updates the metrics JSON in evaluations (AP → mAP)
4. Deletes the AP and mAP@[.5,.95] metrics
5. Recalculates ranks for affected leaderboards
"""

import sys
from backend.database.connection import db_manager
from backend.models.database import Metric, Evaluation
from backend.services.evaluation_service import EvaluationService
from sqlalchemy.orm.attributes import flag_modified


def migrate_ap_to_map():
    """Migrate AP and mAP@[.5,.95] to mAP."""

    with db_manager.session_local() as session:
        # Find the metrics
        mAP_metric = session.query(Metric).filter(Metric.name == "mAP").first()
        AP_metric = session.query(Metric).filter(Metric.name == "AP").first()
        mAP_bracket_metric = (
            session.query(Metric).filter(Metric.name == "mAP@[.5,.95]").first()
        )

        if not mAP_metric:
            print("ERROR: mAP metric not found!")
            return False

        print(f"✓ Found mAP metric: ID={mAP_metric.id}")

        # Track affected leaderboards for rank recalculation
        affected_leaderboards = set()  # (task_id, dataset_id) tuples

        # 1. Migrate evaluations using AP as best_metric
        if AP_metric:
            ap_evals = (
                session.query(Evaluation).filter(Evaluation.best_metric == "AP").all()
            )
            print(
                f"\n=== Migrating {len(ap_evals)} evaluations with best_metric=AP ==="
            )

            for eval in ap_evals:
                print(f"  Eval ID={eval.id}: Updating best_metric AP → mAP")
                eval.best_metric = "mAP"

                # Also update the metrics JSON if it contains AP
                if eval.metrics and "AP" in eval.metrics:
                    ap_value = eval.metrics["AP"]
                    new_metrics = dict(eval.metrics)
                    del new_metrics["AP"]
                    new_metrics["mAP"] = ap_value
                    eval.metrics = new_metrics
                    flag_modified(eval, "metrics")
                    print(f"    Updated metrics: AP={ap_value} → mAP={ap_value}")

                # Mark this leaderboard for rank recalculation
                affected_leaderboards.add((eval.task_id, eval.dataset_id))

        # 2. Migrate evaluations using mAP@[.5,.95] as best_metric
        if mAP_bracket_metric:
            bracket_evals = (
                session.query(Evaluation)
                .filter(Evaluation.best_metric == "mAP@[.5,.95]")
                .all()
            )
            print(
                f"\n=== Migrating {len(bracket_evals)} evaluations with best_metric=mAP@[.5,.95] ==="
            )

            for eval in bracket_evals:
                print(f"  Eval ID={eval.id}: Updating best_metric mAP@[.5,.95] → mAP")
                eval.best_metric = "mAP"

                # Also update the metrics JSON if it contains mAP@[.5,.95]
                if eval.metrics and "mAP@[.5,.95]" in eval.metrics:
                    value = eval.metrics["mAP@[.5,.95]"]
                    new_metrics = dict(eval.metrics)
                    del new_metrics["mAP@[.5,.95]"]
                    new_metrics["mAP"] = value
                    eval.metrics = new_metrics
                    flag_modified(eval, "metrics")
                    print(f"    Updated metrics: mAP@[.5,.95]={value} → mAP={value}")

                # Mark this leaderboard for rank recalculation
                affected_leaderboards.add((eval.task_id, eval.dataset_id))

        # 3. Scan all evaluations for AP or mAP@[.5,.95] in metrics JSON (even if not best_metric)
        print("\n=== Scanning all evaluations for AP/mAP@[.5,.95] in metrics JSON ===")
        all_evals = session.query(Evaluation).all()
        count_updated = 0

        for eval in all_evals:
            if not eval.metrics:
                continue

            updated = False
            new_metrics = None

            # Replace AP with mAP in metrics dict
            if "AP" in eval.metrics and eval.best_metric != "AP":
                if new_metrics is None:
                    new_metrics = dict(eval.metrics)
                ap_value = new_metrics["AP"]
                del new_metrics["AP"]
                new_metrics["mAP"] = ap_value
                print(f"  Eval ID={eval.id}: Updated metrics JSON: AP → mAP")
                updated = True

            # Replace mAP@[.5,.95] with mAP in metrics dict
            if "mAP@[.5,.95]" in eval.metrics and eval.best_metric != "mAP@[.5,.95]":
                if new_metrics is None:
                    new_metrics = dict(eval.metrics)
                value = new_metrics["mAP@[.5,.95]"]
                del new_metrics["mAP@[.5,.95]"]
                new_metrics["mAP"] = value
                print(f"  Eval ID={eval.id}: Updated metrics JSON: mAP@[.5,.95] → mAP")
                updated = True

            if updated:
                eval.metrics = new_metrics
                flag_modified(eval, "metrics")

            if updated:
                count_updated += 1
                affected_leaderboards.add((eval.task_id, eval.dataset_id))

        if count_updated > 0:
            print(f"  Updated {count_updated} additional evaluations")

        # Commit the changes
        session.commit()
        print("\n✓ All evaluation updates committed")

        # 4. Recalculate ranks for affected leaderboards
        print(
            f"\n=== Recalculating ranks for {len(affected_leaderboards)} affected leaderboards ==="
        )
        eval_service = EvaluationService(session)

        for task_id, dataset_id in affected_leaderboards:
            print(f"  Recalculating: Task {task_id}, Dataset {dataset_id}")
            try:
                eval_service.recalculate_ranks(task_id=task_id, dataset_id=dataset_id)
            except Exception as e:
                print(f"    Warning: Failed to recalculate ranks: {e}")

        session.commit()
        print("✓ Rank recalculation completed")

        # 5. Delete the AP and mAP@[.5,.95] metrics
        print("\n=== Deleting redundant metrics ===")

        if AP_metric:
            print(f"  Deleting AP metric (ID={AP_metric.id})")
            session.delete(AP_metric)

        if mAP_bracket_metric:
            print(f"  Deleting mAP@[.5,.95] metric (ID={mAP_bracket_metric.id})")
            session.delete(mAP_bracket_metric)

        session.commit()
        print("✓ Redundant metrics deleted")

        print("\n" + "=" * 60)
        print("✓ Migration completed successfully!")
        print("=" * 60)
        print("Summary:")
        print("  - Migrated evaluations to use mAP")
        print(f"  - Updated {len(affected_leaderboards)} leaderboards")
        print("  - Deleted 2 redundant metrics (AP, mAP@[.5,.95])")
        print("=" * 60)

        return True


if __name__ == "__main__":
    try:
        success = migrate_ap_to_map()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
