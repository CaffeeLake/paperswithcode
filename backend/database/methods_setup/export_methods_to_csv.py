#!/usr/bin/env python3
"""
Export methods table from PostgreSQL to CSV file.
"""

import csv
import sys
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor

# Database connection settings
DB_CONFIG = {
    "dbname": "paperswithcode_hf",
    "user": "paperswithcode_user",
    "password": "paperswithcode123",
    "host": "localhost",
    "port": "5432",
}


def get_db_connection():
    """Create and return a database connection."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except psycopg2.Error as e:
        print(f"Error connecting to database: {e}")
        sys.exit(1)


def export_methods_to_csv(conn, output_file: str) -> None:
    """
    Export all methods from the database to a CSV file.

    Args:
        conn: Database connection
        output_file: Path to output CSV file
    """
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Query to get all methods
    query = """
        SELECT
            id,
            name,
            full_name,
            description,
            introduced_year,
            source_url,
            source_title,
            code_snippet_url,
            collection_name,
            collection_description,
            collection_parent,
            collection_area,
            created_at,
            updated_at,
            area_id,
            image_url,
            image_credit
        FROM methods
        ORDER BY id;
    """

    print("Exporting methods from database...")
    cursor.execute(query)
    methods = cursor.fetchall()

    print(f"Found {len(methods)} methods to export.")

    # Define CSV columns (same order as query)
    fieldnames = [
        "id",
        "name",
        "full_name",
        "description",
        "introduced_year",
        "source_url",
        "source_title",
        "code_snippet_url",
        "collection_name",
        "collection_description",
        "collection_parent",
        "collection_area",
        "created_at",
        "updated_at",
        "area_id",
        "image_url",
        "image_credit",
    ]

    # Write to CSV
    with open(output_file, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for method in methods:
            # Convert datetime objects to strings
            row = dict(method)
            if row.get("created_at"):
                row["created_at"] = row["created_at"].isoformat()
            if row.get("updated_at"):
                row["updated_at"] = row["updated_at"].isoformat()

            writer.writerow(row)

    cursor.close()
    print(f"✅ Successfully exported {len(methods)} methods to: {output_file}")


def main():
    """Main function to export methods."""
    import argparse

    parser = argparse.ArgumentParser(description="Export methods table to CSV")
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Output CSV file path (default: data/methods_export_YYYYMMDD_HHMMSS.csv)",
    )
    args = parser.parse_args()

    # Generate default filename with timestamp if not specified
    if args.output is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = (
            f"/root/python_projects/paperswithcode/data/methods_export_{timestamp}.csv"
        )
    else:
        output_file = args.output

    print("=" * 70)
    print("Methods Table Export Script")
    print("=" * 70)
    print()

    # Connect to database
    print("Connecting to database...")
    conn = get_db_connection()

    try:
        # Export methods
        export_methods_to_csv(conn, output_file)

        print()
        print("=" * 70)
        print("Export completed!")
        print("=" * 70)

    except Exception as e:
        print(f"\nError during export: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
