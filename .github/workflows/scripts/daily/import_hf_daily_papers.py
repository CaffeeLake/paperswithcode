"""
Hourly Hugging Face Papers Import CRON Job

Fetches the current day's daily papers from Hugging Face API and imports any not
yet in the database (deduped per-paper by arxiv_id):
- Papers table with metadata and abstracts
- Authors table with Hugging Face profile information
- Repositories table with GitHub links
- Project_pages table with project page URLs
- Paper_tasks table with automatic task tagging based on keywords
- Paper_methods table with automatic method tagging based on keywords

Per-paper logic (DB inserts, author handling, repo/project page handling, keyword
tagging) lives in `scripts.utils.hf_paper_importer.HuggingFacePaperImporterMixin`,
which is shared with the historical backfill in `.github/workflows/scripts/backfill/`.

Schedule: Hourly
Dependencies: PostgreSQL, Hugging Face API
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import aiohttp

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.database.paper_merge import (
    find_external_paper_for_title,
    merge_external_paper_into_arxiv,
)
from scripts.utils.cron_helpers import DatabaseCronJob
from scripts.utils.hf_paper_importer import HuggingFacePaperImporterMixin


class HuggingFaceDailyPapersJob(HuggingFacePaperImporterMixin, DatabaseCronJob):
    """Daily job to import papers from Hugging Face daily papers API."""

    DEFAULT_LOOKBACK_DAYS = 7

    def __init__(
        self,
        target_date: Optional[str] = None,
        lookback_days: Optional[int] = None,
    ):
        super().__init__(job_name="import_hf_daily_papers", log_level="INFO")
        self.settings = get_settings()
        self.target_date = target_date
        if lookback_days is None:
            lookback_days = int(
                os.environ.get(
                    "PWC_HF_IMPORT_LOOKBACK_DAYS", self.DEFAULT_LOOKBACK_DAYS
                )
            )
        self.lookback_days = max(1, lookback_days)
        self.processed_count = 0
        self.error_count = 0
        self.new_papers_count = 0
        self.new_authors_count = 0
        self.new_repos_count = 0
        self.new_pages_count = 0
        self.new_tasks_count = 0
        self.new_methods_count = 0

        self.task_case_sensitive_patterns = {}
        self.task_case_insensitive_patterns = {}

        self.method_case_sensitive_patterns = {}
        self.method_case_insensitive_patterns = {}

    def run(self):
        """Main execution logic for Hugging Face daily papers import."""
        self.logger.info("Starting Hugging Face daily papers import")

        if self.target_date:
            # Manual/backfill: import exactly the requested day.
            target_dates = [self.target_date]
        else:
            # Scheduled hourly: scan a rolling window of recent days. HF keeps
            # back-filling papers into past days' lists, so re-scanning the last
            # few days (deduped per-paper by arxiv_id) catches late additions
            # that a today-only query would miss.
            today = datetime.now()
            target_dates = [
                (today - timedelta(days=offset)).strftime("%Y-%m-%d")
                for offset in range(self.lookback_days)
            ]

        self.logger.info(f"Target dates: {', '.join(target_dates)}")
        self.load_task_keywords()
        self.load_method_keywords()

        for target_date in target_dates:
            self.logger.info(f"Fetching daily papers for date: {target_date}")
            daily_papers = asyncio.run(self.fetch_daily_papers(target_date))

            if not daily_papers:
                self.logger.info(f"No papers found for date: {target_date}")
                continue

            self.logger.info(f"Found {len(daily_papers)} papers for date {target_date}")

            for paper_data in daily_papers:
                try:
                    self.process_paper(paper_data)
                    self.processed_count += 1
                except Exception as e:
                    self.error_count += 1
                    arxiv_id = paper_data.get("paper", {}).get("id", "unknown")
                    self.logger.error(f"Failed to process paper {arxiv_id}: {e}")

        self.logger.info("Hugging Face daily papers import completed:")
        self.logger.info(f"  - Papers processed: {self.processed_count}")
        self.logger.info(f"  - New papers added: {self.new_papers_count}")
        self.logger.info(f"  - New authors added: {self.new_authors_count}")
        self.logger.info(f"  - New repositories added: {self.new_repos_count}")
        self.logger.info(f"  - New project pages added: {self.new_pages_count}")
        self.logger.info(f"  - New task links added: {self.new_tasks_count}")
        self.logger.info(f"  - New method links added: {self.new_methods_count}")
        self.logger.info(f"  - Errors: {self.error_count}")

        self.vacuum_analyze_table("papers")
        self.vacuum_analyze_table("authors")
        self.vacuum_analyze_table("repositories")
        self.vacuum_analyze_table("project_pages")
        self.vacuum_analyze_table("paper_tasks")
        self.vacuum_analyze_table("paper_methods")

    async def fetch_daily_papers(self, date: str) -> List[Dict]:
        """Fetch daily papers from Hugging Face API."""
        url = f"https://huggingface.co/api/daily_papers?date={date}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    if response.status == 400:
                        # HF returns 400 for a date whose daily-papers list does
                        # not exist yet (e.g. the current day shortly after
                        # 00:00 UTC). Expected, not an error.
                        self.logger.info(
                            f"No daily-papers list yet for {date} (HTTP 400)"
                        )
                        return []
                    self.logger.error(
                        f"Failed to fetch daily papers: HTTP {response.status}"
                    )
                    return []
        except Exception as e:
            self.logger.error(f"Error fetching daily papers: {e}")
            return []

    def process_paper(self, paper_data: Dict):
        """Process a single daily-papers entry."""
        paper_info = paper_data.get("paper", {})
        arxiv_id = paper_info.get("id")

        if not arxiv_id:
            self.logger.warning("Paper missing ArXiv ID, skipping")
            return

        if self.get_paper_by_arxiv_id(arxiv_id):
            self.logger.debug(f"Paper {arxiv_id} already exists, skipping")
            return

        title = (paper_info.get("title") or "").strip()
        abstract = (paper_info.get("summary") or "").strip()
        date_published = self.parse_published_at(paper_info.get("publishedAt"))
        tldr = paper_info.get("ai_summary")

        paper_id = self.insert_paper(arxiv_id, title, abstract, date_published, tldr)
        if not paper_id:
            return

        self.new_papers_count += 1
        self.logger.info(f"Added new paper: {title} (ID: {paper_id})")

        self.process_authors(paper_id, paper_info.get("authors", []))
        self.tag_paper_with_tasks(paper_id, title, abstract)
        self.tag_paper_with_methods(paper_id, title, abstract)

        session = db_manager.session_local()
        try:
            external_match = find_external_paper_for_title(session, title)
            if external_match is not None:
                stats = merge_external_paper_into_arxiv(
                    session, external_match.id, paper_id
                )
                session.commit()
                self.logger.info(
                    "Merged external paper %s into new ArXiv row %s (%s): %s",
                    external_match.id,
                    paper_id,
                    arxiv_id,
                    stats,
                )
        except Exception as exc:
            session.rollback()
            self.logger.error(
                "Failed to merge external duplicate for %s into paper %s: %s",
                arxiv_id,
                paper_id,
                exc,
            )
        finally:
            session.close()

        github_repo, project_page = asyncio.run(self.fetch_paper_urls_legacy(arxiv_id))
        if github_repo:
            self.insert_repository(paper_id, github_repo)
        if project_page:
            self.insert_project_page(paper_id, project_page)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--date",
        help=(
            "Import a specific Hugging Face daily-papers date in YYYY-MM-DD "
            "format. When omitted, scans a rolling window of recent days."
        ),
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=None,
        help=(
            "Number of recent days to scan on the scheduled (no --date) path. "
            "Defaults to PWC_HF_IMPORT_LOOKBACK_DAYS or "
            f"{HuggingFaceDailyPapersJob.DEFAULT_LOOKBACK_DAYS}. Ignored when "
            "--date is given."
        ),
    )
    args = parser.parse_args()

    if args.date:
        datetime.strptime(args.date, "%Y-%m-%d")

    job = HuggingFaceDailyPapersJob(
        target_date=args.date, lookback_days=args.lookback_days
    )
    success = job.execute()
    sys.exit(0 if success else 1)
