"""
GitHub Repository Cleanup Script

This script identifies and removes GitHub repositories from the database that return 404 errors
(repositories that definitively no longer exist). The script is ultra-conservative and ONLY
removes repositories on 404 responses to avoid any risk of removing valid repositories due
to rate limiting, temporary API issues, or private repositories.

Key features:
- Dry-run mode for safe testing
- Comprehensive logging with detailed statistics
- Memory-efficient processing for 4GB VPS environments
- Respects GitHub API rate limits
- Groups repositories by owner/name to minimize API calls
- Creates backup of removed repositories before deletion

Usage:
    # Dry run (recommended first)
    PYTHONPATH=.github/workflows uv run --env-file backend/keys.env python -m scripts.maintenance.cleanup_invalid_repositories --dry-run

    # Actual cleanup
    PYTHONPATH=.github/workflows uv run --env-file backend/keys.env python -m scripts.maintenance.cleanup_invalid_repositories

    # Process only specific number of repositories
    PYTHONPATH=.github/workflows uv run --env-file backend/keys.env python -m scripts.maintenance.cleanup_invalid_repositories --limit 100

Dependencies: PostgreSQL, GitHub API token
"""

import sys
import time
import gc
import os
import json
import argparse
from datetime import datetime
from typing import Optional, List, Dict, Tuple
import requests
from psycopg2.extras import RealDictCursor

from scripts.utils.cron_helpers import DatabaseCronJob


