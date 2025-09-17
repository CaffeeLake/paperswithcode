#!/usr/bin/env python3
"""
Import papers from papers-with-abstracts.json into PostgreSQL database.
Refactored to use PaperService for consistent database operations.
"""

import os
import sys
from datetime import datetime
from typing import Dict, List, Any, Optional, Generator
import argparse
import re
import ijson

from backend.database.connection import get_database_session
from backend.services.paper_service import PaperService


def load_papers_data_streaming(file_path: str) -> Generator[Dict[str, Any], None, None]:
    """Load papers data from JSON file using streaming parser to avoid memory issues."""
    print(f"Loading papers data from {file_path} (streaming)...")

    with open(file_path, "rb") as file:
        # Parse JSON array items one by one
        parser = ijson.items(file, "item")
        for paper in parser:
            yield paper


def load_papers_data(
    file_path: str, limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Load papers data from JSON file with optional limit using streaming approach."""
    print(f"Loading papers data from {file_path}...")

    papers = []
    count = 0

    try:
        for paper in load_papers_data_streaming(file_path):
            papers.append(paper)
            count += 1
            if limit and count >= limit:
                break

            # Progress reporting for large loads
            if count % 1000 == 0:
                print(f"Loaded {count} papers...")

    except Exception as e:
        print(f"Error loading papers data: {e}")
        raise

    print(f"Successfully loaded {len(papers)} papers")
    return papers


def parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse date string to datetime object."""
    if not date_str:
        return None

    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        try:
            # Try alternative formats
            return datetime.strptime(date_str[:10], "%Y-%m-%d")
        except ValueError:
            print(f"Warning: Could not parse date '{date_str}'")
            return None


def extract_arxiv_id_and_version(arxiv_url: str) -> tuple[str, str]:
    """
    Extract ArXiv ID and version from URL.
    Examples:
    - http://arxiv.org/abs/1805.10616v4 -> ('1805.10616', 'v4')
    - http://arxiv.org/abs/1805.10616 -> ('1805.10616', 'v1')
    """
    if not arxiv_url:
        return None, None

    # Extract ArXiv ID with version from URL
    match = re.search(r"arxiv\.org/abs/([^/]+)", arxiv_url)
    if not match:
        return None, None

    arxiv_full = match.group(1)

    # Check if version is specified
    version_match = re.search(r"v(\d+)$", arxiv_full)
    if version_match:
        arxiv_id = arxiv_full[: -len(version_match.group(0))]
        version = version_match.group(0)  # Keep 'v' prefix
    else:
        arxiv_id = arxiv_full
        version = "v1"  # Default version

    return arxiv_id, version


def prepare_paper_data(paper: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Prepare paper data for database insertion using PaperService format."""
    # Parse the date
    paper_date = parse_date(paper.get("date"))

    # Extract ArXiv ID and version from URL
    arxiv_id, version = extract_arxiv_id_and_version(paper.get("url_abs"))

    # If we couldn't extract from URL, try the arxiv_id field directly
    if not arxiv_id and paper.get("arxiv_id"):
        arxiv_id = paper.get("arxiv_id")
        version = "v1"  # Default version

    if not arxiv_id:
        print(f"Warning: No ArXiv ID found for paper '{paper.get('title', 'Unknown')}'")
        return None

    return {
        "title": paper.get("title"),
        "abstract": paper.get("abstract"),
        "arxiv_id": arxiv_id,
        "version": version,
        "is_latest_version": True,  # Assume latest version for now
        "date_published": paper_date,
        "proceeding": paper.get("proceeding"),
        "conference": paper.get("conference"),
        "conference_url_abs": paper.get("conference_url_abs"),
        "conference_url_pdf": paper.get("conference_url_pdf"),
        "citation_count": 0,  # Default citation count
        "semantic_scholar_id": None,  # No Semantic Scholar ID initially
    }


def import_papers(
    papers_data: List[Dict[str, Any]],
    paper_service: PaperService,
    batch_size: int = 1000,
    limit: Optional[int] = None,
) -> None:
    """Import papers data into the database using PaperService."""

    imported_count = 0
    skipped_count = 0

    # Limit the number of papers if specified
    if limit:
        papers_data = papers_data[:limit]
        print(f"Limiting import to first {limit} papers")

    try:
        # Prepare all paper data
        prepared_papers = []
        for paper in papers_data:
            paper_data = prepare_paper_data(paper)
            if paper_data:
                prepared_papers.append(paper_data)
            else:
                skipped_count += 1

        # Use batch import from PaperService
        print(f"Starting batch import of {len(prepared_papers)} papers...")
        stats = paper_service.add_papers_batch(prepared_papers, batch_size)

        imported_count = stats["added"]
        skipped_count += stats["skipped"]
        error_count = stats["errors"]

        print("\nImport completed!")
        print(f"Total papers processed: {len(papers_data)}")
        print(f"Successfully imported: {imported_count}")
        print(f"Skipped: {skipped_count}")
        print(f"Errors: {error_count}")

    except Exception as e:
        print(f"Error during import: {e}")
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Import papers data into PostgreSQL using PaperService"
    )
    parser.add_argument(
        "--json-file",
        default="data/papers-with-abstracts.json",
        help="Path to the papers JSON file",
    )
    parser.add_argument(
        "--batch-size", type=int, default=1000, help="Batch size for progress reporting"
    )
    parser.add_argument(
        "--limit", type=int, help="Limit number of papers to import (for testing)"
    )

    args = parser.parse_args()

    # Check if JSON file exists
    if not os.path.exists(args.json_file):
        print(f"Error: JSON file '{args.json_file}' not found")
        sys.exit(1)

    # Load papers data
    papers_data = load_papers_data(args.json_file, args.limit)

    try:
        # Get database session and create PaperService
        db_session_gen = get_database_session()
        db_session = next(db_session_gen)

        try:
            paper_service = PaperService(db_session)

            # Test connection by getting paper stats
            try:
                stats = paper_service.get_paper_stats()
                print("✅ Database connection successful!")
                print(f"📊 Current papers in database: {stats['total_papers']:,}")
                print()
            except Exception as e:
                print(f"❌ Database connection failed: {e}")
                sys.exit(1)

            # Import papers
            import_papers(papers_data, paper_service, args.batch_size, args.limit)

        finally:
            db_session.close()

    except Exception as e:
        print(f"Import failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
