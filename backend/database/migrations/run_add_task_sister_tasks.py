"""
Run the add_task_sister_tasks migration.

Creates the `task_sister_tasks` junction table for explicit, ordered
sister-task relationships and seeds the `agents` task with Coding Agents,
Computer Use Agents, and Language Modeling.

Idempotent — safe to re-run.
"""

import sys

from sqlalchemy import text

from backend.database.connection import db_manager


SQL_FILE = "backend/database/migrations/add_task_sister_tasks.sql"


def main() -> None:
    print("=" * 80)
    print("Running migration: add_task_sister_tasks")
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
                WHERE table_name = 'task_sister_tasks'
                ORDER BY ordinal_position
                """
            )
        ).fetchall()

        if not cols:
            print("task_sister_tasks table is missing after migration")
            sys.exit(1)

        print("task_sister_tasks columns:")
        for col in cols:
            print(f"   - {col[0]}: {col[1]} (nullable={col[2]})")

        agents_sisters = session.execute(
            text(
                """
                SELECT sister.slug, tst.display_order
                FROM task_sister_tasks tst
                JOIN tasks page ON page.id = tst.task_id
                JOIN tasks sister ON sister.id = tst.sister_task_id
                WHERE page.slug = 'agents'
                ORDER BY tst.display_order
                """
            )
        ).fetchall()

        print(f"agents sister tasks ({len(agents_sisters)}):")
        for slug, order in agents_sisters:
            print(f"   - {order}: {slug}")

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
