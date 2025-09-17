#!/usr/bin/env python3
"""
Import papers from papers-with-abstracts.json into PostgreSQL database.
STREAMING VERSION - processes papers one by one to avoid memory issues.
Refactored to use PaperService for consistent database operations.
"""

import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Any, Optional, Generator
import argparse
import re
import ijson

from sqlalchemy.orm import Session
from backend.database.connection import get_database_session
from backend.services.paper_service import PaperService


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
    """Prepare paper data for database insertion using PaperService format."""
    # Parse the date
    paper_date = parse_date(paper.get('date'))
    
    # Extract ArXiv ID and version from URL
    arxiv_id, version = extract_arxiv_id_and_version(paper.get('url_abs'))
    
    # If we couldn't extract from URL, try the arxiv_id field directly
    if not arxiv_id and paper.get('arxiv_id'):
        arxiv_id = paper.get('arxiv_id')
        version = 'v1'  # Default version
    
    if not arxiv_id:
        return None  # Skip papers without ArXiv ID

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
        'conference_url_pdf': paper.get('conference_url_pdf'),
        'citation_count': 0,  # Default citation count
        'semantic_scholar_id': None  # No Semantic Scholar ID initially
    }


def import_papers_streaming(
    file_path: str,
    paper_service: PaperService,
    batch_size: int = 1000,
    limit: Optional[int] = None
) -> None:
    """Import papers data using streaming to avoid memory issues with PaperService."""

    imported_count = 0
    skipped_count = 0
    processed_count = 0
    error_count = 0
    
    print(f"Starting streaming import from {file_path}...")
    print(f"Batch size: {batch_size}")
    if limit:
        print(f"Limiting to first {limit} papers")
    print()

    try:
        with open(file_path, 'rb') as file:
            # Parse JSON array items one by one using ijson
            parser = ijson.items(file, 'item')
            
            for paper in parser:
                processed_count += 1
                
                # Prepare paper data
                paper_data = prepare_paper_data(paper)
                if not paper_data:
                    skipped_count += 1
                    continue

                # Insert paper using PaperService
                try:
                    paper_id = paper_service.add_paper(paper_data)
                    if paper_id is None:
                        skipped_count += 1
                    else:
                        imported_count += 1
                except Exception as e:
                    error_count += 1
                    if processed_count % 100 == 0:  # Only print occasional errors to avoid spam
                        print(f"Error adding paper {paper_data.get('arxiv_id', 'unknown')}: {e}")

                # Progress reporting
                if processed_count % batch_size == 0:
                    print(f"Processed {processed_count:,} papers... (imported: {imported_count:,}, skipped: {skipped_count:,}, errors: {error_count:,})")

                # Check limit
                if limit and processed_count >= limit:
                    print(f"Reached limit of {limit} papers")
                    break

        print(f"\n=== Import Completed ===")
        print(f"Total papers processed: {processed_count:,}")
        print(f"Successfully imported: {imported_count:,}")
        print(f"Skipped (no ArXiv ID or duplicates): {skipped_count:,}")
        print(f"Errors: {error_count:,}")

    except Exception as e:
        print(f"Error during streaming import: {e}")
        raise


def main():
    parser = argparse.ArgumentParser(description="Import papers data into PostgreSQL (streaming version with PaperService)")
    parser.add_argument(
        "--json-file",
        default="data/papers-with-abstracts.json",
        help="Path to the papers JSON file"
    )
    parser.add_argument("--batch-size", type=int, default=1000, help="Progress reporting interval")
    parser.add_argument("--limit", type=int, help="Limit number of papers to import (for testing)")

    args = parser.parse_args()

    # Check if JSON file exists
    if not os.path.exists(args.json_file):
        print(f"Error: JSON file '{args.json_file}' not found")
        sys.exit(1)

    try:
        # Get database session and create PaperService
        db_session_gen = get_database_session()
        db_session = next(db_session_gen)
        
        try:
            paper_service = PaperService(db_session)
            
            # Test connection by getting paper stats
            try:
                stats = paper_service.get_paper_stats()
                print(f"✅ Database connection successful!")
                print(f"📊 Current papers in database: {stats['total_papers']:,}")
                print()
            except Exception as e:
                print(f"❌ Database connection failed: {e}")
                sys.exit(1)
            
            # Import papers using streaming
            import_papers_streaming(args.json_file, paper_service, args.batch_size, args.limit)
            
        finally:
            db_session.close()
        
    except Exception as e:
        print(f"Import failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
