#!/usr/bin/env python3
"""
Recalculate ranks for all evaluations in the database.

This script ensures that all evaluations have proper ranks calculated based on their
performance metrics. It's useful for:
- Fixing NULL ranks from legacy data imports
- Ensuring consistency across all leaderboards
- One-time cleanup after bulk imports

Usage:
    uv run --env-file backend/keys.env python scripts/recalculate_all_ranks.py
"""

import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from backend.database.connection import db_manager  # noqa: E402
from backend.models.database import Evaluation as DBEvaluation  # noqa: E402
from backend.services.evaluation_service import EvaluationService  # noqa: E402


def main():
    """Recalculate ranks for all task-dataset-metric combinations."""

    print("=" * 80)
    print("RANK RECALCULATION UTILITY")
    print("=" * 80)
    print()

    with db_manager.session_local() as db:
        service = EvaluationService(db)

        # Get statistics before recalculation
        total_evals = db.query(DBEvaluation).count()
        null_ranks_before = (
            db.query(DBEvaluation).filter(DBEvaluation.best_rank.is_(None)).count()
        )

        print("📊 Current Statistics:")
        print(f"   Total evaluations: {total_evals}")
        print(f"   Evaluations with NULL ranks: {null_ranks_before}")
        print()

        # Get all unique (task_id, dataset_id, best_metric) combinations
        combinations = (
            db.query(
                DBEvaluation.task_id, DBEvaluation.dataset_id, DBEvaluation.best_metric
            )
            .filter(DBEvaluation.best_metric.isnot(None))
            .distinct()
            .all()
        )

        print(f"🔄 Found {len(combinations)} unique leaderboards to process")
        print()

        # Recalculate ranks for each combination
        total_updated = 0
        errors = []

        for idx, (task_id, dataset_id, metric) in enumerate(combinations, 1):
            try:
                updated = service.recalculate_ranks(
                    task_id=task_id, dataset_id=dataset_id, metric_name=metric
                )
                total_updated += updated

                if (idx % 10 == 0) or (idx == len(combinations)):
                    print(
                        f"Progress: {idx}/{len(combinations)} leaderboards processed",
                        end="\r",
                    )

            except Exception as e:
                error_msg = f"Error recalculating Task {task_id}, Dataset {dataset_id}, Metric {metric}: {str(e)}"
                errors.append(error_msg)

        print()  # New line after progress
        print()

        # Get statistics after recalculation
        null_ranks_after = (
            db.query(DBEvaluation).filter(DBEvaluation.best_rank.is_(None)).count()
        )

        print("✅ Recalculation Complete!")
        print(f"   Evaluations updated: {total_updated}")
        print(f"   NULL ranks before: {null_ranks_before}")
        print(f"   NULL ranks after: {null_ranks_after}")
        print(f"   NULL ranks fixed: {null_ranks_before - null_ranks_after}")
        print()

        if errors:
            print(f"⚠️  Errors encountered ({len(errors)}):")
            for error in errors[:5]:  # Show first 5 errors
                print(f"   - {error}")
            if len(errors) > 5:
                print(f"   ... and {len(errors) - 5} more errors")
            print()
            return 1

        print("🎉 All ranks recalculated successfully!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
