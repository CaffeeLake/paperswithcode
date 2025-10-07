#!/usr/bin/env python3
"""
Populate paper_methods junction table by connecting papers to methods.

This script:
1. Reads papers from 'data/papers-with-abstracts.json' (streaming to handle 2.2GB file)
2. For each paper, extracts the methods used
3. Matches method names to methods in the database
4. Creates paper_methods relationships
"""

import ijson
import sys
from typing import Dict

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from backend.models.database import Paper, Method, PaperMethod


def get_method_name_to_id_map(db) -> Dict[str, int]:
    """Get mapping of method names (lowercase) to method IDs."""
    methods = db.query(Method).all()
    method_map = {}
    for method in methods:
        # Map by both name and full_name (lowercase)
        method_map[method.name.lower()] = method.id
        if method.full_name:
            method_map[method.full_name.lower()] = method.id
    return method_map


def get_arxiv_to_paper_id_map(db) -> Dict[str, int]:
    """Get mapping of arxiv_id to paper ID (for latest versions only)."""
    papers = db.query(Paper).filter(Paper.is_latest_version).all()
    arxiv_map = {}
    for paper in papers:
        if paper.arxiv_id:
            arxiv_map[paper.arxiv_id] = paper.id
    return arxiv_map


def populate_paper_methods():
    """Populate paper_methods junction table from papers JSON file."""

    DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/paperswithcode_hf"

    try:
        engine = create_engine(DATABASE_URL)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()

        print("=" * 80)
        print("Populating paper_methods Junction Table")
        print("=" * 80)

        # Get mappings
        print("\n1. Loading database mappings...")
        method_map = get_method_name_to_id_map(db)
        print(f"   ✓ Loaded {len(method_map)} method name mappings")

        arxiv_map = get_arxiv_to_paper_id_map(db)
        print(f"   ✓ Loaded {len(arxiv_map)} arxiv_id to paper_id mappings")

        # Check current state
        current_count = db.query(PaperMethod).count()
        print(f"\n2. Current paper_methods count: {current_count}")

        # Stream through papers JSON file
        json_path = "data/papers-with-abstracts.json"
        print(f"\n3. Streaming papers from {json_path}...")
        print("   (This may take a while for 2.2GB file...)")

        papers_processed = 0
        papers_matched = 0
        methods_added = 0
        papers_with_methods = 0
        method_not_found = set()

        batch_size = 1000
        batch = []

        try:
            with open(json_path, "rb") as f:
                # Use ijson to stream parse the JSON array
                parser = ijson.items(f, "item")

                for paper_data in parser:
                    papers_processed += 1

                    if papers_processed % 1000 == 0:
                        print(
                            f"   Processed {papers_processed} papers, matched {papers_matched}, "
                            f"added {methods_added} relationships..."
                        )

                    # Get paper info
                    arxiv_id = paper_data.get("arxiv_id", "")
                    if arxiv_id:
                        arxiv_id = arxiv_id.strip()
                    paper_methods = paper_data.get("methods", [])

                    if not arxiv_id or not paper_methods:
                        continue

                    # Find paper in database
                    paper_id = arxiv_map.get(arxiv_id)
                    if not paper_id:
                        continue

                    papers_matched += 1

                    # Extract method names
                    method_ids_for_paper = set()
                    for method_data in paper_methods:
                        method_name = method_data.get("name", "")
                        if not method_name:
                            continue
                        method_name = method_name.strip().lower()
                        if not method_name:
                            continue

                        # Try to find method in database
                        method_id = method_map.get(method_name)
                        if method_id:
                            method_ids_for_paper.add(method_id)
                        else:
                            method_not_found.add(method_data.get("name", ""))

                    # Add to batch
                    if method_ids_for_paper:
                        papers_with_methods += 1
                        for method_id in method_ids_for_paper:
                            batch.append({"paper_id": paper_id, "method_id": method_id})
                            methods_added += 1

                    # Insert batch
                    if len(batch) >= batch_size:
                        # Use raw SQL for efficient batch insert with ON CONFLICT
                        db.execute(
                            text("""
                            INSERT INTO paper_methods (paper_id, method_id)
                            VALUES (:paper_id, :method_id)
                            ON CONFLICT (paper_id, method_id) DO NOTHING
                        """),
                            batch,
                        )
                        db.commit()
                        batch = []

                # Insert remaining batch
                if batch:
                    db.execute(
                        text("""
                        INSERT INTO paper_methods (paper_id, method_id)
                        VALUES (:paper_id, :method_id)
                        ON CONFLICT (paper_id, method_id) DO NOTHING
                    """),
                        batch,
                    )
                    db.commit()

                print(f"\n✓ Finished processing {papers_processed} papers")

        except FileNotFoundError:
            print(f"\n❌ Error: File not found: {json_path}")
            print(
                "   Please ensure papers-with-abstracts.json exists in the data directory"
            )
            return

        # Final statistics
        final_count = db.query(PaperMethod).count()

        print("\n" + "=" * 80)
        print("Import Statistics")
        print("=" * 80)
        print(f"Papers processed:          {papers_processed:>8,}")
        print(f"Papers matched in DB:      {papers_matched:>8,}")
        print(f"Papers with methods:       {papers_with_methods:>8,}")
        print(f"Method relationships added: {methods_added:>8,}")
        print(f"Final paper_methods count: {final_count:>8,}")
        print(f"New relationships created: {final_count - current_count:>8,}")

        if method_not_found:
            print(f"\nMethods in JSON but not in DB: {len(method_not_found)}")
            print("(These methods are not in our curated list of 133 methods)")
            if len(method_not_found) <= 20:
                print("Sample methods not found:")
                for method in list(method_not_found)[:20]:
                    print(f"  - {method}")

        # Show distribution by method
        print("\n" + "=" * 80)
        print("Top 10 Methods by Paper Count")
        print("=" * 80)

        result = db.execute(
            text("""
            SELECT m.name, m.id, COUNT(pm.paper_id) as paper_count
            FROM methods m
            LEFT JOIN paper_methods pm ON m.id = pm.method_id
            GROUP BY m.id, m.name
            ORDER BY paper_count DESC
            LIMIT 10
        """)
        )

        for row in result:
            print(f"{row[0]:30} {row[2]:>6,} papers")

        print("\n✅ Successfully populated paper_methods junction table!")

        db.close()

    except Exception as e:
        print(f"\n❌ Error populating paper_methods: {str(e)}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    # Check if ijson is installed
    try:
        import ijson
    except ImportError:
        print("❌ Error: ijson package not found")
        print("   Please install it: uv add ijson")
        sys.exit(1)

    populate_paper_methods()
