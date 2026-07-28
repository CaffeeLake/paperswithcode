"""Report public paper SEO completeness without modifying catalog data."""

from __future__ import annotations

import argparse
import json
from datetime import date

from backend.database.connection import db_manager
from backend.services.seo_completeness_service import (
    MAX_REPORT_LIMIT,
    SeoCompletenessService,
)


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from exc


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--paper", help="one ArXiv route ID or internal paper ID")
    result.add_argument("--published-since", type=_date)
    result.add_argument("--published-until", type=_date)
    result.add_argument(
        "--limit", type=int, default=100, choices=range(1, MAX_REPORT_LIMIT + 1)
    )
    result.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )
    return result


def main() -> int:
    args = parser().parse_args()
    with db_manager.session_local() as db:
        service = SeoCompletenessService(db)
        if args.paper:
            results = [service.report_one(args.paper)]
        else:
            results = service.report_window(
                published_since=args.published_since,
                published_until=args.published_until,
                limit=args.limit,
            )

    if args.json:
        print(json.dumps([result.as_dict() for result in results], indent=2))
        return 0

    print("route\trequired\tscore\tmissing")
    for result in results:
        missing = [
            name
            for group in (result.required, result.valuable)
            for name, present in group.items()
            if not present
        ]
        print(
            f"{result.route_identifier}\t"
            f"{'yes' if result.required_complete else 'no'}\t"
            f"{result.score}/{result.possible_score}\t"
            f"{','.join(missing) or '-'}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
