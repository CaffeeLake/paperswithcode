"""Bounded historical paper-centric method reference backfill."""

from __future__ import annotations

import argparse
from datetime import date

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.database.methods_setup.link_papers_by_source_citations import (
    SemanticScholarClient,
)
from backend.services.cron_token_probe import probe_cron_token
from backend.services.method_backfill_service import run_reference_backfill


def _date(value: str) -> date:
    parsed = date.fromisoformat(value)
    return parsed.replace(day=1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method-id", type=int, action="append", default=[])
    parser.add_argument("--method-slug", action="append", default=[])
    parser.add_argument("--month-from", type=_date)
    parser.add_argument("--month-to", type=_date)
    parser.add_argument("--limit", type=int, default=1_000)
    parser.add_argument("--max-runtime-seconds", type=int, default=3_600)
    parser.add_argument("--request-delay", type=float, default=1.0)
    parser.add_argument("--batch-size", type=int, default=250)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--retry-failures", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.semantic_scholar_api_key_2:
        raise SystemExit(
            "PWC_SEMANTIC_SCHOLAR_API_KEY_2 is required; "
            "primary-key fallback is forbidden"
        )
    probe = probe_cron_token("PWC_SEMANTIC_SCHOLAR_API_KEY_2")
    if not probe.success:
        raise SystemExit(
            "secondary Semantic Scholar key validation failed "
            f"(HTTP {probe.http_status})"
        )
    print("Semantic Scholar key route: secondary (historical backfill)")
    client = SemanticScholarClient(
        api_key=settings.semantic_scholar_api_key_2,
        request_delay=args.request_delay,
        exponential_backoff=True,
    )
    try:
        with db_manager.session_local() as db:
            stats = run_reference_backfill(
                db,
                client,
                method_ids=args.method_id,
                method_slugs=args.method_slug,
                month_from=args.month_from,
                month_to=args.month_to,
                limit=args.limit,
                max_runtime_seconds=args.max_runtime_seconds,
                dry_run=args.dry_run,
                resume=args.resume,
                retry_failures=args.retry_failures,
                batch_size=args.batch_size,
            )
    finally:
        client.close()
    print(stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
