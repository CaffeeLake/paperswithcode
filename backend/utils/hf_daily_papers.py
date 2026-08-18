"""One fail-closed pagination contract for Hugging Face daily-paper cohorts."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import aiohttp

HF_DAILY_PAPERS_URL = "https://huggingface.co/api/daily_papers"
HF_DAILY_PAPERS_PAGE_SIZE = 50


async def fetch_hf_daily_papers(
    cohort_date: str,
    *,
    session_factory: Callable[..., Any] = aiohttp.ClientSession,
    logger: Any | None = None,
) -> list[dict]:
    """Fetch the complete cohort, deduplicated in first-seen upstream order."""
    papers: list[dict] = []
    seen_arxiv_ids: set[str] = set()
    async with session_factory() as session:
        page = 0
        while True:
            params = {
                "date": cohort_date,
                "p": page,
                "limit": HF_DAILY_PAPERS_PAGE_SIZE,
                "sort": "publishedAt",
            }
            try:
                async with session.get(
                    HF_DAILY_PAPERS_URL,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status == 400 and page == 0:
                        if logger:
                            logger.info(
                                "No daily-papers list yet for %s (HTTP 400)",
                                cohort_date,
                            )
                        return []
                    if response.status != 200:
                        message = (
                            "Failed to fetch complete daily-papers cohort "
                            f"for {cohort_date}: HTTP {response.status} on page {page}"
                        )
                        if logger:
                            logger.error(message)
                        raise RuntimeError(message)
                    page_papers = await response.json()
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                message = (
                    "Failed to fetch complete daily-papers cohort "
                    f"for {cohort_date} on page {page}: {exc}"
                )
                if logger:
                    logger.error(message)
                raise RuntimeError(message) from exc
            if not isinstance(page_papers, list):
                raise RuntimeError(
                    f"HF daily-papers response for {cohort_date} is not a list"
                )
            for paper_data in page_papers:
                arxiv_id = paper_data.get("paper", {}).get("id")
                if arxiv_id is not None:
                    if arxiv_id in seen_arxiv_ids:
                        continue
                    seen_arxiv_ids.add(arxiv_id)
                papers.append(paper_data)
            if len(page_papers) < HF_DAILY_PAPERS_PAGE_SIZE:
                return papers
            page += 1
