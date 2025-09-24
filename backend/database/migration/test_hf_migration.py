#!/usr/bin/env python3
"""
Test script for the HF database migration.

This script verifies that:
1. The HF CSV file is accessible
2. Database connections work
3. The original database has the expected data
4. The migration process can run in dry-run mode

Usage:
    uv run backend/database/test_hf_migration.py
"""

import csv
import os
import sys

import psycopg2
import psycopg2.extras

# Database connection parameters
DB_PARAMS = {
    "host": "localhost",
    "user": os.getenv("PWC_DB_USER", "paperswithcode_user"),
    "password": os.getenv("PWC_DB_PASSWORD", "paperswithcode123"),
}

ORIGINAL_DB = "paperswithcode"
HF_CSV_PATH = "data" / "arxiv_papers_hf.csv"


def test_hf_csv_access():
    """Test that the HF CSV file is accessible and has expected format."""
    print("🔍 Testing HF CSV file access...")

    try:
        if not HF_CSV_PATH.exists():
            print(f"❌ HF CSV file not found: {HF_CSV_PATH}")
            return False

        # Check file size
        file_size = HF_CSV_PATH.stat().st_size
        print(f"   File size: {file_size:,} bytes ({file_size / 1024 / 1024:.1f} MB)")

        # Read first few rows to verify format
        with open(HF_CSV_PATH, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            # Check header
            if "_id" not in reader.fieldnames:
                print("❌ Expected '_id' column not found in CSV")
                return False

            # Count total rows and sample first few
            sample_rows = []
            total_rows = 0

            for i, row in enumerate(reader):
                total_rows += 1
                if i < 5:
                    sample_rows.append(row["_id"])

                # Don't read entire file for performance - just sample first 1000
                if i >= 999:
                    print(f"   Sampled {i + 1:,} rows (stopping for performance)")
                    break
            else:
                print(f"   Total rows: {total_rows:,}")

            print(f"   Sample ArXiv IDs: {sample_rows}")
            print("✅ HF CSV file is accessible and has correct format")
            return True

    except Exception as e:
        print(f"❌ Error accessing HF CSV file: {e}")
        return False


def test_database_connections():
    """Test connections to PostgreSQL and original database."""
    print("\n🔍 Testing database connections...")

    try:
        # Test PostgreSQL connection to the original database
        conn = psycopg2.connect(database=ORIGINAL_DB, **DB_PARAMS)
        conn.close()
        print("✅ PostgreSQL connection successful")

        # Test original database connection
        conn = psycopg2.connect(database=ORIGINAL_DB, **DB_PARAMS)

        with conn.cursor() as cur:
            # Check if papers table exists and has data
            cur.execute("SELECT COUNT(*) FROM papers")
            paper_count = cur.fetchone()[0]
            print(f"   Original database has {paper_count:,} papers")

            # Check if other tables exist
            cur.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """)
            tables = [row[0] for row in cur.fetchall()]
            print(f"   Available tables: {', '.join(tables)}")

        conn.close()
        print("✅ Original database connection successful")
        return True

    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return False


def test_hf_papers_overlap():
    """Test how many HF papers exist in the original database."""
    print("\n🔍 Testing HF papers overlap with original database...")

    try:
        # Load HF ArXiv IDs (sample for testing)
        hf_arxiv_ids = set()
        with open(HF_CSV_PATH, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                hf_arxiv_ids.add(row["_id"].strip())
                if i >= 999:  # Sample first 1000 for testing
                    break

        print(f"   Loaded {len(hf_arxiv_ids)} HF ArXiv IDs (sample)")

        # Check overlap with original database
        conn = psycopg2.connect(database=ORIGINAL_DB, **DB_PARAMS)

        with conn.cursor() as cur:
            # Find matching papers
            cur.execute(
                """
                SELECT COUNT(DISTINCT arxiv_id)
                FROM papers
                WHERE arxiv_id = ANY(%s)
            """,
                (list(hf_arxiv_ids),),
            )

            matching_papers = cur.fetchone()[0]

            # Get sample of matching papers with details
            cur.execute(
                """
                SELECT arxiv_id, title, citation_count,
                       CASE WHEN primary_category IS NOT NULL THEN 'Yes' ELSE 'No' END as has_category
                FROM papers
                WHERE arxiv_id = ANY(%s)
                AND is_latest_version = TRUE
                LIMIT 5
            """,
                (list(hf_arxiv_ids),),
            )

            sample_papers = cur.fetchall()

        conn.close()

        overlap_percentage = (matching_papers / len(hf_arxiv_ids)) * 100
        print(
            f"   Found {matching_papers:,} matching papers ({overlap_percentage:.1f}% overlap)"
        )

        if sample_papers:
            print("   Sample matching papers:")
            for paper in sample_papers:
                arxiv_id, title, citation_count, has_category = paper
                title_short = title[:50] + "..." if len(title) > 50 else title
                print(
                    f"     {arxiv_id}: {title_short} (citations: {citation_count or 0}, category: {has_category})"
                )

        if matching_papers > 0:
            print("✅ Found overlapping papers in original database")
            return True
        else:
            print("⚠️  No overlapping papers found - this might indicate an issue")
            return False

    except Exception as e:
        print(f"❌ Error testing HF papers overlap: {e}")
        return False


def test_migration_dry_run():
    """Test the migration script in dry-run mode."""
    print("\n🔍 Testing migration script (dry-run)...")

    try:
        from migrate_to_hf_database import DatabaseMigrator

        # Run migration in dry-run and test mode
        migrator = DatabaseMigrator(dry_run=True, test_mode=True)

        # Test loading HF ArXiv IDs
        hf_arxiv_ids = migrator.load_hf_arxiv_ids()

        if not hf_arxiv_ids:
            print("❌ Failed to load HF ArXiv IDs")
            return False

        print(f"   Successfully loaded {len(hf_arxiv_ids)} HF ArXiv IDs")
        print("✅ Migration script dry-run successful")
        return True

    except Exception as e:
        print(f"❌ Migration script test failed: {e}")
        return False


def main():
    """Run all tests."""

    print("🧪 Testing HF Database Migration Setup")
    print("=" * 50)

    tests = [
        ("HF CSV File Access", test_hf_csv_access),
        ("Database Connections", test_database_connections),
        ("HF Papers Overlap", test_hf_papers_overlap),
        ("Migration Dry Run", test_migration_dry_run),
    ]

    results = []

    for test_name, test_func in tests:
        print(f"\n📋 {test_name}")
        result = test_func()
        results.append(result)

    print("\n" + "=" * 50)
    print("📊 Test Results Summary:")

    passed = sum(results)
    total = len(results)

    for i, (test_name, _) in enumerate(tests):
        status = "✅ PASS" if results[i] else "❌ FAIL"
        print(f"   {test_name}: {status}")

    print(f"\n📈 Overall: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! Ready to run the migration.")
        print("\nNext steps:")
        print(
            "1. Run dry-run migration: uv run backend/database/migrate_to_hf_database.py --dry-run"
        )
        print(
            "2. Run test migration: uv run backend/database/migrate_to_hf_database.py --test"
        )
        print(
            "3. Run full migration: uv run backend/database/migrate_to_hf_database.py"
        )
    else:
        print(
            f"\n⚠️  {total - passed} test(s) failed. Please fix the issues above before proceeding."
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
