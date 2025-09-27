#!/usr/bin/env python3
"""
Test script for the repositories migration.

This script verifies that the migration from the old repositories structure
to the new many-to-many relationship works correctly.
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import sys
import os
from pathlib import Path
from typing import Dict, Any

# Add the backend directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))


# Load environment variables
def load_env_file(file_path: str):
    """Load environment variables from a file."""
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key] = value


# Load environment from keys.env
env_file = Path(__file__).parent.parent.parent / "keys.env"
if env_file.exists():
    load_env_file(str(env_file))

# Database connection parameters from environment (same as other scripts)
DB_PARAMS = {
    "host": os.getenv("PWC_DB_HOST", "localhost"),
    "port": int(os.getenv("PWC_DB_PORT", "5432")),
    "user": os.getenv("PWC_DB_USER", "paperswithcode_user"),
    "password": os.getenv("PWC_DB_PASSWORD", "paperswithcode123"),
    "database": os.getenv("PWC_DB_NAME", "paperswithcode_hf"),
}


def get_db_connection():
    """Get database connection using the same parameters as other scripts."""
    return psycopg2.connect(**DB_PARAMS)


def run_verification_queries() -> Dict[str, Any]:
    """
    Run verification queries to check the migration results.

    Returns:
        Dict containing verification results
    """
    results = {}

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 1. Check if backup table exists
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'repositories_backup'
                    );
                """)
                results["backup_exists"] = cur.fetchone()["exists"]

                # 2. Check if new tables exist
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'repositories'
                    );
                """)
                results["repositories_exists"] = cur.fetchone()["exists"]

                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'paper_repositories'
                    );
                """)
                results["paper_repositories_exists"] = cur.fetchone()["exists"]

                # 3. Count records in each table
                if results["backup_exists"]:
                    cur.execute("SELECT COUNT(*) as count FROM repositories_backup;")
                    results["backup_count"] = cur.fetchone()["count"]
                else:
                    results["backup_count"] = 0

                if results["repositories_exists"]:
                    cur.execute("SELECT COUNT(*) as count FROM repositories;")
                    results["repositories_count"] = cur.fetchone()["count"]
                else:
                    results["repositories_count"] = 0

                if results["paper_repositories_exists"]:
                    cur.execute("SELECT COUNT(*) as count FROM paper_repositories;")
                    results["paper_repositories_count"] = cur.fetchone()["count"]
                else:
                    results["paper_repositories_count"] = 0

                # 4. Check for duplicate URLs in new repositories table
                if results["repositories_exists"]:
                    cur.execute("""
                        SELECT url, COUNT(*) as duplicate_count
                        FROM repositories
                        GROUP BY url
                        HAVING COUNT(*) > 1;
                    """)
                    duplicates = cur.fetchall()
                    results["duplicate_urls"] = len(duplicates)
                    results["duplicate_examples"] = duplicates[:5]  # First 5 examples
                else:
                    results["duplicate_urls"] = 0
                    results["duplicate_examples"] = []

                # 5. Check for orphaned relationships
                if results["paper_repositories_exists"]:
                    cur.execute("""
                        SELECT COUNT(*) as orphaned_count
                        FROM paper_repositories pr
                        LEFT JOIN papers p ON pr.paper_id = p.id
                        LEFT JOIN repositories r ON pr.repository_id = r.id
                        WHERE p.id IS NULL OR r.id IS NULL;
                    """)
                    results["orphaned_relationships"] = cur.fetchone()["orphaned_count"]
                else:
                    results["orphaned_relationships"] = 0

                # 6. Sample data comparison
                if results["repositories_exists"]:
                    cur.execute("""
                        SELECT r.url, r.owner, r.name, r.num_stars,
                               COUNT(pr.paper_id) as paper_count
                        FROM repositories r
                        LEFT JOIN paper_repositories pr ON r.id = pr.repository_id
                        GROUP BY r.id, r.url, r.owner, r.name, r.num_stars
                        ORDER BY paper_count DESC, r.num_stars DESC
                        LIMIT 10;
                    """)
                    results["sample_repositories"] = cur.fetchall()
                else:
                    results["sample_repositories"] = []

                # 7. Check indexes exist
                cur.execute("""
                    SELECT indexname
                    FROM pg_indexes
                    WHERE tablename IN ('repositories', 'paper_repositories')
                    ORDER BY tablename, indexname;
                """)
                results["indexes"] = [row["indexname"] for row in cur.fetchall()]

                # 8. Check constraints exist
                cur.execute("""
                    SELECT conname, contype
                    FROM pg_constraint
                    WHERE conrelid IN (
                        SELECT oid FROM pg_class
                        WHERE relname IN ('repositories', 'paper_repositories')
                    );
                """)
                results["constraints"] = cur.fetchall()

    except Exception as e:
        results["error"] = str(e)
        return results

    return results


