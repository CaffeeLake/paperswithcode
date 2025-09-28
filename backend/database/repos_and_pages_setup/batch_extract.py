"""
AI-powered batch processor for extracting GitHub URLs and project pages from papers.

This script processes papers to find GitHub repositories and project pages using:
1. AI extraction via OpenRouterGenerator
2. Memory monitoring for 4GB RAM systems
3. Database-driven deduplication (no caching needed)
4. Prioritization of papers missing both GitHub repos and project pages

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
import logging
import time
import psutil
from typing import List, Dict, Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import get_database_session
from backend.genai_steps.extract_github_and_project_page_url import (
    get_project_github_urls,
    warm_pdf_cache,
)
from backend.generators.openrouter_generator import OpenRouterGenerator
from backend.database.logging_config import setup_logging

# Set up logging with INFO level for clean extraction results
logger = setup_logging("batch_extract", log_level=logging.INFO)


class BatchURLExtractor:
    """Batch processor to extract GitHub URLs and project pages from papers."""

    def __init__(
        self,
        batch_size: int = 20,
        dry_run: bool = False,
        use_paid_tier: bool = True,
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

        self.stats = {
            "papers_processed": 0,
            "papers_with_github": 0,
            "papers_with_project_page": 0,
            "papers_with_both": 0,
            "papers_with_neither": 0,
            "github_skipped_existing": 0,
            "project_page_skipped_existing": 0,
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

        # REFINED PRIORITIZATION:
        # 1. Highest: Never processed by AI + has neither GitHub nor project page
        # 2. Medium: Never processed by AI + has only one type of URL (missing the other)
        # 3. Lower: Processed by AI but missing URLs (with reprocessing control)
        # 4. Skip: Has both URLs or was processed by AI with no results found
        query = """
        SELECT DISTINCT
            p.id,
            p.arxiv_id,
            p.title,
            p.abstract,
            p.date_published,
            CASE WHEN repo_count.count > 0 THEN 1 ELSE 0 END as has_github_repo,
            CASE WHEN page_count.count > 0 THEN 1 ELSE 0 END as has_project_page,
            -- Check if paper has been processed by AI extraction (found URLs)
            CASE WHEN ai_repo_count.count > 0 OR ai_page_count.count > 0 THEN 1 ELSE 0 END as processed_by_ai_with_results,
            -- Check if paper was processed by AI but no URLs found (avoid reprocessing)
            CASE WHEN ai_no_results.paper_id IS NOT NULL THEN 1 ELSE 0 END as processed_by_ai_no_results,
            -- Refined priority system
            CASE
                -- Priority 0: Never processed by AI + has neither GitHub nor project page (HIGHEST)
                WHEN (ai_repo_count.count IS NULL AND ai_page_count.count IS NULL AND ai_no_results.paper_id IS NULL)
                     AND (repo_count.count IS NULL OR repo_count.count = 0)
                     AND (page_count.count IS NULL OR page_count.count = 0) THEN 0

                -- Priority 1: Never processed by AI + has only one type of URL (MEDIUM)
                WHEN (ai_repo_count.count IS NULL AND ai_page_count.count IS NULL AND ai_no_results.paper_id IS NULL)
                     AND ((repo_count.count > 0 AND (page_count.count IS NULL OR page_count.count = 0))
                          OR (page_count.count > 0 AND (repo_count.count IS NULL OR repo_count.count = 0))) THEN 1

                -- Priority 2: Processed by AI with results but missing one type of URL (LOWER)
                WHEN (ai_repo_count.count > 0 OR ai_page_count.count > 0)
                     AND ((repo_count.count IS NULL OR repo_count.count = 0)
                          OR (page_count.count IS NULL OR page_count.count = 0)) THEN 2

                -- Priority 999: Skip - has both URLs or was processed with no results
                ELSE 999
            END as priority
        FROM papers p
        LEFT JOIN (
            SELECT pr.paper_id, COUNT(*) as count
            FROM paper_repositories pr
            GROUP BY pr.paper_id
        ) repo_count ON p.id = repo_count.paper_id
        LEFT JOIN (
            SELECT ppp.paper_id, COUNT(*) as count
            FROM paper_project_pages ppp
            GROUP BY ppp.paper_id
        ) page_count ON p.id = page_count.paper_id
        LEFT JOIN (
            -- Count AI-extracted repositories for this paper
            SELECT pr.paper_id, COUNT(*) as count
            FROM paper_repositories pr
            JOIN repositories r ON pr.repository_id = r.id
            WHERE r.source = 'ai_extraction'
            GROUP BY pr.paper_id
        ) ai_repo_count ON p.id = ai_repo_count.paper_id
        LEFT JOIN (
            -- Count AI-extracted project pages for this paper
            SELECT ppp.paper_id, COUNT(*) as count
            FROM paper_project_pages ppp
            JOIN project_pages pp ON ppp.project_page_id = pp.id
            WHERE pp.source = 'ai_extraction'
            GROUP BY ppp.paper_id
        ) ai_page_count ON p.id = ai_page_count.paper_id
        LEFT JOIN (
            -- Track papers processed by AI with no results (to avoid reprocessing)
            -- Use a dedicated marker: empty repository with special URL pattern
            SELECT DISTINCT pr.paper_id
            FROM paper_repositories pr
            JOIN repositories r ON pr.repository_id = r.id
            WHERE r.source = 'ai_extraction'
              AND r.url = 'AI_PROCESSED_NO_RESULTS'
        ) ai_no_results ON p.id = ai_no_results.paper_id
        WHERE p.abstract IS NOT NULL
          AND p.abstract != ''
          AND p.arxiv_id IS NOT NULL
          AND p.arxiv_id != ''
          AND LENGTH(p.abstract) > 100
          AND p.date_published >= :start_date
          AND (
              -- Only include papers with priority 0, 1, or 2 (skip priority 999)
              CASE
                -- Priority 0: Never processed + has neither URL
                WHEN (ai_repo_count.count IS NULL AND ai_page_count.count IS NULL AND ai_no_results.paper_id IS NULL)
                     AND (repo_count.count IS NULL OR repo_count.count = 0)
                     AND (page_count.count IS NULL OR page_count.count = 0) THEN 0

                -- Priority 1: Never processed + has only one URL
                WHEN (ai_repo_count.count IS NULL AND ai_page_count.count IS NULL AND ai_no_results.paper_id IS NULL)
                     AND ((repo_count.count > 0 AND (page_count.count IS NULL OR page_count.count = 0))
                          OR (page_count.count > 0 AND (repo_count.count IS NULL OR repo_count.count = 0))) THEN 1

                -- Priority 2: Processed with results but missing one URL
                WHEN (ai_repo_count.count > 0 OR ai_page_count.count > 0)
                     AND ((repo_count.count IS NULL OR repo_count.count = 0)
                          OR (page_count.count IS NULL OR page_count.count = 0)) THEN 2

                ELSE 999
              END <= 2
          )
        ORDER BY
            -- Prioritize by refined priority system
            priority,
            p.date_published DESC NULLS LAST,
            p.id DESC
        """

        if limit:
            query += f" LIMIT {limit}"

        result = db.execute(text(query), {"start_date": start_date}).fetchall()

        papers = [
            {
                "id": row.id,
                "arxiv_id": row.arxiv_id,
                "title": row.title,
                "abstract": row.abstract,
                "has_github_repo": bool(row.has_github_repo),
                "has_project_page": bool(row.has_project_page),
                "processed_by_ai_with_results": bool(row.processed_by_ai_with_results),
                "processed_by_ai_no_results": bool(row.processed_by_ai_no_results),
                "priority": row.priority,
            }
            for row in result
        ]

        # Log sample of papers being processed
        if papers:
            logger.info("📋 Sample of papers to process:")
            for i, paper in enumerate(papers[:3]):  # Log first 3 papers
                # Determine AI processing status
                if paper["processed_by_ai_with_results"]:
                    ai_status = "✅ Processed by AI (found URLs)"
                elif paper["processed_by_ai_no_results"]:
                    ai_status = "🔄 Processed by AI (no URLs found)"
                else:
                    ai_status = "🆕 Never processed by AI"

                # Priority descriptions
                priority_desc = {
                    0: "🔥 Highest (never processed + no URLs)",
                    1: "⚡ Medium (never processed + partial URLs)",
                    2: "🔽 Lower (processed but missing URLs)",
                }

                logger.info(
                    f"  {i + 1}. {paper['arxiv_id']} - {paper['title'][:100]}..."
                )
                logger.info(
                    f"     Has GitHub: {paper['has_github_repo']}, Has Project: {paper['has_project_page']}"
                )
                logger.info(f"     AI Status: {ai_status}")
                logger.info(
                    f"     Priority: {priority_desc.get(paper['priority'], f'Unknown ({paper["priority"]})')}"
                )
                logger.info(f"     Abstract length: {len(paper['abstract'])} chars")

        return papers

    def save_results_to_db(
        self,
        db: Session,
        paper_id: int,
        github_url: str,
        project_page_url: str,
        source: str = "ai_extraction",
    ) -> None:
        """Save extracted URLs to the database with proper source tracking."""
        if self.dry_run:
            logger.info(
                f"[DRY RUN] Paper {paper_id}: Would save GitHub={github_url}, Project={project_page_url}"
            )
            return

        try:
            # Insert GitHub repository if found and paper doesn't already have one
            if github_url and github_url.strip():
                # Check if paper already has ANY GitHub repository
                existing_repo_check = """
                SELECT COUNT(*) as repo_count
                FROM paper_repositories pr
                JOIN repositories r ON pr.repository_id = r.id
                WHERE pr.paper_id = :paper_id
                """
                repo_count_result = db.execute(
                    text(existing_repo_check), {"paper_id": paper_id}
                ).fetchone()

                if repo_count_result and repo_count_result.repo_count > 0:
                    pass  # Already has repo, will be handled by skip logic
                else:
                    # First insert into repositories table (normalized - no paper_id)
                    repo_insert = """
                    INSERT INTO repositories (url, source, created_at, updated_at)
                    VALUES (:url, :source, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT (url) DO UPDATE SET updated_at = CURRENT_TIMESTAMP
                    RETURNING id
                    """
                    result = db.execute(
                        text(repo_insert),
                        {"url": github_url.strip(), "source": source},
                    ).fetchone()

                    if result:
                        repo_id = result.id
                        # Then insert into junction table (only foreign keys)
                        junction_insert = """
                        INSERT INTO paper_repositories (paper_id, repository_id)
                        VALUES (:paper_id, :repository_id)
                        ON CONFLICT DO NOTHING
                        """
                        db.execute(
                            text(junction_insert),
                            {"paper_id": paper_id, "repository_id": repo_id},
                        )
                        logger.info(f"💾 Saved GitHub repo: {github_url}")

            # Insert project page if found and paper doesn't already have one
            if project_page_url and project_page_url.strip():
                # Check if paper already has ANY project page
                existing_project_check = """
                SELECT COUNT(*) as page_count
                FROM paper_project_pages
                WHERE paper_id = :paper_id
                """
                page_count_result = db.execute(
                    text(existing_project_check), {"paper_id": paper_id}
                ).fetchone()

                if page_count_result and page_count_result.page_count > 0:
                    pass  # Already has project page, will be handled by skip logic
                else:
                    # Check if project page already exists (no unique constraint, so we need to check manually)
                    existing_page_query = """
                    SELECT id FROM project_pages WHERE url = :url LIMIT 1
                    """
                    existing_page = db.execute(
                        text(existing_page_query),
                        {"url": project_page_url.strip()},
                    ).fetchone()

                    if existing_page:
                        page_id = existing_page.id
                    else:
                        # Insert new project page
                        page_insert = """
                        INSERT INTO project_pages (url, is_official, source, created_at, updated_at)
                        VALUES (:url, true, :source, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                        RETURNING id
                        """
                        result = db.execute(
                            text(page_insert),
                            {"url": project_page_url.strip(), "source": source},
                        ).fetchone()
                        page_id = result.id if result else None

                    if page_id:
                        # Then insert into junction table (only foreign keys)
                        junction_insert = """
                        INSERT INTO paper_project_pages (paper_id, project_page_id)
                        VALUES (:paper_id, :project_page_id)
                        ON CONFLICT DO NOTHING
                        """
                        db.execute(
                            text(junction_insert),
                            {"paper_id": paper_id, "project_page_id": page_id},
                        )
                        logger.info(f"💾 Saved project page: {project_page_url}")

            # If no URLs were found, create a marker to avoid reprocessing
            if not github_url and not project_page_url:
                # Insert a special marker to indicate this paper was processed but no URLs found
                marker_insert = """
                INSERT INTO repositories (url, source, created_at, updated_at)
                VALUES (:url, :source, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (url) DO UPDATE SET updated_at = CURRENT_TIMESTAMP
                RETURNING id
                """
                result = db.execute(
                    text(marker_insert),
                    {"url": "AI_PROCESSED_NO_RESULTS", "source": source},
                ).fetchone()

                if result:
                    marker_id = result.id
                    # Link this marker to the paper
                    junction_insert = """
                    INSERT INTO paper_repositories (paper_id, repository_id)
                    VALUES (:paper_id, :repository_id)
                    ON CONFLICT DO NOTHING
                    """
                    db.execute(
                        text(junction_insert),
                        {"paper_id": paper_id, "repository_id": marker_id},
                    )
                    logger.info(
                        f"🔄 Marked paper {paper_id} as processed with no URLs found"
                    )

            db.commit()

        except Exception as e:
            logger.error(f"❌ Error saving results for paper {paper_id}: {e}")
            db.rollback()

    async def process_paper(self, paper: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """Process a single paper using the unified get_project_github_urls function."""
        arxiv_id = paper["arxiv_id"]
        paper_id = paper["id"]
        has_github_repo = paper.get("has_github_repo", False)
        has_project_page = paper.get("has_project_page", False)
        abstract = paper["abstract"]

        try:
            # Call AI extraction directly - no caching needed since database handles deduplication
            try:
                logger.info(
                    f"🤖 Starting AI extraction for {arxiv_id}: {paper.get('title', 'N/A')[:80]}..."
                )

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

                # Log concise results
                github_status = f"✅ {github_url}" if github_url else "❌ None"
                project_status = (
                    f"✅ {project_page_url}" if project_page_url else "❌ None"
                )
                logger.info(
                    f"🔗 {arxiv_id}: GitHub={github_status}, Project={project_status}"
                )

            except Exception as e:
                logger.error(
                    f"❌ Error calling get_project_github_urls for {arxiv_id}: {e}"
                )
                self.stats["api_errors"] += 1
                github_url = ""
                project_page_url = ""

            # Only process URLs for papers that don't already have them
            final_github_url = github_url if not has_github_repo else ""
            final_project_page_url = project_page_url if not has_project_page else ""

            # Track what we're skipping and update stats
            skip_reasons = []
            if has_github_repo and github_url:
                skip_reasons.append("GitHub (already exists)")
                self.stats["github_skipped_existing"] += 1
            if has_project_page and project_page_url:
                skip_reasons.append("Project page (already exists)")
                self.stats["project_page_skipped_existing"] += 1

            if skip_reasons:
                logger.info(f"⏭️  {arxiv_id}: Skipped {', '.join(skip_reasons)}")

            # Save results with appropriate source
            source = "ai_extraction"

            self.save_results_to_db(
                db,
                paper_id,
                final_github_url,
                final_project_page_url,
                source,
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

            # Final status summary
            github_final = (
                "✅ Saved"
                if final_github_url
                else ("⏭️ Skipped" if has_github_repo else "❌ None")
            )
            project_final = (
                "✅ Saved"
                if final_project_page_url
                else ("⏭️ Skipped" if has_project_page else "❌ None")
            )
            logger.info(
                f"✅ {arxiv_id}: GitHub={github_final}, Project={project_final}"
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
                "github_url": "",
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
        print(
            f"⏭️  GitHub URLs Skipped (existing): {self.stats['github_skipped_existing']}"
        )
        print(
            f"⏭️  Project Pages Skipped (existing): {self.stats['project_page_skipped_existing']}"
        )

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
