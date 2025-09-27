#!/usr/bin/env python3
"""
Migration script to normalize the project_pages table.

This script:
1. Creates a paper_project_pages junction table
2. Migrates existing data from project_pages.paper_id to the junction table
3. Removes the paper_id column from project_pages

Usage:
    uv run --env-file backend/keys.env python backend/database/migration/run_normalize_project_pages.py
"""

import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor
from pathlib import Path


def get_db_connection():
    """Get database connection using environment variables."""
    return psycopg2.connect(
        host=os.getenv("PWC_DB_HOST", "localhost"),
        database=os.getenv("PWC_DB_NAME", "paperswithcode_hf"),
        user=os.getenv("PWC_DB_USER", "postgres"),
        password=os.getenv("PWC_DB_PASSWORD", ""),
    )


def check_prerequisites(cursor, auto_confirm=False):
    """Check if the migration can be safely run."""
    print("🔍 Checking prerequisites...")

    # Check if project_pages table exists and has paper_id column
    cursor.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'project_pages' AND column_name = 'paper_id'
    """)

    if not cursor.fetchone():
        print(
            "❌ Error: project_pages table doesn't have paper_id column. Migration may have already been run."
        )
        return False

    # Check if paper_project_pages table already exists
    cursor.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_name = 'paper_project_pages'
    """)

    if cursor.fetchone():
        print(
            "⚠️  Warning: paper_project_pages table already exists. This may indicate a previous migration attempt."
        )
        if not auto_confirm:
            response = input("Continue anyway? (y/N): ")
            if response.lower() != "y":
                return False
        else:
            print("   Auto-confirming to continue (auto_confirm=True)")

    # Check current data
    cursor.execute("SELECT COUNT(*) as total FROM project_pages")
    total_pages = cursor.fetchone()["total"]

    cursor.execute(
        "SELECT COUNT(*) as with_paper_id FROM project_pages WHERE paper_id IS NOT NULL"
    )
    pages_with_paper_id = cursor.fetchone()["with_paper_id"]

    print("📊 Current state:")
    print(f"   Total project pages: {total_pages}")
    print(f"   Pages with paper_id: {pages_with_paper_id}")
    print(f"   Pages without paper_id: {total_pages - pages_with_paper_id}")

    if pages_with_paper_id == 0:
        print("❌ Error: No project pages have paper_id. Nothing to migrate.")
        return False

    return True


def create_backup(cursor):
    """Create a backup of the current project_pages table."""
    print("💾 Creating backup of project_pages table...")

    # Drop backup table if it exists
    cursor.execute("DROP TABLE IF EXISTS project_pages_backup_before_normalization")

    # Create backup
    cursor.execute("""
        CREATE TABLE project_pages_backup_before_normalization AS
        SELECT * FROM project_pages
    """)

    cursor.execute(
        "SELECT COUNT(*) as count FROM project_pages_backup_before_normalization"
    )
    backup_count = cursor.fetchone()["count"]
    print(f"✅ Backup created with {backup_count} rows")


def run_migration_sql(cursor):
    """Run the migration SQL script."""
    print("🚀 Running migration SQL script...")

    # Read the SQL file
    sql_file = Path(__file__).parent / "normalize_project_pages.sql"

    if not sql_file.exists():
        raise FileNotFoundError(f"Migration SQL file not found: {sql_file}")

    with open(sql_file, "r") as f:
        sql_content = f.read()

    # Execute the SQL
    cursor.execute(sql_content)
    print("✅ Migration SQL executed successfully")


def verify_migration(cursor):
    """Verify the migration was successful."""
    print("🔍 Verifying migration results...")

    # Check that paper_id column is gone
    cursor.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'project_pages' AND column_name = 'paper_id'
    """)

    if cursor.fetchone():
        print("❌ Error: paper_id column still exists in project_pages table")
        return False

    # Check junction table exists and has data
    cursor.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_name = 'paper_project_pages'
    """)

    if not cursor.fetchone():
        print("❌ Error: paper_project_pages junction table was not created")
        return False

    # Check data counts
    cursor.execute("SELECT COUNT(*) as count FROM project_pages")
    total_pages = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) as count FROM paper_project_pages")
    total_relationships = cursor.fetchone()["count"]

    cursor.execute(
        "SELECT COUNT(*) as count FROM project_pages_backup_before_normalization WHERE paper_id IS NOT NULL"
    )
    original_relationships = cursor.fetchone()["count"]

    print("📊 Migration results:")
    print(f"   Project pages (normalized): {total_pages}")
    print(f"   Paper-project page relationships: {total_relationships}")
    print(f"   Original relationships: {original_relationships}")

    if total_relationships != original_relationships:
        print(
            f"❌ Error: Relationship count mismatch. Expected {original_relationships}, got {total_relationships}"
        )
        return False

    # Show sample data
    cursor.execute("""
        SELECT
            p.title,
            pp.url,
            ppp.is_official,
            ppp.source
        FROM papers p
        JOIN paper_project_pages ppp ON p.id = ppp.paper_id
        JOIN project_pages pp ON ppp.project_page_id = pp.id
        LIMIT 3
    """)

    samples = cursor.fetchall()
    print("\n📋 Sample relationships:")
    for i, row in enumerate(samples, 1):
        print(
            f"   {i}. {row['title'][:50]}... -> {row['url'][:50]}... (official: {row['is_official']})"
        )

    print("✅ Migration verification completed successfully")
    return True


def main(auto_confirm=False):
    """Main migration function."""
    print("🔄 Starting project_pages table normalization migration...")
    print("=" * 60)

    try:
        # Connect to database
        conn = get_db_connection()
        conn.autocommit = False  # Use transactions

        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Check prerequisites
            if not check_prerequisites(cursor, auto_confirm):
                print("❌ Prerequisites not met. Aborting migration.")
                return False

            # Confirm with user
            print("\n⚠️  This migration will:")
            print("   1. Create a backup of the current project_pages table")
            print("   2. Create a new paper_project_pages junction table")
            print("   3. Migrate all existing relationships to the junction table")
            print("   4. Remove the paper_id column from project_pages")
            print("\n   This operation is irreversible (except via backup restore).")

            if auto_confirm:
                print("\n✅ Auto-confirming migration (auto_confirm=True)")
            else:
                response = input("\nProceed with migration? (y/N): ")
                if response.lower() != "y":
                    print("❌ Migration cancelled by user.")
                    return False

            try:
                # Create backup
                create_backup(cursor)

                # Run migration
                run_migration_sql(cursor)

                # Verify results
                if not verify_migration(cursor):
                    print("❌ Migration verification failed. Rolling back...")
                    conn.rollback()
                    return False

                # Commit transaction
                conn.commit()

                print("\n" + "=" * 60)
                print("🎉 Migration completed successfully!")
                print("\n📝 Next steps:")
                print(
                    "   1. Update your application code to use the paper_project_pages junction table"
                )
                print("   2. Test your application thoroughly")
                print("   3. Once confirmed working, you can drop the backup table:")
                print("      DROP TABLE project_pages_backup_before_normalization;")

                return True

            except Exception as e:
                print(f"❌ Error during migration: {e}")
                print("🔄 Rolling back transaction...")
                conn.rollback()
                return False

    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return False

    finally:
        if "conn" in locals():
            conn.close()


if __name__ == "__main__":
    # Check for auto-confirm flag
    auto_confirm = len(sys.argv) > 1 and sys.argv[1] == "--auto-confirm"
    success = main(auto_confirm)
    sys.exit(0 if success else 1)
