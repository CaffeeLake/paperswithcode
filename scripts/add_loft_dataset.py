"""
Add LOFT Dataset

This script adds the LOFT (Long-Context Frontiers) benchmark dataset
to the database using the service layer, linking it to the Language Modeling
task and the paper with ArXiv ID 2406.13121.
"""

import sys
from backend.database.connection import db_manager
from backend.models.database import Dataset as DBDataset, Task as DBTask
from backend.services.dataset_service import DatasetService
from backend.services.paper_service import PaperService
from backend.models.api import DatasetCreateRequest
from sqlalchemy.orm import Session


def get_paper_id(db: Session, arxiv_id: str) -> int:
    """Get paper ID by ArXiv ID."""
    print(f"Looking up paper with ArXiv ID: {arxiv_id}...")

    paper_service = PaperService(db)
    try:
        paper = paper_service.get_paper_by_arxiv_id(arxiv_id)
        print(f"✓ Found paper: '{paper.title}' (ID={paper.id})")
        return int(paper.id)
    except Exception as e:
        print(f"✗ Error finding paper: {e}")
        raise


def get_task_id(db: Session, task_name: str) -> int:
    """Get task ID by task name."""
    print(f"Looking up task: {task_name}...")

    # Query task by name (case-insensitive)
    task = db.query(DBTask).filter(DBTask.name.ilike(task_name)).first()

    if not task:
        print(f"✗ Task '{task_name}' not found!")
        raise ValueError(f"Task '{task_name}' not found")

    print(f"✓ Found task: '{task.name}' (ID={task.id})")
    return task.id


def check_existing_dataset(db: Session, name: str) -> bool:
    """Check if dataset already exists."""
    existing = (
        db.query(DBDataset)
        .filter((DBDataset.name.ilike(name)) | (DBDataset.slug == name.lower()))
        .first()
    )

    if existing:
        print(
            f"⚠ Dataset '{name}' already exists: ID={existing.id}, Slug={existing.slug}"
        )
        return True
    return False


def check_child_datasets(db: Session) -> list:
    """Check for potential child datasets that are part of LOFT."""
    print("\nChecking for potential child datasets...")
    print("-" * 80)

    child_names = ["MuSiQue", "QAMPARI", "NarrativeQA", "QUEST"]
    found_children = []

    for name in child_names:
        child = db.query(DBDataset).filter(DBDataset.name.ilike(name)).first()
        if child:
            print(
                f"  ✓ Found child dataset: {child.name} (ID={child.id}, Slug={child.slug})"
            )
            found_children.append(
                {"name": child.name, "id": child.id, "slug": child.slug}
            )
        else:
            print(f"  - Child dataset '{name}' not found in database")

    if found_children:
        print(f"\n  Note: {len(found_children)} potential child datasets found.")
        print("  These can be linked to LOFT later using parent_dataset_id.")

    print()
    return found_children


def create_loft_dataset(db: Session, paper_id: int, task_id: int):
    """Create the LOFT dataset."""
    print("Creating LOFT dataset...")
    print("-" * 80)

    dataset_service = DatasetService(db)

    # Create dataset request
    loft_request = DatasetCreateRequest(
        name="LOFT",
        full_name="Long-Context Frontiers",
        description="A benchmark of real-world tasks requiring context up to millions of tokens designed to evaluate long-context language models' performance on in-context retrieval and reasoning",
        url="https://github.com/google-deepmind/loft",
        paper_url="https://arxiv.org/abs/2406.13121",
        task_ids=[task_id],
        introducing_paper_id=paper_id,
    )

    print(f"  Name: {loft_request.name}")
    print(f"  Full Name: {loft_request.full_name}")
    print(f"  URL: {loft_request.url}")
    print(f"  Paper ID: {paper_id}")
    print(f"  Task ID: {task_id}")
    print()

    # Create the dataset
    loft_dataset = dataset_service.create_dataset(loft_request)

    print("✓ Successfully created LOFT dataset:")
    print(f"  ID: {loft_dataset.id}")
    print(f"  Slug: {loft_dataset.slug}")
    print(f"  Name: {loft_dataset.name}")
    print()

    return loft_dataset


def main():
    """Main execution function."""
    print("=" * 80)
    print("Add LOFT Dataset")
    print("=" * 80)
    print()

    try:
        with db_manager.session_local() as db:
            # Check if LOFT already exists
            if check_existing_dataset(db, "LOFT"):
                print("\nDataset already exists. Exiting without changes.")
                return 0

            print()

            # Step 1: Get paper ID
            paper_id = get_paper_id(db, "2406.13121")
            print()

            # Step 2: Get task ID
            task_id = get_task_id(db, "Language Modeling")
            print()

            # Step 3: Check for child datasets
            child_datasets = check_child_datasets(db)

            # Step 4: Create LOFT dataset
            loft_dataset = create_loft_dataset(db, paper_id, task_id)

            # Commit changes
            db.commit()
            print("✓ Changes committed to database")
            print()

            # Display summary
            print("=" * 80)
            print("✓ LOFT Dataset Added Successfully!")
            print("=" * 80)
            print(f"Dataset ID: {loft_dataset.id}")
            print(f"Dataset Slug: {loft_dataset.slug}")
            print(f"Paper ID: {paper_id}")
            print(f"Task ID: {task_id}")

            if child_datasets:
                print(
                    f"\nFound {len(child_datasets)} potential child datasets that could be linked later:"
                )
                for child in child_datasets:
                    print(f"  - {child['name']} (ID={child['id']})")

            print()

            return 0

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
