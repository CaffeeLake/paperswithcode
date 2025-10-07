#!/usr/bin/env python3
"""
Add papers that mention "Spectrogram" (case-insensitive) in their title or abstract
to the paper_methods table, linking them to the spectrogram method.

Usage:
    uv run --env-file backend/keys.env python backend/database/methods_setup/add_spectrogram_papers.py
"""

import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from backend.models.database import Paper, Method, PaperMethod


def add_spectrogram_papers():
    """Find and link papers that mention Spectrogram to the spectrogram method."""

    DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/paperswithcode_hf"

    try:
        engine = create_engine(DATABASE_URL)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()

        print("=" * 80)
        print("Adding Papers that Mention 'Spectrogram' to paper_methods")
        print("=" * 80)

        # Find the spectrogram method (case-insensitive search)
        print("\n1. Finding spectrogram method in database...")
        spectrogram_method = (
            db.query(Method).filter(Method.name.ilike("spectrogram")).first()
        )

        if not spectrogram_method:
            print("❌ Spectrogram method not found in database!")
            print("   Searching for similar method names...")
            similar_methods = (
                db.query(Method).filter(Method.name.ilike("%spectro%")).all()
            )
            if similar_methods:
                print("   Found similar methods:")
                for method in similar_methods:
                    print(f"     - {method.name} (ID: {method.id})")
            db.close()
            sys.exit(1)

        print(f"   ✓ Found spectrogram method (ID: {spectrogram_method.id})")
        print(f"   Method name: {spectrogram_method.name}")
        if spectrogram_method.full_name:
            print(f"   Full name: {spectrogram_method.full_name}")

        # Check current count
        current_spectrogram_papers = (
            db.query(PaperMethod)
            .filter(PaperMethod.method_id == spectrogram_method.id)
            .count()
        )
        print(
            f"\n2. Current papers linked to spectrogram: {current_spectrogram_papers}"
        )

        # Find papers that mention "Spectrogram" (case-insensitive) in title or abstract
        print(
            "\n3. Searching for papers that mention 'Spectrogram' (case-insensitive)..."
        )
        print("   (Looking in title or abstract)")

        # Query for papers mentioning Spectrogram (case-insensitive)
        # Using ilike for case-insensitive matching
        papers = (
            db.query(Paper)
            .filter(
                (Paper.title.ilike("%spectrogram%"))
                | (Paper.abstract.ilike("%spectrogram%"))
            )
            .filter(Paper.is_latest_version)
            .all()
        )

        print(f"   ✓ Found {len(papers)} papers mentioning 'spectrogram'")

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
                    PaperMethod.method_id == spectrogram_method.id,
                )
                .first()
            )

            if existing:
                skipped_count += 1
                continue

            # Create new relationship
            paper_method = PaperMethod(
                paper_id=paper.id, method_id=spectrogram_method.id
            )
            db.add(paper_method)
            added_count += 1

        # Commit the changes
        db.commit()

        # Final count
        final_spectrogram_papers = (
            db.query(PaperMethod)
            .filter(PaperMethod.method_id == spectrogram_method.id)
            .count()
        )

        print(f"\n{'=' * 80}")
        print("Summary")
        print("=" * 80)
        print(f"Papers found mentioning 'spectrogram':    {len(papers):>6,}")
        print(f"Already linked:                           {skipped_count:>6,}")
        print(f"New relationships created:                {added_count:>6,}")
        print(
            f"Total papers now linked to spectrogram:   {final_spectrogram_papers:>6,}"
        )

        print("\n✅ Successfully added spectrogram papers to paper_methods table!")

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
                {"method_id": spectrogram_method.id},
            )

            for i, row in enumerate(result, 1):
                title_snippet = row[1][:60] + "..." if len(row[1]) > 60 else row[1]
                date = row[2].strftime("%Y-%m-%d") if row[2] else "N/A"
                print(f"{i:2}. [{row[0]}] {title_snippet}")
                print(f"    Published: {date}")

        db.close()

    except Exception as e:
        print(f"\n❌ Error adding spectrogram papers: {str(e)}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    add_spectrogram_papers()
