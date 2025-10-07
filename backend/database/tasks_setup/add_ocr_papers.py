#!/usr/bin/env python3
"""
Populate paper_tasks table with OCR papers from data/ocr_papers.json.

This script links papers to the "OCR" task based on the OCR papers JSON file.
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


def load_ocr_papers_json() -> List[Dict[str, Any]]:
    """Load papers from the ocr_papers.json file."""
    json_path = Path(__file__).parent.parent.parent.parent / "data" / "ocr_papers.json"

    print(f"📂 Loading papers from: {json_path}")

    if not json_path.exists():
        raise FileNotFoundError(f"OCR papers JSON file not found: {json_path}")

    with open(json_path, "r", encoding="utf-8") as f:
        papers = json.load(f)

    print(f"✓ Loaded {len(papers):,} papers from JSON file")
    return papers


def populate_ocr_papers():
    """Populate paper_tasks table with OCR papers."""
    print("=" * 70)
    print("Populating OCR Papers")
    print("=" * 70)

    # Get database settings
    settings = get_settings()

    # Create engine and session
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Load papers from JSON
        ocr_papers_data = load_ocr_papers_json()

        # Get the "OCR" task
        print("\n🔍 Looking up 'OCR' task...")
        task = db.query(Task).filter(Task.name == "OCR").first()

        if not task:
            print("❌ Error: 'OCR' task not found in database!")
            print("   Please ensure tasks have been populated first.")
            return

        print(f"✓ Found task: {task.name} (ID: {task.id})")

        # Extract arxiv IDs from JSON data
        arxiv_ids = []
        for paper_data in ocr_papers_data:
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
            "no_arxiv_id": len(ocr_papers_data) - len(arxiv_ids),
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
                        print(f"  ℹ️  {arxiv_id} - Already tagged with OCR")
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

        # Get final count of OCR papers
        total_ocr_papers = (
            db.query(PaperTask).filter(PaperTask.task_id == task.id).count()
        )

        # Print summary
        print("\n" + "=" * 70)
        print("Summary")
        print("=" * 70)
        print(f"Total papers in JSON file:     {len(ocr_papers_data):>7,}")
        print(f"Papers with arxiv IDs:         {len(arxiv_ids):>7,}")
        print(f"Papers without arxiv IDs:      {stats['no_arxiv_id']:>7,}")
        print(f"  ✓ Papers found in database:  {stats['found']:>7,}")
        print(f"  ⚠️  Papers not found:          {stats['not_found']:>7,}")
        print(f"  ✓ New tags added:            {stats['added']:>7,}")
        print(f"  ℹ️  Already tagged:            {stats['already_tagged']:>7,}")
        print(f"  ❌ Errors:                    {stats['errors']:>7,}")
        print(f"\nTotal papers now tagged with OCR: {total_ocr_papers:>7,}")
        print("=" * 70)

    except Exception as e:
        db.rollback()
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        db.close()


def list_tagged_papers():
    """List sample papers tagged with OCR."""
    print("\n" + "=" * 70)
    print("Sample Papers Tagged with OCR")
    print("=" * 70)

    settings = get_settings()
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Get the "OCR" task
        task = db.query(Task).filter(Task.name == "OCR").first()

        if not task:
            print("\n❌ 'OCR' task not found in database.")
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
            print("\nNo papers found tagged with OCR.")
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
        description="Populate paper_tasks with OCR papers from JSON file"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List sample papers currently tagged with OCR",
    )
    parser.add_argument(
        "--populate",
        action="store_true",
        help="Populate the database with OCR paper tags",
    )

    args = parser.parse_args()

    if args.list:
        list_tagged_papers()
    elif args.populate:
        populate_ocr_papers()
    else:
        # Default: populate then list
        populate_ocr_papers()
        list_tagged_papers()
