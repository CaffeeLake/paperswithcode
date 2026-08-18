"""Production entrypoint for rolling HF daily-paper curation reconciliation."""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import date

from backend.config import get_settings
from backend.database.connection import get_database_session
from backend.services.hf_daily_curation_service import HFDailyCurationService


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=date.fromisoformat)
    parser.add_argument("--lookback-days", type=int, default=7, choices=range(1, 31))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--enable-dispatch", action="store_true")
    action.add_argument("--disable-dispatch", action="store_true")
    action.add_argument("--retry-job", type=uuid.UUID)
    action.add_argument("--status", action="store_true")
    parser.add_argument("--reason")
    args = parser.parse_args()
    session = get_database_session()
    db = next(session)
    try:
        service = HFDailyCurationService(db, get_settings())
        if args.status:
            result = service.status()
        elif args.retry_job:
            result = service.retry_scheduled_job(args.retry_job)
        elif args.enable_dispatch:
            result = service.set_dispatch(True)
        elif args.disable_dispatch:
            result = service.set_dispatch(False, reason=args.reason)
        else:
            result = service.reconcile(
                today=args.date,
                lookback_days=args.lookback_days,
                paper_limit=args.limit,
                dry_run=args.dry_run,
            )
        print(json.dumps(result, default=str, sort_keys=True))
        return 0
    finally:
        try:
            next(session)
        except StopIteration:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
