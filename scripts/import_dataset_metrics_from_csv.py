"""
Import dataset-metric relationships from CSV.

This script reads the dataset_metrics_template.csv file (after manual configuration)
and populates the dataset_metrics junction table in the database.

Usage:
    uv run --env-file backend/keys.env python scripts/import_dataset_metrics_from_csv.py [csv_file]

Arguments:
    csv_file: Path to the CSV file (default: dataset_metrics_template.csv)
"""

import csv
import sys
from pathlib import Path

# Add parent directory to path so we can import from backend
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.database.connection import get_database_session
from backend.services.dataset_metric_service import DatasetMetricService


def import_dataset_metrics_from_csv(csv_file: str = "dataset_metrics_template.csv"):
    """
    Import dataset-metric relationships from a CSV file.

    The CSV should have columns:
    - dataset_id: The database ID of the dataset
    - dataset_name: The name of the dataset (informational only)
    - dataset_slug: The slug (informational only)
    - current_metrics_used: Current metrics (informational only)
    - allowed_metrics: Comma-separated list of metric names to allow

    Args:
        csv_file: Path to the CSV file
    """
    if not Path(csv_file).exists():
        print(f"❌ CSV file not found: {csv_file}")
        print()
        print("Please run the export script first:")
        print(
            "  uv run --env-file backend/keys.env python scripts/export_dataset_metrics_template.py"
        )
        sys.exit(1)

    db = next(get_database_session())
    try:
        service = DatasetMetricService(db)

        total_datasets = 0
        skipped_datasets = 0
        configured_datasets = 0
        total_metrics_added = 0
        errors = []

        with open(csv_file, "r", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)

            for row in reader:
                total_datasets += 1

                dataset_id = int(row["dataset_id"])
                dataset_name = row["dataset_name"]
                allowed_metrics_str = row["allowed_metrics"].strip()

                # Skip if no allowed metrics specified
                if not allowed_metrics_str:
                    skipped_datasets += 1
                    continue

                # Parse comma-separated metric names
                metric_names = [m.strip() for m in allowed_metrics_str.split(",")]
                metric_names = [m for m in metric_names if m]  # Remove empty strings

                if not metric_names:
                    skipped_datasets += 1
                    continue

                try:
                    # Set metrics for this dataset
                    service.set_dataset_metrics(dataset_id, metric_names)

                    configured_datasets += 1
                    total_metrics_added += len(metric_names)

                    print(
                        f"✅ Dataset {dataset_id} ({dataset_name}): Added {len(metric_names)} metrics"
                    )

                except ValueError as e:
                    error_msg = f"Dataset {dataset_id} ({dataset_name}): {e}"
                    errors.append(error_msg)
                    print(f"❌ {error_msg}")

                except Exception as e:
                    error_msg = (
                        f"Dataset {dataset_id} ({dataset_name}): Unexpected error: {e}"
                    )
                    errors.append(error_msg)
                    print(f"❌ {error_msg}")

        # Print summary
        print()
        print("=" * 60)
        print("IMPORT SUMMARY")
        print("=" * 60)
        print(f"Total datasets in CSV: {total_datasets}")
        print(f"Skipped (no metrics specified): {skipped_datasets}")
        print(f"Configured successfully: {configured_datasets}")
        print(f"Total metrics added: {total_metrics_added}")
        print(f"Errors: {len(errors)}")

        if errors:
            print()
            print("ERRORS:")
            for error in errors:
                print(f"  - {error}")

        print()
        if configured_datasets > 0:
            print("✅ Import completed successfully!")
            print()
            print("Next steps:")
            print(
                "1. Run: uv run --env-file backend/keys.env python scripts/migrate_evaluation_metrics.py"
            )
            print("   This will fix existing evaluations with invalid metrics")
        else:
            print("❌ No datasets were configured.")
            print()
            print("Please edit the CSV file and fill in the 'allowed_metrics' column.")

    finally:
        db.close()


if __name__ == "__main__":
    csv_file = sys.argv[1] if len(sys.argv) > 1 else "dataset_metrics_template.csv"

    try:
        import_dataset_metrics_from_csv(csv_file)
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
