#!/usr/bin/env python3
"""
Update datasets table from CSV file.

This script reads the manually curated datasets CSV and updates the PostgreSQL database.
It handles:
- Generating URL-friendly slugs
- Parsing JSONB fields (modalities, languages, variants)
- Using UPSERT logic for updates and inserts
- Preserving relationships
"""

import csv
import json
import re
import sys
from typing import Any, Dict, Optional

import psycopg2
from psycopg2.extras import RealDictCursor


def generate_slug(name: str) -> str:
    """Generate a URL-friendly slug from a dataset name."""
    slug = name.lower()
    # Replace non-alphanumeric characters with hyphens
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    # Remove leading/trailing hyphens
    slug = slug.strip("-")
    return slug


def parse_jsonb_field(value: str) -> Optional[list]:
    """Parse a JSONB field from CSV (stored as JSON string)."""
    if not value or value.strip() in ("", "/", "N/A"):
        return None
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return parsed
        return None
    except (json.JSONDecodeError, TypeError):
        return None


def clean_value(value: str) -> Optional[str]:
    """Clean a CSV value, treating empty/N/A as NULL."""
    if not value or value.strip() in ("", "/", "N/A"):
        return None
    return value.strip()


def parse_int(value: str) -> Optional[int]:
    """Parse an integer value from CSV."""
    if not value or value.strip() in ("", "/", "N/A"):
        return None
    try:
        return int(value)
    except ValueError:
        return None


def read_csv_datasets(csv_path: str) -> list[Dict[str, Any]]:
    """Read datasets from CSV file."""
    datasets = []

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            dataset_id = int(row["id"])
            name = row["name"]
            full_name = clean_value(row["full_name"]) or name  # Use name as fallback

            # Generate slug if not in CSV or use provided one
            slug = clean_value(row.get("slug")) or generate_slug(name)

            dataset = {
                "id": dataset_id,
                "name": name,
                "full_name": full_name,
                "description": clean_value(row["description"]),
                "url": clean_value(row["url"]),
                "paper_url": clean_value(row["paper_url"]),
                "hf_url": clean_value(row["hf_url"]),
                "parent_dataset_id": parse_int(row["parent_dataset_id"]),
                "image_url": clean_value(row["image_url"]),
                "license_name": clean_value(row["license_name"]),
                "license_url": clean_value(row["license_url"]),
                "modalities": parse_jsonb_field(row["modalities"]),
                "languages": parse_jsonb_field(row["languages"]),
                "variants": parse_jsonb_field(row["variants"]),
                "slug": slug,
                "variant_type": clean_value(row["variant_type"]),
                "split_name": clean_value(row["split_name"]),
            }

            datasets.append(dataset)

    return datasets


def check_slug_uniqueness(datasets: list[Dict[str, Any]]) -> tuple[bool, list]:
    """Check if all slugs are unique."""
    slugs = [d["slug"] for d in datasets]
    duplicates = []
    seen = {}

    for i, slug in enumerate(slugs):
        if slug in seen:
            duplicates.append(
                {
                    "slug": slug,
                    "datasets": [datasets[seen[slug]]["name"], datasets[i]["name"]],
                }
            )
        else:
            seen[slug] = i

    return len(duplicates) == 0, duplicates


