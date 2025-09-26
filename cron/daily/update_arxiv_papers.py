#!/usr/bin/env python3
"""
Daily ArXiv Papers Update CRON Job

Fetches new papers from ArXiv API and updates the database with:
- New paper metadata and abstracts
- Author information
- Repository links (if available)
- Thumbnail generation

Schedule: Daily at 2:00 AM UTC
Dependencies: PostgreSQL, ArXiv API, backend services
"""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from datetime import datetime, timedelta

from cron.utils.cron_helpers import DatabaseCronJob
from backend.services.arxiv_service import ArxivService
from backend.services.paper_service import PaperService


class ArxivUpdateJob(DatabaseCronJob):
    """Daily job to update papers from ArXiv API."""

    def __init__(self):
        super().__init__(job_name="update_arxiv_papers", log_level="INFO")
        self.arxiv_service = ArxivService()
        self.paper_service = PaperService()

    def run(self):
        """Main execution logic for ArXiv updates."""
        self.logger.info("Starting ArXiv papers update")

        # Get papers from the last 2 days to catch any we might have missed
        start_date = datetime.now() - timedelta(days=2)
        end_date = datetime.now()

        self.logger.info(
            f"Fetching papers from {start_date.date()} to {end_date.date()}"
        )

        # Fetch new papers from ArXiv
        new_papers = self.arxiv_service.fetch_recent_papers(
            start_date=start_date, end_date=end_date
        )

        self.logger.info(f"Found {len(new_papers)} papers from ArXiv")

        if not new_papers:
            self.logger.info("No new papers to process")
            return

        # Process each paper
        processed_count = 0
        error_count = 0

        for paper_data in new_papers:
            try:
                # Check if paper already exists
                existing_paper = self.paper_service.get_paper_by_arxiv_id(
                    paper_data.get("arxiv_id")
                )

                if existing_paper:
                    self.logger.debug(
                        f"Paper {paper_data.get('arxiv_id')} already exists, skipping"
                    )
                    continue

                # Insert new paper
                paper_id = self.paper_service.create_paper(paper_data)
                self.logger.info(
                    f"Added new paper: {paper_data.get('title')} (ID: {paper_id})"
                )

                processed_count += 1

            except Exception as e:
                error_count += 1
                self.logger.error(
                    f"Failed to process paper {paper_data.get('arxiv_id', 'unknown')}: {e}"
                )

        # Log summary
        self.logger.info("ArXiv update completed:")
        self.logger.info(f"  - Papers processed: {processed_count}")
        self.logger.info(f"  - Errors: {error_count}")
        self.logger.info(
            f"  - Total papers in database: {self.get_table_count('papers')}"
        )

        # Update database statistics
        self.vacuum_analyze_table("papers")
        self.vacuum_analyze_table("paper_authors")


if __name__ == "__main__":
    job = ArxivUpdateJob()
    success = job.execute()
    sys.exit(0 if success else 1)
