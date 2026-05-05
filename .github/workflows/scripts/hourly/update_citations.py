"""
Hourly Citation Count Update CRON Job

Optimized version that processes a bounded chunk of papers each hour while staying
within Semantic Scholar's API limits.

Rate Limits (Semantic Scholar API):
- 1 request per second across all endpoints
- Must stay below this threshold to avoid rejected requests

Optimized Strategy:
- Process at most 1,500 papers per run so the next hourly tick is not skipped
- Use conservative rate limiting with buffer for API variations and retries
- Prioritize papers that haven't been updated recently
- Efficient async processing with proper error handling
- Skip papers updated within the last 30 days (configurable)

Schedule: Hourly (every hour)
Dependencies: PostgreSQL, Semantic Scholar API

Performance:
- Bounded hourly runs keep GitHub Actions and VPS load predictable under throttling
"""

import sys
import time
import asyncio
import signal
from datetime import datetime
from typing import List, Dict, Optional, Any
import httpx
from dataclasses import dataclass

from scripts.utils.cron_helpers import DatabaseCronJob
from backend.config import get_settings
from backend.services.paper_service import PaperService
from backend.database.connection import get_database_session


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

        # Initialize paper service - get the actual session from the generator
        self.db_session = next(get_database_session())
        self.paper_service = PaperService(self.db_session)

        # Semantic Scholar API configuration
        self.api_key = self.settings.semantic_scholar_api_key
        self.base_url = "https://api.semanticscholar.org/graph/v1"

        # Conservative hourly bounds leave room for Semantic Scholar throttling.
        self.request_delay = 1.5
        self.batch_size = 100  # Larger batches for efficiency
        self.max_papers_per_run = 1500
        self.request_timeout = 10.0  # Shorter timeout for hourly jobs
        self.update_threshold_days = (
            7  # Only update papers older than this (reduced for more frequent updates)
        )
        self.chunk_size = 500  # Process papers in smaller chunks to reduce memory usage

        # Timeout protection: keep each hourly tick bounded.
        self.max_runtime_seconds = 45 * 60
        self.shutdown_requested = False

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

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

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        signal_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
        self.logger.warning(f"Received {signal_name} - initiating graceful shutdown")
        self.shutdown_requested = True

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

        # Process papers in streaming chunks to reduce memory usage with timeout protection
        try:
            asyncio.run(
                asyncio.wait_for(
                    self.process_papers_in_streaming_chunks(papers_to_process),
                    timeout=self.max_runtime_seconds,
                )
            )
        except asyncio.TimeoutError:
            self.logger.error(
                f"Job timed out after {self.max_runtime_seconds}s - "
                f"this prevents zombie processes"
            )
            # Don't raise - let it complete gracefully
        except KeyboardInterrupt:
            self.logger.warning("Job interrupted by user")

        # Log summary
        self.log_summary()

        # Update database statistics (less frequent for hourly jobs)
        if datetime.now().hour % 6 == 0:  # Only every 6 hours
            self.vacuum_analyze_table("papers")

    def get_papers_count(self) -> int:
        """Get count of papers that need citation updates."""
        try:
            count = self.paper_service.get_papers_needing_citation_update_count(
                self.update_threshold_days
            )
            self.stats["papers_found"] = count
            return count
        except Exception as e:
            self.logger.error(f"Error counting papers to update: {e}")
            return 0

    def get_papers_chunk(self, offset: int, limit: int) -> List[Dict]:
        """Get a chunk of papers that need citation updates."""
        try:
            results = self.paper_service.get_papers_needing_citation_update_chunk(
                offset, limit, self.update_threshold_days
            )
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
            # Convert CitationResult objects to dictionaries for the paper service
            citation_updates = []
            for result in results:
                citation_updates.append(
                    {
                        "paper_id": result.paper_id,
                        "citation_count": result.citation_count,
                        "semantic_scholar_id": result.semantic_scholar_id,
                        "success": result.success,
                    }
                )

            # Use paper service to update citations in batch
            update_stats = self.paper_service.update_citation_counts_batch(
                citation_updates
            )

            self.stats["citations_updated"] += update_stats["updated"]
            self.logger.debug(
                f"Updated {update_stats['updated']} papers with citations, "
                f"marked {update_stats['failed']} as processed"
            )

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
            stats = self.paper_service.get_citation_statistics()

            self.logger.info(
                f"  - Overall progress: {stats['processed_percentage']:.1f}% "
                f"({stats['papers_processed']:,}/{stats['total_papers']:,})"
            )
            self.logger.info(
                f"  - Papers with citations: {stats['papers_with_citations']:,}"
            )

        except Exception as e:
            self.logger.error(f"Error getting citation statistics: {e}")

    def cleanup(self):
        """Clean up database connections."""
        try:
            if hasattr(self, "db_session") and self.db_session:
                self.db_session.close()
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")


if __name__ == "__main__":
    job = CitationHourlyUpdateJob()
    try:
        success = job.execute()
    finally:
        job.cleanup()
    sys.exit(0 if success else 1)
