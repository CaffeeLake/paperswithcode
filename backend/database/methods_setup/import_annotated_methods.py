#!/usr/bin/env python3
"""
Import annotated methods data from CSV to PostgreSQL methods table.
This script will overwrite existing data with the annotated information.
"""

import csv
import sys
import psycopg2
from typing import Dict, List, Optional

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


def parse_csv_value(value: str) -> Optional[str]:
    """Parse CSV value, converting empty strings to None."""
    if value is None or value.strip() == "":
        return None
    return value.strip()


def parse_int_value(value: str) -> Optional[int]:
    """Parse integer value from CSV, returning None for empty/invalid values."""
    if value is None or value.strip() == "":
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


def read_methods_csv(csv_path: str) -> List[Dict]:
    """Read methods data from CSV file."""
    methods = []

    print(f"Reading CSV file: {csv_path}")

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            method = {
                "id": parse_int_value(row["id"]),
                "name": parse_csv_value(row["name"]),
                "full_name": parse_csv_value(row["full_name"]),
                "description": parse_csv_value(row["description"]),
                "introduced_year": parse_int_value(row.get("introduced_year")),
                "source_url": parse_csv_value(row.get("source_url")),
                "source_title": parse_csv_value(row.get("source_title")),
                "code_snippet_url": parse_csv_value(row.get("code_snippet_url")),
                "collection_name": parse_csv_value(row.get("collection_name")),
                "collection_description": parse_csv_value(
                    row.get("collection_description")
                ),
                "collection_parent": parse_csv_value(row.get("collection_parent")),
                "collection_area": parse_csv_value(row.get("collection_area")),
                "area_id": parse_int_value(row.get("area_id")),
                "image_url": parse_csv_value(row.get("image_url")),
                "image_credit": parse_csv_value(row.get("image_credit")),
            }

            # Skip rows without required fields
            if method["id"] is None or method["name"] is None:
                print(f"Warning: Skipping row with missing id or name: {row}")
                continue

            methods.append(method)

    print(f"Read {len(methods)} methods from CSV")
    return methods


def update_methods(conn, methods: List[Dict]) -> None:
    """Update or insert methods into the database."""
    cursor = conn.cursor()

    # Use UPSERT (INSERT ... ON CONFLICT ... UPDATE) to overwrite existing data
    upsert_query = """
        INSERT INTO methods (
            id, name, full_name, description, introduced_year,
            source_url, source_title, code_snippet_url,
            collection_name, collection_description, collection_parent, collection_area,
            area_id, image_url, image_credit, updated_at
        ) VALUES (
            %(id)s, %(name)s, %(full_name)s, %(description)s, %(introduced_year)s,
            %(source_url)s, %(source_title)s, %(code_snippet_url)s,
            %(collection_name)s, %(collection_description)s, %(collection_parent)s, %(collection_area)s,
            %(area_id)s, %(image_url)s, %(image_credit)s, CURRENT_TIMESTAMP
        )
        ON CONFLICT (id)
        DO UPDATE SET
            name = EXCLUDED.name,
            full_name = EXCLUDED.full_name,
            description = EXCLUDED.description,
            introduced_year = EXCLUDED.introduced_year,
            source_url = EXCLUDED.source_url,
            source_title = EXCLUDED.source_title,
            code_snippet_url = EXCLUDED.code_snippet_url,
            collection_name = EXCLUDED.collection_name,
            collection_description = EXCLUDED.collection_description,
            collection_parent = EXCLUDED.collection_parent,
            collection_area = EXCLUDED.collection_area,
            area_id = EXCLUDED.area_id,
            image_url = EXCLUDED.image_url,
            image_credit = EXCLUDED.image_credit,
            updated_at = CURRENT_TIMESTAMP;
    """

    updated_count = 0
    inserted_count = 0

    for method in methods:
        # Check if method exists
        cursor.execute("SELECT id FROM methods WHERE id = %s", (method["id"],))
        exists = cursor.fetchone() is not None

        # Execute upsert
        cursor.execute(upsert_query, method)

        if exists:
            updated_count += 1
        else:
            inserted_count += 1

        if (updated_count + inserted_count) % 50 == 0:
            print(f"Processed {updated_count + inserted_count} methods...")

    # Update sequence to ensure new inserts don't conflict
    cursor.execute("""
        SELECT setval('methods_id_seq', (SELECT MAX(id) FROM methods));
    """)

    conn.commit()
    cursor.close()

    print("\nImport complete!")
    print(f"  - Updated: {updated_count} methods")
    print(f"  - Inserted: {inserted_count} new methods")
    print(f"  - Total: {updated_count + inserted_count} methods processed")


def verify_import(conn) -> None:
    """Verify the import by checking some statistics."""
    cursor = conn.cursor()

    # Count total methods
    cursor.execute("SELECT COUNT(*) FROM methods")
    total = cursor.fetchone()[0]

    # Count methods with descriptions
    cursor.execute(
        "SELECT COUNT(*) FROM methods WHERE description IS NOT NULL AND description != ''"
    )
    with_desc = cursor.fetchone()[0]

    # Count methods with images
    cursor.execute(
        "SELECT COUNT(*) FROM methods WHERE image_url IS NOT NULL AND image_url != ''"
    )
    with_images = cursor.fetchone()[0]

    # Count methods with source URLs
    cursor.execute(
        "SELECT COUNT(*) FROM methods WHERE source_url IS NOT NULL AND source_url != ''"
    )
    with_sources = cursor.fetchone()[0]

    # Count methods with introduction year
    cursor.execute("SELECT COUNT(*) FROM methods WHERE introduced_year IS NOT NULL")
    with_year = cursor.fetchone()[0]

    cursor.close()

    print("\nDatabase statistics after import:")
    print(f"  Total methods: {total}")
    print(
        f"  With descriptions: {with_desc} ({100 * with_desc // total if total > 0 else 0}%)"
    )
    print(
        f"  With images: {with_images} ({100 * with_images // total if total > 0 else 0}%)"
    )
    print(
        f"  With source URLs: {with_sources} ({100 * with_sources // total if total > 0 else 0}%)"
    )
    print(
        f"  With introduction year: {with_year} ({100 * with_year // total if total > 0 else 0}%)"
    )


def main():
    """Main function to import annotated methods data."""
    csv_path = "/root/python_projects/paperswithcode/data/methods_export_20251006_131751 - methods_export_20251006_131751.csv"

    print("=" * 70)
    print("Methods Annotation Import Script")
    print("=" * 70)
    print()

    # Read CSV data
    methods = read_methods_csv(csv_path)

    if not methods:
        print("No methods found in CSV file. Exiting.")
        return

    # Connect to database
    print("\nConnecting to database...")
    conn = get_db_connection()

    try:
        # Update methods
        print("\nUpdating methods in database...")
        update_methods(conn, methods)

        # Verify import
        verify_import(conn)

        print("\n" + "=" * 70)
        print("Import completed successfully!")
        print("=" * 70)

    except Exception as e:
        print(f"\nError during import: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
