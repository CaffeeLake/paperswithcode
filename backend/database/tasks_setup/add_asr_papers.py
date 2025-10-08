#!/usr/bin/env python3
"""
Populate paper_tasks table with Automatic Speech Recognition papers from data/automatic_speech_recognition_papers.json.

This script links papers to the "Automatic Speech Recognition" task based on the ASR papers JSON file.
"""

import json
import sys
from pathlib import Path
from typing import List, Dict, Any

# Add parent directory to path to import backend modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.models.database import Task, Paper, PaperTask
from backend.config import get_settings


def load_asr_papers_json() -> List[Dict[str, Any]]:
    """Load papers from the automatic_speech_recognition_papers.json file."""
    json_path = (
        Path(__file__).parent.parent.parent.parent
        / "data"
        / "automatic_speech_recognition_papers.json"
    )

    print(f"📂 Loading papers from: {json_path}")

    if not json_path.exists():
        raise FileNotFoundError(f"ASR papers JSON file not found: {json_path}")

    with open(json_path, "r", encoding="utf-8") as f:
        papers = json.load(f)

    print(f"✓ Loaded {len(papers):,} papers from JSON file")
    return papers


def populate_asr_papers():
    """Populate paper_tasks table with ASR papers."""
    print("=" * 70)
    print("Populating Automatic Speech Recognition Papers")
    print("=" * 70)

    # Get database settings
    settings = get_settings()

    # Create engine and session
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Load papers from JSON
        asr_papers_data = load_asr_papers_json()

        # Get the "Automatic Speech Recognition" task
        print("\n🔍 Looking up 'Automatic Speech Recognition' task...")
        task = (
            db.query(Task).filter(Task.name == "Automatic Speech Recognition").first()
        )

        if not task:
            print(
                "❌ Error: 'Automatic Speech Recognition' task not found in database!"
            )
            print("   Please ensure tasks have been populated first.")
            return

        print(f"✓ Found task: {task.name} (ID: {task.id})")

        # Extract arxiv IDs from JSON data
        arxiv_ids = []
        for paper_data in asr_papers_data:
            arxiv_id = paper_data.get("arxiv_id")
            if arxiv_id:
                arxiv_ids.append(arxiv_id)

        print(f"\n📋 Processing {len(arxiv_ids):,} papers with arxiv IDs...")

        # Statistics
        stats = {
            "found": 0,
            "not_found": 0,
            "added": 0,
            "already_tagged": 0,
            "errors": 0,
            "no_arxiv_id": len(asr_papers_data) - len(arxiv_ids),
        }

        # Process each arxiv ID
        for i, arxiv_id in enumerate(arxiv_ids):
            try:
                # Show progress every 500 papers
                if (i + 1) % 500 == 0:
                    print(
                        f"  Progress: {i + 1:,}/{len(arxiv_ids):,} papers processed..."
                    )

                # Find paper by arxiv_id (get latest version)
                paper = (
                    db.query(Paper)
                    .filter(Paper.arxiv_id == arxiv_id)
                    .filter(Paper.is_latest_version)
                    .first()
                )

                if not paper:
                    if i < 10:  # Only print first 10 not found to avoid spam
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
                    if i < 10:  # Only print first 10 already tagged
                        print(
                            f"  ℹ️  {arxiv_id} - Already tagged with Automatic Speech Recognition"
                        )
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
                if i < 10:  # Only print first 10 errors
                    print(f"  ❌ {arxiv_id} - Error: {e}")
                stats["errors"] += 1
                continue

        # Commit all changes
        print("\n💾 Committing changes to database...")
        db.commit()

        # Get final count of ASR papers
        total_asr_papers = (
            db.query(PaperTask).filter(PaperTask.task_id == task.id).count()
        )

        # Print summary
        print("\n" + "=" * 70)
        print("Summary")
        print("=" * 70)
        print(f"Total papers in JSON file:     {len(asr_papers_data):>7,}")
        print(f"Papers with arxiv IDs:         {len(arxiv_ids):>7,}")
        print(f"Papers without arxiv IDs:      {stats['no_arxiv_id']:>7,}")
        print(f"  ✓ Papers found in database:  {stats['found']:>7,}")
        print(f"  ⚠️  Papers not found:          {stats['not_found']:>7,}")
        print(f"  ✓ New tags added:            {stats['added']:>7,}")
        print(f"  ℹ️  Already tagged:            {stats['already_tagged']:>7,}")
        print(f"  ❌ Errors:                    {stats['errors']:>7,}")
        print(
            f"\nTotal papers now tagged with Automatic Speech Recognition: {total_asr_papers:>7,}"
        )
        print("=" * 70)

    except Exception as e:
        db.rollback()
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        db.close()


def list_tagged_papers():
    """List sample papers tagged with Automatic Speech Recognition."""
    print("\n" + "=" * 70)
    print("Sample Papers Tagged with Automatic Speech Recognition")
    print("=" * 70)

    settings = get_settings()
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Get the "Automatic Speech Recognition" task
        task = (
            db.query(Task).filter(Task.name == "Automatic Speech Recognition").first()
        )

        if not task:
            print("\n❌ 'Automatic Speech Recognition' task not found in database.")
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
            print("\nNo papers found tagged with Automatic Speech Recognition.")
        else:
            print(f"\nTotal papers: {len(papers):,}\n")
            print("Most recent 20 papers:")
            for i, paper in enumerate(papers[:20], 1):
                title = (
                    paper.title[:70] + "..." if len(paper.title) > 70 else paper.title
                )
                date = (
                    paper.date_published.strftime("%Y-%m-%d")
                    if paper.date_published
                    else "N/A"
                )
                print(f"{i:3d}. [{paper.arxiv_id}] {title}")
                print(f"     Published: {date}")
                print()

            if len(papers) > 20:
                print(f"... and {len(papers) - 20:,} more papers")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Populate paper_tasks with Automatic Speech Recognition papers from JSON file"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List sample papers currently tagged with Automatic Speech Recognition",
    )
    parser.add_argument(
        "--populate",
        action="store_true",
        help="Populate the database with ASR paper tags",
    )

    args = parser.parse_args()

    if args.list:
        list_tagged_papers()
    elif args.populate:
        populate_asr_papers()
    else:
        # Default: populate then list
        populate_asr_papers()
        list_tagged_papers()
