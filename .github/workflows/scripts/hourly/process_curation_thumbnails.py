"""Process thumbnail work durably queued by remote paper-curation jobs."""

from __future__ import annotations

import argparse

from backend.database.connection import get_database_session
from backend.services.curation_thumbnail_queue_service import (
    curation_thumbnail_queue_service,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10, choices=range(1, 101))
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="retry each currently failed request once during this invocation",
    )
    args = parser.parse_args()
    db = next(get_database_session())
    try:
        processed = curation_thumbnail_queue_service.process_batch(
            db,
            limit=args.limit,
            retry_failed=args.retry_failed,
        )
    finally:
        db.close()
    print(f"processed {processed} curation thumbnail request(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
