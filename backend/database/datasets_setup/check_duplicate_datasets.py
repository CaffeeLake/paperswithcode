"""
Check for duplicate datasets in the database.

This script identifies potential duplicates based on:
- Name (case-insensitive)
- URL (if not null)
- HF URL (if not null)
- Slug (should be unique)
"""

import sys
from collections import defaultdict
from typing import Dict, List

from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import Dataset


def find_duplicates_by_name(db: Session) -> Dict[str, List[Dataset]]:
    """Find datasets with duplicate names (case-insensitive)."""
    duplicates = defaultdict(list)

    # Query all datasets and group by lowercase name
    datasets = db.query(Dataset).all()
    for dataset in datasets:
        if dataset.name:
            key = dataset.name.lower().strip()
            duplicates[key].append(dataset)

    # Filter to only include groups with 2+ datasets
    return {k: v for k, v in duplicates.items() if len(v) > 1}


def find_duplicates_by_url(db: Session) -> Dict[str, List[Dataset]]:
    """Find datasets with duplicate URLs."""
    duplicates = defaultdict(list)

    datasets = db.query(Dataset).filter(Dataset.url.isnot(None)).all()
    for dataset in datasets:
        if dataset.url:
            # Normalize URL (remove trailing slash, lowercase)
            normalized_url = dataset.url.rstrip("/").lower()
            duplicates[normalized_url].append(dataset)

    return {k: v for k, v in duplicates.items() if len(v) > 1}


def find_duplicates_by_hf_url(db: Session) -> Dict[str, List[Dataset]]:
    """Find datasets with duplicate Hugging Face URLs."""
    duplicates = defaultdict(list)

    datasets = db.query(Dataset).filter(Dataset.hf_url.isnot(None)).all()
    for dataset in datasets:
        if dataset.hf_url:
            # Normalize URL (remove trailing slash, lowercase)
            normalized_url = dataset.hf_url.rstrip("/").lower()
            duplicates[normalized_url].append(dataset)

    return {k: v for k, v in duplicates.items() if len(v) > 1}


def find_duplicate_slugs(db: Session) -> Dict[str, List[Dataset]]:
    """Find datasets with duplicate slugs (should not happen due to unique constraint)."""
    duplicates = defaultdict(list)

    datasets = db.query(Dataset).filter(Dataset.slug.isnot(None)).all()
    for dataset in datasets:
        if dataset.slug:
            duplicates[dataset.slug].append(dataset)

    return {k: v for k, v in duplicates.items() if len(v) > 1}


def print_duplicates(title: str, duplicates: Dict[str, List[Dataset]]):
    """Print duplicate datasets in a formatted way."""
    if not duplicates:
        print(f"✓ No duplicates found by {title}")
        return

    print(f"\n{'=' * 80}")
    print(f"⚠️  Duplicates found by {title}: {len(duplicates)} groups")
    print(f"{'=' * 80}")

    for key, datasets in sorted(duplicates.items()):
        print(f"\n{title}: '{key}'")
        print(f"  Found {len(datasets)} datasets:")
        for dataset in sorted(datasets, key=lambda d: d.id):
            print(f"    ID {dataset.id:5d}: {dataset.name}")
            if dataset.slug:
                print(f"             Slug: {dataset.slug}")
            if dataset.url:
                print(f"             URL: {dataset.url}")
            if dataset.hf_url:
                print(f"             HF URL: {dataset.hf_url}")
            if dataset.parent_dataset_id:
                print(f"             Parent ID: {dataset.parent_dataset_id}")
            if dataset.variant_type:
                print(f"             Variant Type: {dataset.variant_type}")
            if dataset.split_name:
                print(f"             Split Name: {dataset.split_name}")
            print()


def get_dataset_stats(db: Session) -> Dict[str, int]:
    """Get overall statistics about datasets."""
    total = db.query(Dataset).count()
    with_slug = db.query(Dataset).filter(Dataset.slug.isnot(None)).count()
    with_url = db.query(Dataset).filter(Dataset.url.isnot(None)).count()
    with_hf_url = db.query(Dataset).filter(Dataset.hf_url.isnot(None)).count()
    with_parent = (
        db.query(Dataset).filter(Dataset.parent_dataset_id.isnot(None)).count()
    )

    return {
        "total": total,
        "with_slug": with_slug,
        "with_url": with_url,
        "with_hf_url": with_hf_url,
        "with_parent": with_parent,
    }


def main():
    """Main function to check for duplicate datasets."""
    print("=" * 80)
    print("Checking for duplicate datasets in the database")
    print("=" * 80)

    # Get database session
    session = db_manager.session_local()

    try:
        # Print statistics
        stats = get_dataset_stats(session)
        print("\nDataset Statistics:")
        print(f"  Total datasets: {stats['total']:,}")
        print(f"  With slug: {stats['with_slug']:,}")
        print(f"  With URL: {stats['with_url']:,}")
        print(f"  With HF URL: {stats['with_hf_url']:,}")
        print(f"  With parent (variants): {stats['with_parent']:,}")

        # Check for duplicates
        print("\n" + "=" * 80)
        print("Checking for duplicates...")
        print("=" * 80)

        name_duplicates = find_duplicates_by_name(session)
        url_duplicates = find_duplicates_by_url(session)
        hf_url_duplicates = find_duplicates_by_hf_url(session)
        slug_duplicates = find_duplicate_slugs(session)

        # Print results
        print_duplicates("Name (case-insensitive)", name_duplicates)
        print_duplicates("URL", url_duplicates)
        print_duplicates("HF URL", hf_url_duplicates)
        print_duplicates("Slug", slug_duplicates)

        # Summary
        total_duplicate_groups = (
            len(name_duplicates)
            + len(url_duplicates)
            + len(hf_url_duplicates)
            + len(slug_duplicates)
        )

        print("\n" + "=" * 80)
        print("Summary")
        print("=" * 80)
        print("Duplicate groups found:")
        print(f"  By name: {len(name_duplicates)}")
        print(f"  By URL: {len(url_duplicates)}")
        print(f"  By HF URL: {len(hf_url_duplicates)}")
        print(f"  By slug: {len(slug_duplicates)}")
        print(f"  Total: {total_duplicate_groups}")

        if total_duplicate_groups > 0:
            print("\n⚠️  WARNING: Duplicates found! Review the output above.")
            return 1
        else:
            print("\n✓ No duplicates found!")
            return 0

    except Exception as e:
        print(f"\n❌ Error checking duplicates: {e}")
        import traceback

        traceback.print_exc()
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
