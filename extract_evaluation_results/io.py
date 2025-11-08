"""
IO utilities for the evaluation extraction pipeline.

This module provides shared functions for:
- Cache directory management
- JSON and text file reading/writing
- Retry logic with exponential backoff
"""

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any, Callable, Awaitable, Optional, TypeVar, Union

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Default retry configuration
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BASE_DELAY = 5.0


def get_markdown_cache_path(arxiv_id: str) -> Path:
    """Get the path to the cached markdown file for a given arxiv_id."""
    # Sanitize arxiv_id for filename (replace / with _)
    safe_arxiv_id = arxiv_id.replace("/", "_").replace(":", "_")
    # Create subfolder for this arxiv_id
    cache_dir = Path("backend/outputs/evaluation_results") / safe_arxiv_id
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "markdown.md"


async def load_cached_markdown(arxiv_id: str) -> Optional[str]:
    """Load cached markdown if it exists."""
    cache_path = get_markdown_cache_path(arxiv_id)
    if cache_path.exists():
        logger.info(f"Found cached markdown for {arxiv_id} at {cache_path}")
        try:
            return cache_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to read cached markdown: {e}")
            return None
    return None


async def save_markdown_to_cache(arxiv_id: str, markdown: str) -> None:
    """Save markdown to cache."""
    cache_path = get_markdown_cache_path(arxiv_id)
    try:
        cache_path.write_text(markdown, encoding="utf-8")
        logger.info(f"Saved markdown to cache: {cache_path}")
    except Exception as e:
        logger.warning(f"Failed to save markdown to cache: {e}")


def get_cache_dir(arxiv_id: str) -> Path:
    """
    Get the cache directory for a given arxiv_id.

    Args:
        arxiv_id: The ArXiv ID of the paper

    Returns:
        Path to the cache directory (creates it if it doesn't exist)
    """
    cache_dir = Path("backend/outputs/evaluation_results") / arxiv_id
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def read_json_if_exists(path: Path) -> Optional[Union[dict, list]]:
    """
    Read JSON from path if it exists, otherwise return None.

    Args:
        path: Path to the JSON file

    Returns:
        Parsed JSON data (dict or list) if file exists and is valid, None otherwise
    """
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to read cache file {path}: {e}")
            return None
    return None


def write_json(path: Path, data: Union[dict, list]) -> None:
    """
    Write data as JSON to path.

    Args:
        path: Path to write to
        data: Data to serialize as JSON
    """
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def write_text(path: Path, text: str) -> None:
    """
    Write text to path.

    Args:
        path: Path to write to
        text: Text content to write
    """
    path.write_text(text)


def read_text_if_exists(path: Path) -> Optional[str]:
    """
    Read text from path if it exists, otherwise return None.

    Args:
        path: Path to the text file

    Returns:
        Text content if file exists, None otherwise
    """
    if path.exists():
        try:
            return path.read_text()
        except IOError as e:
            logger.warning(f"Failed to read file {path}: {e}")
            return None
    return None


async def cached_json(
    path: Path, resume: bool, compute: Callable[[], Awaitable[Union[dict, list]]]
) -> Union[dict, list]:
    """
    Unified read-or-compute-and-write flow for JSON cache.

    If resume is True and cache exists, return cached data.
    Otherwise, compute the data, write to cache, and return it.

    Args:
        path: Path to the cache file
        resume: Whether to use cached data if available
        compute: Async function that computes the data

    Returns:
        The cached or computed data
    """
    if resume:
        cached = read_json_if_exists(path)
        if cached is not None:
            logger.info(f"Using cache: {path.name}")
            return cached
    data = await compute()
    write_json(path, data)
    logger.info(f"Cached: {path.name}")
    return data


async def cached_text(
    path: Path, resume: bool, compute: Callable[[], Awaitable[str]]
) -> str:
    """
    Unified read-or-compute-and-write flow for text cache.

    If resume is True and cache exists, return cached text.
    Otherwise, compute the text, write to cache, and return it.

    Args:
        path: Path to the cache file
        resume: Whether to use cached data if available
        compute: Async function that computes the text

    Returns:
        The cached or computed text
    """
    if resume:
        cached = read_text_if_exists(path)
        if cached is not None:
            logger.info(f"Using cache: {path.name}")
            return cached
    text = await compute()
    write_text(path, text)
    logger.info(f"Cached: {path.name}")
    return text


async def async_run_with_retry(
    label: str,
    coro_fn: Callable[[], Awaitable[T]],
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_RETRY_BASE_DELAY,
    is_rate_limit: Callable[[str], bool] = lambda s: "429" in s
    or "rate limit" in s.lower(),
) -> T:
    """
    Centralized retry/backoff logic for async operations.

    Retries the given coroutine function on failure, with exponential backoff.
    Special handling for rate limit errors (429 or "rate limit" in message).

    Args:
        label: Label for logging (e.g., "Step 2: COCO")
        coro_fn: Async function to retry
        max_retries: Maximum number of retry attempts
        base_delay: Base delay for exponential backoff (seconds)
        is_rate_limit: Function to detect rate limit errors from exception message

    Returns:
        The result of the coroutine function

    Raises:
        The last exception if all retries fail
    """
    for attempt in range(max_retries):
        try:
            return await coro_fn()
        except Exception as e:
            msg = str(e)
            if is_rate_limit(msg) and attempt < max_retries - 1:
                wait = base_delay * (2**attempt)
                # Check if error message contains specific wait time
                m = re.search(r"Please try again in ([\d.]+)s", msg)
                if m:
                    wait = float(m.group(1)) + 1.0
                logger.warning(f"{label}: rate limited, retrying in {wait:.1f}s")
                await asyncio.sleep(wait)
            else:
                logger.error(f"{label}: {type(e).__name__}: {msg}")
                raise


async def map_async_rate_limited(
    items: list[T],
    worker: Callable[[T], Awaitable[Any]],
    *,
    max_concurrent: int,
    delay_between: float,
) -> list[Any]:
    """
    Map items through async worker with semaphore and staggered starts.

    This function processes items in parallel with:
    - Concurrency limiting via semaphore
    - Staggered start times to avoid rate limits

    Args:
        items: List of items to process
        worker: Async function to process each item
        max_concurrent: Maximum number of concurrent workers
        delay_between: Delay between starting each worker (seconds)

    Returns:
        List of results (same order as items)
    """
    sem = asyncio.Semaphore(max_concurrent)

    async def wrapped(item: T) -> Any:
        async with sem:
            return await worker(item)

    tasks = []
    for i, it in enumerate(items):
        tasks.append(asyncio.create_task(wrapped(it)))
        if i < len(items) - 1:
            await asyncio.sleep(delay_between)
    return await asyncio.gather(*tasks)
