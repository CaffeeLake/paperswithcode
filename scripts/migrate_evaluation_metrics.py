"""
Migrate existing evaluations to fix invalid metrics.

This script analyzes all existing evaluations and ensures their metrics are linked
to their datasets. It can:
1. Automatically link metrics found in evaluations to datasets (if metric exists)
2. Report evaluations with invalid metrics for manual review
3. Optionally fix best_metric field if invalid

Usage:
    uv run --env-file backend/keys.env python scripts/migrate_evaluation_metrics.py [--auto-link] [--fix-best-metric]

Options:
    --auto-link: Automatically link metrics to datasets if not already linked
    --fix-best-metric: Fix invalid best_metric by setting it to the first valid metric
    --dry-run: Show what would be done without making changes
"""

import sys
import argparse
from pathlib import Path
from collections import defaultdict

# Add parent directory to path so we can import from backend
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.database.connection import get_database_session
from backend.models.database import (
    Evaluation as DBEvaluation,
    Dataset as DBDataset,
    Metric as DBMetric,
)
from backend.services.dataset_metric_service import DatasetMetricService


def migrate_evaluation_metrics(
    auto_link: bool = False, fix_best_metric: bool = False, dry_run: bool = False
):
    """
    Migrate evaluations to ensure metrics are properly linked to datasets.

    Args:
        auto_link: If True, automatically link metrics to datasets
        fix_best_metric: If True, fix invalid best_metric fields
        dry_run: If True, don't make any changes
    """
    db = next(get_database_session())
    try:
        metric_service = DatasetMetricService(db)

        # Get all evaluations
        evaluations = db.query(DBEvaluation).all()

        print(f"Analyzing {len(evaluations)} evaluations...")
        print()

        # Statistics
        total_evaluations = len(evaluations)
        evaluations_with_issues = 0
        evaluations_fixed = 0
        metrics_linked = 0
        best_metrics_fixed = 0

        # Track issues
        issues_by_dataset = defaultdict(lambda: {"evaluations": [], "metrics": set()})
        invalid_best_metrics = []

        for evaluation in evaluations:
            dataset_id = evaluation.dataset_id
            evaluation_id = evaluation.id

            if not evaluation.metrics:
                continue

            # Get allowed metrics for this dataset
            allowed_metrics = metric_service.get_allowed_metric_names(dataset_id)

            # Check if metrics are valid
            metric_keys = list(evaluation.metrics.keys())
            invalid_metrics = [m for m in metric_keys if m not in allowed_metrics]

            # Check best_metric
            best_metric_invalid = (
                evaluation.best_metric and evaluation.best_metric not in allowed_metrics
            )

            if invalid_metrics or best_metric_invalid:
                evaluations_with_issues += 1

                # Record invalid metrics
                if invalid_metrics:
                    issues_by_dataset[dataset_id]["evaluations"].append(evaluation_id)
                    issues_by_dataset[dataset_id]["metrics"].update(invalid_metrics)

                # Record invalid best_metric
                if best_metric_invalid:
                    invalid_best_metrics.append(
                        {
                            "evaluation_id": evaluation_id,
                            "dataset_id": dataset_id,
                            "best_metric": evaluation.best_metric,
                            "allowed_metrics": list(allowed_metrics),
                        }
                    )

        # Report findings
        print("=" * 70)
        print("ANALYSIS RESULTS")
        print("=" * 70)
        print(f"Total evaluations: {total_evaluations}")
        print(f"Evaluations with invalid metrics: {evaluations_with_issues}")
        print(f"Datasets affected: {len(issues_by_dataset)}")
        print()

        if not issues_by_dataset and not invalid_best_metrics:
            print("✅ All evaluations have valid metrics!")
            return

        # Show details for each affected dataset
        print("INVALID METRICS BY DATASET:")
        print("-" * 70)

        for dataset_id, issues in sorted(issues_by_dataset.items()):
            # Get dataset name
            dataset = db.query(DBDataset).filter(DBDataset.id == dataset_id).first()
            dataset_name = dataset.name if dataset else f"Dataset {dataset_id}"

            print(f"\n{dataset_name} (ID: {dataset_id})")
            print(f"  Affected evaluations: {len(issues['evaluations'])}")
            print(f"  Invalid metrics: {', '.join(sorted(issues['metrics']))}")

            # Show sample evaluation IDs
            sample_evals = issues["evaluations"][:5]
            print(f"  Sample evaluation IDs: {', '.join(map(str, sample_evals))}")
            if len(issues["evaluations"]) > 5:
                print(f"  ... and {len(issues['evaluations']) - 5} more")

        # Show invalid best_metric issues
        if invalid_best_metrics:
            print()
            print("INVALID BEST_METRIC VALUES:")
            print("-" * 70)
            for issue in invalid_best_metrics[:10]:
                print(
                    f"  Evaluation {issue['evaluation_id']} (Dataset {issue['dataset_id']})"
                )
                print(f"    Current: {issue['best_metric']}")
                print(f"    Allowed: {', '.join(issue['allowed_metrics'])}")

            if len(invalid_best_metrics) > 10:
                print(f"  ... and {len(invalid_best_metrics) - 10} more")

        # Perform fixes if requested
        if auto_link or fix_best_metric:
            print()
            print("=" * 70)
            print(
                "APPLYING FIXES" if not dry_run else "DRY RUN - NO CHANGES WILL BE MADE"
            )
            print("=" * 70)
            print()

            if auto_link:
                print("Auto-linking invalid metrics to datasets...")

                for dataset_id, issues in issues_by_dataset.items():
                    dataset = (
                        db.query(DBDataset).filter(DBDataset.id == dataset_id).first()
                    )
                    dataset_name = dataset.name if dataset else f"Dataset {dataset_id}"

                    for metric_name in issues["metrics"]:
                        # Check if metric exists in metrics table
                        metric = (
                            db.query(DBMetric)
                            .filter(DBMetric.name == metric_name)
                            .first()
                        )

                        if not metric:
                            print(
                                f"  ⚠️  Metric '{metric_name}' not found in metrics table - skipping"
                            )
                            continue

                        try:
                            if not dry_run:
                                metric_service.add_metric_to_dataset(
                                    dataset_id, metric_name
                                )
                            print(f"  ✅ Linked '{metric_name}' to {dataset_name}")
                            metrics_linked += 1
                        except ValueError as e:
                            if "already linked" not in str(e):
                                print(
                                    f"  ❌ Failed to link '{metric_name}' to {dataset_name}: {e}"
                                )
                        except Exception as e:
                            print(
                                f"  ❌ Error linking '{metric_name}' to {dataset_name}: {e}"
                            )

                evaluations_fixed = len(issues_by_dataset)

            if fix_best_metric:
                print()
                print("Fixing invalid best_metric values...")

                for issue in invalid_best_metrics:
                    evaluation_id = issue["evaluation_id"]
                    allowed = issue["allowed_metrics"]

                    if not allowed:
                        print(
                            f"  ⚠️  Evaluation {evaluation_id}: No allowed metrics to set as best_metric"
                        )
                        continue

                    # Use the first allowed metric as best_metric
                    new_best_metric = allowed[0]

                    evaluation = (
                        db.query(DBEvaluation)
                        .filter(DBEvaluation.id == evaluation_id)
                        .first()
                    )

                    if evaluation:
                        old_best = evaluation.best_metric
                        if not dry_run:
                            evaluation.best_metric = new_best_metric
                        print(
                            f"  ✅ Evaluation {evaluation_id}: '{old_best}' → '{new_best_metric}'"
                        )
                        best_metrics_fixed += 1

                if not dry_run:
                    db.commit()

        # Print summary
        print()
        print("=" * 70)
        print("SUMMARY")
        print("=" * 70)
        print(f"Evaluations analyzed: {total_evaluations}")
        print(f"Evaluations with issues: {evaluations_with_issues}")

        if auto_link or fix_best_metric:
            if not dry_run:
                print(f"Evaluations fixed: {evaluations_fixed}")
                print(f"Metrics linked: {metrics_linked}")
                print(f"Best metrics fixed: {best_metrics_fixed}")
                print()
                print("✅ Migration completed successfully!")
            else:
                print()
                print("ℹ️  This was a dry run - no changes were made")
                print("   Run without --dry-run to apply fixes")
        else:
            print()
            print("ℹ️  No fixes were applied")
            print("   Use --auto-link to automatically link metrics to datasets")
            print("   Use --fix-best-metric to fix invalid best_metric values")

        print()

    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migrate existing evaluations to fix invalid metrics"
    )
    parser.add_argument(
        "--auto-link",
        action="store_true",
        help="Automatically link metrics to datasets if not already linked",
    )
    parser.add_argument(
        "--fix-best-metric",
        action="store_true",
        help="Fix invalid best_metric by setting it to the first valid metric",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )

    args = parser.parse_args()

    try:
        migrate_evaluation_metrics(
            auto_link=args.auto_link,
            fix_best_metric=args.fix_best_metric,
            dry_run=args.dry_run,
        )
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
