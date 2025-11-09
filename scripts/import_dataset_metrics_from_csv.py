"""
DEPRECATED: Import dataset-metric relationships from CSV.

This script is deprecated as the dataset_metrics table has been removed.
Leaderboards are now defined by (task, dataset, metric) triples in task_dataset_metrics.

Use the API endpoints or LeaderboardMetricService to manage task-dataset-metric triples instead.

Usage:
    uv run --env-file backend/keys.env python scripts/import_dataset_metrics_from_csv.py [csv_file]

Arguments:
    csv_file: Path to the CSV file (default: dataset_metrics_template.csv)
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
