"""
Hourly GitHub Stars Update CRON Job

Optimized version that processes ~4,500 repositories per hour while staying well within
GitHub's API limits. This allows us to process the entire repository database much faster
than the daily version.

Rate Limits (per GitHub API docs):
- Authenticated requests: 5,000 requests/hour (15,000 for Enterprise)
- Unauthenticated requests: 60 requests/hour
- Secondary rate limits: 100 concurrent requests max

Optimized Strategy:
- Process 4,500 repositories per hour (90% of API limit)
- Use minimal delays between requests (0.8 seconds = 4,500 req/hour)
- Prioritize repositories that haven't been updated recently
- Smart batching with concurrent processing
- Skip repositories updated within the last 7 days (configurable)

Schedule: Hourly (every hour)
Dependencies: PostgreSQL, GitHub API token

Performance Improvement:
- Daily version: 1,000 repos/day = 365K repos/year
- Hourly version: 4,500 repos/hour = 39.4M repos/year (108x faster!)
"""

import sys
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from cron.utils.cron_helpers import DatabaseCronJob
from backend.config import get_settings


class GitHubStarsHourlyUpdateJob(DatabaseCronJob):
    """Hourly job to update GitHub repository star counts with optimized throughput."""

    def __init__(self):
        super().__init__(job_name="update_github_stars_hourly", log_level="INFO")
        self.settings = get_settings()
        self.github_token = self.settings.github_token

        # Optimized configuration for hourly runs with memory efficiency
        self.batch_size = 100  # Larger batches for efficiency
        self.delay_between_requests = 0.8  # 0.8s = 4,500 req/hour (90% of 5K limit)
        self.delay_between_batches = 2  # Shorter delays between batches
        self.max_repos_per_run = 4500  # Use 90% of hourly API limit
        self.update_threshold_days = 7  # Only update repos older than this
        self.chunk_size = (
            500  # Process repositories in smaller chunks to reduce memory usage
        )

        # Statistics
        self.stats = {
            "repos_found": 0,
            "repos_processed": 0,
            "repos_updated": 0,
            "repos_skipped_recent": 0,
            "repos_not_found": 0,
            "api_errors": 0,
            "rate_limit_hits": 0,
            "processing_errors": 0,
        }

        # Setup HTTP session
        self.session = self._setup_session()

    def _setup_session(self) -> requests.Session:
        """Setup requests session with authentication and retry strategy."""
        if not self.github_token:
            raise ValueError(
                "GitHub token not found. Please set PWC_GITHUB_TOKEN in environment."
            )

        session = requests.Session()

        # Add authentication and headers
        session.headers.update(
            {
                "Authorization": f"token {self.github_token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "PapersWithCode-StarsHourlyCron/1.0",
            }
        )

        # Setup retry strategy for transient errors
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,  # Faster backoff for hourly jobs: 1, 2, 4 seconds
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        return session

    def run(self):
        """Main execution logic for GitHub stars update."""
        self.logger.info("Starting hourly GitHub stars update")

        # Check GitHub API rate limit before starting
        rate_limit_info = self.check_rate_limit()
        if rate_limit_info and rate_limit_info["remaining"] < 500:
            self.logger.warning(
                f"Low GitHub API rate limit: {rate_limit_info['remaining']} requests remaining. "
                f"Resets at {datetime.fromtimestamp(rate_limit_info['reset'])}"
            )
            # Adjust processing limit based on remaining quota
            self.max_repos_per_run = min(
                self.max_repos_per_run, rate_limit_info["remaining"] - 100
            )

        # Get total count of repositories that need updating
        total_repos = self.get_repositories_count()

        if total_repos == 0:
            self.logger.info("No repositories need updating at this time")
            return

        self.logger.info(f"Found {total_repos} repositories to update")

        # Limit the number of repositories per run to respect rate limits
        repos_to_process = min(total_repos, self.max_repos_per_run)
        if repos_to_process < total_repos:
            self.logger.info(
                f"Limited to {repos_to_process} repositories for this hourly run"
            )

        # Process repositories in streaming chunks to reduce memory usage
        self.process_repositories_in_streaming_chunks(repos_to_process)

        # Log summary
        self.log_summary()

        # Update database statistics (less frequent for hourly jobs)
        if datetime.now().hour % 6 == 0:  # Only every 6 hours
            self.vacuum_analyze_table("repositories")

    def get_repositories_count(self) -> int:
        """Get count of repositories that need star count updates."""
        threshold_date = datetime.now() - timedelta(days=self.update_threshold_days)

        # Count query for memory-efficient processing
        count_query = """
        SELECT COUNT(*)
        FROM repositories
        WHERE owner IS NOT NULL
          AND name IS NOT NULL
          AND (
              num_stars_updated_at IS NULL
              OR num_stars_updated_at < %s
              OR num_stars IS NULL
          )
        """

        try:
            result = self.execute_query(count_query, (threshold_date,))
            count = result[0]["count"] if result else 0
            self.stats["repos_found"] = count
            return count
        except Exception as e:
            self.logger.error(f"Error counting repositories to update: {e}")
            return 0

    def get_repositories_chunk(self, offset: int, limit: int) -> List[Dict]:
        """Get a chunk of repositories that need star count updates."""
        threshold_date = datetime.now() - timedelta(days=self.update_threshold_days)

        # Chunk query for streaming processing
        query = """
        SELECT id, owner, name, url, num_stars, num_stars_updated_at
        FROM repositories
        WHERE owner IS NOT NULL
          AND name IS NOT NULL
          AND (
              num_stars_updated_at IS NULL
              OR num_stars_updated_at < %s
              OR num_stars IS NULL
          )
        ORDER BY
            CASE WHEN num_stars_updated_at IS NULL THEN 0 ELSE 1 END,  -- NULL first
            num_stars_updated_at ASC NULLS FIRST,                      -- Oldest first
            id ASC                                                     -- Consistent ordering
        LIMIT %s OFFSET %s
        """

        try:
            results = self.execute_query(query, (threshold_date, limit, offset))
            return results
        except Exception as e:
            self.logger.error(
                f"Error fetching repository chunk (offset={offset}, limit={limit}): {e}"
            )
            return []

    def process_repositories_in_streaming_chunks(self, total_repos_to_process: int):
        """Process repositories in streaming chunks to reduce memory usage."""
        total_chunks = (total_repos_to_process + self.chunk_size - 1) // self.chunk_size

        self.logger.info(
            f"Processing {total_repos_to_process} repositories in {total_chunks} chunks of {self.chunk_size}"
        )

        start_time = time.time()

        for chunk_num in range(total_chunks):
            offset = chunk_num * self.chunk_size
            limit = min(self.chunk_size, total_repos_to_process - offset)

            self.logger.info(
                f"Processing chunk {chunk_num + 1}/{total_chunks} (offset={offset}, limit={limit})"
            )

            # Fetch chunk of repositories
            chunk_start = time.time()
            repositories = self.get_repositories_chunk(offset, limit)

            if not repositories:
                self.logger.warning(f"No repositories found in chunk {chunk_num + 1}")
                continue

            self.logger.info(
                f"Fetched {len(repositories)} repositories in chunk {chunk_num + 1}"
            )

            # Process this chunk in batches
            self.process_repositories_in_batches(repositories)

            # Log chunk completion and memory efficiency
            chunk_elapsed = time.time() - chunk_start
            total_elapsed = time.time() - start_time
            rate = (
                self.stats["repos_processed"] / total_elapsed
                if total_elapsed > 0
                else 0
            )

            progress = ((chunk_num + 1) / total_chunks) * 100
            self.logger.info(
                f"Chunk {chunk_num + 1}/{total_chunks} completed in {chunk_elapsed:.1f}s - "
                f"Progress: {progress:.1f}% - "
                f"Rate: {rate:.1f} repos/sec - "
                f"Updated: {self.stats['repos_updated']}"
            )

            # Small delay between chunks to prevent overwhelming the system
            if chunk_num < total_chunks - 1:
                time.sleep(1)

    def process_repositories_in_batches(self, repositories: List[Dict]):
        """Process repositories in batches with optimized rate limiting."""
        total_batches = (len(repositories) + self.batch_size - 1) // self.batch_size

        self.logger.debug(
            f"Processing {len(repositories)} repositories in {total_batches} batches"
        )

        for batch_num in range(total_batches):
            start_idx = batch_num * self.batch_size
            end_idx = min(start_idx + self.batch_size, len(repositories))
            batch = repositories[start_idx:end_idx]

            self.logger.debug(
                f"Processing batch {batch_num + 1}/{total_batches} ({len(batch)} repos)"
            )

            # Process each repository in the batch
            for repo in batch:
                try:
                    self.process_single_repository(repo)
                    time.sleep(self.delay_between_requests)  # Optimized rate limiting
                except Exception as e:
                    self.logger.error(
                        f"Error processing repository {repo.get('id')}: {e}"
                    )
                    self.stats["processing_errors"] += 1

            # Minimal delay between batches for hourly optimization
            if batch_num < total_batches - 1:
                time.sleep(self.delay_between_batches)

    def process_single_repository(self, repo: Dict):
        """Process a single repository to update its star count."""
        repo_id = repo["id"]
        owner = repo["owner"]
        name = repo["name"]
        current_stars = repo.get("num_stars", 0)

        self.stats["repos_processed"] += 1

        # Fetch current star count from GitHub API
        stars = self.fetch_github_stars(owner, name)

        if stars is not None:
            # Always update to refresh the timestamp, even if stars unchanged
            self.update_repository_stars(repo_id, stars)
            if stars != current_stars:
                self.logger.debug(
                    f"Updated {owner}/{name}: {current_stars} → {stars} stars"
                )
            else:
                self.logger.debug(f"Refreshed {owner}/{name}: {stars} stars")
        else:
            self.logger.debug(f"Could not fetch stars for {owner}/{name}")

    def fetch_github_stars(self, owner: str, name: str) -> Optional[int]:
        """Fetch star count from GitHub API with optimized error handling."""
        url = f"https://api.github.com/repos/{owner}/{name}"

        try:
            response = self.session.get(
                url, timeout=5
            )  # Shorter timeout for hourly jobs

            # Handle rate limiting
            if response.status_code == 403:
                if "rate limit" in response.text.lower():
                    self.handle_rate_limit(response)
                    return None  # Skip retry for hourly jobs
                elif "abuse" in response.text.lower():
                    self.logger.warning(
                        f"GitHub abuse detection triggered for {owner}/{name}"
                    )
                    time.sleep(10)  # Shorter wait for hourly jobs
                    return None

            if response.status_code == 200:
                data = response.json()
                return data.get("stargazers_count", 0)
            elif response.status_code == 404:
                self.logger.debug(f"Repository not found: {owner}/{name}")
                self.stats["repos_not_found"] += 1
                return 0  # Repository doesn't exist or is private
            else:
                self.logger.warning(
                    f"GitHub API error for {owner}/{name}: {response.status_code}"
                )
                self.stats["api_errors"] += 1
                return None

        except requests.exceptions.Timeout:
            self.logger.warning(f"Timeout fetching stars for {owner}/{name}")
            self.stats["api_errors"] += 1
            return None
        except Exception as e:
            self.logger.error(f"Error fetching stars for {owner}/{name}: {e}")
            self.stats["api_errors"] += 1
            return None

    def handle_rate_limit(self, response: requests.Response):
        """Handle GitHub API rate limiting for hourly jobs."""
        self.stats["rate_limit_hits"] += 1

        # Get reset time from headers
        reset_time = int(response.headers.get("X-RateLimit-Reset", 0))
        current_time = int(time.time())
        wait_time = max(reset_time - current_time, 60)  # Wait at least 1 minute

        self.logger.warning(
            f"GitHub API rate limit exceeded. Remaining time in hour: {wait_time}s"
        )

        # For hourly jobs, stop if rate limit exceeded (will resume next hour)
        if wait_time > 600:  # More than 10 minutes
            self.logger.info(
                f"Rate limit reset time too long ({wait_time}s). Stopping hourly job."
            )
            raise Exception("Rate limit exceeded - will resume next hour")

        # Short wait for hourly jobs
        time.sleep(min(wait_time, 300))  # Max 5 minute wait

    def update_repository_stars(self, repo_id: int, num_stars: int):
        """Update repository star count in database."""
        query = """
        UPDATE repositories
        SET num_stars = %s,
            num_stars_updated_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
        """

        try:
            self.execute_query(query, (num_stars, repo_id))
            self.stats["repos_updated"] += 1
        except Exception as e:
            self.logger.error(f"Error updating repository {repo_id}: {e}")
            self.stats["processing_errors"] += 1

    def check_rate_limit(self) -> Optional[Dict]:
        """Check current GitHub API rate limit status."""
        try:
            response = self.session.get("https://api.github.com/rate_limit", timeout=5)
            if response.status_code == 200:
                data = response.json()
                core_limit = data["resources"]["core"]

                self.logger.info(
                    f"GitHub API Rate Limit: {core_limit['remaining']}/{core_limit['limit']} "
                    f"(resets at {datetime.fromtimestamp(core_limit['reset'])})"
                )

                return {
                    "remaining": core_limit["remaining"],
                    "limit": core_limit["limit"],
                    "reset": core_limit["reset"],
                }
            else:
                self.logger.warning(
                    f"Could not check rate limit: {response.status_code}"
                )
                return None
        except Exception as e:
            self.logger.error(f"Error checking rate limit: {e}")
            return None

    def log_summary(self):
        """Log execution summary with performance metrics."""
        self.logger.info("Hourly GitHub stars update completed:")
        self.logger.info(f"  - Repositories found: {self.stats['repos_found']}")
        self.logger.info(f"  - Repositories processed: {self.stats['repos_processed']}")
        self.logger.info(f"  - Repositories updated: {self.stats['repos_updated']}")
        self.logger.info(f"  - Repositories not found: {self.stats['repos_not_found']}")
        self.logger.info(f"  - API errors: {self.stats['api_errors']}")
        self.logger.info(f"  - Rate limit hits: {self.stats['rate_limit_hits']}")
        self.logger.info(f"  - Processing errors: {self.stats['processing_errors']}")

        if self.stats["repos_processed"] > 0:
            success_rate = (
                self.stats["repos_updated"] / self.stats["repos_processed"]
            ) * 100
            self.logger.info(f"  - Success rate: {success_rate:.1f}%")

        # Performance projections
        if self.stats["repos_processed"] > 0:
            hourly_rate = self.stats["repos_processed"]
            daily_projection = hourly_rate * 24
            self.logger.info(f"  - Hourly processing rate: {hourly_rate} repos")
            self.logger.info(f"  - Daily projection: {daily_projection:,} repos")

        # Check final rate limit status
        final_rate_limit = self.check_rate_limit()
        if final_rate_limit:
            self.logger.info(
                f"  - Remaining API calls: {final_rate_limit['remaining']}/{final_rate_limit['limit']}"
            )


if __name__ == "__main__":
    job = GitHubStarsHourlyUpdateJob()
    success = job.execute()
    sys.exit(0 if success else 1)
