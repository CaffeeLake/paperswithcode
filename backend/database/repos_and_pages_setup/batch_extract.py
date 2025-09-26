"""
AI-powered batch processor for extracting GitHub URLs and project pages from papers.

This script processes papers to find GitHub repositories and project pages using:
1. Hybrid processing (fast methods first, AI as fallback)
2. Semantic caching to avoid redundant API calls
3. Memory monitoring for 4GB RAM systems
4. OpenRouterGenerator

Logs can be saved at backend/database/logs.

Usage:
```bash
# Process papers with default settings
uv run --env-file backend/keys.env -m backend.database.repos_and_pages_setup.batch_extract --limit 100

# Memory-safe processing with custom batch size and start year
uv run --env-file backend/keys.env -m backend.database.repos_and_pages_setup.batch_extract --batch-size 10 --start-year 2020
```
"""

import argparse
import asyncio
import time
import json
import hashlib
import psutil
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import get_database_session
from backend.genai_steps.extract_github_and_project_page_url import (
    get_project_github_urls,
    warm_pdf_cache,
)
from backend.generators.openrouter_generator import OpenRouterGenerator
from backend.database.logging_config import setup_logging

# Set up logging
logger = setup_logging("batch_extract")


class SemanticCache:
    """Simple semantic caching based on content hashing."""

    def __init__(
        self,
        cache_file="backend/database/repos_and_pages_setup/cache/ai_extraction_cache.json",
    ):
        self.cache_file = Path(cache_file)
        self.cache = self._load_cache()

    def _load_cache(self) -> Dict:
        """Load cache from file."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")
        return {}

    def _save_cache(self):
        """Save cache to file."""
        try:
            with open(self.cache_file, "w") as f:
                json.dump(self.cache, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")

    def get_cache_key(self, paper_data: Dict) -> str:
        """Generate cache key based on paper content."""
        content = f"{paper_data.get('title', '')}\n{paper_data.get('abstract', '')}"
        return hashlib.md5(content.encode()).hexdigest()

    def get(self, paper_data: Dict) -> Optional[Dict]:
        """Get cached result."""
        key = self.get_cache_key(paper_data)
        return self.cache.get(key)

    def set(self, paper_data: Dict, result: Dict):
        """Cache result."""
        key = self.get_cache_key(paper_data)
        self.cache[key] = {
            **result,
            "cached_at": datetime.now().isoformat(),
            "paper_id": paper_data.get("id"),
        }
        self._save_cache()


class BatchURLExtractor:
    """Batch processor to extract GitHub URLs and project pages from papers."""

    def __init__(
        self,
        batch_size: int = 20,
        dry_run: bool = False,
        use_paid_tier: bool = False,
        start_year: int = 2014,
    ):
        self.batch_size = batch_size
        self.dry_run = dry_run
        self.start_year = start_year

        # Initialize OpenRouter generator with appropriate rate limits
        requests_per_minute = 20
        requests_per_day = 1000 if use_paid_tier else 50
        self.generator = OpenRouterGenerator(
            requests_per_minute=requests_per_minute, requests_per_day=requests_per_day
        )

        self.cache = SemanticCache()
        self.stats = {
            "papers_processed": 0,
            "papers_with_github": 0,
            "papers_with_project_page": 0,
            "papers_with_both": 0,
            "papers_with_neither": 0,
            "cache_hits": 0,
            "api_errors": 0,
            "start_time": time.time(),
        }

        # Memory monitoring
        self.process = psutil.Process()
        self.memory_limit_mb = 3500

    def get_memory_usage(self) -> Dict[str, float]:
        """Get current memory usage statistics."""
        memory_info = self.process.memory_info()
        system_memory = psutil.virtual_memory()

        return {
            "process_memory_mb": memory_info.rss / 1024 / 1024,
            "system_memory_percent": system_memory.percent,
            "system_available_mb": system_memory.available / 1024 / 1024,
        }

    def check_memory_safety(self) -> tuple[bool, str]:
        """Check if memory usage is safe for continued processing."""
        memory_stats = self.get_memory_usage()

        # Check if we're approaching memory limits
        if memory_stats["process_memory_mb"] > self.memory_limit_mb:
            return (
                False,
                f"Process memory ({memory_stats['process_memory_mb']:.1f}MB) exceeds limit ({self.memory_limit_mb}MB)",
            )

        if memory_stats["system_memory_percent"] > 85:
            return (
                False,
                f"System memory usage ({memory_stats['system_memory_percent']:.1f}%) too high",
            )

        if memory_stats["system_available_mb"] < 500:
            return (
                False,
                f"Available system memory ({memory_stats['system_available_mb']:.1f}MB) too low",
            )

        return True, "Memory usage is safe"

    def get_papers_missing_urls(
        self, db: Session, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get papers that need URL extraction."""

        # Create start date from year
        start_date = f"{self.start_year}-01-01"

        # Process all papers that are missing GitHub repositories or project pages
        query = """
        SELECT DISTINCT
            p.id,
            p.arxiv_id,
            p.title,
            p.abstract,
            p.date_published,
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
          AND (r.paper_id IS NULL OR pp.paper_id IS NULL)
          AND p.date_published >= :start_date
        ORDER BY
            p.date_published DESC NULLS LAST,
            p.id DESC
        """

        if limit:
            query += f" LIMIT {limit}"

        result = db.execute(text(query), {"start_date": start_date}).fetchall()

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
        source: str = "ai_extraction",
        existing_github_url: Optional[str] = None,
    ) -> None:
        """Save extracted URLs to the database with proper source tracking."""
        if self.dry_run:
            logger.debug(
                f"[DRY RUN] Would save for paper {paper_id}: GitHub={github_url}, Project={project_page_url}"
            )
            return

        try:
            # Insert GitHub repository if found and not already exists
            if github_url and github_url.strip() and not existing_github_url:
                github_insert = """
                INSERT INTO repositories (paper_id, url, is_official, source, created_at, updated_at)
                VALUES (:paper_id, :url, true, :source, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT DO NOTHING
                """
                db.execute(
                    text(github_insert),
                    {"paper_id": paper_id, "url": github_url.strip(), "source": source},
                )
                logger.debug(f"📦 Added GitHub repo ({source}): {github_url}")

            # Insert project page if found
            if project_page_url and project_page_url.strip():
                project_insert = """
                INSERT INTO project_pages (paper_id, url, is_official, source, created_at, updated_at)
                VALUES (:paper_id, :url, true, :source, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT DO NOTHING
                """
                db.execute(
                    text(project_insert),
                    {
                        "paper_id": paper_id,
                        "url": project_page_url.strip(),
                        "source": source,
                    },
                )
                logger.debug(f"🌐 Added project page ({source}): {project_page_url}")

            db.commit()

        except Exception as e:
            logger.error(f"❌ Error saving results for paper {paper_id}: {e}")
            db.rollback()

    async def process_paper(self, paper: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """Process a single paper using the unified get_project_github_urls function."""
        arxiv_id = paper["arxiv_id"]
        paper_id = paper["id"]
        existing_github_url = paper.get("existing_github_url")
        abstract = paper["abstract"]

        try:
            # Check cache first
            cached_result = self.cache.get(paper)
            if cached_result:
                logger.debug(f"📋 Cache hit for {arxiv_id}")
                self.stats["cache_hits"] += 1
                github_url = cached_result.get("github_url", "")
                project_page_url = cached_result.get("project_page_url", "")
            else:
                try:
                    reasoning, response = await get_project_github_urls(
                        arxiv_id=arxiv_id,
                        session_id=None,
                        use_reasoning=True,
                        abstract=abstract,
                    )

                    github_url = response.get("github_url", "") if response else ""
                    project_page_url = (
                        response.get("project_page_url", "") if response else ""
                    )

                except Exception as e:
                    logger.error(
                        f"❌ Error calling get_project_github_urls for {arxiv_id}: {e}"
                    )
                    self.stats["api_errors"] += 1
                    github_url = ""
                    project_page_url = ""

                # Cache the result
                result_to_cache = {
                    "github_url": github_url,
                    "project_page_url": project_page_url,
                }
                self.cache.set(paper, result_to_cache)

            # Use existing GitHub URL if available
            final_github_url = existing_github_url or github_url

            # Save results with appropriate source
            source = "ai_extraction"

            self.save_results_to_db(
                db,
                paper_id,
                final_github_url,
                project_page_url,
                source,
                existing_github_url,
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

            logger.info(
                f"✅ Completed {arxiv_id}: GitHub={'✓' if final_github_url else '✗'}, Project={'✓' if project_page_url else '✗'}"
            )

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
        """Process a batch of papers with controlled concurrency."""
        logger.info(f"🚀 Processing batch of {len(papers)} papers (UNIFIED MODE)")

        # Lower concurrency for AI methods to respect rate limits
        semaphore = asyncio.Semaphore(3)  # Only 3 concurrent requests

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

        # Get current memory usage
        memory_stats = self.get_memory_usage()

        print("\n" + "=" * 60)
        print("📊 AI BATCH PROCESSING STATISTICS")
        print("=" * 60)
        print(f"📅 Start Year Filter: {self.start_year}")
        print(f"⏱️  Total Time: {elapsed:.1f} seconds")
        print(f"📄 Papers Processed: {self.stats['papers_processed']}")

        if self.stats["papers_processed"] > 0:
            print(
                f"📋 Cache Hits: {self.stats['cache_hits']} ({self.stats['cache_hits'] / self.stats['papers_processed'] * 100:.1f}%)"
            )
            print(
                f"🔗 Papers with GitHub: {self.stats['papers_with_github']} ({self.stats['papers_with_github'] / self.stats['papers_processed'] * 100:.1f}%)"
            )
            print(
                f"🌐 Papers with Project Page: {self.stats['papers_with_project_page']} ({self.stats['papers_with_project_page'] / self.stats['papers_processed'] * 100:.1f}%)"
            )
            print(
                f"🎯 Papers with Both: {self.stats['papers_with_both']} ({self.stats['papers_with_both'] / self.stats['papers_processed'] * 100:.1f}%)"
            )
            print(
                f"❌ Papers with Neither: {self.stats['papers_with_neither']} ({self.stats['papers_with_neither'] / self.stats['papers_processed'] * 100:.1f}%)"
            )

        print(f"⚠️  API Errors: {self.stats['api_errors']}")

        # Memory information
        print(
            f"💾 Memory Usage: {memory_stats['process_memory_mb']:.1f}MB process, {memory_stats['system_memory_percent']:.1f}% system"
        )
        print(f"💾 Available Memory: {memory_stats['system_available_mb']:.1f}MB")

        if self.stats["papers_processed"] > 0:
            rate = self.stats["papers_processed"] / elapsed
            print(f"⚡ Processing Rate: {rate:.2f} papers/second")

            # Estimate daily capacity based on rate limits
            # Assume all papers may use AI (conservative estimate)
            daily_limit = self.generator.requests_per_day
            estimated_daily = daily_limit  # Conservative: 1 request per paper

            print(f"📈 Estimated Daily Capacity: {estimated_daily:.0f} papers")
            if estimated_daily > 0:
                print(
                    f"📈 Estimated for 10K papers: {10000 / estimated_daily:.1f} days"
                )

        print("=" * 60)

    async def run(self, limit: Optional[int] = None) -> None:
        """Run the batch processing."""
        logger.info(
            f"🚀 Starting batch URL extraction (limit={limit}, batch_size={self.batch_size}, dry_run={self.dry_run})"
        )

        # Warm PDF cache for few-shot examples
        logger.info("📋 Warming PDF cache for few-shot examples...")
        try:
            cache_info = await warm_pdf_cache()
            logger.info(
                f"✅ PDF cache ready: {cache_info['cached_count']} files, {cache_info['total_size_mb']:.1f} MB"
            )
        except Exception as e:
            logger.warning(f"⚠️  Failed to warm PDF cache: {e}")

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
                # Check memory safety before each batch
                memory_safe, memory_message = self.check_memory_safety()
                if not memory_safe:
                    logger.warning(f"⚠️  Memory limit reached: {memory_message}")
                    logger.info("🛑 Stopping processing to avoid system instability")
                    break

                batch = papers[i : i + self.batch_size]
                batch_num = (i // self.batch_size) + 1
                total_batches = (len(papers) + self.batch_size - 1) // self.batch_size

                logger.info(f"📦 Processing batch {batch_num}/{total_batches}")

                await self.process_batch(batch, db)

                # Print progress every 3 batches
                if batch_num % 3 == 0 or batch_num == total_batches:
                    self.print_stats()

                # Delay between batches for rate limiting
                if batch_num < total_batches:
                    await asyncio.sleep(2)  # 2 second delay

            # Final statistics
            self.print_stats()

        except Exception as e:
            logger.error(f"❌ Fatal error in batch processing: {e}")
            raise
        finally:
            db.close()


async def main():
    parser = argparse.ArgumentParser(
        description="AI batch extract GitHub URLs and project pages from papers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--limit", type=int, help="Maximum number of papers to process", default=None
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        help="Number of papers to process in each batch",
        default=20,
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Run without saving results to database"
    )
    parser.add_argument(
        "--paid-tier",
        action="store_false",
        help="Use paid tier rate limits (1000/day instead of 50/day)",
    )
    parser.add_argument(
        "--start-year",
        type=int,
        default=2014,
        help="Start year for filtering papers (default: 2014)",
    )

    args = parser.parse_args()

    extractor = BatchURLExtractor(
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        use_paid_tier=args.paid_tier,
        start_year=args.start_year,
    )

    await extractor.run(limit=args.limit)


if __name__ == "__main__":
    asyncio.run(main())
