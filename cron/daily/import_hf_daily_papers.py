"""
Daily Hugging Face Papers Import CRON Job

Fetches the daily papers from Hugging Face API for the previous day and imports them into the database:
- Papers table with metadata and abstracts
- Authors table with Hugging Face profile information
- Repositories table with GitHub links
- Project_pages table with project page URLs
- Paper_tasks table with automatic task tagging based on keywords
- Paper_methods table with automatic method tagging based on keywords

Automatic Task & Method Tagging:

Matching Strategy:
- TASKS: Simple matching - all matching keywords are tagged (e.g., a paper can have multiple task categories)
- METHODS: Longest-match priority - prevents overlapping matches (e.g., "GPT-4" takes precedence over "GPT")

Case-Sensitivity Rules:
- Keywords with at least one capital letter (e.g., BERT, VLM, GPT-4): case-sensitive matching
  * Uses substring matching to catch plurals (VLMs, GANs) and compounds (LVLMs, OpenCLIP)
  * Case sensitivity prevents false positives (CLIP vs clip)
- All-lowercase keywords (e.g., object detection, transformer): case-insensitive matching
  * Uses word boundary matching to prevent false matches (e.g., "transformed" when looking for "transformer")

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
from backend.utils.verify_url import verify_url
from backend.utils.github_utils import parse_github_url
from backend.utils.keyword_matching import (
    create_keyword_patterns,
    create_keyword_patterns_with_metadata,
    find_matching_items_simple,
    find_matching_items_longest_match,
)


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
        self.new_tasks_count = 0
        self.new_methods_count = 0

        # Task keyword matching patterns (loaded once at start)
        self.task_case_sensitive_patterns = {}
        self.task_case_insensitive_patterns = {}

        # Method keyword matching patterns (loaded once at start)
        self.method_case_sensitive_patterns = {}
        self.method_case_insensitive_patterns = {}

    def run(self):
        """Main execution logic for Hugging Face daily papers import."""
        self.logger.info("Starting Hugging Face daily papers import")

        # Check if today is a valid day to run (Tuesday to Saturday)
        # Papers are submitted Mon-Fri on HF, so we import Tue-Sat to get previous day's papers
        today = datetime.now()
        weekday = today.weekday()  # Monday=0, Sunday=6

        # Skip on Sunday (6) and Monday (0) - only run Tuesday (1) to Saturday (5)
        if weekday in [0, 6]:  # Monday or Sunday
            day_name = today.strftime("%A")
            self.logger.info(
                f"Skipping import on {day_name} - papers are only submitted Mon-Fri on Hugging Face"
            )
            return

        # Load tasks and methods with keywords for automatic tagging
        self.load_task_keywords()
        self.load_method_keywords()

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
        self.logger.info(f"  - New task links added: {self.new_tasks_count}")
        self.logger.info(f"  - New method links added: {self.new_methods_count}")
        self.logger.info(f"  - Errors: {self.error_count}")

        # Update database statistics
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

    def load_task_keywords(self):
        """Load tasks with keywords and create keyword patterns for matching (simple matching)."""
        try:
            query = """
                SELECT id, name, keywords
                FROM tasks
                WHERE keywords IS NOT NULL AND keywords != ''
                ORDER BY id
            """

            tasks = self.execute_query(query)

            if not tasks:
                self.logger.warning("No tasks with keywords found")
                return

            # Create keyword patterns (simple matching for tasks)
            self.task_case_sensitive_patterns, self.task_case_insensitive_patterns = (
                create_keyword_patterns(tasks)
            )

            total_keywords = len(self.task_case_sensitive_patterns) + len(
                self.task_case_insensitive_patterns
            )
            self.logger.info(
                f"Loaded {len(tasks)} tasks with {total_keywords} unique keywords for auto-tagging (simple matching)"
            )

        except Exception as e:
            self.logger.error(f"Failed to load task keywords: {e}")

    def load_method_keywords(self):
        """Load methods with keywords and create keyword patterns for matching (longest-match)."""
        try:
            query = """
                SELECT id, name, keywords
                FROM methods
                WHERE keywords IS NOT NULL AND keywords != ''
                ORDER BY id
            """

            methods = self.execute_query(query)

            if not methods:
                self.logger.warning("No methods with keywords found")
                return

            # Create keyword patterns (longest-match for methods to handle hierarchical names like GPT, GPT-2, GPT-4)
            (
                self.method_case_sensitive_patterns,
                self.method_case_insensitive_patterns,
            ) = create_keyword_patterns_with_metadata(methods)

            total_keywords = len(self.method_case_sensitive_patterns) + len(
                self.method_case_insensitive_patterns
            )
            self.logger.info(
                f"Loaded {len(methods)} methods with {total_keywords} unique keywords for auto-tagging (longest-match)"
            )

        except Exception as e:
            self.logger.error(f"Failed to load method keywords: {e}")

    def tag_paper_with_tasks(self, paper_id: int, title: str, abstract: str):
        """Tag a paper with relevant tasks based on keyword matching (simple matching)."""
        # Combine title and abstract
        text = ""
        if title:
            text = title
        if abstract:
            text += " " + abstract

        if not text.strip():
            return

        # Find matching tasks (simple matching - all matching tasks are tagged)
        matching_task_ids = find_matching_items_simple(
            text, self.task_case_sensitive_patterns, self.task_case_insensitive_patterns
        )

        if not matching_task_ids:
            return

        # Link paper to tasks
        query = """
            INSERT INTO paper_tasks (paper_id, task_id)
            VALUES (%s, %s)
            ON CONFLICT (paper_id, task_id) DO NOTHING
        """

        for task_id in matching_task_ids:
            try:
                self.execute_query(query, (paper_id, task_id))
                self.new_tasks_count += 1
            except Exception as e:
                self.logger.error(
                    f"Failed to link paper {paper_id} to task {task_id}: {e}"
                )

    def tag_paper_with_methods(self, paper_id: int, title: str, abstract: str):
        """Tag a paper with relevant methods based on keyword matching (longest-match)."""
        # Combine title and abstract
        text = ""
        if title:
            text = title
        if abstract:
            text += " " + abstract

        if not text.strip():
            return

        # Find matching methods (longest-match to prevent tagging both GPT and GPT-4)
        matching_method_ids = find_matching_items_longest_match(
            text,
            self.method_case_sensitive_patterns,
            self.method_case_insensitive_patterns,
        )

        if not matching_method_ids:
            return

        # Link paper to methods
        query = """
            INSERT INTO paper_methods (paper_id, method_id)
            VALUES (%s, %s)
            ON CONFLICT (paper_id, method_id) DO NOTHING
        """

        for method_id in matching_method_ids:
            try:
                self.execute_query(query, (paper_id, method_id))
                self.new_methods_count += 1
            except Exception as e:
                self.logger.error(
                    f"Failed to link paper {paper_id} to method {method_id}: {e}"
                )

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

            # Tag paper with relevant tasks and methods based on keywords
            self.tag_paper_with_tasks(paper_id, title, abstract)
            self.tag_paper_with_methods(paper_id, title, abstract)

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
        """Insert a new paper into the database.

        Sets urls_extracted=TRUE since HF API provides GitHub/project URLs.
        This prevents AI batch extraction from re-processing these papers.
        """
        query = """
        INSERT INTO papers (arxiv_id, title, abstract, date_published, urls_extracted, created_at, updated_at)
        VALUES (%s, %s, %s, %s, TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
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
        """Insert repository information using normalized schema with junction table."""
        if not self.is_valid_github_url(github_url):
            self.logger.warning(f"Invalid GitHub URL: {github_url}")
            return

        # Parse owner and name from URL
        owner, name = parse_github_url(github_url)

        # Check if repository already exists (by URL)
        query = "SELECT id FROM repositories WHERE url = %s"
        results = self.execute_query(query, (github_url,))

        if results:
            # Repository exists, check if it's already linked to this paper
            repo_id = results[0]["id"]
            query = "SELECT 1 FROM paper_repositories WHERE paper_id = %s AND repository_id = %s"
            link_results = self.execute_query(query, (paper_id, repo_id))

            if link_results:
                return  # Already linked to this paper

            # Link existing repository to paper
            query = """
            INSERT INTO paper_repositories (paper_id, repository_id, is_official)
            VALUES (%s, %s, %s)
            ON CONFLICT (paper_id, repository_id) DO NOTHING
            """
            try:
                self.execute_query(query, (paper_id, repo_id, True))
                self.logger.debug(f"Linked existing repository to paper: {github_url}")
            except Exception as e:
                self.logger.error(
                    f"Failed to link repository {github_url} to paper {paper_id}: {e}"
                )
        else:
            # Create new repository and link to paper
            query = """
            INSERT INTO repositories (url, owner, name, source, created_at, updated_at)
            VALUES (%s, %s, %s, 'hf_api', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING id
            """

            try:
                results = self.execute_query(query, (github_url, owner, name))
                if results:
                    repo_id = results[0]["id"]

                    # Link to paper
                    query = """
                    INSERT INTO paper_repositories (paper_id, repository_id, is_official)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (paper_id, repository_id) DO NOTHING
                    """
                    self.execute_query(query, (paper_id, repo_id, True))

                    self.new_repos_count += 1
                    self.logger.debug(f"Added new repository: {github_url}")
            except Exception as e:
                self.logger.error(f"Failed to insert repository {github_url}: {e}")

    def insert_project_page(self, paper_id: int, project_url: str):
        """Insert project page information using normalized schema with junction table."""
        # Verify URL asynchronously
        if not asyncio.run(verify_url(project_url)):
            self.logger.warning(f"Invalid project page URL: {project_url}")
            return

        # Project page is always official
        is_official = True

        # Check if project page already exists (by URL)
        query = "SELECT id FROM project_pages WHERE url = %s"
        results = self.execute_query(query, (project_url,))

        if results:
            # Project page exists, check if it's already linked to this paper
            page_id = results[0]["id"]
            query = "SELECT 1 FROM paper_project_pages WHERE paper_id = %s AND project_page_id = %s"
            link_results = self.execute_query(query, (paper_id, page_id))

            if link_results:
                return  # Already linked to this paper

            # Link existing project page to paper (junction table only has paper_id and project_page_id)
            query = """
            INSERT INTO paper_project_pages (paper_id, project_page_id)
            VALUES (%s, %s)
            ON CONFLICT (paper_id, project_page_id) DO NOTHING
            """
            try:
                self.execute_query(query, (paper_id, page_id))
                self.logger.debug(
                    f"Linked existing project page to paper: {project_url} (official: {is_official})"
                )
            except Exception as e:
                self.logger.error(
                    f"Failed to link project page {project_url} to paper {paper_id}: {e}"
                )
        else:
            # Create new project page with is_official flag and link to paper
            query = """
            INSERT INTO project_pages (url, is_official, source, created_at, updated_at)
            VALUES (%s, %s, 'hf_api', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING id
            """

            try:
                results = self.execute_query(query, (project_url, is_official))
                if results:
                    page_id = results[0]["id"]

                    # Link to paper (junction table only has paper_id and project_page_id)
                    query = """
                    INSERT INTO paper_project_pages (paper_id, project_page_id)
                    VALUES (%s, %s)
                    ON CONFLICT (paper_id, project_page_id) DO NOTHING
                    """
                    self.execute_query(query, (paper_id, page_id))

                    self.new_pages_count += 1
                    self.logger.debug(
                        f"Added new project page: {project_url} (official: {is_official})"
                    )
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


if __name__ == "__main__":
    job = HuggingFaceDailyPapersJob()
    success = job.execute()
    sys.exit(0 if success else 1)
