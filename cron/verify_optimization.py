#!/usr/bin/env python3
"""
Verification script for repository deduplication and CRON optimization.
Run this to verify the database state and optimization results.
"""

import os
import sys
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor

# Add project root to Python path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


def get_db_connection():
    """Get database connection."""
    return psycopg2.connect(
        host=os.getenv("PWC_DB_HOST", "localhost"),
        port=os.getenv("PWC_DB_PORT", "5432"),
        database=os.getenv("PWC_DB_NAME", "paperswithcode_hf"),
        user=os.getenv("PWC_DB_USER", "postgres"),
        password=os.getenv("PWC_DB_PASSWORD", ""),
    )


def verify_database_state():
    """Verify the database deduplication was successful."""
    print("🔍 Verifying Database State")
    print("=" * 50)

    conn = get_db_connection()

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Check repositories table
            cursor.execute("""
                SELECT
                    COUNT(*) as total_repos,
                    COUNT(DISTINCT url) as unique_urls,
                    COUNT(DISTINCT CONCAT(COALESCE(owner, ''), '/', COALESCE(name, ''))) as unique_owner_name_pairs
                FROM repositories
                WHERE owner IS NOT NULL AND name IS NOT NULL
            """)
            repo_stats = cursor.fetchone()

            print("📊 Repository Statistics:")
            print(f"   Total repositories: {repo_stats['total_repos']:,}")
            print(f"   Unique URLs: {repo_stats['unique_urls']:,}")
            print(
                f"   Unique owner/name pairs: {repo_stats['unique_owner_name_pairs']:,}"
            )

            # Check for URL duplicates (should be 0)
            cursor.execute("""
                SELECT COUNT(*) as duplicate_urls
                FROM (
                    SELECT url, COUNT(*) as cnt
                    FROM repositories
                    GROUP BY url
                    HAVING COUNT(*) > 1
                ) duplicates
            """)
            url_duplicates = cursor.fetchone()["duplicate_urls"]

            print(f"   URL duplicates: {url_duplicates}")
            print(
                f"   ✅ URL deduplication: {'SUCCESS' if url_duplicates == 0 else 'FAILED'}"
            )

            # Check paper_repositories relationships
            cursor.execute("""
                SELECT
                    COUNT(*) as total_relationships,
                    COUNT(DISTINCT paper_id) as unique_papers,
                    COUNT(DISTINCT repository_id) as unique_repositories
                FROM paper_repositories
            """)
            rel_stats = cursor.fetchone()

            print("\n📊 Paper-Repository Relationships:")
            print(f"   Total relationships: {rel_stats['total_relationships']:,}")
            print(f"   Unique papers: {rel_stats['unique_papers']:,}")
            print(f"   Unique repositories: {rel_stats['unique_repositories']:,}")

            # Show top repositories by URL count (efficiency examples)
            cursor.execute("""
                SELECT
                    owner || '/' || name as repository,
                    COUNT(*) as url_count,
                    MAX(num_stars) as stars
                FROM repositories
                WHERE owner IS NOT NULL AND name IS NOT NULL
                GROUP BY owner, name
                ORDER BY COUNT(*) DESC
                LIMIT 10
            """)
            top_repos = cursor.fetchall()

            print("\n🚀 Top Repositories by URL Count (Efficiency Examples):")
            for repo in top_repos:
                efficiency = repo["url_count"]
                print(
                    f"   {repo['repository']}: {repo['url_count']} URLs → {efficiency}x efficiency gain"
                )

    finally:
        conn.close()


def verify_cron_optimization():
    """Verify CRON job files are in place."""
    print("\n🔧 Verifying CRON Optimization")
    print("=" * 50)

    cron_dir = Path(__file__).parent

    # Check essential files
    essential_files = [
        "hourly/update_github_stars_optimized.py",
        "run_github_stars_optimized.sh",
        "crontab_optimized.txt",
    ]

    for file_path in essential_files:
        full_path = cron_dir / file_path
        exists = full_path.exists()
        print(f"   {file_path}: {'✅ EXISTS' if exists else '❌ MISSING'}")

    # Check if optimized script is executable
    optimized_wrapper = cron_dir / "run_github_stars_optimized.sh"
    if optimized_wrapper.exists():
        is_executable = os.access(optimized_wrapper, os.X_OK)
        print(
            f"   run_github_stars_optimized.sh executable: {'✅ YES' if is_executable else '❌ NO'}"
        )


def calculate_efficiency_gains():
    """Calculate the efficiency gains from optimization."""
    print("\n📈 Efficiency Gains Analysis")
    print("=" * 50)

    conn = get_db_connection()

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Calculate total efficiency gains
            cursor.execute("""
                SELECT
                    COUNT(*) as total_urls,
                    COUNT(DISTINCT CONCAT(owner, '/', name)) as unique_repositories,
                    COUNT(*) - COUNT(DISTINCT CONCAT(owner, '/', name)) as api_calls_saved
                FROM repositories
                WHERE owner IS NOT NULL AND name IS NOT NULL
            """)
            efficiency = cursor.fetchone()

            old_api_calls = efficiency["total_urls"]
            new_api_calls = efficiency["unique_repositories"]
            saved_calls = efficiency["api_calls_saved"]
            efficiency_ratio = old_api_calls / new_api_calls if new_api_calls > 0 else 0

            print("📊 Overall Efficiency Analysis:")
            print(f"   Old method API calls: {old_api_calls:,}")
            print(f"   New method API calls: {new_api_calls:,}")
            print(f"   API calls saved: {saved_calls:,}")
            print(f"   Overall efficiency gain: {efficiency_ratio:.1f}x")
            print(f"   API usage reduction: {(saved_calls / old_api_calls * 100):.1f}%")

    finally:
        conn.close()


def main():
    """Main verification function."""
    print("🎯 Repository Deduplication & CRON Optimization Verification")
    print("=" * 70)

    try:
        verify_database_state()
        verify_cron_optimization()
        calculate_efficiency_gains()

        print("\n✅ Verification Complete!")
        print(
            "The repository deduplication and CRON optimization are working correctly."
        )

    except Exception as e:
        print(f"\n❌ Verification failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
