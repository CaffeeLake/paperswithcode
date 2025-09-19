#!/usr/bin/env python3
"""
Debug script to check paper matching between JSON and database
"""

import sys
import ijson
from pathlib import Path

# Add the project root and backend directory to the Python path
project_root = Path(__file__).parent
backend_dir = project_root / "backend"
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(backend_dir))

from backend.database.connection import get_database_session
from backend.models.database import Paper as DBPaper


def debug_matching():
    """Debug the matching between JSON papers and database papers"""

    print("=== DEBUGGING PAPER MATCHING ===")

    # Check database papers
    db_session = next(get_database_session())
    try:
        # Get some sample papers from database
        db_papers = db_session.query(DBPaper).limit(5).all()
        print("\nDatabase papers (first 5):")
        for paper in db_papers:
            print(
                f"  ID: {paper.id}, ArXiv: {paper.arxiv_id}, Title: {paper.title[:50]}..."
            )

        # Check JSON papers
        json_file = "data/papers-with-abstracts.json"
        print("\nJSON papers (first 10 with authors):")

        count = 0
        matched_count = 0

        with open(json_file, "rb") as file:
            parser = ijson.items(file, "item")

            for paper_data in parser:
                count += 1

                arxiv_id = paper_data.get("arxiv_id")
                authors = paper_data.get("authors", [])
                title = paper_data.get("title", "No title")

                if authors:  # Only show papers with authors
                    print(f"  JSON Paper {count}:")
                    print(f"    ArXiv ID: {arxiv_id}")
                    print(f"    Title: {title[:50]}...")
                    print(f"    Authors: {authors}")

                    # Try to find matching paper in database
                    if arxiv_id:
                        db_paper = (
                            db_session.query(DBPaper)
                            .filter(DBPaper.arxiv_id == arxiv_id)
                            .first()
                        )
                        if db_paper:
                            matched_count += 1
                            print(f"    ✅ MATCH FOUND in database (ID: {db_paper.id})")
                        else:
                            print("    ❌ NO MATCH in database")
                    else:
                        print("    ⚠️  NO ARXIV_ID in JSON")

                    print()

                if count >= 20:  # Check first 20 papers
                    break

        print("\nSUMMARY:")
        print(f"Papers checked: {count}")
        print(f"Matches found: {matched_count}")

        # Check total counts
        total_db_papers = db_session.query(DBPaper).count()
        print(f"Total papers in database: {total_db_papers}")

    finally:
        db_session.close()


if __name__ == "__main__":
    debug_matching()
