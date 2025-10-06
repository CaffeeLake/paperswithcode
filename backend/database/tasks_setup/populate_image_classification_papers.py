"""
Populate paper_tasks table with image classification papers from legacy PapersWithCode.

This script reads the data/image_classification_papers.json file which contains papers
tagged with "image-classification" from the legacy PapersWithCode database, and matches
them with papers in our database by arxiv ID to populate the paper_tasks junction table.
"""

import sys
import json
from pathlib import Path
from typing import List, Set

# Add parent directory to path to import backend modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.models.database import Task, Paper, PaperTask
from backend.config import get_settings


def load_image_classification_papers(json_path: Path) -> List[dict]:
    """
    Load image classification papers from JSON file.

    Args:
        json_path: Path to the JSON file

    Returns:
        List of paper dictionaries
    """
    print(f"📂 Loading papers from {json_path}...")

    with open(json_path, "r") as f:
        papers = json.load(f)

    print(f"✓ Loaded {len(papers)} papers from JSON file")
    return papers


def extract_arxiv_ids(papers: List[dict]) -> Set[str]:
    """
    Extract unique arxiv IDs from papers list.

    Args:
        papers: List of paper dictionaries

    Returns:
        Set of arxiv IDs (only papers that have arxiv_id)
    """
    arxiv_ids = set()
    papers_without_arxiv = 0

    for paper in papers:
        arxiv_id = paper.get("arxiv_id")
        if arxiv_id:
            arxiv_ids.add(arxiv_id)
        else:
            papers_without_arxiv += 1

    print(f"📋 Found {len(arxiv_ids)} unique arxiv IDs")
    if papers_without_arxiv > 0:
        print(f"⚠️  {papers_without_arxiv} papers without arxiv_id (will be skipped)")

    return arxiv_ids


def populate_image_classification_papers():
    """Populate paper_tasks table with image classification papers."""
    print("=" * 70)
    print("Populating Image Classification Papers")
    print("=" * 70)
    print()

    # Load JSON data
    json_path = (
        Path(__file__).parent.parent.parent.parent
        / "data"
        / "image_classification_papers.json"
    )

    if not json_path.exists():
        print(f"❌ Error: JSON file not found at {json_path}")
        return

    papers_data = load_image_classification_papers(json_path)
    arxiv_ids = extract_arxiv_ids(papers_data)

    # Get database settings
    settings = get_settings()

    # Create engine and session
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Get the "Image Classification" task
        print("\n🔍 Looking up 'Image Classification' task...")
        task = db.query(Task).filter(Task.name == "Image Classification").first()

        if not task:
            print("❌ Error: 'Image Classification' task not found in database!")
            print("   Please ensure tasks have been populated first.")
            print(
                "   Run: uv run --env-file backend/keys.env backend/database/tasks_setup/populate_tasks.py"
            )
            return

        print(f"✓ Found task: {task.name} (ID: {task.id})")

        # Statistics
        stats = {
            "found": 0,
            "not_found": 0,
            "added": 0,
            "already_tagged": 0,
            "errors": 0,
        }

        print(f"\n⚙️  Processing {len(arxiv_ids)} papers...")
        print("-" * 70)

        # Process each arxiv ID
        processed = 0
        for arxiv_id in sorted(arxiv_ids):
            processed += 1

            # Show progress every 100 papers
            if processed % 100 == 0:
                print(f"  Progress: {processed}/{len(arxiv_ids)} papers processed...")

            try:
                # Find paper by arxiv_id (get latest version)
                paper = (
                    db.query(Paper)
                    .filter(Paper.arxiv_id == arxiv_id)
                    .filter(Paper.is_latest_version)
                    .first()
                )

                if not paper:
                    if processed <= 10:  # Only show first 10 not found
                        print(f"  ⚠️  {arxiv_id} - Paper not found in database")
                    stats["not_found"] += 1
                    continue

                stats["found"] += 1

                # Check if relationship already exists
                existing = (
                    db.query(PaperTask)
                    .filter(PaperTask.paper_id == paper.id)
                    .filter(PaperTask.task_id == task.id)
                    .first()
                )

                if existing:
                    stats["already_tagged"] += 1
                    continue

                # Create new paper-task relationship
                paper_task = PaperTask(paper_id=paper.id, task_id=task.id)
                db.add(paper_task)
                stats["added"] += 1

                # Show first 10 added papers
                if stats["added"] <= 10:
                    title = (
                        paper.title[:60] + "..."
                        if len(paper.title) > 60
                        else paper.title
                    )
                    print(f"  ✓ {arxiv_id} - Tagged: {title}")

            except Exception as e:
                print(f"  ❌ {arxiv_id} - Error: {e}")
                stats["errors"] += 1
                continue

        # Commit all changes
        print("\n💾 Committing changes to database...")
        db.commit()
        print("✓ Changes committed successfully!")

        # Print summary
        print("\n" + "=" * 70)
        print("Summary")
        print("=" * 70)
        print(f"Total arxiv IDs processed:  {len(arxiv_ids)}")
        print(f"  ✓ Papers found in DB:     {stats['found']}")
        print(f"  ⚠️  Papers not found:       {stats['not_found']}")
        print(f"  ✓ New tags added:         {stats['added']}")
        print(f"  ℹ️  Already tagged:         {stats['already_tagged']}")
        print(f"  ❌ Errors:                 {stats['errors']}")
        print("=" * 70)

        # Show match rate
        if len(arxiv_ids) > 0:
            match_rate = (stats["found"] / len(arxiv_ids)) * 100
            print(
                f"\n📊 Match rate: {match_rate:.1f}% of legacy papers found in current database"
            )

    except Exception as e:
        db.rollback()
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        db.close()


