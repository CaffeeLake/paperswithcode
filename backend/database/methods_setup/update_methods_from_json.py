#!/usr/bin/env python3
"""
Update methods table with description, source_url, and source_title from jul-28-methods.json

This script matches methods in the database with the JSON data by name and updates
the description, source_url, and source_title fields.

Usage:
    uv run --env-file backend/keys.env backend/database/update_methods_from_json.py
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict

import psycopg2
from psycopg2.extras import RealDictCursor

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def load_json_methods(json_path: Path) -> Dict[str, dict]:
    """
    Load methods from JSON file and create a name-to-data mapping.

    Returns:
        Dictionary mapping method name to method data
    """
    print(f"Loading methods from {json_path}...")

    with open(json_path, "r", encoding="utf-8") as f:
        methods_list = json.load(f)

    print(f"Loaded {len(methods_list)} methods from JSON")

    # Create mapping by name (case-insensitive for better matching)
    methods_map = {}
    for method in methods_list:
        name = method.get("name", "").strip()
        if name:
            # Store both the exact name and lowercase version for flexible matching
            methods_map[name] = method
            methods_map[name.lower()] = method

    print(f"Created mapping with {len(methods_map)} entries")
    return methods_map


def get_db_connection():
    """Get database connection using environment variables."""
    db_params = {
        "host": os.getenv("PWC_DB_HOST", "localhost"),
        "port": os.getenv("PWC_DB_PORT", "5432"),
        "database": os.getenv("PWC_DB_NAME", "paperswithcode_hf"),
        "user": os.getenv("PWC_DB_USER", "postgres"),
        "password": os.getenv("PWC_DB_PASSWORD", ""),
    }

    return psycopg2.connect(**db_params)


def update_methods_table(methods_map: Dict[str, dict], dry_run: bool = False):
    """
    Update methods table with data from JSON.

    Args:
        methods_map: Dictionary mapping method names to method data
        dry_run: If True, only show what would be updated without making changes
    """
    conn = get_db_connection()

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get all methods from database
            cur.execute(
                "SELECT id, name, description, source_url, source_title FROM methods ORDER BY id"
            )
            db_methods = cur.fetchall()

            print(f"\nFound {len(db_methods)} methods in database")

            matched = 0
            updated = 0
            already_complete = 0
            not_found = 0

            for db_method in db_methods:
                method_id = db_method["id"]
                method_name = db_method["name"]

                # Check if already has all data
                if (
                    db_method["description"]
                    and db_method["source_url"]
                    and db_method["source_title"]
                ):
                    already_complete += 1
                    continue

                # Try exact match first, then case-insensitive
                json_method = methods_map.get(method_name) or methods_map.get(
                    method_name.lower()
                )

                if json_method:
                    matched += 1

                    # Get values from JSON (handle None values)
                    description = (json_method.get("description") or "").strip()
                    source_url = (json_method.get("source_url") or "").strip()
                    source_title = (json_method.get("source_title") or "").strip()

                    # Determine what needs updating
                    updates = []
                    params = []

                    if description and not db_method["description"]:
                        updates.append("description = %s")
                        params.append(description)

                    if source_url and not db_method["source_url"]:
                        updates.append("source_url = %s")
                        params.append(source_url)

                    if source_title and not db_method["source_title"]:
                        updates.append("source_title = %s")
                        params.append(source_title)

                    if updates:
                        params.append(method_id)
                        update_query = f"""
                            UPDATE methods
                            SET {", ".join(updates)}
                            WHERE id = %s
                        """

                        if dry_run:
                            print(
                                f"\n[DRY RUN] Would update method '{method_name}' (ID: {method_id}):"
                            )
                            if description and not db_method["description"]:
                                print(f"  - Description: {description[:100]}...")
                            if source_url and not db_method["source_url"]:
                                print(f"  - Source URL: {source_url}")
                            if source_title and not db_method["source_title"]:
                                print(f"  - Source Title: {source_title}")
                        else:
                            cur.execute(update_query, params)
                            updated += 1

                            if updated % 10 == 0:
                                print(f"Updated {updated} methods...", end="\r")
                else:
                    not_found += 1
                    if not_found <= 10:  # Show first 10 not found
                        print(f"No match found for: {method_name}")

            if not dry_run:
                conn.commit()
                print(f"\n✓ Successfully updated {updated} methods")
            else:
                print(f"\n[DRY RUN] Would update {matched} methods")

            print("\nSummary:")
            print(f"  - Total methods in database: {len(db_methods)}")
            print(f"  - Already complete: {already_complete}")
            print(f"  - Matched in JSON: {matched}")
            print(f"  - Updated: {updated if not dry_run else 'N/A (dry run)'}")
            print(f"  - Not found in JSON: {not_found}")

    except Exception as e:
        conn.rollback()
        print(f"\n✗ Error updating methods: {e}")
        raise
    finally:
        conn.close()


def main():
    """Main execution function."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Update methods table with data from jul-28-methods.json"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be updated without making changes",
    )

    args = parser.parse_args()

    # Path to JSON file
    json_path = project_root / "data" / "jul-28-methods.json"

    if not json_path.exists():
        print(f"✗ Error: JSON file not found at {json_path}")
        sys.exit(1)

    print("=" * 70)
    print("Methods Table Update Script")
    print("=" * 70)

    if args.dry_run:
        print("\n⚠️  DRY RUN MODE - No changes will be made to the database\n")

    # Load JSON data
    methods_map = load_json_methods(json_path)

    # Update database
    update_methods_table(methods_map, dry_run=args.dry_run)

    print("\n" + "=" * 70)
    print("Update complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()
