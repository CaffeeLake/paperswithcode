"""Production entrypoint for rolling HF daily-paper curation reconciliation."""

from __future__ import annotations

import argparse
import json
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
    parser.add_argument("--enable-dispatch", action="store_true")
    parser.add_argument("--disable-dispatch", action="store_true")
    parser.add_argument("--reason")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    if args.enable_dispatch and args.disable_dispatch:
        parser.error("choose only one dispatch action")
    session = get_database_session()
    db = next(session)
    try:
        service = HFDailyCurationService(db, get_settings())
        if args.status:
            result = service.status()
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
