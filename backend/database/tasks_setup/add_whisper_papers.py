#!/usr/bin/env python3
"""
Add papers that mention "Whisper" (with capital W) in their title or abstract
to the paper_methods table, linking them to the Whisper method.
"""

import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from backend.models.database import Paper, Method, PaperMethod


def add_whisper_papers():
    """Find and link papers that mention Whisper to the Whisper method."""

    DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/paperswithcode_hf"

    try:
        engine = create_engine(DATABASE_URL)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()

        print("=" * 80)
        print("Adding Papers that Mention 'Whisper' to paper_methods")
        print("=" * 80)

        # Find the Whisper method
        print("\n1. Finding Whisper method in database...")
        whisper_method = db.query(Method).filter(Method.name == "Whisper").first()

        if not whisper_method:
            print("❌ Whisper method not found in database!")
            db.close()
            sys.exit(1)

        print(f"   ✓ Found Whisper method (ID: {whisper_method.id})")
        if whisper_method.full_name:
            print(f"   Full name: {whisper_method.full_name}")

        # Check current count
        current_whisper_papers = (
            db.query(PaperMethod)
            .filter(PaperMethod.method_id == whisper_method.id)
            .count()
        )
        print(f"\n2. Current papers linked to Whisper: {current_whisper_papers}")

        # Find papers that mention "Whisper" (with capital W) in title or abstract
        print("\n3. Searching for papers that mention 'Whisper'...")
        print("   (Looking for capital 'W' in title or abstract)")

        # Query for papers mentioning Whisper
        # Using LIKE for exact case-sensitive matching
        papers = (
            db.query(Paper)
            .filter(
                (Paper.title.like("%Whisper%")) | (Paper.abstract.like("%Whisper%"))
            )
            .filter(Paper.is_latest_version)
            .all()
        )

        print(f"   ✓ Found {len(papers)} papers mentioning 'Whisper'")

        if len(papers) == 0:
            print("\n✅ No new papers found to add")
            db.close()
            return

        # Show sample papers
        print("\n4. Sample papers found:")
        for i, paper in enumerate(papers[:5]):
            title_snippet = (
                paper.title[:70] + "..." if len(paper.title) > 70 else paper.title
            )
            print(f"   {i + 1}. [{paper.arxiv_id}] {title_snippet}")
        if len(papers) > 5:
            print(f"   ... and {len(papers) - 5} more papers")

        # Add papers to paper_methods
        print("\n5. Adding papers to paper_methods table...")
        added_count = 0
        skipped_count = 0

        for paper in papers:
            # Check if relationship already exists
            existing = (
                db.query(PaperMethod)
                .filter(
                    PaperMethod.paper_id == paper.id,
                    PaperMethod.method_id == whisper_method.id,
                )
                .first()
            )

            if existing:
                skipped_count += 1
                continue

            # Create new relationship
            paper_method = PaperMethod(paper_id=paper.id, method_id=whisper_method.id)
            db.add(paper_method)
            added_count += 1

        # Commit the changes
        db.commit()

        # Final count
        final_whisper_papers = (
            db.query(PaperMethod)
            .filter(PaperMethod.method_id == whisper_method.id)
            .count()
        )

        print(f"\n{'=' * 80}")
        print("Summary")
        print("=" * 80)
        print(f"Papers found mentioning 'Whisper':  {len(papers):>6,}")
        print(f"Already linked:                     {skipped_count:>6,}")
        print(f"New relationships created:          {added_count:>6,}")
        print(f"Total papers now linked to Whisper: {final_whisper_papers:>6,}")

        print("\n✅ Successfully added Whisper papers to paper_methods table!")

        # Show some example papers with details
        if added_count > 0:
            print(f"\n{'=' * 80}")
            print("Sample of Added Papers")
            print("=" * 80)

            result = db.execute(
                text("""
                SELECT p.arxiv_id, p.title, p.date_published
                FROM papers p
                JOIN paper_methods pm ON p.id = pm.paper_id
                WHERE pm.method_id = :method_id
                AND p.is_latest_version = true
                ORDER BY p.date_published DESC
                LIMIT 10
                """),
                {"method_id": whisper_method.id},
            )

            for i, row in enumerate(result, 1):
                title_snippet = row[1][:60] + "..." if len(row[1]) > 60 else row[1]
                date = row[2].strftime("%Y-%m-%d") if row[2] else "N/A"
                print(f"{i:2}. [{row[0]}] {title_snippet}")
                print(f"    Published: {date}")

        db.close()

    except Exception as e:
        print(f"\n❌ Error adding Whisper papers: {str(e)}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    add_whisper_papers()
