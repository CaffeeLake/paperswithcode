"""
Authors Population Script for PapersWithCode

This script populates the authors and paper_authors tables using data from
the papers-with-abstracts.json file.

The script:
1. Extracts author names from the JSON data
2. Parses full names into first_name/last_name with smart handling
3. Creates Author records with deduplication
4. Links authors to papers via paper_authors junction table
5. Maintains author order from the original data

📊 USAGE:
# Test mode (100 papers)
uv run populate_authors.py --test

# Production mode (process all papers)
uv run populate_authors.py --production

# Custom batch
uv run populate_authors.py --limit 1000

# Dry run (no database writes)
uv run populate_authors.py --dry-run
"""

import sys
import os
import time
import logging
import re
from pathlib import Path
from typing import Dict, Any, Optional
import argparse
import ijson

from backend.database.connection import get_database_session
from backend.models.database import Paper as DBPaper, Author as DBAuthor, PaperAuthor
from sqlalchemy import and_
from sqlalchemy.orm import Session

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class AuthorNameParser:
    """
    Simple parser for author names - now just cleans and normalizes the full name.
    """

    @classmethod
    def parse_name(cls, full_name: str) -> str:
        """
        Clean and normalize a full author name.

        Args:
            full_name: Full author name as string

        Returns:
            Cleaned full name
        """
        if not full_name or not full_name.strip():
            return "Unknown Author"

        # Clean and normalize the name
        name = full_name.strip()
        name = re.sub(r"\s+", " ", name)  # Normalize whitespace

        return name


class AuthorsPopulator:
    """
    Populates authors and paper_authors tables from papers-with-abstracts.json
    """

    def __init__(self, dry_run: bool = False):
        """Initialize the populator."""
        self.dry_run = dry_run
        self.stats = {
            "papers_processed": 0,
            "authors_created": 0,
            "authors_found_existing": 0,
            "paper_author_links_created": 0,
            "papers_without_authors": 0,
            "name_parsing_errors": 0,
            "start_time": time.time(),
        }

        # Cache for author deduplication
        self.author_cache: Dict[str, int] = {}  # name -> author_id

    def load_papers_data_streaming(
        self, file_path: str, limit: Optional[int] = None
    ) -> None:
        """Load and process papers data using streaming parser."""
        logger.info(f"Loading papers data from {file_path} (streaming)...")

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Papers data file not found: {file_path}")

        count = 0
        db_session = next(get_database_session())
        try:
            with open(file_path, "rb") as file:
                # Parse JSON array items one by one
                parser = ijson.items(file, "item")

                for paper_data in parser:
                    try:
                        self._process_paper_authors(db_session, paper_data)
                        count += 1

                        if limit and count >= limit:
                            break

                        # Progress reporting and periodic commits
                        if count % 50 == 0:
                            logger.info(f"Processed {count} papers...")
                            if not self.dry_run:
                                try:
                                    db_session.commit()  # Periodic commits
                                except Exception as commit_error:
                                    logger.error(
                                        f"Commit error at paper {count}: {commit_error}"
                                    )
                                    db_session.rollback()

                    except Exception as e:
                        logger.error(f"Error processing paper {count + 1}: {e}")
                        self.stats["name_parsing_errors"] += 1
                        if not self.dry_run:
                            try:
                                db_session.rollback()
                            except Exception as rollback_error:
                                logger.error(f"Rollback error: {rollback_error}")
                                # Create new session if rollback fails
                                db_session.close()
                                db_session = next(get_database_session())
                        continue

                # Final commit
                if not self.dry_run:
                    try:
                        db_session.commit()
                        logger.info("Final commit successful")
                    except Exception as final_commit_error:
                        logger.error(f"Final commit error: {final_commit_error}")
                        db_session.rollback()
        finally:
            db_session.close()

        logger.info(f"Completed processing {count} papers")

    def _process_paper_authors(self, db: Session, paper_data: Dict[str, Any]) -> None:
        """Process authors for a single paper."""
        self.stats["papers_processed"] += 1

        # Get paper info
        arxiv_id = paper_data.get("arxiv_id")
        if not arxiv_id:
            logger.debug(
                f"Paper missing arxiv_id: {paper_data.get('title', 'Unknown')}"
            )
            return

        # Find the paper in database
        paper = db.query(DBPaper).filter(DBPaper.arxiv_id == arxiv_id).first()
        if not paper:
            logger.debug(f"Paper not found in database: {arxiv_id}")
            return

        # Get authors from JSON
        authors_list = paper_data.get("authors", [])
        if not authors_list:
            self.stats["papers_without_authors"] += 1
            return

        # Process each author
        for author_order, author_name in enumerate(authors_list, 1):
            try:
                author_id = self._get_or_create_author(db, author_name)
                self._link_paper_author(db, paper.id, author_id, author_order)
            except Exception as e:
                logger.error(
                    f"Error processing author '{author_name}' for paper {arxiv_id}: {e}"
                )
                self.stats["name_parsing_errors"] += 1
                # Don't re-raise the exception to avoid transaction abort

    def _get_or_create_author(self, db: Session, full_name: str) -> int:
        """Get existing author or create new one. Returns author_id."""

        # Parse/clean the name
        clean_name = AuthorNameParser.parse_name(full_name)

        # Check cache first
        if clean_name in self.author_cache:
            self.stats["authors_found_existing"] += 1
            return self.author_cache[clean_name]

        # Check database
        existing_author = db.query(DBAuthor).filter(DBAuthor.name == clean_name).first()

        if existing_author:
            self.author_cache[clean_name] = existing_author.id
            self.stats["authors_found_existing"] += 1
            return existing_author.id

        # Create new author
        if not self.dry_run:
            new_author = DBAuthor(name=clean_name)
            db.add(new_author)
            db.flush()  # Get the ID without committing

            self.author_cache[clean_name] = new_author.id
            self.stats["authors_created"] += 1
            return new_author.id
        else:
            # Dry run - simulate ID
            fake_id = len(self.author_cache) + 1
            self.author_cache[clean_name] = fake_id
            self.stats["authors_created"] += 1
            return fake_id

    def _link_paper_author(
        self, db: Session, paper_id: int, author_id: int, author_order: int
    ) -> None:
        """Create paper-author link."""

        if not self.dry_run:
            # Check if link already exists
            existing_link = (
                db.query(PaperAuthor)
                .filter(
                    and_(
                        PaperAuthor.paper_id == paper_id,
                        PaperAuthor.author_id == author_id,
                    )
                )
                .first()
            )

            if not existing_link:
                paper_author = PaperAuthor(
                    paper_id=paper_id, author_id=author_id, author_order=author_order
                )
                db.add(paper_author)
                self.stats["paper_author_links_created"] += 1
        else:
            self.stats["paper_author_links_created"] += 1

    def print_stats(self) -> None:
        """Print processing statistics."""
        elapsed_time = time.time() - self.stats["start_time"]

        print("\n" + "=" * 60)
        print("AUTHORS POPULATION STATISTICS")
        print("=" * 60)
        print(f"Papers processed:           {self.stats['papers_processed']:,}")
        print(f"Authors created:            {self.stats['authors_created']:,}")
        print(f"Authors found existing:     {self.stats['authors_found_existing']:,}")
        print(
            f"Paper-author links created: {self.stats['paper_author_links_created']:,}"
        )
        print(f"Papers without authors:     {self.stats['papers_without_authors']:,}")
        print(f"Name parsing errors:        {self.stats['name_parsing_errors']:,}")
        print(f"Processing time:            {elapsed_time:.2f} seconds")

        if self.stats["papers_processed"] > 0:
            rate = self.stats["papers_processed"] / elapsed_time
            print(f"Processing rate:            {rate:.2f} papers/second")

        print("=" * 60)


