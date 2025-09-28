"""
Hourly Citation Count Update CRON Job

Optimized version that processes ~2,800 papers per hour while staying well within
Semantic Scholar's API limits. This allows us to process the entire papers database
much faster than the daily version.

Rate Limits (Semantic Scholar API):
- 1 request per second across all endpoints
- Must stay below this threshold to avoid rejected requests

Optimized Strategy:
- Process 2,800 papers per hour (77% of theoretical 3,600/hour limit)
- Use optimized rate limiting (1.3s between requests = 2,769 req/hour)
- Conservative buffer to handle API variations and retries
- Prioritize papers that haven't been updated recently
- Efficient async processing with proper error handling
- Skip papers updated within the last 30 days (configurable)

Schedule: Hourly (every hour)
Dependencies: PostgreSQL, Semantic Scholar API

Performance Improvement:
- Daily version: 2,000 papers/day = 730K papers/year
- Hourly version: 2,800 papers/hour = 24.5M papers/year (33x faster!)
"""

import sys
import time
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
import httpx
from dataclasses import dataclass

from cron.utils.cron_helpers import DatabaseCronJob
from backend.config import get_settings


@dataclass
class CitationResult:
    """Result of citation lookup for a paper."""

    paper_id: int
    arxiv_id: str
    title: str
    citation_count: int
    semantic_scholar_id: Optional[str]
    success: bool
    error_message: Optional[str] = None


