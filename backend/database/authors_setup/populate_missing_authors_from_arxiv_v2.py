"""
ArXiv API Author Population Script for PapersWithCode (Updated Version)

This script fetches author information from the ArXiv API for papers that are currently
missing authors in the database. It uses the centralized ArxivService for all ArXiv interactions.

🚀 FEATURES:
- Uses centralized ArxivService with proper rate limiting
- Fetches author data from ArXiv API for papers missing authors
- Parses author names intelligently
- Creates authors and paper-author links
- Provides detailed progress reporting
- Supports dry-run mode for testing

📊 USAGE:
# Test mode (10 papers)
uv run backend/database/authors_setup/populate_missing_authors_from_arxiv_v2.py --test

# Production mode (all missing papers)
uv run backend/database/authors_setup/populate_missing_authors_from_arxiv_v2.py --production

# Custom batch
uv run backend/database/authors_setup/populate_missing_authors_from_arxiv_v2.py --limit 100

# Dry run (no database writes)
uv run backend/database/authors_setup/populate_missing_authors_from_arxiv_v2.py --dry-run --limit 50
"""

import time
import re
import asyncio
from typing import Dict, Optional, List
import argparse
from dataclasses import dataclass

from backend.database.connection import get_database_session
from backend.models.database import Author as DBAuthor, PaperAuthor
from backend.services.arxiv_service import ArxivService
from sqlalchemy import and_, text
from sqlalchemy.orm import Session

# Configure logging
from backend.database.logging_config import setup_logging

logger = setup_logging("populate_missing_authors_from_arxiv_v2")


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
    """Client for interacting with the ArXiv API using the centralized ArxivService."""

    def __init__(self):
        """Initialize the ArXiv API client."""
        self.arxiv_service = ArxivService()

    async def fetch_paper_data(self, arxiv_id: str) -> ArxivPaperData:
        """
        Fetch paper data from ArXiv API using the centralized service.

        Args:
            arxiv_id: ArXiv ID of the paper

        Returns:
            ArxivPaperData object with paper information
        """
        try:
            logger.debug(f"Fetching data for ArXiv ID: {arxiv_id}")

            # Use the centralized ArXiv service
            metadata = await self.arxiv_service.get_paper_metadata(arxiv_id)

            if not metadata.success:
                return ArxivPaperData(
                    arxiv_id=arxiv_id,
                    title="",
                    authors=[],
                    success=False,
                    error_message=metadata.error_message,
                )

            # Convert authors to the expected format
            authors = []
            for author_name in metadata.authors:
                parsed_name = ArxivAuthorNameParser.parse_name(author_name)
                authors.append(ArxivAuthor(name=parsed_name))

            return ArxivPaperData(
                arxiv_id=arxiv_id,
                title=metadata.title,
                authors=authors,
                success=True,
            )

        except Exception as e:
            logger.error(f"Error fetching ArXiv data for {arxiv_id}: {e}")
            return ArxivPaperData(
                arxiv_id=arxiv_id,
                title="",
                authors=[],
                success=False,
                error_message=str(e),
            )


