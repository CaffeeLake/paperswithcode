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
import signal

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

        # Timeout protection (2 hours max - should complete in < 30 minutes normally)
        self.max_runtime_seconds = 2 * 60 * 60
        self.shutdown_requested = False

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        signal_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
        self.logger.warning(f"Received {signal_name} - initiating graceful shutdown")
        self.shutdown_requested = True

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

        # Validate Gemini API key before proceeding
        gemini_api_key = self.settings.gemini_api_key
        openrouter_api_key = self.settings.openrouter_api_key
        if not gemini_api_key and not openrouter_api_key:
            self.logger.error(
                "❌ CRITICAL: Neither PWC_GEMINI_API_KEY nor PWC_OPENROUTER_API_KEY is set in keys.env"
            )
            self.logger.error(
                "   URL extraction requires at least one valid API key (Gemini or OpenRouter)"
            )
            raise ValueError("No LLM API key configured")

        self.logger.info(
            f"  Gemini API Key: {'✓ Configured' if gemini_api_key else '✗ Missing'}"
        )
        self.logger.info(
            f"  OpenRouter API Key: {'✓ Configured' if openrouter_api_key else '✗ Missing'}"
        )

        try:
            # Create batch extractor with hourly configuration
            extractor = BatchURLExtractor(
                batch_size=self.batch_size,
                dry_run=False,
                use_paid_tier=self.use_paid_tier,
                start_year=self.start_year,
            )

            # Run extraction asynchronously with timeout protection
            try:
                asyncio.run(
                    asyncio.wait_for(
                        extractor.run(limit=self.papers_per_hour),
                        timeout=self.max_runtime_seconds,
                    )
                )
            except asyncio.TimeoutError:
                self.logger.error(
                    f"Job timed out after {self.max_runtime_seconds}s - "
                    f"this prevents zombie processes"
                )
                # Don't raise - let it complete gracefully
                stats = extractor.stats if hasattr(extractor, "stats") else {}
            except KeyboardInterrupt:
                self.logger.warning("Job interrupted by user")
                stats = extractor.stats if hasattr(extractor, "stats") else {}
            else:
                # Normal completion
                stats = extractor.stats

            # Log final statistics
            self.logger.info("=" * 80)

            # Check for API key failures before logging completion
            papers_found = stats.get("papers_found", 0)
            papers_processed = stats.get("papers_processed", 0)
            papers_skipped_critical = stats.get("papers_skipped_critical_errors", 0)

            # Detect API key failures: if we found papers but all failed with critical errors
            if (
                papers_found > 0
                and papers_processed == 0
                and papers_skipped_critical > 0
            ):
                error_msg = (
                    f"URL extraction FAILED: Found {papers_found} papers but processed 0 "
                    f"due to {papers_skipped_critical} critical errors (likely invalid API keys)"
                )
                self.logger.error("=" * 80)
                self.logger.error(error_msg)
                self.logger.error("=" * 80)
                self.logger.error("This usually indicates:")
                self.logger.error("  1. Invalid or expired Gemini/OpenRouter API keys")
                self.logger.error("  2. API quota exceeded")
                self.logger.error("  3. Network/authentication issues")
                raise RuntimeError(error_msg)

            # Normal completion logging
            if papers_processed > 0:
                self.logger.info("URL Extraction completed successfully")
            elif papers_found == 0:
                self.logger.info("URL Extraction completed (no papers to process)")
            else:
                # Edge case: papers found but processed 0 without critical errors
                self.logger.warning(
                    f"URL Extraction completed but processed 0 papers "
                    f"(found {papers_found}, skipped {papers_skipped_critical} critical errors)"
                )

            self.logger.info("=" * 80)
            if "papers_found" in stats:
                self.logger.info(f"Papers found: {stats['papers_found']}")
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
