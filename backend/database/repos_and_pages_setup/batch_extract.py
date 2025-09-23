"""
AI-powered batch processor for extracting GitHub URLs and project pages from papers.

This script coordinates with fast_batch_extract.py to avoid processing the same papers:
1. Hybrid processing (fast methods first, AI as fallback)
2. Semantic caching to avoid redundant API calls
3. Memory monitoring for 4GB RAM systems
4. Coordination modes to work alongside other batch scripts
5. Uses rate limiting from OpenRouterGenerator

Coordination Modes:
- ai_focus: Focus on papers needing AI (missing GitHub, complex abstracts)
- fast_complement: Process papers that fast_batch_extract might skip
- all: Process all papers (original behavior)

Logs can be saved at backend/database/logs.

Usage:
```bash
# AI-focused processing (recommended when running with fast_batch_extract)
uv run --env-file backend/keys.env -m backend.database.repos_and_pages_setup.batch_extract --coordination ai_focus --limit 100

# Memory-safe processing with monitoring and custom start year
uv run --env-file backend/keys.env -m backend.database.repos_and_pages_setup.batch_extract --coordination fast_complement --batch-size 10 --start-year 2020
```
"""

import argparse
import asyncio
import time
import json
import hashlib
import psutil
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import get_database_session
from backend.utils.paper_utils import (
    get_github_and_project_page_urls_from_daily_papers,
    find_github_url,
)
from backend.genai_steps.extract_github_and_project_page_url import (
    get_project_github_urls,
    warm_pdf_cache,
)
from backend.utils.pdf_utils import temp_pdf_download, extract_first_two_pages_pymupdf
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
    """Batch processor with hybrid approach and efficient processing."""

    def __init__(
        self,
        batch_size: int = 20,
        dry_run: bool = False,
        use_paid_tier: bool = False,
        coordination_mode: str = "ai_focus",
        start_year: int = 2014,
    ):
        self.batch_size = batch_size
        self.dry_run = dry_run
        self.coordination_mode = (
            coordination_mode  # "ai_focus", "fast_complement", or "all"
        )
        self.start_year = start_year

        # Initialize OpenRouter generator with appropriate rate limits
        if use_paid_tier:
            self.generator = OpenRouterGenerator(
                requests_per_minute=20, requests_per_day=1000
            )
        else:
            self.generator = OpenRouterGenerator(
                requests_per_minute=20, requests_per_day=50
            )

        self.cache = SemanticCache()
        self.stats = {
            "papers_processed": 0,
            "papers_with_github": 0,
            "papers_with_project_page": 0,
            "papers_with_both": 0,
            "papers_with_neither": 0,
            "fast_method_success": 0,
            "ai_method_used": 0,
            "cache_hits": 0,
            "api_errors": 0,
            "start_time": time.time(),
        }

        # Memory monitoring
        self.process = psutil.Process()
        self.memory_limit_mb = (
            3500  # Conservative limit for 4GB system with other processes
        )

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
        """Get papers that need URL extraction with coordination logic."""

        # Create start date from year
        start_date = f"{self.start_year}-01-01"

        if self.coordination_mode == "ai_focus":
            # Focus on papers that need AI processing (missing GitHub, have complex abstracts)
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
              AND LENGTH(p.abstract) > 200  -- Longer abstracts more likely to need AI
              AND r.paper_id IS NULL  -- Focus on missing GitHub (AI's strength)
              AND p.date_published >= :start_date  -- Focus on papers from specified year onwards
              AND (
                -- Prioritize papers less likely to succeed with fast methods
                p.abstract NOT ILIKE '%github%'
                AND p.abstract NOT ILIKE '%code%'
                AND p.abstract NOT ILIKE '%implementation%'
              )
            ORDER BY
                p.date_published DESC NULLS LAST,  -- Newer papers first (more likely to have GitHub)
                p.id DESC
            """
        elif self.coordination_mode == "fast_complement":
            # Process papers that fast script might have skipped
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
              AND p.date_published >= :start_date  -- Focus on papers from specified year onwards
              AND p.id % 2 = 1  -- Take odd IDs (fast script takes newer/even patterns)
            ORDER BY
                p.date_published DESC NULLS LAST,  -- Newer papers first
                p.id DESC
            """
        else:  # "all" mode - original behavior
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

    async def try_fast_methods(self, paper: Dict[str, Any]) -> tuple[str, str]:
        """Try fast methods first (Hugging Face API and regex)."""
        arxiv_id = paper["arxiv_id"]
        abstract = paper["abstract"]

        # Method 1: Hugging Face Daily Papers API
        (
            github_url,
            project_page_url,
        ) = await get_github_and_project_page_urls_from_daily_papers(arxiv_id)

        # Method 2: Regex on abstract
        if not github_url:
            github_url = await find_github_url(arxiv_id, abstract)

        return github_url or "", project_page_url or ""

    async def try_ai_method(self, paper: Dict[str, Any]) -> tuple[str, str]:
        """Use AI method as fallback."""
        arxiv_id = paper["arxiv_id"]
        abstract = paper["abstract"]

        try:
            async with temp_pdf_download(arxiv_id=arxiv_id) as pdf_path:
                if pdf_path is None:
                    logger.warning(f"⚠️  Could not download PDF for {arxiv_id}")
                    return "", ""

                try:
                    # Extract first 2 pages only to improve AI accuracy and reduce processing
                    logger.debug(f"📄 Extracting first 2 pages for {arxiv_id}")
                    first_two_pages_path = await extract_first_two_pages_pymupdf(
                        pdf_path
                    )

                    result = await get_project_github_urls(
                        arxiv_id=arxiv_id,
                        pdf_path=first_two_pages_path,
                        session_id=None,
                        use_reasoning=True,
                        abstract=abstract,
                    )

                    # Clean up the temporary first 2 pages file
                    try:
                        os.unlink(first_two_pages_path)
                        logger.debug(
                            f"🧹 Cleaned up temporary file: {first_two_pages_path}"
                        )
                    except Exception as cleanup_error:
                        logger.warning(
                            f"⚠️  Failed to clean up {first_two_pages_path}: {cleanup_error}"
                        )

                    # Handle case where result might be None or not a tuple
                    if result is None:
                        logger.warning(f"⚠️  AI method returned None for {arxiv_id}")
                        response = {}
                    elif isinstance(result, tuple) and len(result) == 2:
                        reasoning, response = result
                    else:
                        logger.warning(
                            f"⚠️  AI method returned unexpected format for {arxiv_id}: {type(result)}"
                        )
                        response = {}

                    github_url = response.get("github_url", "") if response else ""
                    project_page_url = (
                        response.get("project_page_url", "") if response else ""
                    )

                    self.stats["ai_method_used"] += 1
                    return github_url, project_page_url

                except Exception as ai_error:
                    logger.error(f"❌ AI method call failed for {arxiv_id}: {ai_error}")
                    self.stats["api_errors"] += 1
                    return "", ""

        except Exception as e:
            logger.error(f"❌ AI method setup failed for {arxiv_id}: {e}")
            self.stats["api_errors"] += 1
            return "", ""

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

    async def process_paper_hybrid(
        self, paper: Dict[str, Any], db: Session
    ) -> Dict[str, Any]:
        """Process a single paper using hybrid approach (fast first, AI fallback)."""
        arxiv_id = paper["arxiv_id"]
        paper_id = paper["id"]
        existing_github_url = paper.get("existing_github_url")

        try:
            # Check cache first
            cached_result = self.cache.get(paper)
            if cached_result:
                logger.debug(f"📋 Cache hit for {arxiv_id}")
                self.stats["cache_hits"] += 1
                github_url = cached_result.get("github_url", "")
                project_page_url = cached_result.get("project_page_url", "")
                method_used = "cached"
            else:
                # Step 1: Try fast methods first
                github_url, project_page_url = await self.try_fast_methods(paper)

                if github_url or project_page_url:
                    self.stats["fast_method_success"] += 1
                    logger.debug(f"⚡ Fast method success for {arxiv_id}")
                    method_used = "fast"
                else:
                    # Step 2: Use AI method as fallback
                    logger.info(f"🤖 Using AI method for {arxiv_id}")
                    github_url, project_page_url = await self.try_ai_method(paper)
                    method_used = "ai"

                # Cache the result
                result_to_cache = {
                    "github_url": github_url,
                    "project_page_url": project_page_url,
                }
                self.cache.set(paper, result_to_cache)

            # Use existing GitHub URL if available
            final_github_url = existing_github_url or github_url

            # Save results with appropriate source
            if method_used == "fast":
                source = "fast"
            elif method_used == "ai":
                source = "ai_extraction"
            else:  # cached
                source = "ai_extraction"  # Cached results were originally from AI

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
                f"✅ Completed {arxiv_id}: GitHub={'✓' if final_github_url else '✗'}, Project={'✓' if project_page_url else '✗'} ({method_used})"
            )

            return {
                "paper_id": paper_id,
                "arxiv_id": arxiv_id,
                "github_url": final_github_url,
                "project_page_url": project_page_url,
                "method": method_used,
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
        logger.info(f"🚀 Processing batch of {len(papers)} papers (HYBRID MODE)")

        # Lower concurrency for AI methods to respect rate limits
        semaphore = asyncio.Semaphore(3)  # Only 3 concurrent requests

        async def process_with_semaphore(paper):
            async with semaphore:
                return await self.process_paper_hybrid(paper, db)

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
        print(f"🔧 Coordination Mode: {self.coordination_mode}")
        print(f"📅 Start Year Filter: {self.start_year}")
        print(f"⏱️  Total Time: {elapsed:.1f} seconds")
        print(f"📄 Papers Processed: {self.stats['papers_processed']}")

        if self.stats["papers_processed"] > 0:
            print(
                f"⚡ Fast Method Success: {self.stats['fast_method_success']} ({self.stats['fast_method_success'] / self.stats['papers_processed'] * 100:.1f}%)"
            )
            print(
                f"🤖 AI Method Used: {self.stats['ai_method_used']} ({self.stats['ai_method_used'] / self.stats['papers_processed'] * 100:.1f}%)"
            )
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

            # Estimate based on AI usage
            ai_ratio = self.stats["ai_method_used"] / max(
                1, self.stats["papers_processed"]
            )
            daily_limit = self.generator.requests_per_day
            estimated_daily = daily_limit / max(ai_ratio, 0.1)  # Account for AI usage

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
        epilog="""
Coordination modes:
  ai_focus        Focus on papers needing AI (missing GitHub, complex abstracts)
  fast_complement Process papers that fast_batch_extract might skip
  all             Process all papers (original behavior)

Examples:
  # AI-focused processing (recommended when running with fast_batch_extract)
  uv run --env-file backend/keys.env -m backend.database.repos_and_pages_setup.batch_extract --coordination ai_focus --limit 100

  # Complement fast batch processing with custom start year
  uv run --env-file backend/keys.env -m backend.database.repos_and_pages_setup.batch_extract --coordination fast_complement --limit 500 --start-year 2020
        """,
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
        action="store_true",
        help="Use paid tier rate limits (1000/day instead of 50/day)",
    )
    parser.add_argument(
        "--coordination",
        choices=["ai_focus", "fast_complement", "all"],
        default="ai_focus",
        help="Coordination mode with other batch scripts (default: ai_focus)",
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
        coordination_mode=args.coordination,
        start_year=args.start_year,
    )

    await extractor.run(limit=args.limit)


if __name__ == "__main__":
    asyncio.run(main())
