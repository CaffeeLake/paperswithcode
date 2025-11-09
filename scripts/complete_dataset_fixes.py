#!/usr/bin/env python3
"""
Complete the remaining dataset duplicate fixes.

This script will:
1. Merge Perception Test variants (IDs 89 and 167)
2. Fix invalid HF URLs (6 datasets with "/" as HF URL)
"""

import sys

from sqlalchemy.orm import Session

sys.path.insert(0, "/root/python_projects/paperswithcode")

from backend.database.connection import db_manager
from backend.models.database import (
    Dataset as DBDataset,
    Evaluation as DBEvaluation,
    TaskDataset,
)


def complete_perception_test_merge(session: Session) -> bool:
    """Complete the Perception Test merge that failed earlier."""
    keep_id = 89
    delete_id = 167

    keep_ds = session.query(DBDataset).filter(DBDataset.id == keep_id).first()
    delete_ds = session.query(DBDataset).filter(DBDataset.id == delete_id).first()

    if not delete_ds:
        print(
            f"✓ Dataset {delete_id} (PerceptionTest) already deleted - merge was completed"
        )
        return True

    if not keep_ds:
        print(f"❌ Error: Keep dataset {keep_id} not found!")
        return False

    print("\nMerging Perception Test datasets:")
    print(f"  KEEP:   ID {keep_id} - '{keep_ds.name}' (slug: {keep_ds.slug})")
    print(f"  DELETE: ID {delete_id} - '{delete_ds.name}' (slug: {delete_ds.slug})")

    # 1. Move evaluations
    evaluations = (
        session.query(DBEvaluation).filter(DBEvaluation.dataset_id == delete_id).all()
    )

    if evaluations:
        print(f"  - Moving {len(evaluations)} evaluations...")
        for eval in evaluations:
            eval.dataset_id = keep_id

    # 2. Handle task associations
    # Get task IDs from delete dataset
    delete_task_ids = [
        td.task_id
        for td in session.query(TaskDataset)
        .filter(TaskDataset.dataset_id == delete_id)
        .all()
    ]

    # Get task IDs from keep dataset
    keep_task_ids = [
        td.task_id
        for td in session.query(TaskDataset)
        .filter(TaskDataset.dataset_id == keep_id)
        .all()
    ]

    if delete_task_ids:
        print("  - Processing task associations...")

        # For tasks that don't exist in keep dataset, create new associations
        new_tasks = [tid for tid in delete_task_ids if tid not in keep_task_ids]

        for task_id in new_tasks:
            new_assoc = TaskDataset(dataset_id=keep_id, task_id=task_id)
            session.add(new_assoc)
            print(f"    - Adding task {task_id} to keep dataset")

        # Delete all associations from delete dataset
        session.query(TaskDataset).filter(TaskDataset.dataset_id == delete_id).delete(
            synchronize_session=False
        )

        print(f"    - Added {len(new_tasks)} new task associations")
        print(f"    - Removed {len(delete_task_ids)} old associations")

    # 3. Merge metadata
    if delete_ds.hf_url and delete_ds.hf_url != "/" and not keep_ds.hf_url:
        print(f"  - Copying HF URL from delete dataset: {delete_ds.hf_url}")
        keep_ds.hf_url = delete_ds.hf_url

    if delete_ds.description and not keep_ds.description:
        print("  - Copying description from delete dataset")
        keep_ds.description = delete_ds.description

    # 4. Delete the duplicate dataset
    print(f"  - Deleting duplicate dataset (ID {delete_id})")
    session.delete(delete_ds)

    session.commit()
    print("  ✓ Merge completed successfully!")

    return True


def fix_invalid_hf_urls(session: Session) -> int:
    """Fix datasets with invalid HF URL '/'."""
    print("\nFixing invalid HF URLs (/)...")

    invalid_datasets = session.query(DBDataset).filter(DBDataset.hf_url == "/").all()

    if not invalid_datasets:
        print("✓ No datasets with invalid HF URL '/' found")
        return 0

    print(f"Found {len(invalid_datasets)} datasets with invalid HF URL '/':")

    for ds in invalid_datasets:
        print(f"  - ID {ds.id}: {ds.name} (slug: {ds.slug})")
        ds.hf_url = None

    session.commit()
    print(f"✓ Fixed {len(invalid_datasets)} datasets")

    return len(invalid_datasets)


def main():
    """Main function to complete remaining fixes."""
    print("=" * 80)
    print("COMPLETE DATASET FIXES")
    print("=" * 80)

    with db_manager.session_local() as session:
        # 1. Complete Perception Test merge
        print("\n--- Fix 1: Complete Perception Test merge ---")
        success = complete_perception_test_merge(session)

        if not success:
            print("\n❌ Failed to complete Perception Test merge")
            return

        # 2. Fix invalid HF URLs
        print("\n--- Fix 2: Fix invalid HF URLs ---")
        fixed_count = fix_invalid_hf_urls(session)

    print("\n" + "=" * 80)
    print("✓ ALL FIXES COMPLETED SUCCESSFULLY!")
    print("=" * 80)
    print("\nSummary:")
    print("  - Merged ADE20K duplicates (IDs 15 and 73) ✓")
    print("  - Merged TED-LIUM duplicates (IDs 112 and 124) ✓")
    print("  - Merged Perception Test duplicates (IDs 89 and 167) ✓")
    print(f"  - Fixed {fixed_count} invalid HF URLs ✓")
    print("\nRun check_dataset_duplicates.py again to verify the fixes.")


if __name__ == "__main__":
    main()
