"""
GitHub Stars Population Script

This script populates the num_stars field in the repositories table by fetching
star counts from the GitHub API using the GITHUB_TOKEN for higher rate limits.

📊 USAGE:
  # Test mode (10 repositories)
  uv run --env-file backend/keys.env backend/database/repos_and_pages_setup/populate_github_stars.py --test

  # Production mode (all repositories without star counts)
  uv run --env-file backend/keys.env backend/database/repos_and_pages_setup/populate_github_stars.py --production

  # Custom limit
  uv run --env-file backend/keys.env backend/database/repos_and_pages_setup/populate_github_stars.py --limit 100

  # Dry run (no database writes)
  uv run --env-file backend/keys.env backend/database/repos_and_pages_setup/populate_github_stars.py --dry-run

  # Force update all repositories (including those with existing star counts)
  uv run --env-file backend/keys.env backend/database/repos_and_pages_setup/populate_github_stars.py --force-update
"""

import logging
import argparse
import time
from typing import List, Dict, Optional
from pathlib import Path
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from backend.database.connection import get_database_session
from backend.config import get_settings
from sqlalchemy import text
from sqlalchemy.orm import Session

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class GitHubStarsPopulator:
    """
    Populates the num_stars field in repositories table using GitHub API.
    """

    def __init__(
        self,
        dry_run: bool = False,
        limit: Optional[int] = None,
        force_update: bool = False,
        batch_size: int = 50,
    ):
        self.settings = get_settings()
        self.dry_run = dry_run
        self.limit = limit
        self.force_update = force_update
        self.batch_size = batch_size

        # Get GitHub token from environment
        self.github_token = getattr(self.settings, "github_token", None)
        if not self.github_token:
            # Try to get it from keys.env directly
            try:
                keys_file = Path(__file__).parent.parent.parent / "keys.env"
                if keys_file.exists():
                    with open(keys_file, "r") as f:
                        for line in f:
                            if line.startswith("GITHUB_TOKEN="):
                                self.github_token = line.split("=", 1)[1].strip()
                                break
            except Exception as e:
                logger.debug(f"Could not read keys.env: {e}")

        if not self.github_token:
            raise ValueError("GITHUB_TOKEN not found in environment or keys.env file")

        # Initialize statistics
        self.stats = {
            "repos_total": 0,
            "repos_processed": 0,
            "repos_updated": 0,
            "repos_skipped_existing": 0,
            "repos_not_found": 0,
            "api_errors": 0,
            "rate_limit_hits": 0,
            "processing_errors": 0,
        }

        # Setup HTTP session with retries
        self.session = self._setup_session()

    def _setup_session(self) -> requests.Session:
        """Setup requests session with retry strategy and authentication."""
        session = requests.Session()

        # Add authentication header
        session.headers.update(
            {
                "Authorization": f"token {self.github_token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "PapersWithCode-StarsFetcher/1.0",
            }
        )

        # Setup retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        return session

    def get_repositories_to_update(self, db: Session) -> List[Dict]:
        """Get repositories that need star count updates."""
        try:
            if self.force_update:
                # Get all repositories
                query = """
                    SELECT id, owner, name, url, num_stars
                    FROM repositories
                    WHERE owner IS NOT NULL AND name IS NOT NULL
                    ORDER BY id
                """
            else:
                # Get only repositories without star counts (or with 0 stars)
                query = """
                    SELECT id, owner, name, url, num_stars
                    FROM repositories
                    WHERE owner IS NOT NULL AND name IS NOT NULL
                    AND (num_stars IS NULL OR num_stars = 0)
                    ORDER BY id
                """

            if self.limit:
                query += f" LIMIT {self.limit}"

            result = db.execute(text(query))
            repositories = [dict(row._mapping) for row in result.fetchall()]

            self.stats["repos_total"] = len(repositories)
            logger.info(f"Found {len(repositories)} repositories to process")

            return repositories

        except Exception as e:
            logger.error(f"Error fetching repositories: {e}")
            return []

    def get_github_stars(self, owner: str, name: str) -> Optional[int]:
        """Fetch star count from GitHub API."""
        try:
            url = f"https://api.github.com/repos/{owner}/{name}"

            response = self.session.get(url, timeout=10)

            # Handle rate limiting
            if response.status_code == 403 and "rate limit" in response.text.lower():
                self.stats["rate_limit_hits"] += 1
                reset_time = int(response.headers.get("X-RateLimit-Reset", 0))
                current_time = int(time.time())
                wait_time = max(reset_time - current_time, 60)  # Wait at least 1 minute

                logger.warning(f"Rate limit hit. Waiting {wait_time} seconds...")
                time.sleep(wait_time)

                # Retry the request
                response = self.session.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()
                return data.get("stargazers_count", 0)
            elif response.status_code == 404:
                logger.debug(f"Repository not found: {owner}/{name}")
                self.stats["repos_not_found"] += 1
                return 0  # Repository doesn't exist or is private
            else:
                logger.warning(
                    f"GitHub API error for {owner}/{name}: {response.status_code}"
                )
                self.stats["api_errors"] += 1
                return None

        except requests.exceptions.Timeout:
            logger.warning(f"Timeout fetching stars for {owner}/{name}")
            self.stats["api_errors"] += 1
            return None
        except Exception as e:
            logger.error(f"Error fetching stars for {owner}/{name}: {e}")
            self.stats["api_errors"] += 1
            return None

    def update_repository_stars(self, db: Session, repo_id: int, num_stars: int):
        """Update repository star count in database."""
        try:
            if self.dry_run:
                logger.info(
                    f"[DRY RUN] Would update repository {repo_id} with {num_stars} stars"
                )
                self.stats["repos_updated"] += 1
                return

            db.execute(
                text("""
                    UPDATE repositories
                    SET num_stars = :num_stars, updated_at = CURRENT_TIMESTAMP
                    WHERE id = :repo_id
                """),
                {"repo_id": repo_id, "num_stars": num_stars},
            )
            db.commit()
            self.stats["repos_updated"] += 1

        except Exception as e:
            logger.error(f"Error updating repository {repo_id}: {e}")
            db.rollback()
            self.stats["processing_errors"] += 1

    def process_repositories(self, db: Session, repositories: List[Dict]):
        """Process repositories and update star counts."""
        logger.info(
            f"Processing {len(repositories)} repositories in batches of {self.batch_size}..."
        )

        for i in range(0, len(repositories), self.batch_size):
            batch = repositories[i : i + self.batch_size]
            logger.info(
                f"Processing batch {i // self.batch_size + 1}/{(len(repositories) + self.batch_size - 1) // self.batch_size}"
            )

            for repo in batch:
                try:
                    repo_id = repo["id"]
                    owner = repo["owner"]
                    name = repo["name"]
                    current_stars = repo.get("num_stars", 0)

                    # Skip if already has stars and not forcing update
                    if not self.force_update and current_stars and current_stars > 0:
                        self.stats["repos_skipped_existing"] += 1
                        continue

                    # Fetch stars from GitHub API
                    stars = self.get_github_stars(owner, name)

                    if stars is not None:
                        # Update database
                        self.update_repository_stars(db, repo_id, stars)
                        logger.debug(f"Updated {owner}/{name}: {stars} stars")

                    self.stats["repos_processed"] += 1

                    # Progress logging
                    if self.stats["repos_processed"] % 10 == 0:
                        logger.info(
                            f"Progress: {self.stats['repos_processed']}/{len(repositories)} "
                            f"({self.stats['repos_processed'] / len(repositories) * 100:.1f}%) - "
                            f"Updated: {self.stats['repos_updated']}, "
                            f"Errors: {self.stats['api_errors']}"
                        )

                    # Small delay to be respectful to GitHub API
                    time.sleep(0.1)

                except Exception as e:
                    logger.error(
                        f"Error processing repository {repo.get('id', 'unknown')}: {e}"
                    )
                    self.stats["processing_errors"] += 1
                    continue

            # Longer delay between batches
            if i + self.batch_size < len(repositories):
                logger.info("Pausing between batches...")
                time.sleep(2)

    def check_rate_limit(self):
        """Check current GitHub API rate limit status."""
        try:
            response = self.session.get("https://api.github.com/rate_limit", timeout=10)
            if response.status_code == 200:
                data = response.json()
                core_limit = data["resources"]["core"]
                logger.info(
                    f"GitHub API Rate Limit: {core_limit['remaining']}/{core_limit['limit']} "
                    f"(resets at {time.ctime(core_limit['reset'])})"
                )
                return core_limit["remaining"]
            else:
                logger.warning(f"Could not check rate limit: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Error checking rate limit: {e}")
            return None

    def print_summary(self):
        """Print processing summary."""
        print("\n" + "=" * 80)
        print("GITHUB STARS POPULATION SUMMARY")
        print("=" * 80)

        print("\n📊 PROCESSING STATS:")
        print(f"  Total repositories found: {self.stats['repos_total']:,}")
        print(f"  Repositories processed: {self.stats['repos_processed']:,}")
        print(f"  Repositories updated: {self.stats['repos_updated']:,}")
        print(
            f"  Repositories skipped (existing stars): {self.stats['repos_skipped_existing']:,}"
        )

        print("\n🔍 API RESULTS:")
        print(f"  Repositories not found on GitHub: {self.stats['repos_not_found']:,}")
        print(f"  API errors: {self.stats['api_errors']:,}")
        print(f"  Rate limit hits: {self.stats['rate_limit_hits']:,}")
        print(f"  Processing errors: {self.stats['processing_errors']:,}")

        if self.stats["repos_processed"] > 0:
            success_rate = (
                self.stats["repos_updated"] / self.stats["repos_processed"]
            ) * 100
            print(f"  Success rate: {success_rate:.1f}%")

        mode = "DRY RUN" if self.dry_run else "PRODUCTION"
        force_mode = " (FORCE UPDATE)" if self.force_update else ""
        print(f"\n✅ MODE: {mode}{force_mode}")

        if not self.dry_run and self.stats["repos_updated"] > 0:
            print(
                f"\n🎉 Successfully updated {self.stats['repos_updated']} repositories with star counts!"
            )

        print("=" * 80)

    def run(self):
        """Run the star population process."""
        logger.info("Starting GitHub stars population...")

        # Check rate limit before starting
        remaining = self.check_rate_limit()
        if remaining is not None and remaining < 100:
            logger.warning(
                f"Low rate limit remaining: {remaining}. Consider waiting before running."
            )

        # Get database session
        db_session_gen = get_database_session()
        db = next(db_session_gen)

        try:
            # Get repositories to update
            repositories = self.get_repositories_to_update(db)
            if not repositories:
                logger.info("No repositories found to process")
                return

            # Process repositories
            self.process_repositories(db, repositories)

            # Print summary
            self.print_summary()

        except Exception as e:
            logger.error(f"Error during processing: {e}")
            raise
        finally:
            db.close()
            self.session.close()


def main():
    """Main function with argument parsing."""
    parser = argparse.ArgumentParser(
        description="Populate GitHub star counts for repositories"
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--test", action="store_true", help="Test mode (10 repositories)"
    )
    group.add_argument(
        "--production", action="store_true", help="Production mode (all repositories)"
    )
    group.add_argument(
        "--limit", type=int, help="Custom limit for number of repositories"
    )

    parser.add_argument(
        "--dry-run", action="store_true", help="Dry run (no database writes)"
    )
    parser.add_argument(
        "--force-update",
        action="store_true",
        help="Update all repositories, including those with existing star counts",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Batch size for processing (default: 50)",
    )

    args = parser.parse_args()

    # Determine limit
    limit = None
    if args.test:
        limit = 10
    elif args.limit:
        limit = args.limit

    # Create and run populator
    try:
        populator = GitHubStarsPopulator(
            dry_run=args.dry_run,
            limit=limit,
            force_update=args.force_update,
            batch_size=args.batch_size,
        )
        populator.run()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        print("\n❌ Error: GitHub token not found!")
        print("Please ensure GITHUB_TOKEN is set in your keys.env file.")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
