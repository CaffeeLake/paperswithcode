#!/usr/bin/env python3
"""
Check for possible duplicates in the datasets table.

This script looks for:
1. Exact name duplicates
2. Case-insensitive name duplicates
3. Slug duplicates (shouldn't exist due to UNIQUE constraint)
4. Same URL duplicates
5. Same hf_url duplicates
6. Very similar names (using fuzzy matching)
"""

import sys
from collections import defaultdict
from difflib import SequenceMatcher
from typing import List, Dict, Any

from sqlalchemy import func
from sqlalchemy.orm import Session

sys.path.insert(0, "/root/python_projects/paperswithcode")

from backend.database.connection import db_manager
from backend.models.database import Dataset as DBDataset


def similarity_ratio(a: str, b: str) -> float:
    """Calculate similarity ratio between two strings."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def check_exact_name_duplicates(session: Session) -> List[Dict[str, Any]]:
    """Check for exact name duplicates."""
    print("\n" + "=" * 80)
    print("1. EXACT NAME DUPLICATES")
    print("=" * 80)

    duplicates = []

    # Group by exact name
    query = (
        session.query(DBDataset.name, func.count(DBDataset.id).label("count"))
        .group_by(DBDataset.name)
        .having(func.count(DBDataset.id) > 1)
        .order_by(func.count(DBDataset.id).desc())
    )

    duplicate_names = query.all()

    if not duplicate_names:
        print("✓ No exact name duplicates found!")
        return duplicates

    print(f"⚠ Found {len(duplicate_names)} duplicate names:\n")

    for name, count in duplicate_names:
        # Get all datasets with this name
        datasets = session.query(DBDataset).filter(DBDataset.name == name).all()

        duplicate_info = {
            "type": "exact_name",
            "name": name,
            "count": count,
            "datasets": [],
        }

        print(f"Name: '{name}' ({count} occurrences)")
        for ds in datasets:
            print(f"  - ID: {ds.id}, Slug: {ds.slug}")
            print(f"    URL: {ds.url or 'N/A'}")
            print(f"    HF URL: {ds.hf_url or 'N/A'}")
            print(f"    Description: {(ds.description or '')[:100]}...")

            duplicate_info["datasets"].append(
                {
                    "id": ds.id,
                    "slug": ds.slug,
                    "url": ds.url,
                    "hf_url": ds.hf_url,
                    "description": ds.description,
                }
            )

        print()
        duplicates.append(duplicate_info)

    return duplicates


def check_case_insensitive_duplicates(session: Session) -> List[Dict[str, Any]]:
    """Check for case-insensitive name duplicates."""
    print("\n" + "=" * 80)
    print("2. CASE-INSENSITIVE NAME DUPLICATES")
    print("=" * 80)

    duplicates = []

    # Get all datasets
    all_datasets = session.query(DBDataset).all()

    # Group by lowercase name
    name_groups = defaultdict(list)
    for ds in all_datasets:
        name_groups[ds.name.lower()].append(ds)

    # Find groups with multiple different original names
    found_duplicates = False
    for lower_name, datasets in name_groups.items():
        if len(datasets) > 1:
            # Check if they have different original names
            unique_names = set(ds.name for ds in datasets)
            if len(unique_names) > 1:
                found_duplicates = True

                duplicate_info = {
                    "type": "case_insensitive",
                    "lowercase_name": lower_name,
                    "count": len(datasets),
                    "variants": list(unique_names),
                    "datasets": [],
                }

                print(f"Lowercase: '{lower_name}' ({len(datasets)} occurrences)")
                print(f"  Variants: {', '.join(unique_names)}")
                for ds in datasets:
                    print(f"  - ID: {ds.id}, Name: '{ds.name}', Slug: {ds.slug}")
                    duplicate_info["datasets"].append(
                        {"id": ds.id, "name": ds.name, "slug": ds.slug, "url": ds.url}
                    )
                print()

                duplicates.append(duplicate_info)

    if not found_duplicates:
        print("✓ No case-insensitive name duplicates found!")

    return duplicates


def check_slug_duplicates(session: Session) -> List[Dict[str, Any]]:
    """Check for slug duplicates (shouldn't exist due to UNIQUE constraint)."""
    print("\n" + "=" * 80)
    print("3. SLUG DUPLICATES")
    print("=" * 80)

    duplicates = []

    # Group by slug (excluding NULL)
    query = (
        session.query(DBDataset.slug, func.count(DBDataset.id).label("count"))
        .filter(DBDataset.slug.isnot(None))
        .group_by(DBDataset.slug)
        .having(func.count(DBDataset.id) > 1)
    )

    duplicate_slugs = query.all()

    if not duplicate_slugs:
        print("✓ No slug duplicates found (as expected due to UNIQUE constraint)!")
        return duplicates

    print(f"⚠ Found {len(duplicate_slugs)} duplicate slugs (this is unexpected!):\n")

    for slug, count in duplicate_slugs:
        datasets = session.query(DBDataset).filter(DBDataset.slug == slug).all()

        duplicate_info = {"type": "slug", "slug": slug, "count": count, "datasets": []}

        print(f"Slug: '{slug}' ({count} occurrences)")
        for ds in datasets:
            print(f"  - ID: {ds.id}, Name: '{ds.name}'")
            duplicate_info["datasets"].append({"id": ds.id, "name": ds.name})
        print()

        duplicates.append(duplicate_info)

    return duplicates


def check_url_duplicates(session: Session) -> List[Dict[str, Any]]:
    """Check for same URL duplicates."""
    print("\n" + "=" * 80)
    print("4. URL DUPLICATES")
    print("=" * 80)

    duplicates = []

    # Group by url (excluding NULL)
    query = (
        session.query(DBDataset.url, func.count(DBDataset.id).label("count"))
        .filter(DBDataset.url.isnot(None))
        .filter(DBDataset.url != "")
        .group_by(DBDataset.url)
        .having(func.count(DBDataset.id) > 1)
        .order_by(func.count(DBDataset.id).desc())
    )

    duplicate_urls = query.all()

    if not duplicate_urls:
        print("✓ No URL duplicates found!")
        return duplicates

    print(f"⚠ Found {len(duplicate_urls)} duplicate URLs:\n")

    for url, count in duplicate_urls:
        datasets = session.query(DBDataset).filter(DBDataset.url == url).all()

        duplicate_info = {"type": "url", "url": url, "count": count, "datasets": []}

        print(f"URL: '{url}' ({count} occurrences)")
        for ds in datasets:
            print(f"  - ID: {ds.id}, Name: '{ds.name}', Slug: {ds.slug}")
            duplicate_info["datasets"].append(
                {"id": ds.id, "name": ds.name, "slug": ds.slug}
            )
        print()

        duplicates.append(duplicate_info)

    return duplicates


def check_hf_url_duplicates(session: Session) -> List[Dict[str, Any]]:
    """Check for same hf_url duplicates."""
    print("\n" + "=" * 80)
    print("5. HUGGING FACE URL DUPLICATES")
    print("=" * 80)

    duplicates = []

    # Group by hf_url (excluding NULL)
    query = (
        session.query(DBDataset.hf_url, func.count(DBDataset.id).label("count"))
        .filter(DBDataset.hf_url.isnot(None))
        .filter(DBDataset.hf_url != "")
        .group_by(DBDataset.hf_url)
        .having(func.count(DBDataset.id) > 1)
        .order_by(func.count(DBDataset.id).desc())
    )

    duplicate_hf_urls = query.all()

    if not duplicate_hf_urls:
        print("✓ No Hugging Face URL duplicates found!")
        return duplicates

    print(f"⚠ Found {len(duplicate_hf_urls)} duplicate HF URLs:\n")

    for hf_url, count in duplicate_hf_urls:
        datasets = session.query(DBDataset).filter(DBDataset.hf_url == hf_url).all()

        duplicate_info = {
            "type": "hf_url",
            "hf_url": hf_url,
            "count": count,
            "datasets": [],
        }

        print(f"HF URL: '{hf_url}' ({count} occurrences)")
        for ds in datasets:
            print(f"  - ID: {ds.id}, Name: '{ds.name}', Slug: {ds.slug}")
            duplicate_info["datasets"].append(
                {"id": ds.id, "name": ds.name, "slug": ds.slug}
            )
        print()

        duplicates.append(duplicate_info)

    return duplicates


def check_similar_names(
    session: Session, threshold: float = 0.90
) -> List[Dict[str, Any]]:
    """Check for very similar names using fuzzy matching."""
    print("\n" + "=" * 80)
    print(f"6. SIMILAR NAMES (Similarity >= {threshold * 100:.0f}%)")
    print("=" * 80)

    duplicates = []

    # Get all datasets
    all_datasets = session.query(DBDataset).all()

    print(f"Analyzing {len(all_datasets)} datasets for similar names...")
    print("(This may take a moment...)\n")

    # Compare all pairs
    similar_pairs = []
    for i, ds1 in enumerate(all_datasets):
        for ds2 in all_datasets[i + 1 :]:
            ratio = similarity_ratio(ds1.name, ds2.name)
            if ratio >= threshold and ds1.name != ds2.name:
                similar_pairs.append((ds1, ds2, ratio))

    if not similar_pairs:
        print(f"✓ No similar names found (threshold: {threshold * 100:.0f}%)!")
        return duplicates

    print(f"⚠ Found {len(similar_pairs)} pairs of similar names:\n")

    # Sort by similarity ratio (descending)
    similar_pairs.sort(key=lambda x: x[2], reverse=True)

    for ds1, ds2, ratio in similar_pairs:
        duplicate_info = {
            "type": "similar_names",
            "similarity": ratio,
            "datasets": [
                {"id": ds1.id, "name": ds1.name, "slug": ds1.slug, "url": ds1.url},
                {"id": ds2.id, "name": ds2.name, "slug": ds2.slug, "url": ds2.url},
            ],
        }

        print(f"Similarity: {ratio * 100:.1f}%")
        print(f"  1. ID: {ds1.id}, Name: '{ds1.name}', Slug: {ds1.slug}")
        print(f"     URL: {ds1.url or 'N/A'}")
        print(f"  2. ID: {ds2.id}, Name: '{ds2.name}', Slug: {ds2.slug}")
        print(f"     URL: {ds2.url or 'N/A'}")
        print()

        duplicates.append(duplicate_info)

    return duplicates


def check_datasets_with_null_slug(session: Session) -> List[Dict[str, Any]]:
    """Check for datasets with NULL slugs."""
    print("\n" + "=" * 80)
    print("7. DATASETS WITH NULL SLUGS")
    print("=" * 80)

    null_slug_datasets = session.query(DBDataset).filter(DBDataset.slug.is_(None)).all()

    if not null_slug_datasets:
        print("✓ No datasets with NULL slugs found!")
        return []

    print(f"⚠ Found {len(null_slug_datasets)} datasets with NULL slugs:\n")

    results = []
    for ds in null_slug_datasets[:20]:  # Show first 20
        print(f"  - ID: {ds.id}, Name: '{ds.name}'")
        results.append({"id": ds.id, "name": ds.name, "url": ds.url})

    if len(null_slug_datasets) > 20:
        print(f"  ... and {len(null_slug_datasets) - 20} more")

    return results


def main():
    """Main function to check all types of duplicates."""
    print("\n" + "=" * 80)
    print("DATASET DUPLICATES CHECKER")
    print("=" * 80)

    with db_manager.session_local() as session:
        # Get total count
        total_datasets = session.query(func.count(DBDataset.id)).scalar()
        print(f"\nTotal datasets in database: {total_datasets}")

        # Run all checks
        exact_name_dupes = check_exact_name_duplicates(session)
        case_insensitive_dupes = check_case_insensitive_duplicates(session)
        slug_dupes = check_slug_duplicates(session)
        url_dupes = check_url_duplicates(session)
        hf_url_dupes = check_hf_url_duplicates(session)
        similar_names = check_similar_names(session, threshold=0.90)
        null_slugs = check_datasets_with_null_slug(session)

        # Summary
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Total datasets: {total_datasets}")
        print(f"Exact name duplicates: {len(exact_name_dupes)}")
        print(f"Case-insensitive duplicates: {len(case_insensitive_dupes)}")
        print(f"Slug duplicates: {len(slug_dupes)}")
        print(f"URL duplicates: {len(url_dupes)}")
        print(f"HF URL duplicates: {len(hf_url_dupes)}")
        print(f"Similar name pairs: {len(similar_names)}")
        print(f"Datasets with NULL slugs: {len(null_slugs)}")

        total_issues = (
            len(exact_name_dupes)
            + len(case_insensitive_dupes)
            + len(slug_dupes)
            + len(url_dupes)
            + len(hf_url_dupes)
            + len(similar_names)
            + (1 if null_slugs else 0)
        )

        print(f"\nTotal duplicate issues found: {total_issues}")

        if total_issues == 0:
            print("\n✓ No duplicates found! Database is clean.")
        else:
            print("\n⚠ Found duplicate issues. Review the details above.")

        print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
