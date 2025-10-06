#!/usr/bin/env python3
"""
Update methods table with image_url and image_credit from CSV file

This script imports image URLs and credits from the methods CSV export
and updates the methods table in the database.

Usage:
    uv run --env-file backend/keys.env python backend/database/methods_setup/update_method_images.py
"""

import csv
import os
import sys
from pathlib import Path
from typing import Dict, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))


def get_db_connection():
    """Get database connection using environment variables."""
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        database=os.getenv("DB_NAME", "paperswithcode_hf"),
        user=os.getenv("DB_USER", "paperswithcode_user"),
        password=os.getenv("DB_PASSWORD", "paperswithcode123"),
    )


def load_csv_images(csv_path: Path) -> Dict[int, Dict[str, Optional[str]]]:
    """
    Load image data from CSV file.

    Returns:
        Dictionary mapping method ID to {image_url, image_credit}
    """
    print(f"Loading image data from {csv_path}...")

    images_map = {}
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                method_id = int(row["id"])
                image_url = row.get("image_url", "").strip() or None
                image_credit = row.get("image_credit", "").strip() or None

                # Only add if at least one field has data
                if image_url or image_credit:
                    images_map[method_id] = {
                        "image_url": image_url,
                        "image_credit": image_credit,
                    }
            except (ValueError, KeyError) as e:
                print(f"Warning: Skipping row due to error: {e}")
                continue

    print(f"Loaded image data for {len(images_map)} methods")
    return images_map


def update_method_images():
    """Update methods table with image URLs and credits."""

    # Path to CSV file
    csv_path = Path("data/methods_export - methods_export.csv")

    if not csv_path.exists():
        print(f"Error: CSV file not found at {csv_path}")
        return

    # Load image data from CSV
    images_map = load_csv_images(csv_path)

    if not images_map:
        print("No image data found in CSV. Exiting.")
        return

    # Connect to database
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        print("\nUpdating methods table...")

        updated_count = 0
        skipped_count = 0
        not_found_count = 0

        for method_id, image_data in images_map.items():
            # Check if method exists
            cursor.execute("SELECT id, name FROM methods WHERE id = %s", (method_id,))
            result = cursor.fetchone()

            if not result:
                print(f"  ⚠ Method ID {method_id} not found in database")
                not_found_count += 1
                continue

            method_name = result["name"]
            image_url = image_data["image_url"]
            image_credit = image_data["image_credit"]

            # Update the method with image data
            cursor.execute(
                """
                UPDATE methods
                SET image_url = %s,
                    image_credit = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (image_url, image_credit, method_id),
            )

            if cursor.rowcount > 0:
                status = "✓" if image_url else "·"
                credit_info = (
                    f" (credit: {image_credit[:50]}...)"
                    if image_credit and len(image_credit) > 50
                    else f" (credit: {image_credit})"
                    if image_credit
                    else ""
                )
                print(f"  {status} Updated '{method_name}'{credit_info}")
                updated_count += 1
            else:
                print(f"  ⊘ Skipped '{method_name}' (no changes)")
                skipped_count += 1

        # Commit changes
        conn.commit()

        # Display summary
        print("\n" + "=" * 60)
        print("Update Summary:")
        print(f"  ✓ Updated: {updated_count} methods")
        print(f"  ⊘ Skipped: {skipped_count} methods")
        print(f"  ⚠ Not found: {not_found_count} methods")
        print("=" * 60)

        # Show statistics
        cursor.execute("SELECT COUNT(*) as total FROM methods")
        total_methods = cursor.fetchone()["total"]

        cursor.execute(
            "SELECT COUNT(*) as with_images FROM methods WHERE image_url IS NOT NULL"
        )
        methods_with_images = cursor.fetchone()["with_images"]

        cursor.execute(
            "SELECT COUNT(*) as with_credits FROM methods WHERE image_credit IS NOT NULL"
        )
        methods_with_credits = cursor.fetchone()["with_credits"]

        print("\nDatabase Statistics:")
        print(f"  Total methods: {total_methods}")
        print(
            f"  Methods with images: {methods_with_images} ({methods_with_images / total_methods * 100:.1f}%)"
        )
        print(
            f"  Methods with credits: {methods_with_credits} ({methods_with_credits / total_methods * 100:.1f}%)"
        )

        # Show some examples
        print("\nExample methods with images:")
        cursor.execute(
            """
            SELECT name, image_url, image_credit
            FROM methods
            WHERE image_url IS NOT NULL
            ORDER BY id
            LIMIT 5
            """
        )
        for row in cursor.fetchall():
            credit = (
                f" ({row['image_credit'][:40]}...)"
                if row["image_credit"] and len(row["image_credit"]) > 40
                else f" ({row['image_credit']})"
                if row["image_credit"]
                else ""
            )
            print(f"  • {row['name']}{credit}")

        cursor.close()
        conn.close()

        print("\n✅ Image data update complete!")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    update_method_images()
