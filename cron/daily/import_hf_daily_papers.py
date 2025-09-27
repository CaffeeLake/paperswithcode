"""
Daily Hugging Face Papers Import CRON Job

Fetches the daily papers from Hugging Face API for the previous day and imports them into the database:
- Papers table with metadata and abstracts
- Authors table with Hugging Face profile information
- Repositories table with GitHub links
- Project_pages table with project page URLs

Schedule: Daily at 3:00 AM UTC (after ArXiv update)
Dependencies: PostgreSQL, Hugging Face API
"""

import sys

import aiohttp
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse

from cron.utils.cron_helpers import DatabaseCronJob
from backend.config import get_settings


class HuggingFaceDailyPapersJob(DatabaseCronJob):
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

    def run(self):
        """Main execution logic for Hugging Face daily papers import."""
        self.logger.info("Starting Hugging Face daily papers import")

        # Get yesterday's date
        yesterday = datetime.now() - timedelta(days=1)
        target_date = yesterday.strftime("%Y-%m-%d")

        self.logger.info(f"Fetching daily papers for date: {target_date}")

        # Fetch papers from HF API
        daily_papers = asyncio.run(self.fetch_daily_papers(target_date))

        if not daily_papers:
            self.logger.info("No papers found for the target date")
            return

        self.logger.info(
            f"Found {len(daily_papers)} papers from Hugging Face daily papers"
        )

        # Process each paper
        for paper_data in daily_papers:
            try:
                self.process_paper(paper_data)
                self.processed_count += 1
            except Exception as e:
                self.error_count += 1
                arxiv_id = paper_data.get("paper", {}).get("id", "unknown")
                self.logger.error(f"Failed to process paper {arxiv_id}: {e}")

        # Log summary
        self.logger.info("Hugging Face daily papers import completed:")
        self.logger.info(f"  - Papers processed: {self.processed_count}")
        self.logger.info(f"  - New papers added: {self.new_papers_count}")
        self.logger.info(f"  - New authors added: {self.new_authors_count}")
        self.logger.info(f"  - New repositories added: {self.new_repos_count}")
        self.logger.info(f"  - New project pages added: {self.new_pages_count}")
        self.logger.info(f"  - Errors: {self.error_count}")

        # Update database statistics
        self.vacuum_analyze_table("papers")
        self.vacuum_analyze_table("authors")
        self.vacuum_analyze_table("repositories")
        self.vacuum_analyze_table("project_pages")

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
                    else:
                        self.logger.error(
                            f"Failed to fetch daily papers: HTTP {response.status}"
                        )
                        return []
        except Exception as e:
            self.logger.error(f"Error fetching daily papers: {e}")
            return []

    async def fetch_paper_details(
        self, arxiv_id: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """Fetch additional paper details including GitHub repo and project page."""
        url = f"https://huggingface.co/api/papers/{arxiv_id}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        github_repo = data.get("githubRepo")
                        project_page = data.get("projectPage")
                        return github_repo, project_page
                    else:
                        return None, None
        except Exception as e:
            self.logger.debug(f"Could not fetch details for paper {arxiv_id}: {e}")
            return None, None

    def process_paper(self, paper_data: Dict):
        """Process a single paper and insert into database."""
        paper_info = paper_data.get("paper", {})
        arxiv_id = paper_info.get("id")

        if not arxiv_id:
            self.logger.warning("Paper missing ArXiv ID, skipping")
            return

        # Check if paper already exists
        existing_paper = self.get_paper_by_arxiv_id(arxiv_id)
        if existing_paper:
            self.logger.debug(f"Paper {arxiv_id} already exists, skipping")
            return

        # Extract paper information
        title = paper_info.get("title", "").strip()
        abstract = paper_info.get("summary", "").strip()
        published_at = paper_info.get("publishedAt")

        # Parse published date
        date_published = None
        if published_at:
            try:
                date_published = datetime.fromisoformat(
                    published_at.replace("Z", "+00:00")
                ).date()
            except Exception as e:
                self.logger.debug(f"Could not parse date {published_at}: {e}")

        # Insert paper
        paper_id = self.insert_paper(arxiv_id, title, abstract, date_published)
        if paper_id:
            self.new_papers_count += 1
            self.logger.info(f"Added new paper: {title} (ID: {paper_id})")

            # Process authors
            self.process_authors(paper_id, paper_info.get("authors", []))

            # Fetch and process repositories and project pages
            github_repo, project_page = asyncio.run(self.fetch_paper_details(arxiv_id))

            if github_repo:
                self.insert_repository(paper_id, github_repo)

            if project_page:
                self.insert_project_page(paper_id, project_page)

    def get_paper_by_arxiv_id(self, arxiv_id: str) -> Optional[Dict]:
        """Check if paper already exists in database."""
        query = "SELECT id FROM papers WHERE arxiv_id = %s"
        results = self.execute_query(query, (arxiv_id,))
        return results[0] if results else None

    def insert_paper(
        self,
        arxiv_id: str,
        title: str,
        abstract: str,
        date_published: Optional[datetime],
    ) -> Optional[int]:
        """Insert a new paper into the database."""
        query = """
        INSERT INTO papers (arxiv_id, title, abstract, date_published, created_at, updated_at)
        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING id
        """

        try:
            results = self.execute_query(
                query, (arxiv_id, title, abstract, date_published)
            )
            return results[0]["id"] if results else None
        except Exception as e:
            self.logger.error(f"Failed to insert paper {arxiv_id}: {e}")
            return None

    def process_authors(self, paper_id: int, authors_data: List[Dict]):
        """Process and insert authors for a paper."""
        for author_data in authors_data:
            author_name = author_data.get("name")
            if not author_name:
                continue

            # Extract Hugging Face user information
            user_info = author_data.get("user", {})
            hf_username = user_info.get("user") if user_info else None
            hf_id = user_info.get("_id") if user_info else None
            hf_avatar_url = user_info.get("avatarUrl") if user_info else None
            hf_is_pro = user_info.get("isPro", False) if user_info else False
            hf_status = author_data.get("status")

            # Get or create author
            author_id = self.get_or_create_author(
                name=author_name,
                hf_username=hf_username,
                hf_id=hf_id,
                hf_avatar_url=hf_avatar_url,
                hf_status=hf_status,
                hf_is_pro=hf_is_pro,
            )

            if author_id:
                # Link author to paper
                self.link_paper_author(paper_id, author_id)

    def get_or_create_author(
        self,
        name: str,
        hf_username: Optional[str] = None,
        hf_id: Optional[str] = None,
        hf_avatar_url: Optional[str] = None,
        hf_status: Optional[str] = None,
        hf_is_pro: bool = False,
    ) -> Optional[int]:
        """Get existing author or create new one."""
        # First try to find by HF username or ID
        if hf_username:
            query = "SELECT id FROM authors WHERE hf_username = %s"
            results = self.execute_query(query, (hf_username,))
            if results:
                return results[0]["id"]

        if hf_id:
            query = "SELECT id FROM authors WHERE hf_id = %s"
            results = self.execute_query(query, (hf_id,))
            if results:
                return results[0]["id"]

        # Try to find by name (case-insensitive)
        query = "SELECT id FROM authors WHERE LOWER(name) = LOWER(%s)"
        results = self.execute_query(query, (name,))
        if results:
            # Update existing author with HF information if available
            author_id = results[0]["id"]
            if hf_username or hf_id:
                self.update_author_hf_info(
                    author_id, hf_username, hf_id, hf_avatar_url, hf_status, hf_is_pro
                )
            return author_id

        # Create new author
        return self.create_author(
            name, hf_username, hf_id, hf_avatar_url, hf_status, hf_is_pro
        )

    def create_author(
        self,
        name: str,
        hf_username: Optional[str] = None,
        hf_id: Optional[str] = None,
        hf_avatar_url: Optional[str] = None,
        hf_status: Optional[str] = None,
        hf_is_pro: bool = False,
    ) -> Optional[int]:
        """Create a new author."""
        query = """
        INSERT INTO authors (name, hf_username, hf_id, hf_avatar_url, hf_status, hf_is_pro, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING id
        """

        try:
            results = self.execute_query(
                query, (name, hf_username, hf_id, hf_avatar_url, hf_status, hf_is_pro)
            )
            if results:
                self.new_authors_count += 1
                return results[0]["id"]
            return None
        except Exception as e:
            self.logger.error(f"Failed to create author {name}: {e}")
            return None

    def update_author_hf_info(
        self,
        author_id: int,
        hf_username: Optional[str],
        hf_id: Optional[str],
        hf_avatar_url: Optional[str],
        hf_status: Optional[str],
        hf_is_pro: bool,
    ):
        """Update author with Hugging Face information."""
        query = """
        UPDATE authors
        SET hf_username = COALESCE(%s, hf_username),
            hf_id = COALESCE(%s, hf_id),
            hf_avatar_url = COALESCE(%s, hf_avatar_url),
            hf_status = COALESCE(%s, hf_status),
            hf_is_pro = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
        """

        try:
            self.execute_query(
                query,
                (hf_username, hf_id, hf_avatar_url, hf_status, hf_is_pro, author_id),
            )
        except Exception as e:
            self.logger.error(f"Failed to update author {author_id} HF info: {e}")

    def link_paper_author(self, paper_id: int, author_id: int):
        """Link paper to author."""
        query = """
        INSERT INTO paper_authors (paper_id, author_id)
        VALUES (%s, %s)
        ON CONFLICT (paper_id, author_id) DO NOTHING
        """

        try:
            self.execute_query(query, (paper_id, author_id))
        except Exception as e:
            self.logger.error(
                f"Failed to link paper {paper_id} to author {author_id}: {e}"
            )

    def insert_repository(self, paper_id: int, github_url: str):
        """Insert repository information."""
        if not self.is_valid_github_url(github_url):
            self.logger.warning(f"Invalid GitHub URL: {github_url}")
            return

        # Parse owner and name from URL
        owner, name = self.parse_github_url(github_url)

        # Check if repository already exists for this paper
        query = "SELECT id FROM repositories WHERE paper_id = %s AND url = %s"
        results = self.execute_query(query, (paper_id, github_url))
        if results:
            return  # Already exists

        query = """
        INSERT INTO repositories (paper_id, url, owner, name, source, created_at, updated_at)
        VALUES (%s, %s, %s, %s, 'hf_daily_papers', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """

        try:
            self.execute_query(query, (paper_id, github_url, owner, name))
            self.new_repos_count += 1
            self.logger.debug(f"Added repository: {github_url}")
        except Exception as e:
            self.logger.error(f"Failed to insert repository {github_url}: {e}")

    def insert_project_page(self, paper_id: int, project_url: str):
        """Insert project page information."""
        if not self.is_valid_url(project_url):
            self.logger.warning(f"Invalid project page URL: {project_url}")
            return

        # Check if project page already exists for this paper
        query = "SELECT id FROM project_pages WHERE paper_id = %s AND url = %s"
        results = self.execute_query(query, (paper_id, project_url))
        if results:
            return  # Already exists

        query = """
        INSERT INTO project_pages (paper_id, url, source, created_at, updated_at)
        VALUES (%s, %s, 'hf_daily_papers', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """

        try:
            self.execute_query(query, (paper_id, project_url))
            self.new_pages_count += 1
            self.logger.debug(f"Added project page: {project_url}")
        except Exception as e:
            self.logger.error(f"Failed to insert project page {project_url}: {e}")

    def is_valid_github_url(self, url: str) -> bool:
        """Check if URL is a valid GitHub repository URL."""
        try:
            parsed = urlparse(url)
            return (
                parsed.netloc.lower() in ["github.com", "www.github.com"]
                and len(parsed.path.strip("/").split("/")) >= 2
            )
        except Exception:
            return False

    def is_valid_url(self, url: str) -> bool:
        """Check if URL is valid."""
        try:
            parsed = urlparse(url)
            return parsed.scheme in ["http", "https"] and parsed.netloc
        except Exception:
            return False

    def parse_github_url(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """Parse GitHub URL to extract owner and repository name."""
        try:
            parsed = urlparse(url)
            path_parts = parsed.path.strip("/").split("/")
            if len(path_parts) >= 2:
                return path_parts[0], path_parts[1]
        except Exception:
            pass
        return None, None


if __name__ == "__main__":
    job = HuggingFaceDailyPapersJob()
    success = job.execute()
    sys.exit(0 if success else 1)