class GitHubRepositoryCleanup(DatabaseCronJob):
    """Clean up invalid GitHub repositories from the database."""

    def __init__(self, dry_run: bool = True, limit: Optional[int] = None):
        super().__init__(job_name="cleanup_invalid_repositories", log_level="INFO")
        self.dry_run = dry_run
        self.limit = limit
        self.github_token = os.getenv("PWC_GITHUB_TOKEN")
        self.backup_file = f".github/workflows/scripts/logs/removed_repositories_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        self.processed_file = f".github/workflows/scripts/logs/processed_repositories_{datetime.now().strftime('%Y%m%d')}.txt"
        self.processed_repos = self.load_processed_repos()

        # Statistics
        self.stats = {
            "total_unique_repos": 0,
            "checked_repos": 0,
            "invalid_repos": 0,
            "removed_repo_urls": 0,
            "api_calls": 0,
            "api_errors": 0,
            "rate_limit_hits": 0,
        }

        if not self.github_token:
            self.logger.error("PWC_GITHUB_TOKEN environment variable not set")
            sys.exit(1)

        mode = "DRY RUN" if self.dry_run else "LIVE MODE"
        self.logger.info(f"Initialized GitHub Repository Cleanup - {mode}")
        if self.limit:
            self.logger.info(f"Processing limit: {self.limit} unique repositories")
        self.logger.info(
            "Rate limiting: 2.5s delays (conservative due to shared GitHub token)"
        )
        self.logger.info(
            f"Processed repos tracking: {len(self.processed_repos)} already checked today"
        )

    def load_processed_repos(self) -> set:
        """Load the set of already processed repositories from today's file."""
        try:
            if os.path.exists(self.processed_file):
                with open(self.processed_file, "r") as f:
                    return set(line.strip() for line in f if line.strip())
            return set()
        except Exception as e:
            self.logger.warning(f"Could not load processed repos file: {e}")
            return set()

    def save_processed_repo(self, owner: str, name: str):
        """Save a processed repository to the tracking file."""
        repo_key = f"{owner}/{name}"
        if repo_key not in self.processed_repos:
            self.processed_repos.add(repo_key)
            try:
                # Ensure directory exists
                os.makedirs(os.path.dirname(self.processed_file), exist_ok=True)
                with open(self.processed_file, "a") as f:
                    f.write(f"{repo_key}\n")
            except Exception as e:
                self.logger.warning(f"Could not save processed repo {repo_key}: {e}")

    def is_already_processed(self, owner: str, name: str) -> bool:
        """Check if a repository has already been processed today."""
        return f"{owner}/{name}" in self.processed_repos

    def run(self):
        """Main execution logic."""
        try:
            self.logger.info("Starting GitHub repository cleanup")

            # Get total count first
            total_count = self.get_total_unique_repositories()
            self.stats["total_unique_repos"] = total_count
            self.logger.info(f"Total unique repositories in database: {total_count}")

            if total_count == 0:
                self.logger.info("No repositories found to process")
                return

            # Process repositories
            self.process_repositories()

            # Log final statistics
            self.log_final_statistics()

        except Exception as e:
            self.logger.error(f"Repository cleanup failed: {e}")
            raise

    def get_total_unique_repositories(self) -> int:
        """Get total count of unique repositories (by owner/name)."""
        query = """
        SELECT COUNT(DISTINCT (owner, name))
        FROM repositories
        WHERE owner IS NOT NULL
          AND name IS NOT NULL
          AND owner != ''
          AND name != ''
          AND url LIKE 'https://github.com/%'
        """

        with self.get_database_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query)
                return cursor.fetchone()[0]

    def get_next_repository_group(self) -> Optional[Dict]:
        """Get the next unique repository group to check, excluding already processed ones."""
        query = """
        SELECT
            owner,
            name,
            ARRAY_AGG(id ORDER BY id) as repository_ids,
            ARRAY_AGG(url ORDER BY id) as urls,
            COUNT(*) as url_count,
            MIN(created_at) as first_added,
            MAX(num_stars) as max_stars
        FROM repositories
        WHERE owner IS NOT NULL
          AND name IS NOT NULL
          AND owner != ''
          AND name != ''
          AND url LIKE 'https://github.com/%'
        GROUP BY owner, name
        ORDER BY
            MAX(num_stars) ASC,  -- Check low-star repos first (more likely to be invalid)
            MIN(created_at) ASC  -- Then older repos
        LIMIT 1
        """

        with self.get_database_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query)
                result = cursor.fetchone()
                return dict(result) if result else None

    def check_repository_exists(
        self, owner: str, name: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if a GitHub repository exists and is accessible.

        Returns:
            Tuple of (exists, error_reason)
            - exists: True if repo is accessible, False if 404/403/etc
            - error_reason: Description of why repo is not accessible (if exists=False)
        """
        url = f"https://api.github.com/repos/{owner}/{name}"

        headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "PapersWithCode-Cleanup/1.0",
        }

        try:
            self.stats["api_calls"] += 1
            response = requests.get(url, headers=headers, timeout=15)

            # Check rate limit headers first - this is critical for safety
            rate_limit_remaining = response.headers.get("X-RateLimit-Remaining")
            rate_limit_reset = response.headers.get("X-RateLimit-Reset")

            if rate_limit_remaining is not None:
                remaining = int(rate_limit_remaining)
                if remaining < 10:  # Very close to rate limit
                    self.logger.warning(
                        f"Rate limit nearly exhausted: {remaining} requests remaining"
                    )
                    if remaining == 0:
                        reset_time = int(rate_limit_reset) if rate_limit_reset else 3600
                        wait_time = max(
                            60, reset_time - int(time.time()) + 10
                        )  # Wait until reset + 10s buffer
                        self.logger.warning(
                            f"Rate limit exhausted, waiting {wait_time} seconds"
                        )
                        time.sleep(wait_time)

            if response.status_code == 200:
                return True, None
            elif response.status_code == 404:
                return False, "Repository not found (404)"
            elif response.status_code == 403:
                # CRITICAL: Be very careful with 403 responses
                response_text = response.text.lower()

                # Check for explicit rate limit indicators
                rate_limit_indicators = [
                    "rate limit exceeded",
                    "api rate limit",
                    "rate_limit_exceeded",
                    "rate limit",
                    "too many requests",
                ]

                is_rate_limit = any(
                    indicator in response_text for indicator in rate_limit_indicators
                )

                # Also check if we have 0 remaining requests
                if rate_limit_remaining == "0":
                    is_rate_limit = True

                if is_rate_limit:
                    self.logger.warning(
                        f"Rate limit detected for {owner}/{name} - preserving repository"
                    )
                    self.stats["rate_limit_hits"] += 1
                    # Wait longer for rate limit recovery
                    wait_time = (
                        300
                        if rate_limit_reset is None
                        else max(300, int(rate_limit_reset) - int(time.time()) + 60)
                    )
                    self.logger.info(
                        f"Waiting {wait_time} seconds for rate limit recovery"
                    )
                    time.sleep(wait_time)
                    return True, None  # NEVER delete on rate limit
                else:
                    # This might be a private repository or other access issue
                    # But let's be extra cautious and NOT delete it
                    self.logger.info(
                        f"403 response for {owner}/{name} - preserving repository (could be private)"
                    )
                    return True, None  # CONSERVATIVE: Don't delete on any 403

            elif response.status_code == 451:
                # Even for 451 (legal reasons), let's be conservative and not delete
                # The repository might become available again
                self.logger.info(
                    f"451 response for {owner}/{name} - preserving repository (legal reasons)"
                )
                return True, None  # CONSERVATIVE: Don't delete on 451 either
            else:
                self.logger.warning(
                    f"Unexpected API response {response.status_code} for {owner}/{name}"
                )
                self.stats["api_errors"] += 1
                return True, None  # Don't delete on unknown errors

        except Exception as e:
            self.logger.warning(f"API error for {owner}/{name}: {e}")
            self.stats["api_errors"] += 1
            return True, None  # Don't delete on API errors
        finally:
            gc.collect()

    def backup_repositories(self, repository_data: List[Dict]):
        """Backup repository data before deletion."""
        if not repository_data:
            return

        backup_entry = {
            "timestamp": datetime.now().isoformat(),
            "dry_run": self.dry_run,
            "repositories": repository_data,
        }

        # Ensure backup directory exists
        os.makedirs(os.path.dirname(self.backup_file), exist_ok=True)

        # Append to backup file
        try:
            if os.path.exists(self.backup_file):
                with open(self.backup_file, "r") as f:
                    existing_data = json.load(f)
                if not isinstance(existing_data, list):
                    existing_data = [existing_data]
            else:
                existing_data = []

            existing_data.append(backup_entry)

            with open(self.backup_file, "w") as f:
                json.dump(existing_data, f, indent=2, default=str)

            self.logger.info(
                f"Backed up {len(repository_data)} repositories to {self.backup_file}"
            )

        except Exception as e:
            self.logger.error(f"Failed to backup repositories: {e}")

    def remove_repository_group(
        self, repository_ids: List[int], owner: str, name: str, reason: str
    ) -> int:
        """
        Remove all repository URLs for a given owner/name group.

        Returns number of repositories removed.
        """
        if self.dry_run:
            self.logger.info(
                f"DRY RUN: Would remove {len(repository_ids)} URLs for {owner}/{name} - {reason}"
            )
            return len(repository_ids)

        # First, get the repository data for backup
        backup_query = """
        SELECT id, url, owner, name, num_stars, is_official, source, created_at, updated_at
        FROM repositories
        WHERE id = ANY(%s)
        """

        repository_data = []
        with self.get_database_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(backup_query, (repository_ids,))
                repository_data = [dict(row) for row in cursor.fetchall()]

        # Add removal reason to backup data
        for repo in repository_data:
            repo["removal_reason"] = reason
            repo["removed_at"] = datetime.now().isoformat()

        # Backup before deletion
        self.backup_repositories(repository_data)

        # Delete repositories
        delete_query = """
        DELETE FROM repositories
        WHERE id = ANY(%s)
        """

        try:
            with self.get_database_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(delete_query, (repository_ids,))
                    removed_count = cursor.rowcount
                    conn.commit()

                    self.logger.info(
                        f"Removed {removed_count} repository URLs for {owner}/{name} - {reason}"
                    )
                    return removed_count

        except Exception as e:
            self.logger.error(f"Failed to remove repositories for {owner}/{name}: {e}")
            return 0

    def process_repositories(self):
        """Process repositories and remove invalid ones."""
        processed = 0
        start_time = time.time()
        max_runtime = 50 * 60  # 50 minutes max

        self.logger.info("Starting repository processing...")

        while True:
            # Check runtime limit
            if time.time() - start_time > max_runtime:
                self.logger.info("Runtime limit reached - stopping")
                break

            # Check processing limit
            if self.limit and processed >= self.limit:
                self.logger.info(f"Processing limit ({self.limit}) reached")
                break

            # Check memory
            if not self.check_memory_available():
                break

            # Get next repository group
            repo_group = self.get_next_repository_group()
            if not repo_group:
                self.logger.info("No more repositories to process")
                break

            owner = repo_group["owner"]
            name = repo_group["name"]
            repository_ids = repo_group["repository_ids"]
            url_count = repo_group["url_count"]
            max_stars = repo_group.get("max_stars", 0)

            # Skip if already processed today
            if self.is_already_processed(owner, name):
                self.logger.debug(
                    f"Skipping already processed repository {owner}/{name}"
                )
                continue

            # Check if repository exists
            exists, error_reason = self.check_repository_exists(owner, name)

            # Mark as processed regardless of result
            self.save_processed_repo(owner, name)

            self.stats["checked_repos"] += 1

            if not exists:
                # Repository is invalid - remove it
                self.stats["invalid_repos"] += 1
                removed_count = self.remove_repository_group(
                    repository_ids, owner, name, error_reason
                )
                self.stats["removed_repo_urls"] += removed_count

                self.logger.warning(
                    f"Invalid repository {owner}/{name} ({url_count} URLs, {max_stars} stars): {error_reason}"
                )
            else:
                self.logger.debug(
                    f"Valid repository {owner}/{name} ({url_count} URLs, {max_stars} stars)"
                )

            processed += 1

            # Progress update every 25 repositories
            if processed % 25 == 0:
                elapsed = (time.time() - start_time) / 60
                invalid_rate = (
                    self.stats["invalid_repos"] / self.stats["checked_repos"]
                ) * 100
                self.logger.info(
                    f"Progress: {processed} unique repos checked, "
                    f"{self.stats['invalid_repos']} invalid ({invalid_rate:.1f}%), "
                    f"{self.stats['removed_repo_urls']} URLs removed, "
                    f"{elapsed:.1f}min elapsed"
                )

            # Rate limiting - be conservative due to shared token with stars update job
            # Stars update job uses ~3000 calls/hour, so we use longer delays
            time.sleep(2.5)  # 2.5 seconds between requests (~1440 calls/hour max)

            # Garbage collection every 10 repositories
            if processed % 10 == 0:
                gc.collect()

    def check_memory_available(self) -> bool:
        """Check if sufficient memory is available."""
        try:
            with open("/proc/meminfo", "r") as f:
                meminfo = f.read()

            for line in meminfo.split("\n"):
                if "MemAvailable:" in line:
                    available_kb = int(line.split()[1])
                    available_mb = available_kb // 1024

                    if available_mb < 200:  # Less than 200MB available
                        self.logger.warning(
                            f"Low memory ({available_mb}MB) - stopping to prevent OOM"
                        )
                        return False
                    return True
        except:  # noqa: E722
            return True  # Default to continue if can't check memory

    def log_final_statistics(self):
        """Log comprehensive final statistics."""
        self.logger.info("=== CLEANUP STATISTICS ===")
        self.logger.info(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE CLEANUP'}")
        self.logger.info(
            f"Total unique repositories in database: {self.stats['total_unique_repos']}"
        )
        self.logger.info(f"Unique repositories checked: {self.stats['checked_repos']}")
        self.logger.info(f"Invalid repositories found: {self.stats['invalid_repos']}")
        self.logger.info(f"Repository URLs removed: {self.stats['removed_repo_urls']}")
        self.logger.info(f"API calls made: {self.stats['api_calls']}")
        self.logger.info(f"API errors encountered: {self.stats['api_errors']}")
        self.logger.info(f"Rate limit hits: {self.stats['rate_limit_hits']}")

        if self.stats["checked_repos"] > 0:
            invalid_rate = (
                self.stats["invalid_repos"] / self.stats["checked_repos"]
            ) * 100
            self.logger.info(f"Invalid repository rate: {invalid_rate:.2f}%")

        if not self.dry_run and self.stats["removed_repo_urls"] > 0:
            self.logger.info(f"Backup file created: {self.backup_file}")

        self.logger.info("=== END STATISTICS ===")


def main():
    """Main entry point with argument parsing."""
    parser = argparse.ArgumentParser(description="Clean up invalid GitHub repositories")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Run in dry-run mode (default: True)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run in live mode (actually remove repositories)",
    )
    parser.add_argument(
        "--limit", type=int, help="Limit number of unique repositories to process"
    )

    args = parser.parse_args()

    # If --live is specified, disable dry-run
    dry_run = not args.live

    try:
        cleanup = GitHubRepositoryCleanup(dry_run=dry_run, limit=args.limit)
        cleanup.execute()
    except KeyboardInterrupt:
        print("\nCleanup interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Cleanup failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
