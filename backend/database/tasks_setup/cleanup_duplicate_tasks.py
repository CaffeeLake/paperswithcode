"""
Clean up duplicate tasks that differ only in case.

This script merges duplicate tasks and reassigns papers to the properly capitalized version.
"""

import sys
from pathlib import Path
from typing import Dict, List

# Add parent directory to path to import backend modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.models.database import Task, PaperTask
from backend.config import get_settings


def find_duplicate_groups(db) -> Dict[str, List[Task]]:
    """Find groups of tasks that differ only in case."""
    all_tasks = db.query(Task).order_by(Task.name).all()

    # Group by lowercase name
    groups = {}
    for task in all_tasks:
        key = task.name.lower()
        if key not in groups:
            groups[key] = []
        groups[key].append(task)

    # Return only groups with duplicates
    return {k: v for k, v in groups.items() if len(v) > 1}


def get_preferred_task(tasks: List[Task]) -> Task:
    """
    Choose the preferred version from duplicate tasks.

    Prefer:
    1. Tasks with paper associations
    2. Tasks with proper title case
    3. Oldest task (by ID)
    """
    # Count papers for each task
    task_paper_counts = []
    for task in tasks:
        paper_count = len(task.papers)
        task_paper_counts.append((task, paper_count))

    # Sort by paper count (desc), then by title case preference, then by ID
    def sort_key(item):
        task, paper_count = item
        # Check if properly title-cased (starts with uppercase, no lowercase start)
        is_title_case = task.name[0].isupper() if task.name else False
        return (
            -paper_count,  # More papers = better (negative for desc)
            not is_title_case,  # Title case preferred
            task.id,  # Lower ID = older = preferred
        )

    task_paper_counts.sort(key=sort_key)
    return task_paper_counts[0][0]


def cleanup_duplicates():
    """Clean up duplicate tasks."""
    print("=" * 70)
    print("Cleaning Up Duplicate Tasks")
    print("=" * 70)

    # Get database settings
    settings = get_settings()

    # Create engine and session
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Find duplicate groups
        print("\n🔍 Looking for duplicate tasks...")
        duplicate_groups = find_duplicate_groups(db)

        if not duplicate_groups:
            print("✓ No duplicate tasks found!")
            return

        print(f"✓ Found {len(duplicate_groups)} groups of duplicates")
        print()

        # Statistics
        stats = {
            "groups_processed": 0,
            "tasks_merged": 0,
            "papers_reassigned": 0,
            "tasks_deleted": 0,
        }

        # Process each group
        for lower_name, tasks in duplicate_groups.items():
            print(f"📋 Processing: '{lower_name}'")

            # Show all versions
            for task in tasks:
                paper_count = len(task.papers)
                print(f"  - '{task.name}' (ID: {task.id}, {paper_count} papers)")

            # Choose preferred version
            preferred = get_preferred_task(tasks)
            others = [t for t in tasks if t.id != preferred.id]

            print(f"  ✓ Keeping: '{preferred.name}' (ID: {preferred.id})")

            # Merge others into preferred
            for other in others:
                # Get papers associated with the task to be deleted
                paper_tasks = (
                    db.query(PaperTask).filter(PaperTask.task_id == other.id).all()
                )

                papers_moved = 0
                for pt in paper_tasks:
                    # Check if paper already has the preferred task
                    existing = (
                        db.query(PaperTask)
                        .filter(
                            PaperTask.paper_id == pt.paper_id,
                            PaperTask.task_id == preferred.id,
                        )
                        .first()
                    )

                    if existing:
                        # Just delete the old association
                        db.delete(pt)
                    else:
                        # Reassign to preferred task
                        pt.task_id = preferred.id
                        papers_moved += 1

                print(f"  → Merged '{other.name}': {papers_moved} papers reassigned")
                stats["papers_reassigned"] += papers_moved

                # Delete the duplicate task
                db.delete(other)
                stats["tasks_deleted"] += 1

            stats["groups_processed"] += 1
            stats["tasks_merged"] += len(others)
            print()

        # Commit all changes
        db.commit()

        # Print summary
        print("=" * 70)
        print("Summary")
        print("=" * 70)
        print(f"Duplicate groups processed:  {stats['groups_processed']}")
        print(f"  ✓ Tasks merged:            {stats['tasks_merged']}")
        print(f"  ✓ Papers reassigned:       {stats['papers_reassigned']}")
        print(f"  ✓ Tasks deleted:           {stats['tasks_deleted']}")
        print("=" * 70)

        # Show remaining tasks
        remaining_tasks = db.query(Task).order_by(Task.name).all()
        print(f"\n📊 Total tasks in database: {len(remaining_tasks)}")
        print("\nAll tasks:")
        for i, task in enumerate(remaining_tasks, 1):
            paper_count = len(task.papers)
            print(f"  {i:3d}. {task.name:40s} ({paper_count} papers)")

    except Exception as e:
        db.rollback()
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    cleanup_duplicates()