class CitationHourlyUpdateJob(DatabaseCronJob):
    """Hourly job to update paper citation counts with optimized throughput."""

    def __init__(self):
        super().__init__(job_name="update_citations_hourly", log_level="INFO")
        self.settings = get_settings()

        # Semantic Scholar API configuration
        self.api_key = "6Wa5zD2S3HahK5AAjMRnr6n31usSpq1a3gpksOQa"
        self.base_url = "https://api.semanticscholar.org/graph/v1"

        # Optimized rate limiting for hourly runs (77% of theoretical max)
        self.request_delay = 1.3  # 1.3 seconds between requests (2,769 req/hour)
        self.batch_size = 100  # Larger batches for efficiency
        self.max_papers_per_run = 2800  # Use 77% of hourly theoretical limit
        self.request_timeout = 10.0  # Shorter timeout for hourly jobs
        self.update_threshold_days = (
            7  # Only update papers older than this (reduced for more frequent updates)
        )
        self.chunk_size = 500  # Process papers in smaller chunks to reduce memory usage

        # Statistics
        self.stats = {
            "papers_found": 0,
            "papers_processed": 0,
            "citations_updated": 0,
            "papers_not_found": 0,
            "api_errors": 0,
            "rate_limit_hits": 0,
            "processing_errors": 0,
            "api_calls": 0,
        }

        # HTTP client will be created in async context
        self.client = None

    def run(self):
        """Main execution logic for citation updates."""
        self.logger.info("Starting hourly citation count update")

        # Get total count of papers that need citation updates
        total_papers = self.get_papers_count()

        if total_papers == 0:
            self.logger.info("No papers need citation updates at this time")
            return

        self.logger.info(f"Found {total_papers} papers to update")

        # Limit the number of papers per run to respect rate limits
        papers_to_process = min(total_papers, self.max_papers_per_run)
        if papers_to_process < total_papers:
            self.logger.info(
                f"Limited to {papers_to_process} papers for this hourly run"
            )

        # Process papers in streaming chunks to reduce memory usage
        asyncio.run(self.process_papers_in_streaming_chunks(papers_to_process))

        # Log summary
        self.log_summary()

        # Update database statistics (less frequent for hourly jobs)
        if datetime.now().hour % 6 == 0:  # Only every 6 hours
            self.vacuum_analyze_table("papers")

    def get_papers_count(self) -> int:
        """Get count of papers that need citation updates."""
        threshold_date = datetime.now() - timedelta(days=self.update_threshold_days)

        # Count query for memory-efficient processing
        count_query = """
        SELECT COUNT(*)
        FROM papers
        WHERE is_latest_version = true
          AND arxiv_id IS NOT NULL
          AND (
              citation_updated_at IS NULL
              OR citation_updated_at < %s
          )
        """

        try:
            result = self.execute_query(count_query, (threshold_date,))
            count = result[0]["count"] if result else 0
            self.stats["papers_found"] = count
            return count
        except Exception as e:
            self.logger.error(f"Error counting papers to update: {e}")
            return 0

    def get_papers_chunk(self, offset: int, limit: int) -> List[Dict]:
        """Get a chunk of papers that need citation updates."""
        threshold_date = datetime.now() - timedelta(days=self.update_threshold_days)

        # Chunk query for streaming processing with priority information
        query = """
        SELECT
            id,
            arxiv_id,
            title,
            citation_count,
            citation_updated_at,
            date_published,
            -- Priority indicators for logging
            CASE WHEN citation_updated_at IS NULL THEN 'NEVER_UPDATED'
                 WHEN citation_count = 0 THEN 'ZERO_CITATIONS'
                 ELSE 'REFRESH' END as priority_type
        FROM papers
        WHERE is_latest_version = true
          AND arxiv_id IS NOT NULL
          AND (
              citation_updated_at IS NULL
              OR citation_updated_at < %s
          )
        ORDER BY
            -- Prioritize papers never updated (highest priority)
            CASE WHEN citation_updated_at IS NULL THEN 0 ELSE 1 END,
            -- Then prioritize papers with 0 citations (may have gained citations)
            CASE WHEN citation_count = 0 THEN 1 ELSE 2 END,
            -- Then prioritize high-citation years (2017-2024)
            CASE
                WHEN EXTRACT(YEAR FROM date_published) BETWEEN 2019 AND 2022 THEN 1
                WHEN EXTRACT(YEAR FROM date_published) BETWEEN 2017 AND 2018 THEN 2
                WHEN EXTRACT(YEAR FROM date_published) BETWEEN 2023 AND 2024 THEN 3
                ELSE 4
            END,
            -- Within each tier, oldest updates first
            citation_updated_at ASC NULLS FIRST,
            id ASC
        LIMIT %s OFFSET %s
        """

        try:
            results = self.execute_query(query, (threshold_date, limit, offset))
            return results
        except Exception as e:
            self.logger.error(
                f"Error fetching papers chunk (offset={offset}, limit={limit}): {e}"
            )
            return []

    async def process_papers_in_streaming_chunks(self, total_papers_to_process: int):
        """Process papers in streaming chunks to reduce memory usage."""
        total_chunks = (
            total_papers_to_process + self.chunk_size - 1
        ) // self.chunk_size

        self.logger.info(
            f"Processing {total_papers_to_process} papers in {total_chunks} chunks of {self.chunk_size}"
        )

        start_time = time.time()

        for chunk_num in range(total_chunks):
            offset = chunk_num * self.chunk_size
            limit = min(self.chunk_size, total_papers_to_process - offset)

            self.logger.info(
                f"Processing chunk {chunk_num + 1}/{total_chunks} (offset={offset}, limit={limit})"
            )

            # Fetch chunk of papers
            chunk_start = time.time()
            papers = self.get_papers_chunk(offset, limit)

            if not papers:
                self.logger.warning(f"No papers found in chunk {chunk_num + 1}")
                continue

            self.logger.info(f"Fetched {len(papers)} papers in chunk {chunk_num + 1}")

            # Process this chunk with rate limiting
            await self.process_papers_with_rate_limiting(papers)

            # Log chunk completion and memory efficiency
            chunk_elapsed = time.time() - chunk_start
            total_elapsed = time.time() - start_time
            rate = (
                self.stats["papers_processed"] / total_elapsed
                if total_elapsed > 0
                else 0
            )

            progress = ((chunk_num + 1) / total_chunks) * 100
            self.logger.info(
                f"Chunk {chunk_num + 1}/{total_chunks} completed in {chunk_elapsed:.1f}s - "
                f"Progress: {progress:.1f}% - "
                f"Rate: {rate:.1f} papers/sec - "
                f"Updated: {self.stats['citations_updated']}"
            )

            # Small delay between chunks to prevent overwhelming the system
            if chunk_num < total_chunks - 1:
                await asyncio.sleep(1)

    async def process_papers_with_rate_limiting(self, papers: List[Dict]):
        """Process papers with optimized rate limiting for hourly execution."""
        self.logger.debug(
            f"Processing {len(papers)} papers with {self.request_delay}s delays"
        )

        # Create HTTP client with optimized settings
        headers = {"x-api-key": self.api_key} if self.api_key else {}
        limits = httpx.Limits(max_keepalive_connections=10, max_connections=10)

        async with httpx.AsyncClient(
            timeout=self.request_timeout, limits=limits, headers=headers
        ) as client:
            self.client = client

            # Process papers in batches
            total_batches = (len(papers) + self.batch_size - 1) // self.batch_size

            for batch_num in range(total_batches):
                start_idx = batch_num * self.batch_size
                end_idx = min(start_idx + self.batch_size, len(papers))
                batch = papers[start_idx:end_idx]

                self.logger.debug(
                    f"Processing batch {batch_num + 1}/{total_batches} ({len(batch)} papers)"
                )

                # Process each paper in the batch with rate limiting
                batch_results = []

                for paper in batch:
                    try:
                        result = await self.process_single_paper(paper)
                        batch_results.append(result)

                        # Optimized rate limiting - wait between each request
                        if result:  # Only count actual API calls
                            await asyncio.sleep(self.request_delay)

                    except Exception as e:
                        self.logger.error(
                            f"Error processing paper {paper.get('id')}: {e}"
                        )
                        self.stats["processing_errors"] += 1

                # Update database with batch results
                if batch_results:
                    self.update_citations_batch(batch_results)

    async def process_single_paper(self, paper: Dict) -> Optional[CitationResult]:
        """Process a single paper to update its citation count."""
        paper_id = paper["id"]
        arxiv_id = paper["arxiv_id"]
        title = paper["title"]

        self.stats["papers_processed"] += 1

        # Log high-priority papers
        priority_type = paper.get("priority_type", "UNKNOWN")
        if priority_type in ["NEVER_UPDATED", "ZERO_CITATIONS"]:
            self.logger.debug(
                f"Processing {priority_type} paper: {arxiv_id} (current citations: {paper.get('citation_count', 0)})"
            )

        # Fetch citation data from Semantic Scholar API
        citation_data = await self.fetch_citation_data(arxiv_id, title)

        if citation_data:
            new_citation_count = citation_data.get("citationCount", 0)
            current_citation_count = paper.get("citation_count", 0)

            # Log significant updates for high-priority papers
            if (
                priority_type in ["NEVER_UPDATED", "ZERO_CITATIONS"]
                and new_citation_count != current_citation_count
            ):
                self.logger.info(
                    f"Updated {priority_type} paper {arxiv_id}: {current_citation_count} → {new_citation_count} citations"
                )

            return CitationResult(
                paper_id=paper_id,
                arxiv_id=arxiv_id,
                title=title,
                citation_count=new_citation_count,
                semantic_scholar_id=citation_data.get("paperId"),
                success=True,
            )
        else:
            # Mark as processed but not found
            return CitationResult(
                paper_id=paper_id,
                arxiv_id=arxiv_id,
                title=title,
                citation_count=0,
                semantic_scholar_id=None,
                success=False,
                error_message="Not found in Semantic Scholar",
            )

    async def fetch_citation_data(
        self, arxiv_id: str, title: str
    ) -> Optional[Dict[str, Any]]:
        """Fetch citation data from Semantic Scholar API with optimized error handling."""
        url = f"{self.base_url}/paper/arXiv:{arxiv_id}"
        params = {"fields": "paperId,title,citationCount,year"}

        try:
            self.stats["api_calls"] += 1

            response = await self.client.get(url, params=params)

            if response.status_code == 200:
                data = response.json()

                # Verify title match for accuracy
                if self.titles_match(title, data.get("title", "")):
                    self.logger.debug(
                        f"Found citations for {arxiv_id}: {data.get('citationCount', 0)}"
                    )
                    return data
                else:
                    self.logger.debug(f"Title mismatch for {arxiv_id}")
                    return None

            elif response.status_code == 404:
                self.logger.debug(f"Paper not found in Semantic Scholar: {arxiv_id}")
                self.stats["papers_not_found"] += 1
                return None

            elif response.status_code == 429:
                # Rate limited - for hourly jobs, just skip and continue
                self.logger.warning(f"Rate limited for {arxiv_id}")
                self.stats["rate_limit_hits"] += 1
                await asyncio.sleep(self.request_delay * 2)  # Wait double time
                return None

            else:
                self.logger.warning(
                    f"Semantic Scholar API error for {arxiv_id}: {response.status_code}"
                )
                self.stats["api_errors"] += 1
                return None

        except asyncio.TimeoutError:
            self.logger.warning(f"Timeout fetching citation data for {arxiv_id}")
            self.stats["api_errors"] += 1
            return None
        except Exception as e:
            self.logger.error(f"Error fetching citation data for {arxiv_id}: {e}")
            self.stats["api_errors"] += 1
            return None

    def titles_match(self, title1: str, title2: str, threshold: float = 0.8) -> bool:
        """Check if two titles are similar enough using word-based similarity."""
        import re

        def normalize_title(title):
            # Convert to lowercase, remove punctuation, split into words
            return set(re.findall(r"\w+", title.lower()))

        words1 = normalize_title(title1)
        words2 = normalize_title(title2)

        if not words1 or not words2:
            return False

        # Calculate Jaccard similarity
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))

        similarity = intersection / union if union > 0 else 0
        return similarity >= threshold

    def update_citations_batch(self, results: List[CitationResult]):
        """Update database with citation results in batch."""
        if not results:
            return

        try:
            # Process successful updates
            successful_results = [
                r for r in results if r.success and r.semantic_scholar_id
            ]
            if successful_results:
                for result in successful_results:
                    query = """
                    UPDATE papers
                    SET citation_count = %s,
                        semantic_scholar_id = %s,
                        citation_updated_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    """
                    self.execute_query(
                        query,
                        (
                            result.citation_count,
                            result.semantic_scholar_id,
                            result.paper_id,
                        ),
                    )

                self.stats["citations_updated"] += len(successful_results)
                self.logger.debug(
                    f"Updated {len(successful_results)} papers with citations"
                )

            # Process failed updates (mark as processed to avoid re-processing)
            failed_results = [
                r for r in results if not r.success or not r.semantic_scholar_id
            ]
            if failed_results:
                for result in failed_results:
                    query = """
                    UPDATE papers
                    SET citation_updated_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    """
                    self.execute_query(query, (result.paper_id,))

                self.logger.debug(f"Marked {len(failed_results)} papers as processed")

        except Exception as e:
            self.logger.error(f"Error updating citations batch: {e}")
            self.stats["processing_errors"] += 1

    def log_summary(self):
        """Log execution summary with performance metrics."""
        self.logger.info("Hourly citation count update completed:")
        self.logger.info(f"  - Papers found: {self.stats['papers_found']}")
        self.logger.info(f"  - Papers processed: {self.stats['papers_processed']}")
        self.logger.info(f"  - Citations updated: {self.stats['citations_updated']}")
        self.logger.info(f"  - Papers not found: {self.stats['papers_not_found']}")
        self.logger.info(f"  - API calls made: {self.stats['api_calls']}")
        self.logger.info(f"  - API errors: {self.stats['api_errors']}")
        self.logger.info(f"  - Rate limit hits: {self.stats['rate_limit_hits']}")
        self.logger.info(f"  - Processing errors: {self.stats['processing_errors']}")

        if self.stats["papers_processed"] > 0:
            success_rate = (
                self.stats["citations_updated"] / self.stats["papers_processed"]
            ) * 100
            self.logger.info(f"  - Success rate: {success_rate:.1f}%")

        # Performance projections
        if self.stats["api_calls"] > 0:
            # Calculate actual request rate
            estimated_time = self.stats["api_calls"] * self.request_delay
            actual_rate = (
                self.stats["api_calls"] / estimated_time if estimated_time > 0 else 0
            )
            hourly_projection = self.stats["papers_processed"]
            daily_projection = hourly_projection * 24

            self.logger.info(f"  - Actual API rate: {actual_rate:.2f} req/sec")
            self.logger.info(f"  - Hourly processing rate: {hourly_projection} papers")
            self.logger.info(f"  - Daily projection: {daily_projection:,} papers")

        # Get current citation statistics (brief version for hourly jobs)
        self.log_citation_statistics_brief()

    def log_citation_statistics_brief(self):
        """Log brief citation statistics for hourly jobs."""
        try:
            query = """
            SELECT
                COUNT(*) as total_papers,
                COUNT(CASE WHEN citation_updated_at IS NOT NULL THEN 1 END) as papers_processed,
                COUNT(CASE WHEN citation_count > 0 THEN 1 END) as papers_with_citations
            FROM papers
            WHERE is_latest_version = true
            """

            result = self.execute_query(query)
            if result:
                stats = result[0]
                processed_pct = (
                    (stats["papers_processed"] / stats["total_papers"]) * 100
                    if stats["total_papers"] > 0
                    else 0
                )
                self.logger.info(
                    f"  - Overall progress: {processed_pct:.1f}% ({stats['papers_processed']:,}/{stats['total_papers']:,})"
                )
                self.logger.info(
                    f"  - Papers with citations: {stats['papers_with_citations']:,}"
                )

        except Exception as e:
            self.logger.error(f"Error getting citation statistics: {e}")


if __name__ == "__main__":
    job = CitationHourlyUpdateJob()
    success = job.execute()
    sys.exit(0 if success else 1)
