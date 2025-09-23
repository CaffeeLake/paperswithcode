"""
ArXiv API Author Population Script for PapersWithCode

This script fetches author information from the ArXiv API for papers that are currently
missing authors in the database. It's designed to complement the main populate_authors.py
script by filling in gaps using the ArXiv API as a fallback data source.

🚀 FEATURES:
- Fetches author data from ArXiv API for papers missing authors
- Handles ArXiv API rate limiting (3 seconds between requests)
- Parses author names intelligently
- Creates authors and paper-author links
- Provides detailed progress reporting
- Supports dry-run mode for testing

📊 USAGE:
# Test mode (10 papers)
uv run backend/database/authors_setup/populate_missing_authors_from_arxiv.py --test

# Production mode (all missing papers)
uv run backend/database/authors_setup/populate_missing_authors_from_arxiv.py --production

# Custom batch
uv run backend/database/authors_setup/populate_missing_authors_from_arxiv.py --limit 100

# Dry run (no database writes)
uv run backend/database/authors_setup/populate_missing_authors_from_arxiv.py --dry-run --limit 50
"""

import sys
import time
import re
import xml.etree.ElementTree as ET
from typing import Dict, Any, Optional, List
import argparse
import requests
from dataclasses import dataclass

from backend.database.connection import get_database_session
from backend.models.database import Author as DBAuthor, PaperAuthor
from sqlalchemy import and_, text
from sqlalchemy.orm import Session

# Configure logging
from backend.database.logging_config import setup_logging

logger = setup_logging("populate_missing_authors_from_arxiv")

# ArXiv API configuration
ARXIV_API_BASE_URL = "http://export.arxiv.org/api/query"
ARXIV_API_DELAY = 3.0  # ArXiv recommends 3 seconds between requests
REQUEST_TIMEOUT = 30.0


@dataclass
class ArxivAuthor:
    """Represents an author from ArXiv API response."""

    name: str
    affiliation: Optional[str] = None


@dataclass
class ArxivPaperData:
    """Represents paper data from ArXiv API response."""

    arxiv_id: str
    title: str
    authors: List[ArxivAuthor]
    success: bool
    error_message: Optional[str] = None


