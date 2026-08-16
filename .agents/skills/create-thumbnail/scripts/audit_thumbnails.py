#!/usr/bin/env python3
"""Read-only audit of public thumbnails for papers or benchmark leaderboards."""

from __future__ import annotations

import argparse
import json
import re
from urllib.parse import urljoin

import httpx
from sqlalchemy import text

from backend.database.connection import get_engine


DEFAULT_EXTERNAL_RE = re.compile(r"/external_\d+\.jpg(?:\?|$)")


def resolve_ids(papers: list[int], benchmark: str | None) -> list[int]:
    if papers:
        return sorted(set(papers))
    with get_engine().connect() as connection:
        dataset_id = connection.execute(
            text("SELECT id FROM datasets WHERE slug = :slug"), {"slug": benchmark}
        ).scalar_one_or_none()
        if dataset_id is None:
            raise SystemExit(f"benchmark {benchmark!r} not found")
        return list(
            connection.execute(
                text(
                    "SELECT DISTINCT paper_id FROM evaluations "
                    "WHERE dataset_id = :dataset_id ORDER BY paper_id"
                ),
                {"dataset_id": dataset_id},
            ).scalars()
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--paper", action="append", type=int, default=[])
    scope.add_argument("--benchmark")
    parser.add_argument("--base-url", default="https://paperswithcode.co")
    args = parser.parse_args()

    ids = resolve_ids(args.paper, args.benchmark)
    rows = []
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        for paper_id in ids:
            api = client.get(f"{args.base_url}/api/v1/papers/{paper_id}")
            api.raise_for_status()
            paper = api.json()
            thumbnail_url = paper.get("thumbnail_url")
            content_type = None
            status_code = None
            if not thumbnail_url:
                status = "missing_url"
            else:
                image = client.get(urljoin(args.base_url, thumbnail_url))
                status_code = image.status_code
                content_type = image.headers.get("content-type")
                if status_code != 200 or not (content_type or "").startswith("image/"):
                    status = "broken"
                elif paper.get("source") == "external" and DEFAULT_EXTERNAL_RE.search(
                    thumbnail_url
                ):
                    status = "review_default_external"
                else:
                    status = "healthy"
            rows.append(
                {
                    "paper_id": paper_id,
                    "title": paper.get("title"),
                    "source": paper.get("source"),
                    "thumbnail_url": thumbnail_url,
                    "status": status,
                    "http_status": status_code,
                    "content_type": content_type,
                }
            )

    print(
        json.dumps(
            {
                "scope": {"papers": args.paper, "benchmark": args.benchmark},
                "count": len(rows),
                "summary": {
                    name: sum(row["status"] == name for row in rows)
                    for name in (
                        "healthy",
                        "missing_url",
                        "broken",
                        "review_default_external",
                    )
                },
                "papers": rows,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
