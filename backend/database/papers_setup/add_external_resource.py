"""
CLI for ingesting an external (non-ArXiv) resource.

Examples:

```bash
# AI-assisted: fetch the URL and let the LLM extract metadata.
uv run --env-file backend/keys.env python -m \\
    backend.database.papers_setup.add_external_resource \\
    --url https://www.zyphra.com/zaya1-vl-8b-technical-report

# Manual override (skip AI extraction):
uv run --env-file backend/keys.env python -m \\
    backend.database.papers_setup.add_external_resource \\
    --url https://example.com/post \\
    --title "Some Title" \\
    --date-published 2026-05-01 \\
    --abstract "Short summary" \\
    --skip-extraction
```
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import date as date_type
from typing import Optional

from backend.database.connection import db_manager
from backend.services.external_resource_service import (
    ExternalResourceError,
    ExternalResourceInput,
    ExternalResourceService,
)


logger = logging.getLogger(__name__)


def _parse_date(value: Optional[str]) -> Optional[date_type]:
    if value is None:
        return None
    return date_type.fromisoformat(value)


async def run(args: argparse.Namespace) -> int:
    session = db_manager.session_local()
    try:
        service = ExternalResourceService(session)

        if args.skip_extraction:
            if not args.title or not args.date_published:
                raise ExternalResourceError(
                    "--title and --date-published are required when "
                    "--skip-extraction is set"
                )
            payload = ExternalResourceInput(
                source_url=args.url,
                title=args.title,
                abstract=args.abstract,
                authors=args.authors or [],
                date_published=_parse_date(args.date_published),
                thumbnail_url=args.thumbnail_url,
                github_repository_urls=args.github or [],
                hf_artifact_urls=args.hf or [],
            )
            result = service.add_external_resource(payload)
        else:
            result = await service.add_from_url(
                source_url=args.url,
                date_published=_parse_date(args.date_published),
                title_override=args.title,
                abstract_override=args.abstract,
                authors_override=args.authors,
                thumbnail_url=args.thumbnail_url,
            )
    except ExternalResourceError as exc:
        logger.error("Ingestion rejected: %s", exc)
        return 2
    except Exception:
        logger.exception("Unexpected error during ingestion")
        return 1
    finally:
        session.close()

    summary = {
        "paper_id": result.paper.id,
        "title": result.paper.title,
        "source": result.paper.source,
        "source_url": result.paper.source_url,
        "url_abs": result.paper.url_abs,
        "thumbnail_url": result.paper.thumbnail_url,
        "authors": result.paper.authors,
        "published": str(result.paper.published) if result.paper.published else None,
        "repositories_added": result.repositories_added,
        "repositories_existing": result.repositories_existing,
        "hf_models_added": result.hf_models_added,
        "hf_datasets_added": result.hf_datasets_added,
        "hf_spaces_added": result.hf_spaces_added,
        "hf_artifacts_existing": result.hf_artifacts_existing,
        "authors_added": result.authors_added,
        "authors_existing": result.authors_existing,
    }
    print(json.dumps(summary, indent=2))
    return 0


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ingest an external (non-ArXiv) resource into the papers table."
    )
    parser.add_argument("--url", required=True, help="Canonical page URL")
    parser.add_argument(
        "--title", help="Title override (or required with --skip-extraction)"
    )
    parser.add_argument("--abstract", help="Abstract/summary override")
    parser.add_argument(
        "--authors",
        nargs="*",
        help=("Author names (zero or more). Replaces extracted authors when provided."),
    )
    parser.add_argument(
        "--date-published",
        help=(
            "ISO date (YYYY-MM-DD). Required when --skip-extraction is set, "
            "otherwise overrides the extracted date if provided."
        ),
    )
    parser.add_argument(
        "--thumbnail-url",
        help=(
            "Optional thumbnail URL to store on the external paper row. For "
            "manually captured thumbnails, use /api/thumbnails/custom/<file>.jpg"
        ),
    )
    parser.add_argument(
        "--github", nargs="*", help="Manual list of GitHub repository URLs"
    )
    parser.add_argument(
        "--hf", nargs="*", help="Manual list of Hugging Face artifact URLs"
    )
    parser.add_argument(
        "--skip-extraction",
        action="store_true",
        help="Skip the LLM extraction step; require manual fields instead",
    )
    return parser


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    parser = _build_arg_parser()
    args = parser.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
