"""
Populate tasks table from the annotated CSV file.

This script extracts unique tasks from the "Relevant areas" column
and adds them to the database.
"""

import sys
import csv
from pathlib import Path
from typing import Set
import re

# Add parent directory to path to import backend modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.models.database import Task
from backend.config import get_settings


def slugify(text: str) -> str:
    """Convert text to a URL-friendly slug."""
    # Convert to lowercase
    text = text.lower()
    # Replace spaces and special characters with hyphens
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    # Remove leading/trailing hyphens
    text = text.strip("-")
    return text


def extract_tasks_from_csv(csv_path: str) -> Set[str]:
    """Extract unique tasks from the CSV file."""
    tasks = set()

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            areas_text = row.get("Relevant areas", "").strip()
            if areas_text:
                # Split by comma and clean up each task
                for task in areas_text.split(","):
                    task = task.strip()
                    if task:
                        tasks.add(task)

    return tasks


def populate_tasks():
    """Populate tasks table with extracted tasks."""
    print("=" * 70)
    print("Populating Tasks from CSV")
    print("=" * 70)

    # CSV path
    csv_path = (
        Path(__file__).parent.parent.parent
        / "data"
        / "Methods, areas and tasks - Annotated areas.csv"
    )

    if not csv_path.exists():
        print(f"❌ Error: CSV file not found at {csv_path}")
        return

    print(f"\n📄 Reading CSV file: {csv_path.name}")

    # Extract tasks from CSV
    extracted_tasks = extract_tasks_from_csv(str(csv_path))
    print(f"✓ Found {len(extracted_tasks)} unique tasks in CSV")

    # Get database settings
    settings = get_settings()

    # Create engine and session
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Get existing tasks from database
        existing_tasks = db.query(Task).all()
        existing_task_names = {task.name for task in existing_tasks}
        print(f"✓ Found {len(existing_tasks)} existing tasks in database")

        # Statistics
        stats = {
            "added": 0,
            "already_exists": 0,
            "errors": 0,
        }

        print("\n📝 Processing tasks...")
        print()

        # Sort tasks for consistent output
        sorted_tasks = sorted(extracted_tasks)

        for task_name in sorted_tasks:
            try:
                # Check if task already exists (case-insensitive)
                if task_name in existing_task_names:
                    print(f"  ℹ️  {task_name:40s} - Already exists")
                    stats["already_exists"] += 1
                    continue

                # Check case-insensitive duplicates
                task_name_lower = task_name.lower()
                if any(
                    existing.lower() == task_name_lower
                    for existing in existing_task_names
                ):
                    print(f"  ℹ️  {task_name:40s} - Already exists (different case)")
                    stats["already_exists"] += 1
                    continue

                # Create slug
                slug = slugify(task_name)

                # Check if slug already exists
                existing_slug = db.query(Task).filter(Task.slug == slug).first()
                if existing_slug:
                    # Add a suffix to make it unique
                    counter = 1
                    new_slug = f"{slug}-{counter}"
                    while db.query(Task).filter(Task.slug == new_slug).first():
                        counter += 1
                        new_slug = f"{slug}-{counter}"
                    slug = new_slug

                # Create new task
                new_task = Task(
                    name=task_name,
                    slug=slug,
                    description=None,  # Can be filled in later
                    level=0,  # Top-level task
                )
                db.add(new_task)

                print(f"  ✓ {task_name:40s} - Added (slug: {slug})")
                stats["added"] += 1

            except Exception as e:
                print(f"  ❌ {task_name:40s} - Error: {e}")
                stats["errors"] += 1
                continue

        # Commit all changes
        db.commit()

        # Print summary
        print("\n" + "=" * 70)
        print("Summary")
        print("=" * 70)
        print(f"Tasks in CSV:          {len(extracted_tasks)}")
        print(f"  ✓ New tasks added:   {stats['added']}")
        print(f"  ℹ️  Already existed:   {stats['already_exists']}")
        print(f"  ❌ Errors:            {stats['errors']}")
        print("=" * 70)

        # Show all tasks in database
        all_tasks = db.query(Task).order_by(Task.name).all()
        print(f"\n📊 Total tasks in database: {len(all_tasks)}")
        print("\nAll tasks:")
        for i, task in enumerate(all_tasks, 1):
            print(f"  {i:3d}. {task.name}")

    except Exception as e:
        db.rollback()
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    populate_tasks()
