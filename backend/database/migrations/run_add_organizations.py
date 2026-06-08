"""
Run the add_organizations migration.

Creates the `organizations` table and `paper_organizations` junction table.

Idempotent — safe to re-run.
"""

import sys

from sqlalchemy import text

from backend.database.connection import db_manager


SQL_FILE = "backend/database/migrations/add_organizations.sql"


def main() -> None:
    print("=" * 80)
    print("Running migration: add_organizations")
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

        for table in ("organizations", "paper_organizations"):
            cols = session.execute(
                text(
                    """
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_name = :table_name
                    ORDER BY ordinal_position
                    """
                ),
                {"table_name": table},
            ).fetchall()

            if not cols:
                print(f"{table} table is missing after migration")
                sys.exit(1)

            print(f"{table} columns:")
            for col in cols:
                print(f"   - {col[0]}: {col[1]} (nullable={col[2]})")

        count = session.execute(text("SELECT COUNT(*) FROM organizations")).scalar()
        print(f"organizations row count: {count}")

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