def print_verification_report(results: Dict[str, Any]) -> None:
    """
    Print a formatted verification report.

    Args:
        results: Dictionary containing verification results
    """
    print("=" * 80)
    print("REPOSITORIES MIGRATION VERIFICATION REPORT")
    print("=" * 80)

    if "error" in results:
        print(f"❌ ERROR: {results['error']}")
        return

    # Table existence checks
    print("\n📋 TABLE EXISTENCE CHECKS:")
    print(f"  ✅ Backup table exists: {results['backup_exists']}")
    print(f"  ✅ New repositories table exists: {results['repositories_exists']}")
    print(
        f"  ✅ Paper_repositories junction table exists: {results['paper_repositories_exists']}"
    )

    # Record counts
    print("\n📊 RECORD COUNTS:")
    print(f"  📦 Original repositories (backup): {results['backup_count']:,}")
    print(f"  🏪 New unique repositories: {results['repositories_count']:,}")
    print(
        f"  🔗 Paper-repository relationships: {results['paper_repositories_count']:,}"
    )

    # Data quality checks
    print("\n🔍 DATA QUALITY CHECKS:")
    print(f"  🚫 Duplicate URLs: {results['duplicate_urls']}")
    if results["duplicate_examples"]:
        print("     Examples of duplicates:")
        for dup in results["duplicate_examples"]:
            print(f"       - {dup['url']} ({dup['duplicate_count']} times)")

    print(f"  🔗 Orphaned relationships: {results['orphaned_relationships']}")

    # Deduplication efficiency
    if results["backup_count"] > 0:
        dedup_ratio = (
            (results["backup_count"] - results["repositories_count"])
            / results["backup_count"]
            * 100
        )
        print(f"  📈 Deduplication efficiency: {dedup_ratio:.1f}% reduction")

    # Sample data
    print("\n📋 SAMPLE REPOSITORIES (Top 10 by paper count):")
    for i, repo in enumerate(results["sample_repositories"], 1):
        print(f"  {i:2d}. {repo['url']}")
        print(f"      Owner: {repo['owner']}, Name: {repo['name']}")
        print(f"      Stars: {repo['num_stars']:,}, Papers: {repo['paper_count']}")

    # Infrastructure checks
    print("\n🏗️  INFRASTRUCTURE CHECKS:")
    print(f"  📇 Indexes created: {len(results['indexes'])}")
    for idx in sorted(results["indexes"]):
        print(f"     - {idx}")

    print(f"  🔒 Constraints created: {len(results['constraints'])}")
    for constraint in results["constraints"]:
        constraint_type = {
            "p": "PRIMARY KEY",
            "f": "FOREIGN KEY",
            "u": "UNIQUE",
            "c": "CHECK",
        }.get(constraint["contype"], constraint["contype"])
        print(f"     - {constraint['conname']} ({constraint_type})")

    # Overall assessment
    print("\n🎯 MIGRATION ASSESSMENT:")
    issues = []

    if not results["repositories_exists"]:
        issues.append("❌ New repositories table missing")
    if not results["paper_repositories_exists"]:
        issues.append("❌ Paper_repositories junction table missing")
    if results["duplicate_urls"] > 0:
        issues.append(f"⚠️  {results['duplicate_urls']} duplicate URLs found")
    if results["orphaned_relationships"] > 0:
        issues.append(f"❌ {results['orphaned_relationships']} orphaned relationships")
    if results["paper_repositories_count"] == 0 and results["backup_count"] > 0:
        issues.append("❌ No relationships migrated")

    if not issues:
        print("  ✅ MIGRATION SUCCESSFUL - All checks passed!")
        print("  🎉 The database is ready to use the new many-to-many structure.")
    else:
        print("  ⚠️  ISSUES FOUND:")
        for issue in issues:
            print(f"     {issue}")

    print("=" * 80)


def main():
    """Main function to run the verification."""
    print("Starting repositories migration verification...")
    print(f"🔗 Connecting to database: {DB_PARAMS['database']} on {DB_PARAMS['host']}")

    try:
        results = run_verification_queries()
        print_verification_report(results)

        # Return appropriate exit code
        if "error" in results:
            sys.exit(1)

        # Check for critical issues
        critical_issues = (
            not results.get("repositories_exists", False)
            or not results.get("paper_repositories_exists", False)
            or results.get("orphaned_relationships", 0) > 0
        )

        if critical_issues:
            sys.exit(1)
        else:
            sys.exit(0)

    except Exception as e:
        print(f"❌ Verification failed with error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
