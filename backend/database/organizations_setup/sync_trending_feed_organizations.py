#!/usr/bin/env python3
"""Discover and sync organizations represented in top trending paper feeds.

The discovery pass reads the first 100 trending papers from the homepage and
from every task, conference, and method page. For untagged arXiv papers it uses
the same Hugging Face paper API contract as ``hf papers info`` to discover an
organization handle. The apply pass calls the authenticated Papers With Code
organization sync endpoint once per unique handle.

The command is a dry run unless ``--apply`` is supplied. Resolution results are
checkpointed outside the repository so interrupted runs can resume safely.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import httpx

from backend.utils.hf_utils import build_hf_headers

DEFAULT_READ_API = "https://paperswithcode.co/api/v1"
DEFAULT_HF_API = "https://huggingface.co"
DEFAULT_CACHE = Path("/tmp/pwc-trending-feed-organizations.json")
FEED_PAGE_SIZE = 100


def _retry_delay(response: httpx.Response, attempt: int) -> int:
    retry_after = response.headers.get("retry-after")
    reset_match = re.search(r"(?:^|;)t=(\d+)", response.headers.get("ratelimit", ""))
    if retry_after and retry_after.isdigit():
        return int(retry_after) + 1
    if reset_match:
        return int(reset_match.group(1)) + 1
    return 2**attempt


async def _get_json(
    client: httpx.AsyncClient,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    attempts: int = 4,
) -> Any:
    for attempt in range(attempts):
        response = await client.get(path, params=params)
        if response.status_code not in {429, 500, 502, 503, 504}:
            response.raise_for_status()
            return response.json()
        if attempt + 1 < attempts:
            await asyncio.sleep(_retry_delay(response, attempt))
    response.raise_for_status()
    raise AssertionError("unreachable")


async def _list_paginated_entities(
    client: httpx.AsyncClient, path: str, *, page_size: int
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    page = 1
    while True:
        payload = await _get_json(
            client, path, params={"page": page, "page_size": page_size}
        )
        results.extend(payload.get("results") or [])
        if not payload.get("next_page"):
            return results
        page += 1


async def _collect_feed_papers(
    read_api_base_url: str, concurrency: int
) -> tuple[dict[str, dict[str, Any]], dict[str, set[str]], dict[str, int]]:
    timeout = httpx.Timeout(60)
    limits = httpx.Limits(
        max_connections=concurrency, max_keepalive_connections=concurrency
    )
    async with httpx.AsyncClient(
        base_url=read_api_base_url.rstrip("/"), timeout=timeout, limits=limits
    ) as client:
        tasks, methods, conference_payload = await asyncio.gather(
            _list_paginated_entities(client, "/tasks/", page_size=100),
            _list_paginated_entities(client, "/methods/", page_size=500),
            _get_json(client, "/conferences/"),
        )
        conferences = conference_payload.get("results") or []
        feeds: list[tuple[str, str, dict[str, Any]]] = [
            (
                "homepage",
                "/papers/",
                {
                    "page": 1,
                    "page_size": FEED_PAGE_SIZE,
                    "order_by": "trending",
                    "order_dir": "desc",
                },
            )
        ]
        feeds.extend(
            (
                "tasks",
                f"/tasks/{task['id']}/papers",
                {
                    "page": 1,
                    "page_size": FEED_PAGE_SIZE,
                    "latest_only": "true",
                    "order_by": "trending",
                    "order_dir": "desc",
                },
            )
            for task in tasks
        )
        feeds.extend(
            (
                "conferences",
                f"/conferences/{conference['slug']}/papers",
                {
                    "page": 1,
                    "page_size": FEED_PAGE_SIZE,
                    "latest_only": "true",
                    "order_by": "trending",
                    "order_dir": "desc",
                },
            )
            for conference in conferences
        )
        feeds.extend(
            (
                "methods",
                f"/methods/{method['id']}/papers",
                {
                    "page": 1,
                    "page_size": FEED_PAGE_SIZE,
                    "latest_only": "true",
                    "order_by": "trending",
                    "order_dir": "desc",
                },
            )
            for method in methods
        )

        semaphore = asyncio.Semaphore(concurrency)

        async def fetch_feed(
            feed_type: str, path: str, params: dict[str, Any]
        ) -> tuple[str, list[dict[str, Any]]]:
            async with semaphore:
                payload = await _get_json(client, path, params=params)
            return feed_type, payload.get("results") or []

        responses = await asyncio.gather(
            *(fetch_feed(feed_type, path, params) for feed_type, path, params in feeds)
        )

    papers: dict[str, dict[str, Any]] = {}
    ids_by_type: dict[str, set[str]] = defaultdict(set)
    for feed_type, rows in responses:
        for paper in rows:
            paper_id = str(paper["id"])
            papers.setdefault(paper_id, paper)
            ids_by_type[feed_type].add(paper_id)
    feed_counts = {
        "homepage": 1,
        "tasks": len(tasks),
        "conferences": len(conferences),
        "methods": len(methods),
    }
    return papers, ids_by_type, feed_counts


def _load_cache(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"Resolution cache {path} must contain a JSON object")
    return payload


def _save_cache(path: Path, cache: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(cache, sort_keys=True))
    temporary.replace(path)


async def _resolve_organizations(
    arxiv_ids: list[str],
    *,
    cache_path: Path,
    concurrency: int,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
    cache = _load_cache(cache_path)
    pending = [arxiv_id for arxiv_id in arxiv_ids if arxiv_id not in cache]
    errors: list[dict[str, str]] = []
    completed = 0
    lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(concurrency)
    timeout = httpx.Timeout(30)
    limits = httpx.Limits(
        max_connections=concurrency, max_keepalive_connections=concurrency
    )

    async with httpx.AsyncClient(
        base_url=DEFAULT_HF_API,
        headers=build_hf_headers(),
        timeout=timeout,
        limits=limits,
    ) as client:

        async def resolve(arxiv_id: str) -> None:
            nonlocal completed
            async with semaphore:
                try:
                    response = None
                    for attempt in range(4):
                        response = await client.get(f"/api/papers/{arxiv_id}")
                        if response.status_code not in {429, 500, 502, 503, 504}:
                            break
                        if attempt < 3:
                            await asyncio.sleep(_retry_delay(response, attempt))
                    assert response is not None
                    if response.status_code == 404:
                        result = {"status": "not_found", "organization": None}
                    else:
                        response.raise_for_status()
                        payload = response.json()
                        organization = payload.get("organization")
                        handle = (
                            organization.get("name")
                            if isinstance(organization, dict)
                            else None
                        )
                        result = {
                            "status": "organization" if handle else "no_organization",
                            "organization": handle,
                        }
                except Exception as exc:
                    async with lock:
                        errors.append(
                            {"arxiv_id": arxiv_id, "error": type(exc).__name__}
                        )
                    return

            async with lock:
                cache[arxiv_id] = result
                completed += 1
                if completed % 250 == 0:
                    _save_cache(cache_path, cache)
                    print(
                        json.dumps(
                            {
                                "resolution_progress": completed,
                                "resolution_pending": len(pending) - completed,
                            },
                            sort_keys=True,
                        ),
                        flush=True,
                    )

        await asyncio.gather(*(resolve(arxiv_id) for arxiv_id in pending))

    _save_cache(cache_path, cache)
    return cache, errors


async def _sync_handles(
    handles: list[str],
    *,
    write_api_base_url: str,
    admin_token: str,
    skip_missing_papers: bool,
    skip_existing_organizations: bool,
    sync_delay: float,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    headers = {"X-Admin-Token": admin_token}
    async with httpx.AsyncClient(
        base_url=write_api_base_url.rstrip("/"),
        headers=headers,
        timeout=httpx.Timeout(600),
    ) as client:
        pending_handles = handles
        if skip_existing_organizations:
            payload = await _get_json(client, "/organizations/")
            existing_hf_slugs = {
                str(organization["hf_slug"]).lower()
                for organization in payload.get("results") or []
                if organization.get("hf_slug")
            }
            pending_handles = [
                handle for handle in handles if handle.lower() not in existing_hf_slugs
            ]
            print(
                json.dumps(
                    {
                        "existing_organizations_skipped": len(handles)
                        - len(pending_handles),
                        "organizations_remaining": len(pending_handles),
                    },
                    sort_keys=True,
                ),
                flush=True,
            )

        loop = asyncio.get_running_loop()
        for index, handle in enumerate(pending_handles, start=1):
            started_at = loop.time()
            response = await client.post(
                "/organizations/sync",
                json={
                    "hf_slug": handle,
                    "skip_missing_papers": skip_missing_papers,
                },
            )
            if response.is_success:
                result = response.json()
                result["status"] = "synced"
            else:
                result = {
                    "organization": handle,
                    "status": "failed",
                    "http_status": response.status_code,
                    "detail": response.text[:500],
                }
            results.append(result)
            print(
                json.dumps(
                    {
                        "sync_progress": index,
                        "sync_total": len(pending_handles),
                        **result,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            delay = sync_delay - (loop.time() - started_at)
            if delay > 0 and index < len(pending_handles):
                await asyncio.sleep(delay)
    return results


async def run(args: argparse.Namespace) -> int:
    papers, ids_by_type, feed_counts = await _collect_feed_papers(
        args.read_api_base_url, args.feed_concurrency
    )
    untagged = [paper for paper in papers.values() if not paper.get("organizations")]
    arxiv_ids = sorted(
        {str(paper["arxiv_id"]) for paper in untagged if paper.get("arxiv_id")}
    )
    discovery = {
        "feed_counts": feed_counts,
        "unique_papers_by_type": {
            key: len(value) for key, value in sorted(ids_by_type.items())
        },
        "unique_papers": len(papers),
        "already_tagged": len(papers) - len(untagged),
        "untagged": len(untagged),
        "untagged_with_arxiv": len(arxiv_ids),
        "untagged_without_arxiv": sum(not paper.get("arxiv_id") for paper in untagged),
    }
    print(json.dumps({"discovery": discovery}, sort_keys=True), flush=True)

    cache, resolution_errors = await _resolve_organizations(
        arxiv_ids,
        cache_path=args.cache,
        concurrency=args.hf_concurrency,
    )
    relevant = {
        arxiv_id: cache[arxiv_id] for arxiv_id in arxiv_ids if arxiv_id in cache
    }
    handles = sorted(
        {
            str(result["organization"])
            for result in relevant.values()
            if result.get("organization")
        },
        key=str.lower,
    )
    resolution = {
        "status_counts": dict(
            Counter(result["status"] for result in relevant.values())
        ),
        "errors": len(resolution_errors),
        "unique_organizations": len(handles),
    }
    print(json.dumps({"resolution": resolution}, sort_keys=True), flush=True)

    sync_results: list[dict[str, Any]] = []
    if args.apply:
        admin_token = os.environ.get("PWC_ADMIN_API_TOKEN", "")
        if not admin_token:
            raise RuntimeError("PWC_ADMIN_API_TOKEN is required with --apply")
        sync_results = await _sync_handles(
            handles,
            write_api_base_url=args.write_api_base_url,
            admin_token=admin_token,
            skip_missing_papers=args.skip_missing_papers,
            skip_existing_organizations=args.skip_existing_organizations,
            sync_delay=args.sync_delay,
        )

    totals: Counter[str] = Counter()
    for result in sync_results:
        if result.get("status") == "synced":
            for key in (
                "fetched",
                "existing",
                "imported",
                "linked",
                "already_linked",
                "failed",
            ):
                totals[key] += int(result.get(key) or 0)
    summary = {
        "applied": args.apply,
        "organizations_discovered": len(handles),
        "organizations_synced": sum(
            result.get("status") == "synced" for result in sync_results
        ),
        "organizations_failed": sum(
            result.get("status") == "failed" for result in sync_results
        ),
        "sync_totals": dict(totals),
        "unresolved": {
            **resolution["status_counts"],
            "errors": len(resolution_errors),
            "without_arxiv": discovery["untagged_without_arxiv"],
        },
    }
    print(json.dumps({"summary": summary}, sort_keys=True), flush=True)
    return 1 if resolution_errors or summary["organizations_failed"] else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--read-api-base-url", default=DEFAULT_READ_API)
    parser.add_argument("--write-api-base-url", default="http://127.0.0.1:8010/api/v1")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--feed-concurrency", type=int, default=12)
    parser.add_argument("--hf-concurrency", type=int, default=16)
    parser.add_argument("--skip-missing-papers", action="store_true")
    parser.add_argument("--skip-existing-organizations", action="store_true")
    parser.add_argument(
        "--sync-delay",
        type=float,
        default=3.2,
        help="Minimum seconds between organization sync starts (default: 3.2)",
    )
    args = parser.parse_args()
    if not 1 <= args.feed_concurrency <= 32:
        parser.error("--feed-concurrency must be between 1 and 32")
    if not 1 <= args.hf_concurrency <= 32:
        parser.error("--hf-concurrency must be between 1 and 32")
    if args.sync_delay < 0:
        parser.error("--sync-delay must be non-negative")
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
