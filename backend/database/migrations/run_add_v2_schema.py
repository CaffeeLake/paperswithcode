"""
Run the add_v2_schema migration.

Adds two nullable columns to the `papers` table for the frontend v2 migration:
  - tldr       TEXT NULL
  - num_pages  INTEGER NULL

See PLAN.md §11 for context. Idempotent — safe to re-run.
"""

import sys

from sqlalchemy import text

from backend.database.connection import db_manager


SQL_FILE = "backend/database/migrations/add_v2_schema.sql"
EXPECTED_COLUMNS = {"tldr", "num_pages"}


def main() -> None:
    print("=" * 80)
    print("Running migration: add_v2_schema")
    print("=" * 80)

    session = db_manager.session_local()
    try:
        with open(SQL_FILE, "r") as f:
            sql_content = f.read()

        session.execute(text(sql_content))
        session.commit()

        print("Migration completed successfully")
        print()
        print("Verifying changes...")

        result = session.execute(
            text(
                """
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'papers'
                  AND column_name IN ('tldr', 'num_pages')
                ORDER BY column_name
                """
            )
        )

        rows = result.fetchall()
        found = {row[0] for row in rows}
        missing = EXPECTED_COLUMNS - found

        if not missing:
            print("All expected columns present:")
            for col in rows:
                print(f"   - {col[0]}: {col[1]} (nullable={col[2]})")
        else:
            print(f"Missing expected columns: {sorted(missing)}")
            sys.exit(1)

        print()
        print("=" * 80)

    except Exception as exc:
        print(f"Migration failed: {exc}")
        session.rollback()
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