def list_tagged_papers():
    """List sample of papers tagged with Image Classification."""
    print("\n" + "=" * 70)
    print("Papers Tagged with Image Classification")
    print("=" * 70)

    settings = get_settings()
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Get the "Image Classification" task
        task = db.query(Task).filter(Task.name == "Image Classification").first()

        if not task:
            print("\n❌ 'Image Classification' task not found in database.")
            return

        # Get all papers with this task
        papers = (
            db.query(Paper)
            .join(PaperTask, Paper.id == PaperTask.paper_id)
            .filter(PaperTask.task_id == task.id)
            .filter(Paper.is_latest_version)
            .order_by(Paper.date_published.desc())
            .all()
        )

        if not papers:
            print("\nNo papers found tagged with Image Classification.")
        else:
            print(f"\nTotal papers: {len(papers)}\n")
            print("Most recent 20 papers:")
            print("-" * 70)
            for i, paper in enumerate(papers[:20], 1):
                print(f"{i:3d}. [{paper.arxiv_id}] {paper.title}")
                print(f"     Published: {paper.date_published}")
                print()

            if len(papers) > 20:
                print(f"... and {len(papers) - 20} more papers")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        db.close()


def show_stats():
    """Show statistics about image classification papers."""
    print("\n" + "=" * 70)
    print("Image Classification Task Statistics")
    print("=" * 70)

    settings = get_settings()
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Get the "Image Classification" task
        task = db.query(Task).filter(Task.name == "Image Classification").first()

        if not task:
            print("\n❌ 'Image Classification' task not found in database.")
            return

        # Count papers
        total_papers = (
            db.query(Paper)
            .join(PaperTask, Paper.id == PaperTask.paper_id)
            .filter(PaperTask.task_id == task.id)
            .filter(Paper.is_latest_version)
            .count()
        )

        # Get date range
        from sqlalchemy import func

        date_stats = (
            db.query(
                func.min(Paper.date_published).label("earliest"),
                func.max(Paper.date_published).label("latest"),
            )
            .join(PaperTask, Paper.id == PaperTask.paper_id)
            .filter(PaperTask.task_id == task.id)
            .filter(Paper.is_latest_version)
            .filter(Paper.date_published.isnot(None))
            .first()
        )

        print(f"\n📊 Total papers: {total_papers}")

        if date_stats and date_stats.earliest and date_stats.latest:
            print(f"📅 Date range: {date_stats.earliest} to {date_stats.latest}")

        # Count papers by year (recent 5 years)
        print("\n📈 Papers by year (recent 5 years):")
        from sqlalchemy import extract

        current_year = 2024
        for year in range(current_year, current_year - 5, -1):
            count = (
                db.query(Paper)
                .join(PaperTask, Paper.id == PaperTask.paper_id)
                .filter(PaperTask.task_id == task.id)
                .filter(Paper.is_latest_version)
                .filter(extract("year", Paper.date_published) == year)
                .count()
            )
            print(f"  {year}: {count} papers")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Populate paper_tasks with image classification papers from legacy PapersWithCode"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List sample of papers currently tagged with Image Classification",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show statistics about image classification papers",
    )
    parser.add_argument(
        "--populate",
        action="store_true",
        help="Populate the database with image classification paper tags",
    )

    args = parser.parse_args()

    if args.list:
        list_tagged_papers()
    elif args.stats:
        show_stats()
    elif args.populate:
        populate_image_classification_papers()
    else:
        # Default: populate, then show stats and list
        populate_image_classification_papers()
        show_stats()
        list_tagged_papers()
