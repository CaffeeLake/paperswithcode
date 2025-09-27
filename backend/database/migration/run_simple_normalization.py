#!/usr/bin/env python3
"""
Simple migration script to normalize the project_pages table.
This version works with limited permissions by creating new tables instead of altering existing ones.

Usage:
    uv run --env-file backend/keys.env python backend/database/migration/run_simple_normalization.py
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


def run_migration():
    """Run the simple migration."""
    print("🔄 Starting simple project_pages normalization...")
    print("=" * 60)

    try:
        conn = get_db_connection()

        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Check current state
            cursor.execute(
                "SELECT COUNT(*) as count FROM project_pages WHERE paper_id IS NOT NULL"
            )
            original_count = cursor.fetchone()["count"]
            print(f"📊 Found {original_count} project pages with paper relationships")

            # Read and execute the SQL file
            sql_file = Path(__file__).parent / "normalize_project_pages_simple.sql"

            if not sql_file.exists():
                raise FileNotFoundError(f"Migration SQL file not found: {sql_file}")

            with open(sql_file, "r") as f:
                sql_content = f.read()

            print("🚀 Running migration SQL...")
            cursor.execute(sql_content)

            # Verify results
            cursor.execute("SELECT COUNT(*) as count FROM paper_project_pages")
            junction_count = cursor.fetchone()["count"]

            cursor.execute("SELECT COUNT(*) as count FROM project_pages_normalized")
            normalized_count = cursor.fetchone()["count"]

            print("✅ Migration completed:")
            print(f"   Junction table relationships: {junction_count}")
            print(f"   Normalized project pages: {normalized_count}")

            if junction_count == original_count:
                print("✅ All relationships successfully migrated!")
            else:
                print(
                    f"⚠️  Warning: Expected {original_count} relationships, got {junction_count}"
                )

            # Show sample data
            cursor.execute("""
                SELECT
                    p.title,
                    pp.url,
                    ppp.is_official
                FROM papers p
                JOIN paper_project_pages ppp ON p.id = ppp.paper_id
                JOIN project_pages_normalized pp ON ppp.project_page_id = pp.id
                LIMIT 3
            """)

            samples = cursor.fetchall()
            print("\n📋 Sample relationships:")
            for i, row in enumerate(samples, 1):
                print(f"   {i}. {row['title'][:50]}... -> {row['url'][:50]}...")

            conn.commit()

            print("\n" + "=" * 60)
            print("🎉 Simple migration completed successfully!")
            print("\n📝 Next steps (requires database admin):")
            print(
                "   1. Verify the data in project_pages_normalized and paper_project_pages"
            )
            print("   2. Update application code to use the new structure")
            print("   3. When ready, have a database admin run:")
            print("      DROP TABLE project_pages;")
            print("      ALTER TABLE project_pages_normalized RENAME TO project_pages;")
            print("   4. Update foreign key references in paper_project_pages")

            return True

    except Exception as e:
        print(f"❌ Error during migration: {e}")
        if "conn" in locals():
            conn.rollback()
        return False

    finally:
        if "conn" in locals():
            conn.close()


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
