"""
Hugging Face Papers Full Backfill

Walks the cursor-paginated `https://huggingface.co/api/papers` endpoint and
imports every indexed paper into our database (papers + authors + github repo
+ project page + automatic task/method tagging).

For papers that already exist in the DB, this script enriches them
opportunistically:
- Always upserts HF profile data on existing authors using the list payload
  (no extra API call needed).
- If the paper is missing both a github repo AND a project page link, fetch
  the per-paper detail and fill in whichever URLs are available, plus tldr
  if it's currently NULL.

The script is resumable: a JSON checkpoint is written after every page so it
can pick up where it left off after interruption.

HF artifact counts (linked models / datasets / spaces) are intentionally not
stored - the frontend already fetches those live from the HF hub API.

Usage:
    uv run --env-file backend/keys.env cron/backfill/backfill_hf_papers.py
    uv run --env-file backend/keys.env cron/backfill/backfill_hf_papers.py --max-papers 200
    uv run --env-file backend/keys.env cron/backfill/backfill_hf_papers.py --reset
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import aiohttp

from backend.utils.verify_url import verify_url
from cron.utils.cron_helpers import DatabaseCronJob
from cron.utils.hf_paper_importer import HuggingFacePaperImporterMixin


HF_API_BASE = "https://huggingface.co"
HF_PAPERS_LIST = f"{HF_API_BASE}/api/papers"
DEFAULT_PAGE_SIZE = 100
DEFAULT_MAX_REQUESTS_PER_MINUTE = 90  # HF allows 500 / 5min = 100/min, leave headroom

CHECKPOINT_PATH = Path(__file__).parent / "checkpoint.json"


class RateLimiter:
    """Simple sliding-window rate limiter (requests per minute)."""

    def __init__(self, max_per_minute: int):
        self.max_per_minute = max_per_minute
        self.window: List[float] = []

    async def wait(self):
        now = time.monotonic()
        cutoff = now - 60.0
        self.window = [t for t in self.window if t > cutoff]
        if len(self.window) >= self.max_per_minute:
            sleep_for = 60.0 - (now - self.window[0]) + 0.05
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)
            now = time.monotonic()
            cutoff = now - 60.0
            self.window = [t for t in self.window if t > cutoff]
        self.window.append(now)


class HuggingFaceBackfillJob(HuggingFacePaperImporterMixin, DatabaseCronJob):
    """Backfill the database from the full /api/papers cursor stream."""

    def __init__(self, args: argparse.Namespace):
        super().__init__(job_name="backfill_hf_papers", log_level="INFO")
        self.args = args

        self.processed_count = 0
        self.error_count = 0
        self.new_papers_count = 0
        self.new_authors_count = 0
        self.new_repos_count = 0
        self.new_pages_count = 0
        self.new_tasks_count = 0
        self.new_methods_count = 0
        self.detail_calls = 0
        self.skipped_existing = 0
        self.enriched_existing = 0

        self.task_case_sensitive_patterns = {}
        self.task_case_insensitive_patterns = {}
        self.method_case_sensitive_patterns = {}
        self.method_case_insensitive_patterns = {}

        self.rate_limiter = RateLimiter(DEFAULT_MAX_REQUESTS_PER_MINUTE)

        self.headers: Dict[str, str] = {
            "Accept": "application/json",
            "User-Agent": "paperswithcode.co backfill",
        }
        token = os.environ.get("PWC_HF_TOKEN")
        if token:
            self.headers["Authorization"] = f"Bearer {token}"
            self.logger.info("Using HF token from PWC_HF_TOKEN")
        else:
            self.logger.info(
                "No PWC_HF_TOKEN set; proceeding unauthenticated (lower rate limit)"
            )

    # ------------------------------------------------------------------
    # Checkpoint handling
    # ------------------------------------------------------------------

    def load_checkpoint(self) -> Dict:
        if self.args.reset or not CHECKPOINT_PATH.exists():
            return {}
        try:
            with CHECKPOINT_PATH.open() as f:
                return json.load(f)
        except Exception as e:
            self.logger.warning(f"Could not read checkpoint: {e}")
            return {}

    def save_checkpoint(self, next_cursor: Optional[str]) -> None:
        data = {
            "next_cursor": next_cursor,
            "papers_processed": self.processed_count,
            "papers_inserted": self.new_papers_count,
            "detail_calls": self.detail_calls,
            "last_run_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            with CHECKPOINT_PATH.open("w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            self.logger.error(f"Failed to write checkpoint: {e}")

    # ------------------------------------------------------------------
    # HF list pagination
    # ------------------------------------------------------------------

    async def fetch_page(
        self, session: aiohttp.ClientSession, cursor: Optional[str], limit: int
    ) -> Tuple[List[Dict], Optional[str]]:
        """Fetch one page of /api/papers; return (papers, next_cursor)."""
        params = {"limit": str(limit)}
        if cursor:
            params["cursor"] = cursor

        backoff_schedule = [1, 5, 30, 60]
        attempt = 0
        while True:
            await self.rate_limiter.wait()
            try:
                async with session.get(
                    HF_PAPERS_LIST,
                    params=params,
                    headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status == 200:
                        body = await response.json()
                        next_cursor = self._parse_next_cursor(
                            response.headers.get("Link")
                        )
                        return body, next_cursor

                    if response.status in (429, 500, 502, 503, 504):
                        if attempt >= len(backoff_schedule):
                            raise RuntimeError(
                                f"HF list page failed after retries: HTTP {response.status}"
                            )
                        sleep_for = backoff_schedule[attempt]
                        attempt += 1
                        self.logger.warning(
                            f"HF returned {response.status}; sleeping {sleep_for}s"
                        )
                        await asyncio.sleep(sleep_for)
                        continue

                    raise RuntimeError(
                        f"HF list page returned unexpected HTTP {response.status}"
                    )
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempt >= len(backoff_schedule):
                    raise
                sleep_for = backoff_schedule[attempt]
                attempt += 1
                self.logger.warning(f"HF request error '{e}', sleeping {sleep_for}s")
                await asyncio.sleep(sleep_for)

    @staticmethod
    def _parse_next_cursor(link_header: Optional[str]) -> Optional[str]:
        """Extract cursor=... from RFC 5988 Link header (rel=\"next\")."""
        if not link_header:
            return None
        for part in link_header.split(","):
            m = re.search(r'<([^>]+)>\s*;\s*rel="next"', part)
            if not m:
                continue
            url = m.group(1)
            cm = re.search(r"[?&]cursor=([^&]+)", url)
            if cm:
                from urllib.parse import unquote

                return unquote(cm.group(1))
        return None

    async def fetch_paper_detail_throttled(
        self, session: aiohttp.ClientSession, arxiv_id: str
    ) -> Optional[Dict]:
        """Wrapper around fetch_paper_detail that uses our rate limiter."""
        backoff_schedule = [1, 5, 30, 60]
        attempt = 0
        url = f"{HF_API_BASE}/api/papers/{arxiv_id}"
        while True:
            await self.rate_limiter.wait()
            try:
                async with session.get(
                    url,
                    headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as response:
                    if response.status == 200:
                        self.detail_calls += 1
                        return await response.json()

                    if response.status == 404:
                        self.logger.debug(f"Detail 404 for {arxiv_id}")
                        return None

                    if response.status in (429, 500, 502, 503, 504):
                        if attempt >= len(backoff_schedule):
                            self.logger.error(
                                f"Detail fetch for {arxiv_id} gave up after retries"
                            )
                            return None
                        sleep_for = backoff_schedule[attempt]
                        attempt += 1
                        self.logger.warning(
                            f"Detail HTTP {response.status} for {arxiv_id}; sleeping {sleep_for}s"
                        )
                        await asyncio.sleep(sleep_for)
                        continue

                    self.logger.warning(
                        f"Detail returned HTTP {response.status} for {arxiv_id}"
                    )
                    return None
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempt >= len(backoff_schedule):
                    self.logger.error(f"Detail fetch for {arxiv_id} failed: {e}")
                    return None
                sleep_for = backoff_schedule[attempt]
                attempt += 1
                self.logger.warning(
                    f"Detail error for {arxiv_id}: {e}; sleeping {sleep_for}s"
                )
                await asyncio.sleep(sleep_for)

    # ------------------------------------------------------------------
    # Per-paper processing
    # ------------------------------------------------------------------

    async def process_list_item(
        self, session: aiohttp.ClientSession, list_item: Dict
    ) -> None:
        arxiv_id = list_item.get("id")
        if not arxiv_id:
            self.logger.warning("List item missing arxiv id, skipping")
            return

        existing = self.get_paper_by_arxiv_id(arxiv_id)
        title = (list_item.get("title") or "").strip()
        authors = list_item.get("authors") or []

        if existing is None:
            await self._insert_new_paper(session, arxiv_id, title, authors)
            return

        if self.args.no_enrich_existing:
            self.skipped_existing += 1
            return

        paper_id = existing["id"]

        # Free wins from the list payload (no extra API call):
        if authors:
            self.process_authors(paper_id, authors, link_to_paper=False)

        if not self.paper_has_complete_urls(paper_id):
            await self._enrich_existing_paper_urls(session, paper_id, arxiv_id)
        else:
            self.skipped_existing += 1

    async def _insert_new_paper(
        self,
        session: aiohttp.ClientSession,
        arxiv_id: str,
        title_hint: str,
        authors: List[Dict],
    ) -> None:
        detail = await self.fetch_paper_detail_throttled(session, arxiv_id)
        if not detail:
            self.logger.warning(
                f"No detail returned for new paper {arxiv_id}; skipping insert"
            )
            return

        title = (detail.get("title") or title_hint or "").strip()
        abstract = (detail.get("summary") or "").strip()
        date_published = self.parse_published_at(detail.get("publishedAt"))
        tldr = detail.get("ai_summary")

        if self.args.dry_run:
            self.logger.info(f"[dry-run] Would insert paper {arxiv_id}: {title[:80]}")
            return

        paper_id = self.insert_paper(arxiv_id, title, abstract, date_published, tldr)
        if not paper_id:
            return

        self.new_papers_count += 1
        self.logger.info(f"Added new paper {arxiv_id}: {title[:80]}")

        # Prefer the list-payload authors (richer HF user data); fall back to detail.
        author_data = authors or detail.get("authors") or []
        self.process_authors(paper_id, author_data)

        if not self.args.skip_task_tagging:
            self.tag_paper_with_tasks(paper_id, title, abstract)
            self.tag_paper_with_methods(paper_id, title, abstract)

        github_repo = detail.get("githubRepo")
        if github_repo:
            self.insert_repository(paper_id, github_repo)

        project_page = detail.get("projectPage")
        if project_page:
            await self._insert_project_page_async(paper_id, project_page)

    async def _insert_project_page_async(self, paper_id: int, project_url: str) -> None:
        """Verify a project page URL asynchronously, then insert it."""
        if not await verify_url(project_url):
            self.logger.warning(f"Invalid project page URL: {project_url}")
            return
        self.insert_project_page(paper_id, project_url, skip_verification=True)

    async def _enrich_existing_paper_urls(
        self, session: aiohttp.ClientSession, paper_id: int, arxiv_id: str
    ) -> None:
        detail = await self.fetch_paper_detail_throttled(session, arxiv_id)
        if not detail:
            return

        if self.args.dry_run:
            self.logger.info(
                f"[dry-run] Would enrich {arxiv_id} (github={bool(detail.get('githubRepo'))}, "
                f"projectPage={bool(detail.get('projectPage'))}, tldr={bool(detail.get('ai_summary'))})"
            )
            return

        github_repo = detail.get("githubRepo")
        if github_repo:
            self.insert_repository(paper_id, github_repo)

        project_page = detail.get("projectPage")
        if project_page:
            await self._insert_project_page_async(paper_id, project_page)

        tldr = detail.get("ai_summary")
        if tldr:
            self.update_paper_tldr_if_null(paper_id, tldr)

        self.enriched_existing += 1

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self):
        if not self.args.skip_task_tagging:
            self.load_task_keywords()
            self.load_method_keywords()
        else:
            self.logger.info(
                "Skipping task/method keyword tagging (per --skip-task-tagging)"
            )

        asyncio.run(self._run_async())

    async def _run_async(self):
        checkpoint = self.load_checkpoint()
        cursor: Optional[str] = self.args.start_cursor or checkpoint.get("next_cursor")
        if cursor:
            self.logger.info(f"Resuming from cursor: {cursor[:60]}...")
        else:
            self.logger.info("Starting from the beginning of the HF papers stream")

        page_index = 0
        connector = aiohttp.TCPConnector(limit=4)
        async with aiohttp.ClientSession(connector=connector) as session:
            while True:
                if (
                    self.args.max_papers
                    and self.processed_count >= self.args.max_papers
                ):
                    self.logger.info(
                        f"Reached --max-papers={self.args.max_papers}, stopping"
                    )
                    break

                try:
                    page, next_cursor = await self.fetch_page(
                        session, cursor, DEFAULT_PAGE_SIZE
                    )
                except Exception as e:
                    self.logger.error(f"Failed to fetch page (cursor={cursor}): {e}")
                    self.save_checkpoint(cursor)
                    raise

                if not page:
                    self.logger.info("HF returned an empty page; reached the end.")
                    self.save_checkpoint(None)
                    break

                page_index += 1
                page_new_before = self.new_papers_count
                page_enriched_before = self.enriched_existing
                page_skipped_before = self.skipped_existing

                for list_item in page:
                    if (
                        self.args.max_papers
                        and self.processed_count >= self.args.max_papers
                    ):
                        break
                    try:
                        await self.process_list_item(session, list_item)
                    except Exception as e:
                        self.error_count += 1
                        arxiv_id = list_item.get("id", "unknown")
                        self.logger.error(f"Failed to process paper {arxiv_id}: {e}")
                    finally:
                        self.processed_count += 1

                page_new = self.new_papers_count - page_new_before
                page_enriched = self.enriched_existing - page_enriched_before
                page_skipped = self.skipped_existing - page_skipped_before
                self.logger.info(
                    f"Page {page_index}: processed={len(page)}, new={page_new}, "
                    f"enriched={page_enriched}, skipped={page_skipped}, "
                    f"total_processed={self.processed_count}, "
                    f"total_new={self.new_papers_count}, detail_calls={self.detail_calls}"
                )

                self.save_checkpoint(next_cursor)

                if not next_cursor:
                    self.logger.info("No next cursor returned; reached the end.")
                    break

                cursor = next_cursor

        self.logger.info("Backfill summary:")
        self.logger.info(f"  - Pages fetched: {page_index}")
        self.logger.info(f"  - Papers processed: {self.processed_count}")
        self.logger.info(f"  - New papers added: {self.new_papers_count}")
        self.logger.info(f"  - Existing papers enriched: {self.enriched_existing}")
        self.logger.info(f"  - Existing papers skipped: {self.skipped_existing}")
        self.logger.info(f"  - New authors added: {self.new_authors_count}")
        self.logger.info(f"  - New repositories added: {self.new_repos_count}")
        self.logger.info(f"  - New project pages added: {self.new_pages_count}")
        self.logger.info(f"  - New task links added: {self.new_tasks_count}")
        self.logger.info(f"  - New method links added: {self.new_methods_count}")
        self.logger.info(f"  - Detail API calls: {self.detail_calls}")
        self.logger.info(f"  - Errors: {self.error_count}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--start-cursor",
        type=str,
        default=None,
        help="Manually start from a specific HF cursor (overrides checkpoint).",
    )
    parser.add_argument(
        "--max-papers",
        type=int,
        default=None,
        help="Stop after processing this many papers (smoke test mode).",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Ignore the checkpoint file and start from page 1.",
    )
    parser.add_argument(
        "--no-enrich-existing",
        action="store_true",
        help="Do not fetch detail or enrich existing papers; insert-only mode.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log what would happen without writing to the database.",
    )
    parser.add_argument(
        "--skip-task-tagging",
        action="store_true",
        help="Skip keyword-based task/method tagging on inserts.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    job = HuggingFaceBackfillJob(args)
    success = job.execute()
    sys.exit(0 if success else 1)
