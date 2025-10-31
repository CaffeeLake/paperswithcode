"""
Export dataset metrics template CSV for manual configuration.

This script generates a CSV file with all datasets and their currently-used metrics
(extracted from existing evaluations). The CSV includes an empty 'allowed_metrics'
column that can be manually filled in to configure which metrics are valid for each dataset.

Usage:
    uv run --env-file backend/keys.env python scripts/export_dataset_metrics_template.py
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

# Add parent directory to path so we can import from backend
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.database.connection import get_database_session
from backend.models.database import (
    Dataset as DBDataset,
    Evaluation as DBEvaluation,
)


def export_dataset_metrics_template():
    """
    Export a CSV template for configuring dataset-metric relationships.

    The CSV contains:
    - dataset_id: The database ID of the dataset
    - dataset_name: The name of the dataset
    - dataset_slug: The URL-friendly slug
    - current_metrics_used: Comma-separated list of metrics currently used in evaluations
    - allowed_metrics: Empty column for manual configuration
    """
    db = next(get_database_session())
    try:
        # Get all datasets
        datasets = db.query(DBDataset).order_by(DBDataset.name).all()

        # Collect metrics currently used for each dataset
        dataset_metrics = defaultdict(set)

        # Query all evaluations and extract metrics
        evaluations = db.query(DBEvaluation).all()
        for evaluation in evaluations:
            if evaluation.metrics:
                # Add all metric keys from this evaluation
                metric_keys = evaluation.metrics.keys()
                dataset_metrics[evaluation.dataset_id].update(metric_keys)

        # Generate CSV
        output_file = "dataset_metrics_template.csv"
        with open(output_file, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)

            # Write header
            writer.writerow(
                [
                    "dataset_id",
                    "dataset_name",
                    "dataset_slug",
                    "current_metrics_used",
                    "allowed_metrics",
                ]
            )

            # Write dataset rows
            for dataset in datasets:
                # Get metrics currently used for this dataset
                current_metrics = dataset_metrics.get(dataset.id, set())
                current_metrics_str = ", ".join(sorted(current_metrics))

                writer.writerow(
                    [
                        dataset.id,
                        dataset.name,
                        dataset.slug or "",
                        current_metrics_str,
                        "",  # Empty allowed_metrics column for manual entry
                    ]
                )

        print(f"✅ Exported dataset metrics template to: {output_file}")
        print(f"   Total datasets: {len(datasets)}")
        print(f"   Datasets with evaluations: {len(dataset_metrics)}")
        print()
        print("Next steps:")
        print("1. Open dataset_metrics_template.csv")
        print(
            "2. Fill in the 'allowed_metrics' column with comma-separated metric names"
        )
        print(
            "3. Run: uv run --env-file backend/keys.env python scripts/import_dataset_metrics_from_csv.py"
        )
        print()
        print("Example allowed_metrics values:")
        print("  - For COCO detection: AP, AP50, AP75, APs, APm, APl")
        print("  - For MMLU: Accuracy")
        print("  - For ASR datasets: WER, CER")

    finally:
        db.close()


if __name__ == "__main__":
    try:
        export_dataset_metrics_template()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
