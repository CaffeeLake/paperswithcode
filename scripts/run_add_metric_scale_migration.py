"""
Run the add_metric_scale migration.

This script executes the SQL migration to add the scale column to the metrics table.
"""

import sys
from pathlib import Path
from sqlalchemy import text
from backend.database.connection import db_manager


def main():
    """Run the migration."""
    # Read the migration SQL file
    migration_path = (
        Path(__file__).parent.parent
        / "backend"
        / "database"
        / "migration"
        / "add_metric_scale.sql"
    )

    if not migration_path.exists():
        print(f"❌ Migration file not found: {migration_path}")
        return 1

    print("Reading migration file...")
    migration_sql = migration_path.read_text()

    print(f"Executing migration: {migration_path.name}")
    print("=" * 80)

    try:
        with db_manager.session_local() as session:
            # Execute the migration SQL
            session.execute(text(migration_sql))
            session.commit()
            print("✅ Migration executed successfully!")
            print("=" * 80)

            # Verify the column was added
            result = session.execute(
                text("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'metrics' AND column_name = 'scale'
            """)
            )
            row = result.fetchone()

            if row:
                print(f"✅ Verified: 'scale' column exists (type: {row[1]})")
            else:
                print("⚠️  Warning: Could not verify 'scale' column")

            # Count metrics with scales
            result = session.execute(
                text("""
                SELECT
                    COUNT(*) as total,
                    COUNT(scale) as with_scale,
                    COUNT(*) - COUNT(scale) as without_scale
                FROM metrics
            """)
            )
            row = result.fetchone()
            print("\nMetrics summary:")
            print(f"  Total metrics: {row[0]}")
            print(f"  With scale: {row[1]}")
            print(f"  Without scale: {row[2]}")

        return 0

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
