#!/usr/bin/env python3
"""
Import papers from papers-with-abstracts.json into PostgreSQL database.
Refactored to use the centralized Database class.
"""

import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Any, Optional, Generator
import argparse
import re
import ijson

from backend.database.db_connection import PapersDatabase, DatabaseConfig


def load_papers_data_streaming(file_path: str) -> Generator[Dict[str, Any], None, None]:
    """Load papers data from JSON file using streaming parser to avoid memory issues."""
    print(f"Loading papers data from {file_path} (streaming)...")
    
    with open(file_path, 'rb') as file:
        # Parse JSON array items one by one
        parser = ijson.items(file, 'item')
        for paper in parser:
            yield paper


def load_papers_data(file_path: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
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
    match = re.search(r'arxiv\.org/abs/([^/]+)', arxiv_url)
    if not match:
        return None, None
    
    arxiv_full = match.group(1)
    
    # Check if version is specified
    version_match = re.search(r'v(\d+)$', arxiv_full)
    if version_match:
        arxiv_id = arxiv_full[:-len(version_match.group(0))]
        version = version_match.group(0)  # Keep 'v' prefix
    else:
        arxiv_id = arxiv_full
        version = 'v1'  # Default version
    
    return arxiv_id, version


def prepare_paper_data(paper: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Prepare paper data for database insertion."""
    # Parse the date
    paper_date = parse_date(paper.get('date'))
    
    # Extract ArXiv ID and version from URL
    arxiv_id, version = extract_arxiv_id_and_version(paper.get('url_abs'))
    
    # If we couldn't extract from URL, try the arxiv_id field directly
    if not arxiv_id and paper.get('arxiv_id'):
        arxiv_id = paper.get('arxiv_id')
        version = 'v1'  # Default version
    
    if not arxiv_id:
        print(f"Warning: No ArXiv ID found for paper '{paper.get('title', 'Unknown')}'")
        return None

    return {
        'title': paper.get('title'),
        'abstract': paper.get('abstract'),
        'arxiv_id': arxiv_id,
        'version': version,
        'is_latest_version': True,  # Assume latest version for now
        'date_published': paper_date,
        'proceeding': paper.get('proceeding'),
        'conference': paper.get('conference'),
        'conference_url_abs': paper.get('conference_url_abs'),
        'conference_url_pdf': paper.get('conference_url_pdf')
    }


def import_papers(
    papers_data: List[Dict[str, Any]],
    db: PapersDatabase,
    batch_size: int = 1000,
    limit: Optional[int] = None
) -> None:
    """Import papers data into the database."""

    imported_count = 0
    skipped_count = 0
    
    # Limit the number of papers if specified
    if limit:
        papers_data = papers_data[:limit]
        print(f"Limiting import to first {limit} papers")

    try:
        for i, paper in enumerate(papers_data):
            # Prepare paper data
            paper_data = prepare_paper_data(paper)
            if not paper_data:
                skipped_count += 1
                continue

            # Insert paper (the database class handles duplicates)
            paper_id = db.insert_paper(paper_data)

            if paper_id is None:
                skipped_count += 1
            else:
                imported_count += 1

            # Progress reporting
            if (i + 1) % batch_size == 0:
                print(f"Processed {i + 1} papers... (imported: {imported_count}, skipped: {skipped_count})")

        print(f"\nImport completed!")
        print(f"Total papers processed: {len(papers_data)}")
        print(f"Successfully imported: {imported_count}")
        print(f"Skipped: {skipped_count}")

    except Exception as e:
        print(f"Error during import: {e}")
        raise


def main():
    parser = argparse.ArgumentParser(description="Import papers data into PostgreSQL")
    parser.add_argument(
        "--json-file",
        default="data/papers-with-abstracts.json",
        help="Path to the papers JSON file"
    )
    parser.add_argument("--host", default="localhost", help="Database host")
    parser.add_argument("--database", default="paperswithcode", help="Database name")
    parser.add_argument("--user", help="Database user (defaults to current user)")
    parser.add_argument("--password", help="Database password (or set POSTGRES_PASSWORD env var)")
    parser.add_argument("--port", type=int, default=5432, help="Database port")
    parser.add_argument("--batch-size", type=int, default=1000, help="Batch size for progress reporting")
    parser.add_argument("--limit", type=int, help="Limit number of papers to import (for testing)")

    args = parser.parse_args()

    # Check if JSON file exists
    if not os.path.exists(args.json_file):
        print(f"Error: JSON file '{args.json_file}' not found")
        sys.exit(1)

    # Load papers data
    papers_data = load_papers_data(args.json_file, args.limit)

    # Create database config and connection
    db_config = DatabaseConfig(
        host=args.host,
        port=args.port,
        database=args.database,
        user=args.user,
        password=args.password
    )
    
    db = PapersDatabase(db_config)

    try:
        # Test connection
        if not db.test_connection():
            print("Error: Could not connect to database")
            sys.exit(1)
        
        # Import papers
        import_papers(papers_data, db, args.batch_size, args.limit)
        
    except Exception as e:
        print(f"Import failed: {e}")
        sys.exit(1)
    finally:
        db.disconnect()
        print("Database connection closed.")


if __name__ == "__main__":
    main()