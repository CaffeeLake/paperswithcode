"""Bounded, resumable catalog-wide historical method keyword backfill."""

from __future__ import annotations

import argparse

from backend.database.connection import db_manager
from backend.services.method_backfill_service import (
    audit_undated_method_links,
    run_keyword_backfill,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--after-paper-id", type=int)
    parser.add_argument("--limit", type=int, default=5_000)
    parser.add_argument("--max-runtime-seconds", type=int, default=3_600)
    parser.add_argument("--batch-size", type=int, default=250)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--audit-undated",
        action="store_true",
        help="Print links excluded from monthly charts without running a backfill",
    )
    args = parser.parse_args()
    with db_manager.session_local() as db:
        if args.audit_undated:
            print(audit_undated_method_links(db))
            return 0
        stats = run_keyword_backfill(
            db,
            after_paper_id=args.after_paper_id,
            limit=args.limit,
            max_runtime_seconds=args.max_runtime_seconds,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
            resume=args.resume,
        )
    print(stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
