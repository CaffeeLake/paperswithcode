"""Batched OpenAlex lookups for historical method-reference backfills."""

from __future__ import annotations

import re
import sys
import time
from dataclasses import dataclass, field
from typing import Iterable

import httpx

OPENALEX_WORKS_URL = "https://api.openalex.org/works"
ARXIV_URL_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/([^/?#]+)", re.IGNORECASE)
MAX_ARXIV_IDS_PER_REQUEST = 50


@dataclass
class OpenAlexWorkBatch:
    work_ids_by_arxiv: dict[str, set[str]] = field(default_factory=dict)
    references_by_arxiv: dict[str, set[str]] = field(default_factory=dict)


class OpenAlexReferenceClient:
    """Resolve arXiv papers and their bibliographies in bounded list requests."""

    provider_name = "openalex"

    def __init__(
        self,
        *,
        api_key: str = "",
        request_delay: float = 0.1,
        request_timeout: float = 30.0,
        max_retries: int = 5,
        client: httpx.Client | None = None,
        sleep=time.sleep,
    ):
        self.api_key = api_key
        self.request_delay = request_delay
        self.max_retries = max_retries
        self._sleep = sleep
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=request_timeout,
            headers={"User-Agent": "paperswithcode-method-backfill/1.0"},
        )
        self.api_calls = 0
        self.api_errors = 0
        self.rate_limit_hits = 0
        self.retry_attempts = 0
        self.failed_requests = 0

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _request(
        self,
        url: str,
        params: dict[str, object],
        *,
        not_found_is_empty: bool = False,
    ) -> dict | None:
        if self.api_key:
            params["api_key"] = self.api_key

        for attempt in range(self.max_retries):
            self.api_calls += 1
            try:
                response = self._client.get(url, params=params)
            except httpx.HTTPError as exc:
                self.api_errors += 1
                print(f"  ! OpenAlex HTTP error: {exc}", file=sys.stderr)
            else:
                if response.status_code == 200:
                    self._sleep(self.request_delay)
                    return response.json()
                if response.status_code == 404 and not_found_is_empty:
                    self._sleep(self.request_delay)
                    return {}
                if response.status_code == 429:
                    self.rate_limit_hits += 1
                elif 500 <= response.status_code < 600:
                    self.api_errors += 1
                else:
                    self.api_errors += 1
                    self.failed_requests += 1
                    print(
                        f"  ! OpenAlex unexpected status {response.status_code}: "
                        f"{response.text[:200]}",
                        file=sys.stderr,
                    )
                    return None

            if attempt + 1 < self.max_retries:
                self.retry_attempts += 1
                self._sleep(self.request_delay * (2 ** (attempt + 1)))

        self.failed_requests += 1
        print("  ! OpenAlex request failed after retries", file=sys.stderr)
        return None

    def _request_batch(self, arxiv_ids: list[str]) -> dict | None:
        landing_urls = [
            url
            for arxiv_id in arxiv_ids
            for url in (
                f"http://arxiv.org/abs/{arxiv_id}",
                f"https://arxiv.org/abs/{arxiv_id}",
            )
        ]
        return self._request(
            OPENALEX_WORKS_URL,
            {
                "filter": "locations.landing_page_url:" + "|".join(landing_urls),
                "per_page": 100,
                "select": "id,locations,referenced_works",
            },
        )

    def _request_arxiv_doi(self, arxiv_id: str) -> dict | None:
        return self._request(
            f"{OPENALEX_WORKS_URL}/https://doi.org/10.48550/arxiv.{arxiv_id}",
            {"select": "id,referenced_works"},
            not_found_is_empty=True,
        )

    def fetch_works(self, arxiv_ids: Iterable[str]) -> OpenAlexWorkBatch | None:
        """Return all OpenAlex IDs and reference IDs for each requested arXiv ID."""
        requested = list(dict.fromkeys(arxiv_id for arxiv_id in arxiv_ids if arxiv_id))
        batch = OpenAlexWorkBatch()
        for offset in range(0, len(requested), MAX_ARXIV_IDS_PER_REQUEST):
            chunk = requested[offset : offset + MAX_ARXIV_IDS_PER_REQUEST]
            payload = self._request_batch(chunk)
            if payload is None:
                return None
            chunk_set = set(chunk)
            for work in payload.get("results") or []:
                matched_arxiv_ids = {
                    match.group(1).removesuffix(".pdf")
                    for location in work.get("locations") or []
                    if (
                        match := ARXIV_URL_RE.search(
                            location.get("landing_page_url") or ""
                        )
                    )
                } & chunk_set
                for arxiv_id in matched_arxiv_ids:
                    batch.work_ids_by_arxiv.setdefault(arxiv_id, set()).add(work["id"])
                    batch.references_by_arxiv.setdefault(arxiv_id, set()).update(
                        work.get("referenced_works") or []
                    )
            for arxiv_id in chunk:
                if arxiv_id in batch.work_ids_by_arxiv:
                    continue
                work = self._request_arxiv_doi(arxiv_id)
                if work is None:
                    return None
                if not work:
                    continue
                batch.work_ids_by_arxiv.setdefault(arxiv_id, set()).add(work["id"])
                batch.references_by_arxiv.setdefault(arxiv_id, set()).update(
                    work.get("referenced_works") or []
                )
        return batch
