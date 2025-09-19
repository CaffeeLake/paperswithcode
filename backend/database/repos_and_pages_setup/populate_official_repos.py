"""
Official Repository Population Script

This script populates the repositories table using only official entries
(is_official: true) from the paperswithcode links-between-papers-and-code.json file.

This ensures we're adding high-quality, verified paper-repository links to our database.

📊 USAGE:
  # Test mode (100 entries)
  python populate_official_repos.py --test

  # Production mode (process all official entries)
  python populate_official_repos.py --production

  # Custom limit
  python populate_official_repos.py --limit 1000

  # Dry run (no database writes)
  python populate_official_repos.py --dry-run
"""

import sys
import json
import logging
import re
import argparse
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse

# Add the project root and backend directory to the Python path
project_root = Path(__file__).parent.parent.parent.parent
backend_dir = project_root / "backend"
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(backend_dir))

from backend.database.connection import get_database_session  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class OfficialRepoPopulator:
    """
    Populates the repositories table with official entries from paperswithcode JSON.
    """

    def __init__(self, dry_run: bool = False, limit: Optional[int] = None):
        self.json_file_path = (
            project_root / "data" / "links-between-papers-and-code.json"
        )
        self.dry_run = dry_run
        self.limit = limit
        self.stats = {
            "json_entries_total": 0,
            "json_entries_official": 0,
            "json_entries_with_arxiv": 0,
            "papers_found_in_db": 0,
            "papers_not_found": 0,
            "repos_already_exist": 0,
            "repos_added": 0,
            "repos_skipped_invalid_url": 0,
            "processing_errors": 0,
        }

    def normalize_github_url(self, url: str) -> str:
        """Normalize GitHub URL for consistency."""
        if not url:
            return ""

        # Remove trailing slashes, convert to lowercase
        url = url.rstrip("/").lower()

        # Ensure it starts with https://github.com
        if url.startswith("http://github.com"):
            url = url.replace("http://github.com", "https://github.com")
        elif not url.startswith("https://github.com"):
            if url.startswith("github.com"):
                url = "https://" + url
            else:
                return ""  # Not a GitHub URL

        return url

    def extract_arxiv_id(self, arxiv_id: str) -> str:
        """Extract base ArXiv ID without version."""
        if not arxiv_id:
            return ""

        # Remove version suffix (e.g., "1234.5678v2" -> "1234.5678")
        return re.sub(r"v\d+$", "", arxiv_id)

    def parse_github_url(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """Parse GitHub URL to extract owner and repository name."""
        try:
            parsed = urlparse(url)
            if parsed.netloc != "github.com":
                return None, None

            path_parts = parsed.path.strip("/").split("/")
            if len(path_parts) >= 2:
                owner = path_parts[0]
                name = path_parts[1]
                return owner, name

            return None, None

        except Exception as e:
            logger.debug(f"Error parsing GitHub URL {url}: {e}")
            return None, None

    def load_official_entries(self) -> List[Dict]:
        """Load official entries from the JSON file."""
        logger.info(f"Loading official entries from {self.json_file_path}...")

        try:
            with open(self.json_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.stats["json_entries_total"] = len(data)

            # Filter for official entries with required fields
            official_entries = []
            for entry in data:
                if (
                    entry.get("is_official")
                    and entry.get("paper_arxiv_id")
                    and entry.get("repo_url")
                ):
                    arxiv_id = self.extract_arxiv_id(entry["paper_arxiv_id"])
                    repo_url = self.normalize_github_url(entry["repo_url"])

                    if arxiv_id and repo_url:
                        processed_entry = {
                            "paper_arxiv_id": arxiv_id,
                            "repo_url": repo_url,
                            "paper_title": entry.get("paper_title", ""),
                            "mentioned_in_paper": entry.get(
                                "mentioned_in_paper", False
                            ),
                            "mentioned_in_github": entry.get(
                                "mentioned_in_github", False
                            ),
                            "framework": entry.get("framework", "none"),
                        }
                        official_entries.append(processed_entry)

            self.stats["json_entries_official"] = len(
                [e for e in data if e.get("is_official")]
            )
            self.stats["json_entries_with_arxiv"] = len(official_entries)

            # Apply limit if specified
            if self.limit:
                official_entries = official_entries[: self.limit]
                logger.info(f"Limited to {self.limit} entries for processing")

            logger.info(f"Total JSON entries: {self.stats['json_entries_total']:,}")
            logger.info(f"Official entries: {self.stats['json_entries_official']:,}")
            logger.info(
                f"Official entries with ArXiv ID + valid GitHub URL: {len(official_entries):,}"
            )

            return official_entries

        except Exception as e:
            logger.error(f"Error loading JSON data: {e}")
            return []

    def find_paper_id(self, db: Session, arxiv_id: str) -> Optional[int]:
        """Find paper ID by ArXiv ID."""
        try:
            result = db.execute(
                text("SELECT id FROM papers WHERE arxiv_id = :arxiv_id LIMIT 1"),
                {"arxiv_id": arxiv_id},
            )
            row = result.fetchone()
            return row.id if row else None

        except Exception as e:
            logger.debug(f"Error finding paper {arxiv_id}: {e}")
            return None

    def repository_exists(self, db: Session, paper_id: int, url: str) -> bool:
        """Check if repository already exists for this paper."""
        try:
            result = db.execute(
                text(
                    "SELECT 1 FROM repositories WHERE paper_id = :paper_id AND url = :url"
                ),
                {"paper_id": paper_id, "url": url},
            )
            return result.fetchone() is not None

        except Exception as e:
            logger.debug(f"Error checking repository existence: {e}")
            return True  # Assume exists to avoid duplicates on error

    def insert_repository(
        self, db: Session, paper_id: int, url: str, owner: str, name: str
    ):
        """Insert repository record."""
        try:
            if self.dry_run:
                logger.info(
                    f"[DRY RUN] Would insert repository: {url} for paper {paper_id}"
                )
                self.stats["repos_added"] += 1
                return

            db.execute(
                text("""
                    INSERT INTO repositories (paper_id, url, owner, name, is_official)
                    VALUES (:paper_id, :url, :owner, :name, :is_official)
                """),
                {
                    "paper_id": paper_id,
                    "url": url,
                    "owner": owner,
                    "name": name,
                    "is_official": True,  # All entries we're adding are official
                },
            )
            db.commit()
            self.stats["repos_added"] += 1
            logger.debug(f"Added repository: {url}")

        except Exception as e:
            logger.error(f"Error inserting repository {url}: {e}")
            db.rollback()
            self.stats["processing_errors"] += 1

    def process_entries(self, db: Session, entries: List[Dict]):
        """Process official entries and add to database."""
        logger.info(f"Processing {len(entries)} official entries...")

        processed_count = 0

        for i, entry in enumerate(entries):
            try:
                arxiv_id = entry["paper_arxiv_id"]
                repo_url = entry["repo_url"]

                # Find paper in database
                paper_id = self.find_paper_id(db, arxiv_id)
                if not paper_id:
                    self.stats["papers_not_found"] += 1
                    logger.debug(f"Paper not found: {arxiv_id}")
                    continue

                self.stats["papers_found_in_db"] += 1

                # Parse GitHub URL
                owner, name = self.parse_github_url(repo_url)
                if not owner or not name:
                    self.stats["repos_skipped_invalid_url"] += 1
                    logger.debug(f"Invalid GitHub URL: {repo_url}")
                    continue

                # Check if repository already exists
                if self.repository_exists(db, paper_id, repo_url):
                    self.stats["repos_already_exist"] += 1
                    logger.debug(f"Repository already exists: {repo_url}")
                    continue

                # Insert repository
                self.insert_repository(db, paper_id, repo_url, owner, name)

                processed_count += 1

                # Progress logging
                if processed_count % 100 == 0:
                    logger.info(
                        f"Processed {processed_count}/{len(entries)} entries..."
                    )

            except Exception as e:
                logger.error(f"Error processing entry {i}: {e}")
                self.stats["processing_errors"] += 1
                continue

        logger.info(f"Completed processing {processed_count} entries")

    def print_summary(self):
        """Print processing summary."""
        print("\n" + "=" * 80)
        print("OFFICIAL REPOSITORY POPULATION SUMMARY")
        print("=" * 80)

        print("\n📊 INPUT DATA:")
        print(f"  Total JSON entries: {self.stats['json_entries_total']:,}")
        print(f"  Official entries: {self.stats['json_entries_official']:,}")
        print(
            f"  Official entries with valid data: {self.stats['json_entries_with_arxiv']:,}"
        )

        print("\n🔍 PAPER MATCHING:")
        print(f"  Papers found in database: {self.stats['papers_found_in_db']:,}")
        print(f"  Papers not found: {self.stats['papers_not_found']:,}")

        if self.stats["papers_found_in_db"] > 0:
            match_rate = (
                self.stats["papers_found_in_db"]
                / (self.stats["papers_found_in_db"] + self.stats["papers_not_found"])
            ) * 100
            print(f"  Paper match rate: {match_rate:.1f}%")

        print("\n📦 REPOSITORY PROCESSING:")
        print(f"  Repositories already existed: {self.stats['repos_already_exist']:,}")
        print(f"  Repositories added: {self.stats['repos_added']:,}")
        print(f"  Invalid URLs skipped: {self.stats['repos_skipped_invalid_url']:,}")
        print(f"  Processing errors: {self.stats['processing_errors']:,}")

        mode = "DRY RUN" if self.dry_run else "PRODUCTION"
        print(f"\n✅ MODE: {mode}")

        if not self.dry_run and self.stats["repos_added"] > 0:
            print(
                f"\n🎉 Successfully added {self.stats['repos_added']} official repositories!"
            )

        print("=" * 80)

    def run(self):
        """Run the population process."""
        logger.info("Starting official repository population...")

        # Load official entries
        entries = self.load_official_entries()
        if not entries:
            logger.error("No official entries found to process")
            return

        # Get database session
        db_session_gen = get_database_session()
        db = next(db_session_gen)

        try:
            # Process entries
            self.process_entries(db, entries)

            # Print summary
            self.print_summary()

        except Exception as e:
            logger.error(f"Error during processing: {e}")
            raise
        finally:
            db.close()


def main():
    """Main function with argument parsing."""
    parser = argparse.ArgumentParser(
        description="Populate repositories with official paperswithcode entries"
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--test", action="store_true", help="Test mode (100 entries)")
    group.add_argument(
        "--production", action="store_true", help="Production mode (all entries)"
    )
    group.add_argument("--limit", type=int, help="Custom limit for number of entries")

    parser.add_argument(
        "--dry-run", action="store_true", help="Dry run (no database writes)"
    )

    args = parser.parse_args()

    # Determine limit
    limit = None
    if args.test:
        limit = 100
    elif args.limit:
        limit = args.limit

    # Create and run populator
    populator = OfficialRepoPopulator(dry_run=args.dry_run, limit=limit)
    populator.run()


if __name__ == "__main__":
    main()
