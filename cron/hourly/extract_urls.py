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

    async def _validate_api_keys(self):
        """Validate API keys by making test requests.

        Raises:
            ValueError: If no API key is configured or if the configured key is invalid
        """
        from backend.generators.google_generator import GoogleGenerator
        from backend.models.generators import Message

        gemini_api_key = self.settings.gemini_api_key

        # Check if Gemini API key is configured (we're not using OpenRouter fallback)
        if not gemini_api_key:
            raise ValueError(
                "No Gemini API key configured. URL extraction requires PWC_GEMINI_API_KEY in keys.env"
            )

        self.logger.info("Validating Gemini API key with test request...")

        try:
            # Create a test generator with minimal rate limits
            test_generator = GoogleGenerator(
                requests_per_minute=10, requests_per_day=350
            )

            # Make a minimal test request
            test_messages = [Message(role="user", content="Respond with just 'OK'")]

            response, model_name = await test_generator.generate(test_messages)

            if response:
                self.logger.info(
                    f"✓ Gemini API key validation successful (model: {model_name})"
                )
            else:
                raise ValueError("Gemini API returned empty response")

        except Exception as e:
            error_str = str(e).lower()

            # Check for authentication-related errors
            auth_markers = [
                "api key",
                "invalid_api_key",
                "api_key_invalid",
                "expired",
                "unauthorized",
                "forbidden",
                "permission",
                "not authenticated",
                "unauthenticated",
                "invalid authentication",
                "key not active",
                "insufficient authentication",
            ]

            is_auth_error = any(marker in error_str for marker in auth_markers)

            if is_auth_error:
                raise ValueError(
                    f"Gemini API key validation FAILED: Invalid or expired API key. "
                    f"Please check PWC_GEMINI_API_KEY in keys.env. Error: {e}"
                ) from e
            else:
                # Other errors (network, quota, etc.)
                raise ValueError(
                    f"Gemini API key validation FAILED: {e}. "
                    f"This may be a temporary issue (network, quota exceeded, etc.)"
                ) from e

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

        # Validate Gemini API key with test request before proceeding
        try:
            asyncio.run(self._validate_api_keys())
        except ValueError as e:
            self.logger.error("=" * 80)
            self.logger.error("❌ CRITICAL: API Key Validation Failed")
            self.logger.error("=" * 80)
            self.logger.error(str(e))
            self.logger.error("=" * 80)
            self.logger.error("URL extraction cannot proceed without a valid API key.")
            self.logger.error("Please update PWC_GEMINI_API_KEY in backend/keys.env")
            raise

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
                    f"due to {papers_skipped_critical} critical errors"
                )
                self.logger.error("=" * 80)
                self.logger.error(error_msg)
                self.logger.error("=" * 80)
                self.logger.error("This usually indicates one of the following issues:")
                self.logger.error(
                    "  1. Invalid or expired Gemini API key (PWC_GEMINI_API_KEY)"
                )
                self.logger.error("     - Check that the key is valid and active")
                self.logger.error("     - Verify you haven't exceeded your API quota")
                self.logger.error(
                    "  2. API quota exceeded for the current billing period"
                )
                self.logger.error("  3. Network connectivity or authentication issues")
                self.logger.error("")
                self.logger.error("Action required:")
                self.logger.error(
                    "  - Update PWC_GEMINI_API_KEY in backend/keys.env with a valid key"
                )
                self.logger.error("  - Check your Google Cloud Console for API status")
                self.logger.error("  - Verify billing is enabled if using paid tier")
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
