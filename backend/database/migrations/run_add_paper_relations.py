"""
Run the add_paper_relations migration.

Creates the `paper_relations` junction table for directed predecessor/
successor edges between papers, with the canonical DINOv2 -> DINOv3 seed.

Idempotent — safe to re-run.
"""

import sys

from sqlalchemy import text

from backend.database.connection import db_manager


SQL_FILE = "backend/database/migrations/add_paper_relations.sql"


def main() -> None:
    print("=" * 80)
    print("Running migration: add_paper_relations")
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

        cols = session.execute(
            text(
                """
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'paper_relations'
                ORDER BY ordinal_position
                """
            )
        ).fetchall()

        if not cols:
            print("paper_relations table is missing after migration")
            sys.exit(1)

        print("paper_relations columns:")
        for col in cols:
            print(f"   - {col[0]}: {col[1]} (nullable={col[2]})")

        count = session.execute(text("SELECT COUNT(*) FROM paper_relations")).scalar()
        print(f"paper_relations row count: {count}")

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
