"""
Run the add_user_bookmarks migration.

Creates the `user_bookmarks` table that backs the per-HF-user paper bookmarks
feature. Idempotent — safe to re-run.
"""

import sys

from sqlalchemy import text

from backend.database.connection import db_manager


SQL_FILE = "backend/database/migrations/add_user_bookmarks.sql"


def main() -> None:
    print("=" * 80)
    print("Running migration: add_user_bookmarks")
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
                WHERE table_name = 'user_bookmarks'
                ORDER BY ordinal_position
                """
            )
        )

        rows = result.fetchall()
        if not rows:
            print("Expected table user_bookmarks not found")
            sys.exit(1)

        print("user_bookmarks columns:")
        for col in rows:
            print(f"   - {col[0]}: {col[1]} (nullable={col[2]})")

        index_result = session.execute(
            text(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE tablename = 'user_bookmarks'
                ORDER BY indexname
                """
            )
        )
        indexes = [row[0] for row in index_result.fetchall()]
        print(f"Indexes: {indexes}")

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