class ArxivAuthorNameParser:
    """
    Parser for author names from ArXiv API responses.
    ArXiv typically provides names in "Last, First" format.
    """

    @classmethod
    def parse_name(cls, full_name: str) -> str:
        """
        Clean and normalize a full author name from ArXiv.

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

        # Remove common prefixes/suffixes that might cause issues
        name = re.sub(r"^\(.*?\)\s*", "", name)  # Remove parenthetical prefixes
        name = re.sub(r"\s*\(.*?\)$", "", name)  # Remove parenthetical suffixes

        return name


class ArxivApiClient:
    """Client for interacting with the ArXiv API."""

    def __init__(self):
        """Initialize the ArXiv API client."""
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "PapersWithCode-AuthorPopulator/1.0 (https://paperswithcode.ai)"
            }
        )

    def fetch_paper_data(self, arxiv_id: str) -> ArxivPaperData:
        """
        Fetch paper data from ArXiv API.

        Args:
            arxiv_id: ArXiv ID of the paper

        Returns:
            ArxivPaperData object with paper information
        """
        try:
            # Clean the ArXiv ID (remove any prefixes)
            clean_arxiv_id = arxiv_id.replace("arXiv:", "").strip()

            # Construct API URL
            url = f"{ARXIV_API_BASE_URL}?id_list={clean_arxiv_id}"

            logger.debug(f"Fetching data for ArXiv ID: {clean_arxiv_id}")

            # Make the request
            response = self.session.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()

            # Parse XML response
            root = ET.fromstring(response.content)

            # Find the entry (paper)
            entries = root.findall("{http://www.w3.org/2005/Atom}entry")

            if not entries:
                return ArxivPaperData(
                    arxiv_id=arxiv_id,
                    title="",
                    authors=[],
                    success=False,
                    error_message="Paper not found in ArXiv",
                )

            entry = entries[0]

            # Extract title
            title_elem = entry.find("{http://www.w3.org/2005/Atom}title")
            title = title_elem.text.strip() if title_elem is not None else ""

            # Extract authors
            authors = []
            author_elements = entry.findall("{http://www.w3.org/2005/Atom}author")

            for author_elem in author_elements:
                name_elem = author_elem.find("{http://www.w3.org/2005/Atom}name")
                if name_elem is not None:
                    author_name = name_elem.text.strip()

                    # Try to get affiliation if available
                    affiliation_elem = author_elem.find(
                        "{http://arxiv.org/schemas/atom}affiliation"
                    )
                    affiliation = (
                        affiliation_elem.text.strip()
                        if affiliation_elem is not None
                        else None
                    )

                    authors.append(
                        ArxivAuthor(name=author_name, affiliation=affiliation)
                    )

            return ArxivPaperData(
                arxiv_id=arxiv_id, title=title, authors=authors, success=True
            )

        except requests.exceptions.RequestException as e:
            logger.error(f"Network error fetching ArXiv data for {arxiv_id}: {str(e)}")
            return ArxivPaperData(
                arxiv_id=arxiv_id,
                title="",
                authors=[],
                success=False,
                error_message=f"Network error: {str(e)}",
            )
        except ET.ParseError as e:
            logger.error(f"XML parsing error for {arxiv_id}: {str(e)}")
            return ArxivPaperData(
                arxiv_id=arxiv_id,
                title="",
                authors=[],
                success=False,
                error_message=f"XML parsing error: {str(e)}",
            )
        except Exception as e:
            logger.error(
                f"Unexpected error fetching ArXiv data for {arxiv_id}: {str(e)}"
            )
            return ArxivPaperData(
                arxiv_id=arxiv_id,
                title="",
                authors=[],
                success=False,
                error_message=f"Unexpected error: {str(e)}",
            )


class ArxivAuthorsPopulator:
    """
    Populates missing authors using ArXiv API data.
    """

    def __init__(self, dry_run: bool = False):
        """Initialize the populator."""
        self.dry_run = dry_run
        self.arxiv_client = ArxivApiClient()
        self.stats = {
            "papers_processed": 0,
            "papers_with_authors_found": 0,
            "papers_without_authors": 0,
            "authors_created": 0,
            "authors_found_existing": 0,
            "paper_author_links_created": 0,
            "api_errors": 0,
            "start_time": time.time(),
        }

        # Cache for author deduplication
        self.author_cache: Dict[str, int] = {}  # name -> author_id

    def get_papers_missing_authors(
        self, db: Session, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get papers that are missing authors."""
        query = """
        SELECT p.id, p.arxiv_id, p.title
        FROM papers p
        LEFT JOIN (SELECT DISTINCT paper_id FROM paper_authors) pa ON p.id = pa.paper_id
        WHERE pa.paper_id IS NULL
        AND p.arxiv_id IS NOT NULL
        AND p.arxiv_id != ''
        ORDER BY p.id
        """

        if limit:
            query += f" LIMIT {limit}"

        result = db.execute(text(query)).fetchall()

        return [
            {
                "id": row.id,
                "arxiv_id": row.arxiv_id,
                "title": row.title,
            }
            for row in result
        ]

    def populate_missing_authors(self, limit: Optional[int] = None) -> None:
        """Main process to populate missing authors from ArXiv API."""
        logger.info("🚀 Starting ArXiv API Authors Population")
        logger.info("=" * 60)

        db_session = next(get_database_session())

        try:
            # Get papers missing authors
            papers_missing_authors = self.get_papers_missing_authors(db_session, limit)

            if not papers_missing_authors:
                logger.info("✅ No papers missing authors found!")
                return

            logger.info(
                f"📊 Found {len(papers_missing_authors)} papers missing authors"
            )
            logger.info(
                f"🔄 ArXiv API delay: {ARXIV_API_DELAY} seconds between requests"
            )
            logger.info(
                f"⏱️  Estimated time: {len(papers_missing_authors) * ARXIV_API_DELAY / 60:.1f} minutes"
            )

            if self.dry_run:
                logger.info("⚠️  DRY RUN MODE - No database changes will be made")

            logger.info("")

            # Process each paper
            for i, paper_data in enumerate(papers_missing_authors, 1):
                try:
                    logger.info(
                        f"📄 Processing paper {i}/{len(papers_missing_authors)}: {paper_data['arxiv_id']}"
                    )

                    # Fetch data from ArXiv API
                    arxiv_data = self.arxiv_client.fetch_paper_data(
                        paper_data["arxiv_id"]
                    )

                    if not arxiv_data.success:
                        logger.warning(
                            f"❌ Failed to fetch data: {arxiv_data.error_message}"
                        )
                        self.stats["api_errors"] += 1
                    elif not arxiv_data.authors:
                        logger.info("📝 No authors found in ArXiv data")
                        self.stats["papers_without_authors"] += 1
                    else:
                        # Process authors
                        logger.info(f"👥 Found {len(arxiv_data.authors)} authors")
                        self._process_paper_authors(
                            db_session, paper_data, arxiv_data.authors
                        )
                        self.stats["papers_with_authors_found"] += 1

                    self.stats["papers_processed"] += 1

                    # Progress reporting
                    if i % 10 == 0:
                        elapsed = time.time() - self.stats["start_time"]
                        rate = i / elapsed if elapsed > 0 else 0
                        remaining_time = (
                            (len(papers_missing_authors) - i) / rate if rate > 0 else 0
                        )

                        logger.info(
                            f"📈 Progress: {i}/{len(papers_missing_authors)} ({i / len(papers_missing_authors) * 100:.1f}%)"
                        )
                        logger.info(
                            f"⏱️  Rate: {rate:.2f} papers/sec | ETA: {remaining_time / 60:.1f} min"
                        )

                        # Periodic commit
                        if not self.dry_run:
                            try:
                                db_session.commit()
                                logger.debug("💾 Periodic commit successful")
                            except Exception as commit_error:
                                logger.error(f"Commit error: {commit_error}")
                                db_session.rollback()

                    # Rate limiting
                    if i < len(
                        papers_missing_authors
                    ):  # Don't sleep after the last request
                        time.sleep(ARXIV_API_DELAY)

                except Exception as e:
                    logger.error(
                        f"Error processing paper {paper_data['arxiv_id']}: {e}"
                    )
                    self.stats["api_errors"] += 1
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
                    logger.info("💾 Final commit successful")
                except Exception as final_commit_error:
                    logger.error(f"Final commit error: {final_commit_error}")
                    db_session.rollback()

        finally:
            db_session.close()

        logger.info(f"✅ Completed processing {len(papers_missing_authors)} papers")

    def _process_paper_authors(
        self, db: Session, paper_data: Dict[str, Any], arxiv_authors: List[ArxivAuthor]
    ) -> None:
        """Process authors for a single paper."""
        paper_id = paper_data["id"]

        # Process each author
        for author_order, arxiv_author in enumerate(arxiv_authors, 1):
            try:
                author_id = self._get_or_create_author(db, arxiv_author.name)
                self._link_paper_author(db, paper_id, author_id, author_order)
            except Exception as e:
                logger.error(
                    f"Error processing author '{arxiv_author.name}' for paper {paper_data['arxiv_id']}: {e}"
                )
                # Don't re-raise the exception to avoid transaction abort

    def _get_or_create_author(self, db: Session, full_name: str) -> int:
        """Get existing author or create new one. Returns author_id."""

        # Parse/clean the name
        clean_name = ArxivAuthorNameParser.parse_name(full_name)

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
            fake_id = (
                len(self.author_cache) + 1000000
            )  # Use high numbers to avoid conflicts
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
        print("ARXIV API AUTHORS POPULATION STATISTICS")
        print("=" * 60)
        print(f"Papers processed:           {self.stats['papers_processed']:,}")
        print(
            f"Papers with authors found:  {self.stats['papers_with_authors_found']:,}"
        )
        print(f"Papers without authors:     {self.stats['papers_without_authors']:,}")
        print(f"Authors created:            {self.stats['authors_created']:,}")
        print(f"Authors found existing:     {self.stats['authors_found_existing']:,}")
        print(
            f"Paper-author links created: {self.stats['paper_author_links_created']:,}"
        )
        print(f"API errors:                 {self.stats['api_errors']:,}")
        print(f"Processing time:            {elapsed_time:.2f} seconds")

        if self.stats["papers_processed"] > 0:
            rate = self.stats["papers_processed"] / elapsed_time
            print(f"Processing rate:            {rate:.2f} papers/second")

            success_rate = (
                self.stats["papers_with_authors_found"] / self.stats["papers_processed"]
            ) * 100
            print(f"Success rate:               {success_rate:.1f}%")

        print("=" * 60)


