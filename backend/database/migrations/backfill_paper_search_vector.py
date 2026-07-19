"""Backfill ``papers.search_vector`` in resumable, committed batches.

Examples:
    uv run --env-file backend/keys.env python \
      backend/database/migrations/backfill_paper_search_vector.py --max-batches 10

    uv run --env-file backend/keys.env python \
      backend/database/migrations/backfill_paper_search_vector.py \
      --database-url postgresql://.../isolated_db --batch-size 500

Each invocation is bounded by ``--max-batches`` and commits after every batch.
Rows left NULL are picked up by a later invocation, so interruption is safe.
"""

import argparse

from sqlalchemy import create_engine, text

from backend.config import get_settings


BACKFILL_BATCH = text("""
    WITH batch AS (
        SELECT id
        FROM papers
        WHERE search_vector IS NULL
        ORDER BY id
        LIMIT :batch_size
        FOR UPDATE SKIP LOCKED
    )
    UPDATE papers AS p
    SET search_vector =
        setweight(to_tsvector('english', coalesce(p.title, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(p.abstract, '')), 'B')
    FROM batch
    WHERE p.id = batch.id
""")


def backfill(database_url: str, batch_size: int, max_batches: int) -> tuple[int, int]:
    engine = create_engine(database_url)
    updated = 0
    try:
        for _ in range(max_batches):
            with engine.begin() as connection:
                result = connection.execute(BACKFILL_BATCH, {"batch_size": batch_size})
                batch_count = result.rowcount
            updated += batch_count
            if batch_count < batch_size:
                break

        with engine.connect() as connection:
            remaining = connection.execute(
                text("SELECT count(*) FROM papers WHERE search_vector IS NULL")
            ).scalar_one()
    finally:
        engine.dispose()
    return updated, remaining


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--batch-size", type=int, default=1_000)
    parser.add_argument("--max-batches", type=int, default=1)
    args = parser.parse_args()
    if args.batch_size < 1 or args.max_batches < 1:
        parser.error("--batch-size and --max-batches must be positive")

    database_url = args.database_url or get_settings().database_url
    updated, remaining = backfill(database_url, args.batch_size, args.max_batches)
    print(f"updated={updated} remaining={remaining}")


if __name__ == "__main__":
    main()