def upsert_datasets(conn, datasets: list[Dict[str, Any]], dry_run: bool = True):
    """Upsert datasets into the database."""
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # SQL for UPSERT - match on slug first, then ID
    upsert_sql = """
    INSERT INTO datasets (
        id, name, full_name, description, url, paper_url, hf_url,
        parent_dataset_id, image_url, license_name, license_url,
        modalities, languages, variants, slug, variant_type, split_name,
        updated_at
    ) VALUES (
        %(id)s, %(name)s, %(full_name)s, %(description)s, %(url)s,
        %(paper_url)s, %(hf_url)s, %(parent_dataset_id)s, %(image_url)s,
        %(license_name)s, %(license_url)s, %(modalities)s, %(languages)s,
        %(variants)s, %(slug)s, %(variant_type)s, %(split_name)s,
        CURRENT_TIMESTAMP
    )
    ON CONFLICT (slug) DO UPDATE SET
        name = EXCLUDED.name,
        full_name = EXCLUDED.full_name,
        description = EXCLUDED.description,
        url = EXCLUDED.url,
        paper_url = EXCLUDED.paper_url,
        hf_url = EXCLUDED.hf_url,
        parent_dataset_id = EXCLUDED.parent_dataset_id,
        image_url = EXCLUDED.image_url,
        license_name = EXCLUDED.license_name,
        license_url = EXCLUDED.license_url,
        modalities = EXCLUDED.modalities,
        languages = EXCLUDED.languages,
        variants = EXCLUDED.variants,
        variant_type = EXCLUDED.variant_type,
        split_name = EXCLUDED.split_name,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id, name, slug;
    """

    updated_count = 0
    inserted_count = 0

    # Check which datasets are new vs existing (by slug)
    cur.execute("SELECT id, slug FROM datasets")
    existing_slugs = {row["slug"]: row["id"] for row in cur.fetchall() if row["slug"]}

    print(f"\n{'=' * 80}")
    print(f"UPSERT DATASETS - {'DRY RUN' if dry_run else 'EXECUTING'}")
    print(f"{'=' * 80}\n")

    for dataset in datasets:
        is_new = dataset["slug"] not in existing_slugs
        existing_id = existing_slugs.get(dataset["slug"])

        if dry_run:
            action = "INSERT" if is_new else "UPDATE"
            id_note = (
                f" (DB ID: {existing_id})"
                if existing_id and existing_id != dataset["id"]
                else ""
            )
            print(
                f"[{action}] ID {dataset['id']}: {dataset['name']} (slug: {dataset['slug']}){id_note}"
            )
        else:
            # Convert lists to JSON strings for JSONB fields
            params = dataset.copy()
            if params["modalities"]:
                params["modalities"] = json.dumps(params["modalities"])
            if params["languages"]:
                params["languages"] = json.dumps(params["languages"])
            if params["variants"]:
                params["variants"] = json.dumps(params["variants"])

            cur.execute(upsert_sql, params)
            result = cur.fetchone()

            if is_new:
                inserted_count += 1
                print(
                    f"[INSERTED] ID {result['id']}: {result['name']} (slug: {result['slug']})"
                )
            else:
                updated_count += 1
                id_note = (
                    f" (DB ID: {result['id']})" if result["id"] != dataset["id"] else ""
                )
                print(
                    f"[UPDATED] ID {result['id']}: {result['name']} (slug: {result['slug']}){id_note}"
                )

    print(f"\n{'=' * 80}")
    if dry_run:
        print("DRY RUN SUMMARY:")
        print(
            f"  Would insert: {len([d for d in datasets if d['slug'] not in existing_slugs])} datasets"
        )
        print(
            f"  Would update: {len([d for d in datasets if d['slug'] in existing_slugs])} datasets"
        )
    else:
        print("EXECUTION SUMMARY:")
        print(f"  Inserted: {inserted_count} datasets")
        print(f"  Updated: {updated_count} datasets")
    print(f"{'=' * 80}\n")

    cur.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Update datasets from CSV file")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute the update without confirmation prompt",
    )
    parser.add_argument(
        "--dry-run-only",
        action="store_true",
        help="Only perform dry run without asking for confirmation",
    )
    args = parser.parse_args()

    csv_path = "data/updated_datasets.csv"

    print("Reading datasets from CSV...")
    datasets = read_csv_datasets(csv_path)
    print(f"✓ Loaded {len(datasets)} datasets from CSV\n")

    # Check slug uniqueness
    print("Checking slug uniqueness...")
    is_unique, duplicates = check_slug_uniqueness(datasets)

    if not is_unique:
        print("✗ ERROR: Duplicate slugs found!")
        for dup in duplicates:
            print(f"  Slug '{dup['slug']}' used by: {', '.join(dup['datasets'])}")
        sys.exit(1)

    print(f"✓ All {len(datasets)} slugs are unique\n")

    # Show sample slugs
    print("Sample generated slugs:")
    for dataset in datasets[:10]:
        print(f"  {dataset['name']:30s} → {dataset['slug']}")
    print()

    # Connect to database
    try:
        conn = psycopg2.connect(
            "host=localhost dbname=paperswithcode_hf user=paperswithcode_user password=paperswithcode123"
        )
    except psycopg2.Error as e:
        print(f"✗ Database connection error: {e}")
        sys.exit(1)

    print("✓ Connected to database\n")

    try:
        # First, do a dry run
        upsert_datasets(conn, datasets, dry_run=True)

        if args.dry_run_only:
            print("\nDry run only mode - exiting without making changes.")
            return

        # Determine if we should proceed
        should_proceed = args.execute

        if not should_proceed:
            try:
                response = (
                    input("\nProceed with actual database update? (yes/no): ")
                    .strip()
                    .lower()
                )
                should_proceed = response == "yes"
            except EOFError:
                print(
                    "\n✗ No input available. Use --execute flag to run without confirmation."
                )
                conn.rollback()
                return

        if should_proceed:
            print("\nExecuting database update...")
            upsert_datasets(conn, datasets, dry_run=False)
            conn.commit()
            print("✓ Database update committed successfully!")
        else:
            print("Update cancelled by user.")
            conn.rollback()

    except Exception as e:
        print(f"\n✗ Error during update: {e}")
        conn.rollback()
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    main()
