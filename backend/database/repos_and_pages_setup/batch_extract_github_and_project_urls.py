"""
Batch processor for extracting GitHub URLs and project pages from papers at scale.

This script queries the database for papers missing GitHub repositories or project pages,
then uses the extract_github_and_project_page_url.py script to find them using AI.

Usage:
    uv run -m backend.database.repos_and_pages_setup.batch_extract_github_and_project_urls --limit 100 --batch-size 10
"""

import argparse
import asyncio
import time
from typing import List, Dict, Any, Optional
import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import get_database_session
from backend.genai_steps.extract_github_and_project_page_url import (
    get_project_github_urls,
)
from backend.utils.pdf_utils import temp_pdf_download

# Set up logging first
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class BatchURLExtractor:
    """Batch processor for extracting GitHub URLs and project pages."""

    def __init__(self, batch_size: int = 10, dry_run: bool = False):
        self.batch_size = batch_size
        self.dry_run = dry_run
        self.stats = {
            "papers_processed": 0,
            "papers_with_github": 0,
            "papers_with_project_page": 0,
            "papers_with_both": 0,
            "papers_with_neither": 0,
            "api_errors": 0,
            "start_time": time.time(),
        }

    def get_papers_missing_urls(
        self, db: Session, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get papers that need URL extraction (prioritizing project pages)."""
        query = """
        SELECT DISTINCT
            p.id,
            p.arxiv_id,
            p.title,
            p.abstract,
            p.date_published,
            CASE WHEN r.paper_id IS NOT NULL THEN r.url ELSE NULL END as existing_github_url,
            CASE WHEN pp.paper_id IS NOT NULL THEN 1 ELSE 0 END as has_project_page,
            CASE WHEN r.paper_id IS NULL THEN 0 ELSE 1 END as has_github_repo
        FROM papers p
        LEFT JOIN repositories r ON p.id = r.paper_id
        LEFT JOIN project_pages pp ON p.id = pp.paper_id
        WHERE p.abstract IS NOT NULL
          AND p.abstract != ''
          AND p.arxiv_id IS NOT NULL
          AND p.arxiv_id != ''
          AND LENGTH(p.abstract) > 100  -- Ensure meaningful abstracts
          AND pp.paper_id IS NULL  -- Prioritize papers missing project pages
        ORDER BY
            has_github_repo,  -- Papers without GitHub first
            p.date_published DESC NULLS LAST,
            p.id DESC
        """

        if limit:
            query += f" LIMIT {limit}"

        result = db.execute(text(query)).fetchall()

        return [
            {
                "id": row.id,
                "arxiv_id": row.arxiv_id,
                "title": row.title,
                "abstract": row.abstract,
                "existing_github_url": row.existing_github_url,
                "has_project_page": bool(row.has_project_page),
            }
            for row in result
        ]

    def save_results_to_db(
        self,
        db: Session,
        paper_id: int,
        github_url: str,
        project_page_url: str,
        existing_github_url: Optional[str] = None,
    ) -> None:
        """Save extracted URLs to the database."""
        if self.dry_run:
            logger.info(
                f"[DRY RUN] Would save for paper {paper_id}: GitHub={github_url}, Project={project_page_url}"
            )
            return

        try:
            # Insert GitHub repository if found and not already exists
            if github_url and github_url.strip() and not existing_github_url:
                github_insert = """
                INSERT INTO repositories (paper_id, url, is_official, created_at, updated_at)
                VALUES (:paper_id, :url, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT DO NOTHING
                """
                db.execute(
                    text(github_insert),
                    {"paper_id": paper_id, "url": github_url.strip()},
                )
                logger.info(f"📦 Added GitHub repo: {github_url}")
            elif existing_github_url:
                logger.info(f"📦 Using existing GitHub repo: {existing_github_url}")

            # Insert project page if found
            if project_page_url and project_page_url.strip():
                project_insert = """
                INSERT INTO project_pages (paper_id, url, is_official, created_at, updated_at)
                VALUES (:paper_id, :url, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT DO NOTHING
                """
                db.execute(
                    text(project_insert),
                    {"paper_id": paper_id, "url": project_page_url.strip()},
                )
                logger.info(f"🌐 Added project page: {project_page_url}")

            db.commit()
            logger.info(f"✅ Saved results for paper {paper_id}")

        except Exception as e:
            logger.error(f"❌ Error saving results for paper {paper_id}: {e}")
            db.rollback()

    async def process_paper(self, paper: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """Process a single paper to extract URLs."""
        arxiv_id = paper["arxiv_id"]
        paper_id = paper["id"]
        abstract = paper["abstract"]
        existing_github_url = paper.get("existing_github_url")
        has_project_page = paper.get("has_project_page", False)

        logger.info(f"🔍 Processing paper {paper_id}: {arxiv_id}")
        if existing_github_url:
            logger.info(f"📦 Paper already has GitHub repo: {existing_github_url}")
        if has_project_page:
            logger.info("🌐 Paper already has project page")

        try:
            async with temp_pdf_download(arxiv_id=arxiv_id) as pdf_path:
                if pdf_path is None:
                    logger.warning(f"⚠️  Could not download PDF for {arxiv_id}")
                    return {
                        "paper_id": paper_id,
                        "arxiv_id": arxiv_id,
                        "github_url": existing_github_url or "",
                        "project_page_url": "",
                        "error": "PDF download failed",
                    }

                reasoning, response = await get_project_github_urls(
                    arxiv_id=arxiv_id,
                    pdf_path=pdf_path,
                    session_id=None,
                    use_reasoning=False,  # Disable reasoning for faster processing
                    abstract=abstract,  # Use database abstract
                )

                # Use existing GitHub URL if available, otherwise use extracted one
                github_url = existing_github_url or response.get("github_url", "")
                project_page_url = response.get("project_page_url", "")

                # Save results to database
                self.save_results_to_db(
                    db, paper_id, github_url, project_page_url, existing_github_url
                )

                # Update stats
                self.stats["papers_processed"] += 1
                if github_url:
                    self.stats["papers_with_github"] += 1
                if project_page_url:
                    self.stats["papers_with_project_page"] += 1
                if github_url and project_page_url:
                    self.stats["papers_with_both"] += 1
                if not github_url and not project_page_url:
                    self.stats["papers_with_neither"] += 1

                logger.info(
                    f"✅ Completed {arxiv_id}: GitHub={'✓' if github_url else '✗'}, Project={'✓' if project_page_url else '✗'}"
                )

                return {
                    "paper_id": paper_id,
                    "arxiv_id": arxiv_id,
                    "github_url": github_url,
                    "project_page_url": project_page_url,
                    "reasoning": reasoning,
                }

        except Exception as e:
            logger.error(f"❌ Error processing paper {arxiv_id}: {e}")
            self.stats["api_errors"] += 1
            return {
                "paper_id": paper_id,
                "arxiv_id": arxiv_id,
                "github_url": "",
                "project_page_url": "",
                "error": str(e),
            }

    async def process_batch(
        self, papers: List[Dict[str, Any]], db: Session
    ) -> List[Dict[str, Any]]:
        """Process a batch of papers concurrently."""
        logger.info(f"🚀 Processing batch of {len(papers)} papers")

        # Process papers concurrently but limit concurrency to avoid overwhelming APIs
        semaphore = asyncio.Semaphore(3)  # Max 3 concurrent requests

        async def process_with_semaphore(paper):
            async with semaphore:
                return await self.process_paper(paper, db)

        results = await asyncio.gather(
            *[process_with_semaphore(paper) for paper in papers], return_exceptions=True
        )

        # Handle any exceptions
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    f"❌ Exception processing paper {papers[i]['arxiv_id']}: {result}"
                )
                self.stats["api_errors"] += 1
            else:
                processed_results.append(result)

        return processed_results

    def print_stats(self) -> None:
        """Print processing statistics."""
        elapsed = time.time() - self.stats["start_time"]

        print("\n" + "=" * 60)
        print("📊 BATCH PROCESSING STATISTICS")
        print("=" * 60)
        print(f"⏱️  Total Time: {elapsed:.1f} seconds")
        print(f"📄 Papers Processed: {self.stats['papers_processed']}")
        print(
            f"🔗 Papers with GitHub: {self.stats['papers_with_github']} ({self.stats['papers_with_github'] / max(1, self.stats['papers_processed']) * 100:.1f}%)"
        )
        print(
            f"🌐 Papers with Project Page: {self.stats['papers_with_project_page']} ({self.stats['papers_with_project_page'] / max(1, self.stats['papers_processed']) * 100:.1f}%)"
        )
        print(
            f"🎯 Papers with Both: {self.stats['papers_with_both']} ({self.stats['papers_with_both'] / max(1, self.stats['papers_processed']) * 100:.1f}%)"
        )
        print(
            f"❌ Papers with Neither: {self.stats['papers_with_neither']} ({self.stats['papers_with_neither'] / max(1, self.stats['papers_processed']) * 100:.1f}%)"
        )
        print(f"⚠️  API Errors: {self.stats['api_errors']}")

        if self.stats["papers_processed"] > 0:
            rate = self.stats["papers_processed"] / elapsed
            print(f"⚡ Processing Rate: {rate:.2f} papers/second")

        print("=" * 60)

    async def run(self, limit: Optional[int] = None) -> None:
        """Run the batch processing."""
        logger.info(
            f"🚀 Starting batch URL extraction (limit={limit}, batch_size={self.batch_size}, dry_run={self.dry_run})"
        )

        # Get database session
        db_session_gen = get_database_session()
        db = next(db_session_gen)

        try:
            # Get papers that need processing
            papers = self.get_papers_missing_urls(db, limit)
            logger.info(f"📄 Found {len(papers)} papers needing URL extraction")

            if not papers:
                logger.info("✅ No papers found that need processing")
                return

            # Process in batches
            for i in range(0, len(papers), self.batch_size):
                batch = papers[i : i + self.batch_size]
                batch_num = (i // self.batch_size) + 1
                total_batches = (len(papers) + self.batch_size - 1) // self.batch_size

                logger.info(f"📦 Processing batch {batch_num}/{total_batches}")

                await self.process_batch(batch, db)

                # Print progress
                if batch_num % 5 == 0 or batch_num == total_batches:
                    self.print_stats()

                # Small delay between batches to be respectful to APIs
                if batch_num < total_batches:
                    await asyncio.sleep(2)

            # Final statistics
            self.print_stats()

        except Exception as e:
            logger.error(f"❌ Fatal error in batch processing: {e}")
            raise
        finally:
            db.close()


async def main():
    parser = argparse.ArgumentParser(
        description="Batch extract GitHub URLs and project pages from papers"
    )
    parser.add_argument(
        "--limit", type=int, help="Maximum number of papers to process", default=None
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        help="Number of papers to process in each batch",
        default=10,
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Run without saving results to database"
    )

    args = parser.parse_args()

    extractor = BatchURLExtractor(batch_size=args.batch_size, dry_run=args.dry_run)

    await extractor.run(limit=args.limit)


if __name__ == "__main__":
    asyncio.run(main())
