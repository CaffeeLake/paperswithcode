"""Backfill entity name search vectors in bounded, committed batches."""

from __future__ import annotations

import argparse

from sqlalchemy import create_engine, text

from backend.config import get_settings

TABLES = ("datasets", "methods", "tasks")


def _backfill_table(connection, table: str, batch_size: int) -> int:
    result = connection.execute(
        text(f"""
            WITH batch AS (
                SELECT id
                FROM {table}
                WHERE search_vector IS NULL
                ORDER BY id
                LIMIT :batch_size
                FOR UPDATE SKIP LOCKED
            )
            UPDATE {table} AS entity
            SET search_vector =
                setweight(to_tsvector('simple', coalesce(entity.name, '')), 'A')
            FROM batch
            WHERE entity.id = batch.id
        """),
        {"batch_size": batch_size},
    )
    return result.rowcount


def backfill(
    database_url: str, batch_size: int, max_batches: int
) -> tuple[dict[str, int], dict[str, int]]:
    engine = create_engine(database_url)
    updated = {table: 0 for table in TABLES}
    try:
        for table in TABLES:
            for _ in range(max_batches):
                with engine.begin() as connection:
                    batch_count = _backfill_table(connection, table, batch_size)
                updated[table] += batch_count
                if batch_count < batch_size:
                    break

        with engine.connect() as connection:
            remaining = {
                table: connection.execute(
                    text(f"SELECT count(*) FROM {table} WHERE search_vector IS NULL")
                ).scalar_one()
                for table in TABLES
            }
    finally:
        engine.dispose()
    return updated, remaining


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--max-batches", type=int, default=10)
    args = parser.parse_args()
    if args.batch_size < 1 or args.max_batches < 1:
        parser.error("--batch-size and --max-batches must be positive")

    database_url = args.database_url or get_settings().database_url
    updated, remaining = backfill(database_url, args.batch_size, args.max_batches)
    print(f"updated={updated} remaining={remaining}")


if __name__ == "__main__":
    main()