class AuthorPopulator:
    """
    Main class for populating missing author data from ArXiv API.
    """

    def __init__(self, db: Session, dry_run: bool = False):
        """
        Initialize the author populator.

        Args:
            db: Database session
            dry_run: If True, don't make database changes
        """
        self.db = db
        self.dry_run = dry_run
        self.arxiv_client = ArxivApiClient()

        # Statistics
        self.stats = {
            "papers_processed": 0,
            "papers_successful": 0,
            "papers_failed": 0,
            "authors_created": 0,
            "paper_author_links_created": 0,
        }

    def get_papers_missing_authors(self, limit: Optional[int] = None) -> List[Dict]:
        """
        Get papers that are missing author information.

        Args:
            limit: Maximum number of papers to return

        Returns:
            List of paper dictionaries
        """
        query = """
        SELECT DISTINCT p.id, p.arxiv_id, p.title
        FROM papers p
        LEFT JOIN paper_authors pa ON p.id = pa.paper_id
        WHERE p.arxiv_id IS NOT NULL
          AND p.arxiv_id != ''
          AND pa.paper_id IS NULL
        ORDER BY p.id DESC
        """

        if limit:
            query += f" LIMIT {limit}"

        result = self.db.execute(text(query)).fetchall()

        return [
            {
                "id": row.id,
                "arxiv_id": row.arxiv_id,
                "title": row.title,
            }
            for row in result
        ]

    def get_or_create_author(self, author_name: str) -> Optional[DBAuthor]:
        """
        Get existing author or create new one.

        Args:
            author_name: Name of the author

        Returns:
            Author object or None if creation failed
        """
        if self.dry_run:
            logger.debug(f"[DRY RUN] Would get/create author: {author_name}")
            return None

        try:
            # Check if author already exists
            existing_author = (
                self.db.query(DBAuthor).filter(DBAuthor.name == author_name).first()
            )

            if existing_author:
                logger.debug(f"Found existing author: {author_name}")
                return existing_author

            # Create new author
            new_author = DBAuthor(name=author_name)
            self.db.add(new_author)
            self.db.flush()  # Get the ID without committing

            self.stats["authors_created"] += 1
            logger.debug(f"Created new author: {author_name} (ID: {new_author.id})")

            return new_author

        except Exception as e:
            logger.error(f"Error creating author {author_name}: {e}")
            return None

    def create_paper_author_link(
        self, paper_id: int, author_id: int, author_order: int
    ) -> bool:
        """
        Create paper-author relationship.

        Args:
            paper_id: ID of the paper
            author_id: ID of the author
            author_order: Order of the author in the paper

        Returns:
            True if successful, False otherwise
        """
        if self.dry_run:
            logger.debug(
                f"[DRY RUN] Would create paper-author link: paper={paper_id}, author={author_id}, order={author_order}"
            )
            return True

        try:
            # Check if link already exists
            existing_link = (
                self.db.query(PaperAuthor)
                .filter(
                    and_(
                        PaperAuthor.paper_id == paper_id,
                        PaperAuthor.author_id == author_id,
                    )
                )
                .first()
            )

            if existing_link:
                logger.debug(
                    f"Paper-author link already exists: paper={paper_id}, author={author_id}"
                )
                return True

            # Create new link
            paper_author = PaperAuthor(
                paper_id=paper_id, author_id=author_id, author_order=author_order
            )
            self.db.add(paper_author)

            self.stats["paper_author_links_created"] += 1
            logger.debug(
                f"Created paper-author link: paper={paper_id}, author={author_id}, order={author_order}"
            )

            return True

        except Exception as e:
            logger.error(
                f"Error creating paper-author link (paper={paper_id}, author={author_id}): {e}"
            )
            return False

    async def process_paper(self, paper: Dict) -> bool:
        """
        Process a single paper to populate its authors.

        Args:
            paper: Paper dictionary with id, arxiv_id, title

        Returns:
            True if successful, False otherwise
        """
        paper_id = paper["id"]
        arxiv_id = paper["arxiv_id"]
        title = paper["title"]

        logger.info(f"Processing paper {paper_id}: {arxiv_id}")
        logger.debug(f"  Title: {title[:100]}...")

        try:
            # Fetch paper data from ArXiv
            paper_data = await self.arxiv_client.fetch_paper_data(arxiv_id)
            self.stats["papers_processed"] += 1

            if not paper_data.success:
                logger.warning(
                    f"Failed to fetch ArXiv data for {arxiv_id}: {paper_data.error_message}"
                )
                self.stats["papers_failed"] += 1
                return False

            if not paper_data.authors:
                logger.warning(f"No authors found for {arxiv_id}")
                self.stats["papers_failed"] += 1
                return False

            logger.info(f"  Found {len(paper_data.authors)} authors")

            # Process each author
            success = True
            for order, arxiv_author in enumerate(paper_data.authors):
                author_name = arxiv_author.name

                # Get or create author
                db_author = self.get_or_create_author(author_name)
                if db_author is None:
                    logger.error(f"Failed to get/create author: {author_name}")
                    success = False
                    continue

                # Create paper-author link
                if not self.create_paper_author_link(paper_id, db_author.id, order):
                    logger.error(
                        f"Failed to create paper-author link for {author_name}"
                    )
                    success = False

            # Commit changes for this paper
            if success and not self.dry_run:
                try:
                    self.db.commit()
                    logger.info(f"  ✅ Successfully processed {arxiv_id}")
                    self.stats["papers_successful"] += 1
                except Exception as e:
                    logger.error(f"Failed to commit changes for {arxiv_id}: {e}")
                    self.db.rollback()
                    success = False

            if not success:
                self.stats["papers_failed"] += 1
                if not self.dry_run:
                    self.db.rollback()

            return success

        except Exception as e:
            logger.error(f"Unexpected error processing paper {arxiv_id}: {e}")
            self.stats["papers_failed"] += 1
            if not self.dry_run:
                self.db.rollback()
            return False

    async def run(self, limit: Optional[int] = None) -> None:
        """
        Run the author population process.

        Args:
            limit: Maximum number of papers to process
        """
        logger.info("🚀 Starting ArXiv author population process")

        if self.dry_run:
            logger.info("🔍 DRY RUN MODE - No database changes will be made")

        # Get papers missing authors
        papers = self.get_papers_missing_authors(limit)
        logger.info(f"📄 Found {len(papers)} papers missing author information")

        if not papers:
            logger.info("✅ No papers need author population")
            return

        # Process papers
        start_time = time.time()

        for i, paper in enumerate(papers):
            logger.info(f"\n📄 Processing paper {i + 1}/{len(papers)}")

            await self.process_paper(paper)

            # Progress update every 10 papers
            if (i + 1) % 10 == 0:
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed
                logger.info(
                    f"📊 Progress: {i + 1}/{len(papers)} papers ({rate:.2f} papers/sec)"
                )

        # Final statistics
        elapsed = time.time() - start_time
        self.print_final_stats(elapsed)

    def print_final_stats(self, elapsed_time: float) -> None:
        """Print final processing statistics."""
        logger.info("\n" + "=" * 60)
        logger.info("📊 ARXIV AUTHOR POPULATION COMPLETE")
        logger.info("=" * 60)
        logger.info(f"⏱️  Total Time: {elapsed_time:.1f} seconds")
        logger.info(f"📄 Papers Processed: {self.stats['papers_processed']}")
        logger.info(f"✅ Papers Successful: {self.stats['papers_successful']}")
        logger.info(f"❌ Papers Failed: {self.stats['papers_failed']}")
        logger.info(f"👥 Authors Created: {self.stats['authors_created']}")
        logger.info(
            f"🔗 Paper-Author Links Created: {self.stats['paper_author_links_created']}"
        )

        if self.stats["papers_processed"] > 0:
            success_rate = (
                self.stats["papers_successful"] / self.stats["papers_processed"]
            ) * 100
            rate = self.stats["papers_processed"] / elapsed_time
            logger.info(f"📈 Success Rate: {success_rate:.1f}%")
            logger.info(f"⚡ Processing Rate: {rate:.2f} papers/second")

        logger.info("=" * 60)


async def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Populate missing author data from ArXiv API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Mutually exclusive group for test/production modes
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--test", action="store_true", help="Test mode (process 10 papers)"
    )
    mode_group.add_argument(
        "--production", action="store_true", help="Production mode (process all papers)"
    )

    parser.add_argument("--limit", type=int, help="Maximum number of papers to process")
    parser.add_argument(
        "--dry-run", action="store_true", help="Don't make database changes"
    )

    args = parser.parse_args()

    # Determine limit
    if args.test:
        limit = 10
    elif args.production:
        limit = None
    else:
        limit = args.limit

    # Get database session
    db_session_gen = get_database_session()
    db = next(db_session_gen)

    try:
        # Create and run populator
        populator = AuthorPopulator(db, dry_run=args.dry_run)
        await populator.run(limit)

    except KeyboardInterrupt:
        logger.info("\n⚠️  Process interrupted by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
