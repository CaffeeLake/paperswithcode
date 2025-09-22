"""
Fast batch processor for extracting GitHub URLs and project pages.

This optimized version focuses on speed by:
1. Using ONLY simple methods (no AI/PDF downloads)
2. Higher concurrency
3. Faster database queries
4. Skip expensive operations

Usage:
    uv run -m backend.database.repos_and_pages_setup.fast_batch_extract --limit 1000 --batch-size 50
"""

import argparse
import asyncio
import time
from typing import List, Dict, Any, Optional
import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import get_database_session
from backend.utils.paper_utils import (
    get_github_and_project_page_urls_from_daily_papers,
    find_github_url,
)

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class FastBatchURLExtractor:
    """Fast batch processor focusing on simple methods only."""

    def __init__(self, batch_size: int = 50, dry_run: bool = False):
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
        """Get papers that need URL extraction (fast query)."""
        query = """
        SELECT DISTINCT
            p.id,
            p.arxiv_id,
            p.title,
            p.abstract,
            CASE WHEN r.paper_id IS NOT NULL THEN r.url ELSE NULL END as existing_github_url,
            CASE WHEN pp.paper_id IS NOT NULL THEN 1 ELSE 0 END as has_project_page
        FROM papers p
        LEFT JOIN repositories r ON p.id = r.paper_id
        LEFT JOIN project_pages pp ON p.id = pp.paper_id
        WHERE p.abstract IS NOT NULL
          AND p.abstract != ''
          AND p.arxiv_id IS NOT NULL
          AND p.arxiv_id != ''
          AND LENGTH(p.abstract) > 100
          AND pp.paper_id IS NULL  -- Focus on missing project pages
        ORDER BY p.id DESC  -- Simple ordering for speed
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
            logger.debug(
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

            db.commit()

        except Exception as e:
            logger.error(f"❌ Error saving results for paper {paper_id}: {e}")
            db.rollback()

    async def process_paper_fast(
        self, paper: Dict[str, Any], db: Session
    ) -> Dict[str, Any]:
        """Process a single paper using ONLY fast simple methods."""
        arxiv_id = paper["arxiv_id"]
        paper_id = paper["id"]
        abstract = paper["abstract"]
        existing_github_url = paper.get("existing_github_url")

        try:
            # Method 1: Try Hugging Face Daily Papers API (fast)
            (
                github_url,
                project_page_url,
            ) = await get_github_and_project_page_urls_from_daily_papers(arxiv_id)

            # Method 2: Try regex on abstract (very fast)
            if not github_url:
                github_url = await find_github_url(arxiv_id, abstract)

            # Use existing GitHub URL if available
            final_github_url = existing_github_url or github_url

            # Save results
            self.save_results_to_db(
                db, paper_id, final_github_url, project_page_url, existing_github_url
            )

            # Update stats
            self.stats["papers_processed"] += 1
            if final_github_url:
                self.stats["papers_with_github"] += 1
            if project_page_url:
                self.stats["papers_with_project_page"] += 1
            if final_github_url and project_page_url:
                self.stats["papers_with_both"] += 1
            if not final_github_url and not project_page_url:
                self.stats["papers_with_neither"] += 1

            return {
                "paper_id": paper_id,
                "arxiv_id": arxiv_id,
                "github_url": final_github_url,
                "project_page_url": project_page_url,
                "success": True,
            }

        except Exception as e:
            logger.error(f"❌ Error processing paper {arxiv_id}: {e}")
            self.stats["api_errors"] += 1
            return {
                "paper_id": paper_id,
                "arxiv_id": arxiv_id,
                "github_url": existing_github_url or "",
                "project_page_url": "",
                "error": str(e),
                "success": False,
            }

    async def process_batch(
        self, papers: List[Dict[str, Any]], db: Session
    ) -> List[Dict[str, Any]]:
        """Process a batch of papers concurrently."""
        logger.info(f"🚀 Processing batch of {len(papers)} papers (FAST MODE)")

        # Higher concurrency for simple methods
        semaphore = asyncio.Semaphore(20)  # 20 concurrent requests

        async def process_with_semaphore(paper):
            async with semaphore:
                return await self.process_paper_fast(paper, db)

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
        print("📊 FAST BATCH PROCESSING STATISTICS")
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
            print(
                f"📈 Estimated for 510K papers: {510000 / rate / 3600:.1f} hours ({510000 / rate / 3600 / 24:.1f} days)"
            )

        print("=" * 60)

    async def run(self, limit: Optional[int] = None) -> None:
        """Run the fast batch processing."""
        logger.info(
            f"🚀 Starting FAST batch URL extraction (limit={limit}, batch_size={self.batch_size}, dry_run={self.dry_run})"
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

                # Print progress every 5 batches
                if batch_num % 5 == 0 or batch_num == total_batches:
                    self.print_stats()

                # Small delay between batches
                if batch_num < total_batches:
                    await asyncio.sleep(0.5)  # Much shorter delay

            # Final statistics
            self.print_stats()

        except Exception as e:
            logger.error(f"❌ Fatal error in batch processing: {e}")
            raise
        finally:
            db.close()


async def main():
    parser = argparse.ArgumentParser(
        description="Fast batch extract GitHub URLs and project pages (simple methods only)"
    )
    parser.add_argument(
        "--limit", type=int, help="Maximum number of papers to process", default=None
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        help="Number of papers to process in each batch",
        default=50,
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Run without saving results to database"
    )

    args = parser.parse_args()

    extractor = FastBatchURLExtractor(batch_size=args.batch_size, dry_run=args.dry_run)

    await extractor.run(limit=args.limit)


if __name__ == "__main__":
    asyncio.run(main())
