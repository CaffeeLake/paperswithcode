"""
Repository and Project Pages Population Script

This script populates the repositories and project_pages tables using data from
the Hugging Face 'community-science-merged' dataset.

The dataset contains columns:
- arxiv_id: ArXiv paper ID
- github: GitHub repository URL
- project_page_url: Project page URL

📊 USAGE:
  # Test mode (100 papers)
  uv run -m backend.database.repos_and_pages_setup.populate_repos_and_pages_from_hf --test

  # Production mode (process all papers)
  uv run -m backend.database.repos_and_pages_setup.populate_repos_and_pages_from_hf --production

  # Custom batch
  uv run -m backend.database.repos_and_pages_setup.populate_repos_and_pages_from_hf --limit 1000

  # Dry run (no database writes)
  uv run -m backend.database.repos_and_pages_setup.populate_repos_and_pages_from_hf --dry-run
"""

import sys
import time
import logging
from typing import Optional, Tuple
import argparse
from urllib.parse import urlparse
import pandas as pd
from sqlalchemy import text, and_
from sqlalchemy.orm import Session

from backend.database.connection import get_database_session
from backend.models.database import Paper as DBPaper

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class RepoAndPagesPopulator:
    """Repository and project pages population service."""

    def __init__(self, dry_run: bool = False):
        """Initialize the populator."""
        self.dry_run = dry_run
        self.stats = {
            "processed": 0,
            "repos_added": 0,
            "pages_added": 0,
            "papers_not_found": 0,
            "invalid_urls": 0,
            "duplicates_skipped": 0,
            "start_time": time.time(),
        }

    def load_hf_dataset(self) -> pd.DataFrame:
        """Load the Hugging Face community-science-merged dataset."""
        try:
            from datasets import load_dataset

            logger.info("Loading Hugging Face community-science-merged dataset...")
            dataset = load_dataset(
                "huggingface/community-science-merged", split="train"
            )
            df = dataset.to_pandas()

            logger.info(f"Loaded {len(df)} records from HuggingFace dataset")
            logger.info(f"Columns: {list(df.columns)}")

            # Filter to only records with arxiv_id and at least one URL
            df = df.dropna(subset=["arxiv_id"])
            df = df[(df["github"].notna()) | (df["project_page_url"].notna())]

            logger.info(f"After filtering: {len(df)} records with arxiv_id and URLs")
            return df

        except ImportError:
            logger.error("Please install the 'datasets' library: pip install datasets")
            sys.exit(1)
        except Exception as e:
            logger.error(f"Error loading dataset: {e}")
            sys.exit(1)

    def validate_github_url(self, url: str) -> Optional[Tuple[str, str]]:
        """
        Validate GitHub URL and extract owner/repo name.
        Returns (owner, name) tuple or None if invalid.
        """
        if not url or pd.isna(url):
            return None

        # Clean up common issues
        url = str(url).strip()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        try:
            parsed = urlparse(url)
            if parsed.netloc.lower() not in ["github.com", "www.github.com"]:
                return None

            # Extract owner/repo from path
            path_parts = [p for p in parsed.path.split("/") if p]
            if len(path_parts) >= 2:
                owner = path_parts[0]
                name = path_parts[1]
                # Remove .git suffix if present
                if name.endswith(".git"):
                    name = name[:-4]
                return (owner, name)

        except Exception as e:
            logger.debug(f"Invalid GitHub URL {url}: {e}")

        return None

    def validate_project_url(self, url: str) -> bool:
        """Validate project page URL."""
        if not url or pd.isna(url):
            return False

        url = str(url).strip()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        try:
            parsed = urlparse(url)
            return bool(parsed.netloc and parsed.scheme in ["http", "https"])
        except:  # noqa: E722
            return False

    def find_paper_by_arxiv_id(self, db: Session, arxiv_id: str) -> Optional[DBPaper]:
        """Find paper by ArXiv ID, preferring latest version."""
        try:
            # First try to find the latest version
            paper = (
                db.query(DBPaper)
                .filter(and_(DBPaper.arxiv_id == arxiv_id, DBPaper.is_latest_version))
                .first()
            )

            # If no latest version found, get any version
            if not paper:
                paper = db.query(DBPaper).filter(DBPaper.arxiv_id == arxiv_id).first()

            return paper
        except Exception as e:
            logger.error(f"Error finding paper {arxiv_id}: {e}")
            # Rollback on error to prevent transaction issues
            db.rollback()
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
            logger.error(f"Error checking repository existence: {e}")
            db.rollback()
            return True  # Assume exists to avoid duplicates on error

    def project_page_exists(self, db: Session, paper_id: int, url: str) -> bool:
        """Check if project page already exists for this paper."""
        try:
            result = db.execute(
                text(
                    "SELECT 1 FROM project_pages WHERE paper_id = :paper_id AND url = :url"
                ),
                {"paper_id": paper_id, "url": url},
            )
            return result.fetchone() is not None
        except Exception as e:
            logger.error(f"Error checking project page existence: {e}")
            db.rollback()
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
                return

            db.execute(
                text("""
                    INSERT INTO repositories (paper_id, url, owner, name)
                    VALUES (:paper_id, :url, :owner, :name)
                """),
                {"paper_id": paper_id, "url": url, "owner": owner, "name": name},
            )
            self.stats["repos_added"] += 1
            logger.debug(f"Added repository: {url}")

        except Exception as e:
            logger.error(f"Error inserting repository {url}: {e}")

    def insert_project_page(self, db: Session, paper_id: int, url: str):
        """Insert project page record."""
        try:
            if self.dry_run:
                logger.info(
                    f"[DRY RUN] Would insert project page: {url} for paper {paper_id}"
                )
                return

            db.execute(
                text("""
                    INSERT INTO project_pages (paper_id, url)
                    VALUES (:paper_id, :url)
                """),
                {"paper_id": paper_id, "url": url},
            )
            self.stats["pages_added"] += 1
            logger.debug(f"Added project page: {url}")

        except Exception as e:
            logger.error(f"Error inserting project page {url}: {e}")

    def process_batch(self, db: Session, batch_df: pd.DataFrame):
        """Process a batch of records."""
        for _, row in batch_df.iterrows():
            self.stats["processed"] += 1

            try:
                arxiv_id = str(row["arxiv_id"]).strip()
                github_url = row.get("github")
                project_url = row.get("project_page_url")

                # Find the paper
                paper = self.find_paper_by_arxiv_id(db, arxiv_id)
                if not paper:
                    self.stats["papers_not_found"] += 1
                    logger.debug(f"Paper not found for ArXiv ID: {arxiv_id}")
                    continue

                # Process GitHub repository
                if github_url and pd.notna(github_url):
                    repo_info = self.validate_github_url(github_url)
                    if repo_info:
                        owner, name = repo_info
                        clean_url = f"https://github.com/{owner}/{name}"

                        if not self.repository_exists(db, paper.id, clean_url):
                            self.insert_repository(db, paper.id, clean_url, owner, name)
                        else:
                            self.stats["duplicates_skipped"] += 1
                            logger.debug(f"Repository already exists: {clean_url}")
                    else:
                        self.stats["invalid_urls"] += 1
                        logger.debug(f"Invalid GitHub URL: {github_url}")

                # Process project page
                if project_url and pd.notna(project_url):
                    if self.validate_project_url(project_url):
                        clean_url = str(project_url).strip()
                        if not clean_url.startswith(("http://", "https://")):
                            clean_url = "https://" + clean_url

                        if not self.project_page_exists(db, paper.id, clean_url):
                            self.insert_project_page(db, paper.id, clean_url)
                        else:
                            self.stats["duplicates_skipped"] += 1
                            logger.debug(f"Project page already exists: {clean_url}")
                    else:
                        self.stats["invalid_urls"] += 1
                        logger.debug(f"Invalid project URL: {project_url}")

            except Exception as e:
                logger.error(f"Error processing record {arxiv_id}: {e}")
                # Rollback the current transaction and start a new one
                db.rollback()
                continue

            # Progress logging
            if self.stats["processed"] % 100 == 0:
                self.log_progress()

    def log_progress(self):
        """Log current progress."""
        elapsed = time.time() - self.stats["start_time"]
        rate = self.stats["processed"] / elapsed if elapsed > 0 else 0

        logger.info(
            f"Progress: {self.stats['processed']} processed, "
            f"{self.stats['repos_added']} repos added, "
            f"{self.stats['pages_added']} pages added, "
            f"{self.stats['papers_not_found']} papers not found, "
            f"Rate: {rate:.1f} records/sec"
        )

    def populate(self, limit: Optional[int] = None, batch_size: int = 1000):
        """Main population method."""
        logger.info("Starting repository and project pages population...")

        # Load dataset
        df = self.load_hf_dataset()

        # Apply limit if specified
        if limit:
            df = df.head(limit)
            logger.info(f"Limited to {len(df)} records")

        # Process in batches
        total_batches = (len(df) + batch_size - 1) // batch_size

        for i in range(0, len(df), batch_size):
            batch_num = i // batch_size + 1
            batch_df = df.iloc[i : i + batch_size]

            logger.info(
                f"Processing batch {batch_num}/{total_batches} ({len(batch_df)} records)"
            )

            try:
                with next(get_database_session()) as db:
                    self.process_batch(db, batch_df)

                    if not self.dry_run:
                        db.commit()
                        logger.info(f"Committed batch {batch_num}")

            except Exception as e:
                logger.error(f"Error processing batch {batch_num}: {e}")
                continue

        # Final stats
        self.log_final_stats()

    def log_final_stats(self):
        """Log final statistics."""
        elapsed = time.time() - self.stats["start_time"]

        logger.info("=" * 60)
        logger.info("POPULATION COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Total processed: {self.stats['processed']}")
        logger.info(f"Repositories added: {self.stats['repos_added']}")
        logger.info(f"Project pages added: {self.stats['pages_added']}")
        logger.info(f"Papers not found: {self.stats['papers_not_found']}")
        logger.info(f"Invalid URLs: {self.stats['invalid_urls']}")
        logger.info(f"Duplicates skipped: {self.stats['duplicates_skipped']}")
        logger.info(f"Total time: {elapsed:.1f} seconds")
        logger.info(
            f"Average rate: {self.stats['processed'] / elapsed:.1f} records/sec"
        )


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Populate repositories and project pages from HuggingFace dataset"
    )

    parser.add_argument(
        "--test", action="store_true", help="Test mode (limit to 100 records)"
    )
    parser.add_argument(
        "--production",
        action="store_true",
        help="Production mode (process all records)",
    )
    parser.add_argument("--limit", type=int, help="Limit number of records to process")
    parser.add_argument(
        "--batch-size", type=int, default=1000, help="Batch size for processing"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Dry run mode (no database writes)"
    )

    args = parser.parse_args()

    # Determine limit
    limit = None
    if args.test:
        limit = 100
        logger.info("Running in TEST mode (100 records)")
    elif args.limit:
        limit = args.limit
        logger.info(f"Processing {limit} records")
    elif args.production:
        logger.info("Running in PRODUCTION mode (all records)")
    else:
        limit = 100
        logger.info("No mode specified, defaulting to TEST mode (100 records)")

    if args.dry_run:
        logger.info("Running in DRY RUN mode (no database writes)")

    # Create populator and run
    populator = RepoAndPagesPopulator(dry_run=args.dry_run)

    try:
        populator.populate(limit=limit, batch_size=args.batch_size)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        populator.log_final_stats()
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        populator.log_final_stats()
        sys.exit(1)


if __name__ == "__main__":
    main()
