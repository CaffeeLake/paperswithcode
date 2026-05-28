"""
Run the add_pending_paper_edits migration.

Creates the ``pending_paper_edits`` table that backs the non-admin
edit-submission workflow described in the paper-edit-approval plan.
Idempotent -- safe to re-run.
"""

import sys

from sqlalchemy import text

from backend.database.connection import db_manager


SQL_FILE = "backend/database/migrations/add_pending_paper_edits.sql"


def main() -> None:
    print("=" * 80)
    print("Running migration: add_pending_paper_edits")
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
                WHERE table_name = 'pending_paper_edits'
                ORDER BY ordinal_position
                """
            )
        )

        rows = result.fetchall()
        if not rows:
            print("Expected table pending_paper_edits not found")
            sys.exit(1)

        print("pending_paper_edits columns:")
        for col in rows:
            print(f"   - {col[0]}: {col[1]} (nullable={col[2]})")

        index_result = session.execute(
            text(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE tablename = 'pending_paper_edits'
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
