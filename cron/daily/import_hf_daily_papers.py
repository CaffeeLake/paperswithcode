"""
Daily Hugging Face Papers Import CRON Job

Fetches the daily papers from Hugging Face API for the previous day and imports them into the database:
- Papers table with metadata and abstracts
- Authors table with Hugging Face profile information
- Repositories table with GitHub links
- Project_pages table with project page URLs
- Paper_tasks table with automatic task tagging based on keywords
- Paper_methods table with automatic method tagging based on keywords

Per-paper logic (DB inserts, author handling, repo/project page handling, keyword
tagging) lives in `cron.utils.hf_paper_importer.HuggingFacePaperImporterMixin`,
which is shared with the historical backfill in `cron/backfill/`.

Schedule: Daily at 3:00 AM UTC (after ArXiv update)
Dependencies: PostgreSQL, Hugging Face API
"""

import sys
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List

import aiohttp

from backend.config import get_settings
from cron.utils.cron_helpers import DatabaseCronJob
from cron.utils.hf_paper_importer import HuggingFacePaperImporterMixin


class HuggingFaceDailyPapersJob(HuggingFacePaperImporterMixin, DatabaseCronJob):
    """Daily job to import papers from Hugging Face daily papers API."""

    def __init__(self):
        super().__init__(job_name="import_hf_daily_papers", log_level="INFO")
        self.settings = get_settings()
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

        # Papers are submitted Mon-Fri on HF, so we import Tue-Sat to get previous day's papers
        today = datetime.now()
        weekday = today.weekday()
        if weekday in [0, 6]:  # Monday or Sunday
            day_name = today.strftime("%A")
            self.logger.info(
                f"Skipping import on {day_name} - papers are only submitted Mon-Fri on Hugging Face"
            )
            return

        self.load_task_keywords()
        self.load_method_keywords()

        yesterday = datetime.now() - timedelta(days=1)
        target_date = yesterday.strftime("%Y-%m-%d")

        self.logger.info(f"Fetching daily papers for date: {target_date}")

        daily_papers = asyncio.run(self.fetch_daily_papers(target_date))

        if not daily_papers:
            self.logger.info("No papers found for the target date")
            return

        self.logger.info(
            f"Found {len(daily_papers)} papers from Hugging Face daily papers"
        )

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

        github_repo, project_page = asyncio.run(self.fetch_paper_urls_legacy(arxiv_id))
        if github_repo:
            self.insert_repository(paper_id, github_repo)
        if project_page:
            self.insert_project_page(paper_id, project_page)


if __name__ == "__main__":
    job = HuggingFaceDailyPapersJob()
    success = job.execute()
    sys.exit(0 if success else 1)
