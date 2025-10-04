"""
Tag papers with tasks based on the annotated CSV file.

This script reads the CSV file and tags papers with their relevant tasks.
"""

import sys
import csv
from pathlib import Path
from typing import Dict, Set
import re

# Add parent directory to path to import backend modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.models.database import Task, Paper, PaperTask
from backend.config import get_settings


def extract_arxiv_id_from_url(url: str) -> str:
    """Extract arxiv ID from huggingface papers URL."""
    # Example: https://huggingface.co/papers/2507.05595 -> 2507.05595
    match = re.search(r"/papers/(\d+\.\d+)", url)
    if match:
        return match.group(1)
    return None


def load_csv_data(csv_path: str) -> Dict[str, Set[str]]:
    """
    Load CSV and create mapping of arxiv_id -> set of task names.

    Returns:
        Dict mapping arxiv_id to set of task names
    """
    paper_tasks = {}

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Extract arxiv ID from URL
            url = row.get("Paper", "").strip()
            arxiv_id = extract_arxiv_id_from_url(url)

            if not arxiv_id:
                continue

            # Extract tasks from "Relevant areas" column
            areas_text = row.get("Relevant areas", "").strip()
            if areas_text:
                tasks = {task.strip() for task in areas_text.split(",") if task.strip()}
                if arxiv_id not in paper_tasks:
                    paper_tasks[arxiv_id] = set()
                paper_tasks[arxiv_id].update(tasks)

    return paper_tasks


def normalize_task_name(name: str) -> str:
    """Normalize task name for matching (case-insensitive, handle variations)."""
    return name.lower().strip()


def populate_paper_tasks():
    """Tag papers with tasks based on CSV data."""
    print("=" * 70)
    print("Tagging Papers with Tasks from CSV")
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

    # Load CSV data
    paper_tasks_map = load_csv_data(str(csv_path))
    print(f"✓ Found {len(paper_tasks_map)} papers with task annotations in CSV")

    # Get database settings
    settings = get_settings()

    # Create engine and session
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Load all tasks from database
        all_tasks = db.query(Task).all()
        task_lookup = {}  # normalized name -> Task object
        for task in all_tasks:
            normalized = normalize_task_name(task.name)
            task_lookup[normalized] = task

        print(f"✓ Loaded {len(all_tasks)} tasks from database")

        # Statistics
        stats = {
            "papers_processed": 0,
            "papers_found": 0,
            "papers_not_found": 0,
            "tags_added": 0,
            "tags_already_existed": 0,
            "tasks_not_found": 0,
            "errors": 0,
        }

        task_not_found_set = set()  # Track which tasks weren't found

        print("\n📝 Processing papers...")
        print()

        # Process each paper
        for arxiv_id, task_names in sorted(paper_tasks_map.items()):
            stats["papers_processed"] += 1

            try:
                # Find paper by arxiv_id (get latest version)
                paper = (
                    db.query(Paper)
                    .filter(Paper.arxiv_id == arxiv_id)
                    .filter(Paper.is_latest_version)
                    .first()
                )

                if not paper:
                    print(f"  ⚠️  {arxiv_id} - Paper not found in database")
                    stats["papers_not_found"] += 1
                    continue

                stats["papers_found"] += 1

                # Get paper title for display
                title = (
                    paper.title[:50] + "..." if len(paper.title) > 50 else paper.title
                )

                tags_for_paper = 0

                # Process each task for this paper
                for task_name in task_names:
                    normalized = normalize_task_name(task_name)

                    # Look up task in database
                    task = task_lookup.get(normalized)

                    if not task:
                        if normalized not in task_not_found_set:
                            # print(f"    ⚠️  Task '{task_name}' not found in database")
                            task_not_found_set.add(normalized)
                            stats["tasks_not_found"] += 1
                        continue

                    # Check if relationship already exists
                    existing = (
                        db.query(PaperTask)
                        .filter(PaperTask.paper_id == paper.id)
                        .filter(PaperTask.task_id == task.id)
                        .first()
                    )

                    if existing:
                        stats["tags_already_existed"] += 1
                        continue

                    # Create new paper-task relationship
                    paper_task = PaperTask(paper_id=paper.id, task_id=task.id)
                    db.add(paper_task)
                    stats["tags_added"] += 1
                    tags_for_paper += 1

                if tags_for_paper > 0:
                    task_list = ", ".join(sorted(task_names))
                    print(f"  ✓ {arxiv_id} - {title}")
                    print(f"    Tagged with: {task_list}")

            except Exception as e:
                print(f"  ❌ {arxiv_id} - Error: {e}")
                stats["errors"] += 1
                continue

        # Commit all changes
        db.commit()

        # Print summary
        print("\n" + "=" * 70)
        print("Summary")
        print("=" * 70)
        print(f"Papers in CSV:              {len(paper_tasks_map)}")
        print(f"  ✓ Papers found in DB:     {stats['papers_found']}")
        print(f"  ⚠️  Papers not found:       {stats['papers_not_found']}")
        print("\nTags:")
        print(f"  ✓ New tags added:         {stats['tags_added']}")
        print(f"  ℹ️  Tags already existed:   {stats['tags_already_existed']}")
        print(f"  ⚠️  Tasks not in DB:        {stats['tasks_not_found']}")
        print(f"  ❌ Errors:                 {stats['errors']}")
        print("=" * 70)

        if task_not_found_set:
            print("\n⚠️  Tasks mentioned in CSV but not found in database:")
            for task_name in sorted(task_not_found_set):
                print(f"  - {task_name}")

        # Show task statistics
        print("\n📊 Task Statistics (papers per task):")
        tasks_with_papers = (
            db.query(Task)
            .join(PaperTask, Task.id == PaperTask.task_id)
            .distinct()
            .all()
        )

        # Count papers for each task
        task_counts = []
        for task in tasks_with_papers:
            count = db.query(PaperTask).filter(PaperTask.task_id == task.id).count()
            task_counts.append((task.name, count))

        # Sort by count descending
        task_counts.sort(key=lambda x: -x[1])

        for task_name, count in task_counts[:20]:  # Top 20
            print(f"  {task_name:40s} {count:5d} papers")

        if len(task_counts) > 20:
            print(f"  ... and {len(task_counts) - 20} more tasks")

    except Exception as e:
        db.rollback()
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    populate_paper_tasks()