def main():
    """Main function with command line argument parsing."""
    parser = argparse.ArgumentParser(
        description="Populate authors tables from papers-with-abstracts.json"
    )
    parser.add_argument(
        "--json-file",
        default="data/papers-with-abstracts.json",
        help="Path to papers JSON file",
    )
    parser.add_argument(
        "--test", action="store_true", help="Test mode - process only 100 papers"
    )
    parser.add_argument(
        "--production", action="store_true", help="Production mode - process all papers"
    )
    parser.add_argument("--limit", type=int, help="Limit number of papers to process")
    parser.add_argument(
        "--dry-run", action="store_true", help="Dry run - no database writes"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Batch size for commits (default: 100)",
    )

    args = parser.parse_args()

    # Determine limit
    if args.test:
        limit = 100
    elif args.production:
        limit = None
    elif args.limit:
        limit = args.limit
    else:
        print("Please specify --test, --production, or --limit")
        sys.exit(1)

    # Validate JSON file exists
    json_file_path = Path(args.json_file)
    if not json_file_path.exists():
        print(f"Error: JSON file not found: {json_file_path}")
        sys.exit(1)

    print("Authors Population Script")
    print(f"JSON file: {json_file_path}")
    print(f"Limit: {limit if limit else 'All papers'}")
    print(f"Dry run: {args.dry_run}")
    print(f"Batch size: {args.batch_size}")

    if args.dry_run:
        print("\n⚠️  DRY RUN MODE - No database changes will be made")

    # Create populator and run
    populator = AuthorsPopulator(dry_run=args.dry_run)

    try:
        populator.load_papers_data_streaming(str(json_file_path), limit)
        populator.print_stats()

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        populator.print_stats()
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        populator.print_stats()
        sys.exit(1)


if __name__ == "__main__":
    main()
