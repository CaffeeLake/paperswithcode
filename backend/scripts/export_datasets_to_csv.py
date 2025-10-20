"""
Export datasets table to CSV for manual editing in Excel.
Includes all columns from the datasets table.
"""

import csv
import json
import os
from typing import Any
import psycopg2
from psycopg2.extras import RealDictCursor
from logging_config import setup_logging

logger = setup_logging("export_datasets_to_csv")


def get_db_connection():
    """Get database connection using environment variables."""
    return psycopg2.connect(
        host=os.getenv("PWC_DB_HOST", "localhost"),
        port=os.getenv("PWC_DB_PORT", "5432"),
        database=os.getenv("PWC_DB_NAME", "paperswithcode_hf"),
        user=os.getenv("PWC_DB_USER", "postgres"),
        password=os.getenv("PWC_DB_PASSWORD", ""),
    )


def convert_value_for_csv(value: Any) -> str:
    """Convert database values to CSV-friendly strings."""
    if value is None:
        return ""
    elif isinstance(value, (list, dict)):
        # Convert JSONB arrays/objects to JSON strings
        return json.dumps(value)
    elif isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    else:
        return str(value)


def export_datasets_to_csv(output_file: str = "datasets_export.csv"):
    """Export all datasets with all columns to CSV."""

    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # Get all columns from the datasets table
        cursor.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'datasets'
            ORDER BY ordinal_position
        """)

        columns_info = cursor.fetchall()
        column_names = [col["column_name"] for col in columns_info]

        logger.info(f"Found {len(column_names)} columns in datasets table")
        logger.info(f"Columns: {', '.join(column_names)}")

        # Fetch all datasets
        cursor.execute("""
            SELECT *
            FROM datasets
            ORDER BY id
        """)

        datasets = cursor.fetchall()
        logger.info(f"Found {len(datasets)} datasets to export")

        # Write to CSV
        with open(output_file, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile, quoting=csv.QUOTE_MINIMAL)

            # Write header
            writer.writerow(column_names)

            # Write data rows
            for dataset in datasets:
                row = [convert_value_for_csv(dataset[col]) for col in column_names]
                writer.writerow(row)

        cursor.close()
        conn.close()

        logger.info(f"Successfully exported {len(datasets)} datasets to {output_file}")
        print("\n✓ Export complete!")
        print(f"  File: {output_file}")
        print(f"  Datasets exported: {len(datasets)}")
        print(f"  Columns: {len(column_names)}")

        return output_file

    except Exception as e:
        logger.error(f"Error exporting datasets: {e}", exc_info=True)
        print(f"\n✗ Error: {e}")
        raise


if __name__ == "__main__":
    export_datasets_to_csv()
