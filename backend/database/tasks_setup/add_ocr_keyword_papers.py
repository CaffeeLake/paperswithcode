#!/usr/bin/env python3
"""
Add papers that mention OCR-related terms to the paper_tasks table,
linking them to the OCR task.

Searches for:
- "OCR" (capitalized)
- "optical character recognition"
- "optical-character recognition"

in paper titles and abstracts.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import create_engine, text, or_
from sqlalchemy.orm import sessionmaker
from backend.models.database import Paper, Task, PaperTask
from backend.config import get_settings


def add_ocr_keyword_papers():
    """Find and link papers that mention OCR-related terms to the OCR task."""

    settings = get_settings()

    try:
        engine = create_engine(settings.database_url)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()

        print("=" * 80)
        print("Adding Papers that Mention OCR-Related Terms to paper_tasks")
        print("=" * 80)

        # Find the OCR task
        print("\n1. Finding OCR task in database...")
        ocr_task = db.query(Task).filter(Task.name == "OCR").first()

        if not ocr_task:
            print("❌ OCR task not found in database!")
            db.close()
            sys.exit(1)

        print(f"   ✓ Found OCR task (ID: {ocr_task.id})")

        # Check current count
        current_ocr_papers = (
            db.query(PaperTask).filter(PaperTask.task_id == ocr_task.id).count()
        )
        print(f"\n2. Current papers linked to OCR: {current_ocr_papers:,}")

        # Find papers that mention OCR-related terms in title or abstract
        print("\n3. Searching for papers with OCR-related terms...")
        print("   Looking for:")
        print("     - 'OCR' (capitalized)")
        print("     - 'optical character recognition'")
        print("     - 'optical-character recognition'")

        # Build the search query using OR conditions
        # Use LIKE for case-sensitive search (OCR must be uppercase)
        # Use ILIKE for case-insensitive search (optical character recognition variants)
        papers = (
            db.query(Paper)
            .filter(
                or_(
                    # Search for "OCR" (capitalized) in title or abstract
                    Paper.title.like("%OCR%"),
                    Paper.abstract.like("%OCR%"),
                    # Search for "optical character recognition" (case-insensitive)
                    Paper.title.ilike("%optical character recognition%"),
                    Paper.abstract.ilike("%optical character recognition%"),
                    # Search for "optical-character recognition" (case-insensitive)
                    Paper.title.ilike("%optical-character recognition%"),
                    Paper.abstract.ilike("%optical-character recognition%"),
                )
            )
            .filter(Paper.is_latest_version)
            .all()
        )

        print(f"   ✓ Found {len(papers):,} papers matching OCR-related terms")

        if len(papers) == 0:
            print("\n✅ No new papers found to add")
            db.close()
            return

        # Show sample papers
        print("\n4. Sample papers found:")
        for i, paper in enumerate(papers[:10]):
            title_snippet = (
                paper.title[:70] + "..." if len(paper.title) > 70 else paper.title
            )
            print(f"   {i + 1}. [{paper.arxiv_id}] {title_snippet}")
        if len(papers) > 10:
            print(f"   ... and {len(papers) - 10:,} more papers")

        # Add papers to paper_tasks
        print("\n5. Adding papers to paper_tasks table...")
        added_count = 0
        skipped_count = 0

        for paper in papers:
            # Check if relationship already exists
            existing = (
                db.query(PaperTask)
                .filter(
                    PaperTask.paper_id == paper.id,
                    PaperTask.task_id == ocr_task.id,
                )
                .first()
            )

            if existing:
                skipped_count += 1
                continue

            # Create new relationship
            paper_task = PaperTask(paper_id=paper.id, task_id=ocr_task.id)
            db.add(paper_task)
            added_count += 1

        # Commit the changes
        db.commit()

        # Final count
        final_ocr_papers = (
            db.query(PaperTask).filter(PaperTask.task_id == ocr_task.id).count()
        )

        print(f"\n{'=' * 80}")
        print("Summary")
        print("=" * 80)
        print(f"Papers found with OCR terms:        {len(papers):>7,}")
        print(f"Already linked to OCR:              {skipped_count:>7,}")
        print(f"New relationships created:          {added_count:>7,}")
        print(f"Total papers now linked to OCR:     {final_ocr_papers:>7,}")

        print("\n✅ Successfully added OCR keyword papers to paper_tasks table!")

        # Show some example papers with details
        if added_count > 0:
            print(f"\n{'=' * 80}")
            print("Sample of Recently Added Papers")
            print("=" * 80)

            result = db.execute(
                text("""
                SELECT p.arxiv_id, p.title, p.date_published
                FROM papers p
                JOIN paper_tasks pt ON p.id = pt.paper_id
                WHERE pt.task_id = :task_id
                AND p.is_latest_version = true
                ORDER BY p.date_published DESC
                LIMIT 10
                """),
                {"task_id": ocr_task.id},
            )

            for i, row in enumerate(result, 1):
                title_snippet = row[1][:70] + "..." if len(row[1]) > 70 else row[1]
                date = row[2].strftime("%Y-%m-%d") if row[2] else "N/A"
                print(f"{i:2}. [{row[0]}] {title_snippet}")
                print(f"    Published: {date}")

        db.close()

    except Exception as e:
        print(f"\n❌ Error adding OCR keyword papers: {str(e)}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    add_ocr_keyword_papers()
