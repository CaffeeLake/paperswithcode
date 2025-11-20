"""
Check specific datasets to determine if they're variants or duplicates.
"""

import sys

from backend.database.connection import db_manager
from backend.models.database import Dataset


def print_dataset_details(dataset: Dataset):
    """Print detailed information about a dataset."""
    print(f"\n  ID: {dataset.id}")
    print(f"  Name: {dataset.name}")
    print(f"  Full Name: {dataset.full_name or 'N/A'}")
    print(f"  Slug: {dataset.slug}")
    print(
        f"  Description: {dataset.description[:200] if dataset.description else 'N/A'}..."
    )
    print(f"  URL: {dataset.url or 'N/A'}")
    print(f"  HF URL: {dataset.hf_url or 'N/A'}")
    print(f"  Homepage: {dataset.homepage or 'N/A'}")
    print(f"  Parent Dataset ID: {dataset.parent_dataset_id or 'N/A'}")
    print(f"  Variant Type: {dataset.variant_type or 'N/A'}")
    print(f"  Split Name: {dataset.split_name or 'N/A'}")
    print(f"  Introduced Year: {dataset.introduced_year or 'N/A'}")
    print(f"  Paper URL: {dataset.paper_url or 'N/A'}")
    print(f"  Num Papers: {dataset.num_papers}")

    # Get tasks
    if dataset.tasks:
        print(f"  Tasks: {', '.join([t.name for t in dataset.tasks[:5]])}")

    # Get evaluations count
    if dataset.evaluations:
        print(f"  Evaluations: {len(dataset.evaluations)}")


def check_datasets(dataset_ids: list[int], name: str):
    """Check specific datasets by ID."""
    print(f"\n{'=' * 80}")
    print(f"Checking {name} datasets")
    print(f"{'=' * 80}")

    session = db_manager.session_local()

    try:
        datasets = session.query(Dataset).filter(Dataset.id.in_(dataset_ids)).all()

        if not datasets:
            print(f"No datasets found with IDs: {dataset_ids}")
            return

        print(f"\nFound {len(datasets)} datasets:")

        for dataset in sorted(datasets, key=lambda d: d.id):
            print_dataset_details(dataset)

        # Check if they're related
        print(f"\n{'=' * 80}")
        print("Relationship Analysis")
        print(f"{'=' * 80}")

        if len(datasets) == 2:
            d1, d2 = sorted(datasets, key=lambda d: d.id)

            # Check if one is parent of the other
            if d1.parent_dataset_id == d2.id:
                print(
                    f"✓ {d2.name} (ID {d2.id}) is the parent of {d1.name} (ID {d1.id})"
                )
            elif d2.parent_dataset_id == d1.id:
                print(
                    f"✓ {d1.name} (ID {d1.id}) is the parent of {d2.name} (ID {d2.id})"
                )
            elif (
                d1.parent_dataset_id == d2.parent_dataset_id
                and d1.parent_dataset_id is not None
            ):
                print(
                    f"✓ Both are variants of the same parent (ID {d1.parent_dataset_id})"
                )
            else:
                print("⚠️  No parent-child relationship found")
                print(
                    "   They may be duplicates or should have a parent-child relationship"
                )

            # Compare names
            if d1.name.lower() in d2.name.lower() or d2.name.lower() in d1.name.lower():
                print(f"✓ Names are related: '{d1.name}' and '{d2.name}'")

            # Compare descriptions
            if d1.description and d2.description:
                words1 = set(d1.description.lower().split())
                words2 = set(d2.description.lower().split())
                common_words = words1.intersection(words2)
                if len(common_words) > 10:
                    print(f"✓ Descriptions share {len(common_words)} common words")

            # Check if they share tasks
            if d1.tasks and d2.tasks:
                common_tasks = set(t.id for t in d1.tasks) & set(t.id for t in d2.tasks)
                if common_tasks:
                    print(f"✓ Share {len(common_tasks)} common task(s)")
                else:
                    print("⚠️  Do not share any common tasks")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        session.close()


def main():
    """Main function."""
    # Check DIODE datasets
    check_datasets([240, 242], "DIODE")

    # Check X-ARES datasets
    check_datasets([214, 215], "X-ARES")

    return 0


if __name__ == "__main__":
    sys.exit(main())