def main():
    """Main function with command line argument parsing."""
    parser = argparse.ArgumentParser(
        description="Populate missing authors from ArXiv API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --test                    # Test mode (10 papers)
  %(prog)s --production              # Production mode (all missing papers)
  %(prog)s --limit 100               # Process 100 papers
  %(prog)s --dry-run --limit 50      # Dry run with 50 papers
        """,
    )
    parser.add_argument(
        "--test", action="store_true", help="Test mode - process only 10 papers"
    )
    parser.add_argument(
        "--production",
        action="store_true",
        help="Production mode - process all missing papers",
    )
    parser.add_argument("--limit", type=int, help="Limit number of papers to process")
    parser.add_argument(
        "--dry-run", action="store_true", help="Dry run - no database writes"
    )

    args = parser.parse_args()

    # Determine limit
    if args.test:
        limit = 10
        print("🧪 Running in TEST MODE")
    elif args.production:
        limit = None
        print("🏭 Running in PRODUCTION MODE")
    elif args.limit:
        limit = args.limit
    else:
        print("Please specify --test, --production, or --limit")
        sys.exit(1)

    print("ArXiv API Authors Population Script")
    print(f"Limit: {limit if limit else 'All missing papers'}")
    print(f"Dry run: {args.dry_run}")

    if args.dry_run:
        print("\n⚠️  DRY RUN MODE - No database changes will be made")

    # Create populator and run
    populator = ArxivAuthorsPopulator(dry_run=args.dry_run)

    try:
        populator.populate_missing_authors(limit)
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
