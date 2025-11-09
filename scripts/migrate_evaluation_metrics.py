"""
DEPRECATED: Migrate existing evaluations to fix invalid metrics.

This script is deprecated as the dataset_metrics table has been removed.
Leaderboards are now defined by (task, dataset, metric) triples in task_dataset_metrics.

Use LeaderboardMetricService or API endpoints to manage task-dataset-metric triples instead.

Usage:
    uv run --env-file backend/keys.env python scripts/migrate_evaluation_metrics.py [--auto-link] [--fix-best-metric]

Options:
    --auto-link: Automatically link metrics to datasets if not already linked
    --fix-best-metric: Fix invalid best_metric by setting it to the first valid metric
    --dry-run: Show what would be done without making changes
"""

import sys

if __name__ == "__main__":
    print("=" * 70)
    print("DEPRECATED SCRIPT")
    print("=" * 70)
    print()
    print(
        "This script has been deprecated as the dataset_metrics table has been removed."
    )
    print("Leaderboards are now defined by (task, dataset, metric) triples.")
    print()
    print(
        "Use LeaderboardMetricService or API endpoints to manage task-dataset-metric triples:"
    )
    print("  - /api/v1/datasets/{dataset_id}/tasks/{task_id}/metrics")
    print()
    print(
        "Example: from backend.services.leaderboard_metric_service import LeaderboardMetricService"
    )
    print("=" * 70)
    sys.exit(1)
