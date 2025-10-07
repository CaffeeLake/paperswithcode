"""
Hourly GitHub URLs and Project Pages Extraction CRON Job

AI-powered extraction of GitHub repositories and project pages from papers using
Google Gemini AI models. This job processes papers that haven't been analyzed yet
(urls_extracted = FALSE) to find official GitHub repos and project pages.

Rate Limits (Google Gemini Free Tier):
- Gemini 2.5 Flash: 250 requests per day (10 RPM)
- Gemini 2.5 Pro: 100 requests per day (5 RPM)
- Combined: 350 requests per day

Optimized Strategy:
- Process 14 papers per hour (conservative for free tier = 336/day with buffer)
- Use memory-safe batch processing (4GB RAM system)
- Prioritize recent papers (2014 onwards by default)
- Skip papers already processed by HF API import
- Mark papers as processed to avoid reprocessing

Processing Logic:
- Only processes papers where urls_extracted = FALSE
- Papers imported from HF API have urls_extracted = TRUE (already have URLs)
- AI-extracted URLs saved with source='ai_extraction' and is_official=True
- After successful processing, marks paper with urls_extracted = TRUE
- Critical errors (rate limits, PDF failures) do NOT mark paper as processed

Schedule: Hourly (every hour)
Dependencies: PostgreSQL, OpenRouter API, ArXiv access

Performance:
- Free tier: 50 papers/hour max (can run 1 hour/day)
- Paid tier: 50 papers/hour (sustainable 24/7 = 1,200 papers/day)
- Memory optimized for 4GB RAM systems
"""

import sys
import asyncio

from cron.utils.cron_helpers import DatabaseCronJob
from backend.config import get_settings
from backend.database.repos_and_pages_setup.batch_extract import BatchURLExtractor


class URLExtractionHourlyJob(DatabaseCronJob):
    """Hourly job to extract GitHub URLs and project pages from papers using AI."""

    def __init__(self):
        super().__init__(job_name="extract_urls_hourly", log_level="INFO")
        self.settings = get_settings()

        # Configuration for hourly runs with Gemini free tier
        # Free tier: 350 RPD (250 Flash + 100 Pro) / 24 hours = ~14 papers/hour max
        self.papers_per_hour = 14  # Conservative for Gemini free tier (350 RPD / 24)
        self.batch_size = 10  # Smaller batches for memory safety (4GB RAM)
        self.start_year = 2014  # Only process papers from 2014 onwards
        self.use_paid_tier = False  # Using Gemini free tier (350 RPD)

    def run(self):
        """Main execution logic for URL extraction."""
        self.logger.info("=" * 80)
        self.logger.info("Starting hourly GitHub URLs and Project Pages extraction")
        self.logger.info("=" * 80)
        self.logger.info("Configuration:")
        self.logger.info(f"  Papers per run: {self.papers_per_hour}")
        self.logger.info(f"  Batch size: {self.batch_size}")
        self.logger.info(f"  Start year: {self.start_year}")
        self.logger.info(f"  Rate tier: {'Paid' if self.use_paid_tier else 'Free'}")

        try:
            # Create batch extractor with hourly configuration
            extractor = BatchURLExtractor(
                batch_size=self.batch_size,
                dry_run=False,
                use_paid_tier=self.use_paid_tier,
                start_year=self.start_year,
            )

            # Run extraction asynchronously
            asyncio.run(extractor.run(limit=self.papers_per_hour))

            # Log final statistics
            stats = extractor.stats
            self.logger.info("=" * 80)
            self.logger.info("URL Extraction completed successfully")
            self.logger.info("=" * 80)
            self.logger.info(f"Papers processed: {stats['papers_processed']}")
            self.logger.info(f"Papers with GitHub: {stats['papers_with_github']}")
            self.logger.info(
                f"Papers with Project Page: {stats['papers_with_project_page']}"
            )
            self.logger.info(f"Papers with both: {stats['papers_with_both']}")
            self.logger.info(f"Papers with neither: {stats['papers_with_neither']}")
            self.logger.info(f"API errors: {stats['api_errors']}")
            self.logger.info(
                f"Papers skipped (critical errors): {stats['papers_skipped_critical_errors']}"
            )

            # Calculate success rate
            if stats["papers_processed"] > 0:
                github_rate = (
                    stats["papers_with_github"] / stats["papers_processed"] * 100
                )
                project_rate = (
                    stats["papers_with_project_page"] / stats["papers_processed"] * 100
                )
                self.logger.info(f"GitHub URL success rate: {github_rate:.1f}%")
                self.logger.info(f"Project page success rate: {project_rate:.1f}%")

            # Log estimated progress
            if stats["papers_processed"] > 0:
                daily_capacity = self.papers_per_hour * 24  # Assuming 24/7 operation
                self.logger.info(f"Daily capacity (24/7): ~{daily_capacity} papers")
                self.logger.info(
                    f"Estimated for 10K papers: {10000 / daily_capacity:.1f} days"
                )

        except Exception as e:
            self.logger.error(f"URL extraction failed: {e}")
            self.logger.error(f"Error type: {type(e).__name__}")
            import traceback

            self.logger.error(f"Traceback:\n{traceback.format_exc()}")
            raise


if __name__ == "__main__":
    job = URLExtractionHourlyJob()
    success = job.execute()
    sys.exit(0 if success else 1)
