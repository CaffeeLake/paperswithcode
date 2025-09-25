#!/usr/bin/env python3
"""
Citation Migration Script

Migrate citation counts and Semantic Scholar IDs from the old paperswithcode database
to the new paperswithcode_hf database. This is much faster than re-running citation
population from scratch.

Usage:
    uv run backend/database/migration/migrate_citations.py --dry-run
    uv run backend/database/migration/migrate_citations.py --execute
"""

import argparse
import sys
import time
from typing import Dict, Any
import psycopg2
from psycopg2.extras import RealDictCursor


def get_database_connection(
    db_name: str, user: str = "paperswithcode_user", password: str = "paperswithcode123"
):
    """Get database connection."""
    return psycopg2.connect(
        host="localhost", port=5432, database=db_name, user=user, password=password
    )


def get_citation_stats(conn) -> Dict[str, int]:
    """Get citation statistics from a database."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                COUNT(*) as total_papers,
                COUNT(CASE WHEN semantic_scholar_id IS NOT NULL THEN 1 END) as papers_with_ss_id,
                COUNT(CASE WHEN citation_count > 0 THEN 1 END) as papers_with_citations,
                MAX(citation_count) as max_citations,
                AVG(CASE WHEN citation_count > 0 THEN citation_count END) as avg_citations
            FROM papers
            WHERE is_latest_version = true
        """)

        row = cur.fetchone()
        return {
            "total_papers": row[0],
            "papers_with_ss_id": row[1] or 0,
            "papers_with_citations": row[2] or 0,
            "max_citations": row[3] or 0,
            "avg_citations": float(row[4]) if row[4] else 0.0,
        }


def migrate_citations(dry_run: bool = True) -> Dict[str, Any]:
    """
    Migrate citation data from paperswithcode to paperswithcode_hf database.

    Args:
        dry_run: If True, only show what would be migrated without making changes

    Returns:
        Dictionary with migration statistics
    """
    print("🔄 Citation Migration Script")
    print("=" * 50)

    # Connect to both databases
    print("📡 Connecting to databases...")

    try:
        source_conn = get_database_connection("paperswithcode")
        target_conn = get_database_connection("paperswithcode_hf")

        print("✅ Connected to both databases")

        # Get initial statistics
        print("\n📊 Initial Statistics:")
        source_stats = get_citation_stats(source_conn)
        target_stats = get_citation_stats(target_conn)

        print("📚 Source DB (paperswithcode):")
        print(f"   Total papers: {source_stats['total_papers']:,}")
        print(f"   With Semantic Scholar ID: {source_stats['papers_with_ss_id']:,}")
        print(f"   With citations: {source_stats['papers_with_citations']:,}")
        print(f"   Max citations: {source_stats['max_citations']:,}")
        print(f"   Avg citations: {source_stats['avg_citations']:.1f}")

        print("\n🎯 Target DB (paperswithcode_hf):")
        print(f"   Total papers: {target_stats['total_papers']:,}")
        print(f"   With Semantic Scholar ID: {target_stats['papers_with_ss_id']:,}")
        print(f"   With citations: {target_stats['papers_with_citations']:,}")
        print(f"   Max citations: {target_stats['max_citations']:,}")
        print(f"   Avg citations: {target_stats['avg_citations']:.1f}")

        # Find matching papers and get citation data to migrate
        print("\n🔍 Finding papers to migrate...")

        with source_conn.cursor(cursor_factory=RealDictCursor) as source_cur:
            # Get all papers with citation data from source database
            source_cur.execute("""
                SELECT arxiv_id, version, citation_count, semantic_scholar_id, citation_updated_at
                FROM papers
                WHERE is_latest_version = true
                AND (semantic_scholar_id IS NOT NULL OR citation_count > 0)
                ORDER BY arxiv_id, version
            """)

            source_papers = source_cur.fetchall()

        print(
            f"📋 Found {len(source_papers):,} papers with citation data in source database"
        )

        # Find matching papers in target database
        migration_data = []

        with target_conn.cursor(cursor_factory=RealDictCursor) as target_cur:
            for source_paper in source_papers:
                # Find matching paper in target database
                target_cur.execute(
                    """
                    SELECT id, arxiv_id, version, citation_count, semantic_scholar_id
                    FROM papers
                    WHERE arxiv_id = %s AND version = %s AND is_latest_version = true
                """,
                    (source_paper["arxiv_id"], source_paper["version"]),
                )

                target_paper = target_cur.fetchone()

                if target_paper:
                    # Check if we need to update
                    needs_update = (
                        target_paper["semantic_scholar_id"]
                        != source_paper["semantic_scholar_id"]
                        or target_paper["citation_count"]
                        != source_paper["citation_count"]
                    )

                    if needs_update:
                        migration_data.append(
                            {
                                "target_id": target_paper["id"],
                                "arxiv_id": source_paper["arxiv_id"],
                                "version": source_paper["version"],
                                "old_citation_count": target_paper["citation_count"],
                                "new_citation_count": source_paper["citation_count"],
                                "old_ss_id": target_paper["semantic_scholar_id"],
                                "new_ss_id": source_paper["semantic_scholar_id"],
                                "citation_updated_at": source_paper[
                                    "citation_updated_at"
                                ],
                            }
                        )

        print(f"🎯 Found {len(migration_data):,} papers that need citation updates")

        if not migration_data:
            print("✅ No papers need citation updates!")
            return {"papers_processed": 0, "papers_updated": 0, "dry_run": dry_run}

        # Show sample of what will be migrated
        print("\n📝 Sample of papers to be updated:")
        for i, paper in enumerate(migration_data[:5]):
            print(f"   {i + 1}. {paper['arxiv_id']} v{paper['version']}")
            print(
                f"      Citations: {paper['old_citation_count']} → {paper['new_citation_count']}"
            )
            print(f"      SS ID: {paper['old_ss_id']} → {paper['new_ss_id']}")

        if len(migration_data) > 5:
            print(f"   ... and {len(migration_data) - 5:,} more papers")

        if dry_run:
            print("\n🔍 DRY RUN MODE - No changes will be made")
            print(f"📊 Would update {len(migration_data):,} papers")
            return {
                "papers_processed": len(migration_data),
                "papers_updated": 0,
                "dry_run": True,
            }

        # Perform the migration
        print(f"\n🚀 Starting migration of {len(migration_data):,} papers...")
        start_time = time.time()

        with target_conn.cursor() as target_cur:
            # Batch update for better performance
            update_params = []
            for paper in migration_data:
                update_params.append(
                    (
                        paper["new_citation_count"],
                        paper["new_ss_id"],
                        paper["citation_updated_at"],
                        paper["target_id"],
                    )
                )

            # Execute batch update
            target_cur.executemany(
                """
                UPDATE papers
                SET citation_count = %s,
                    semantic_scholar_id = %s,
                    citation_updated_at = %s,
                    updated_at = NOW()
                WHERE id = %s
            """,
                update_params,
            )

            target_conn.commit()

        migration_time = time.time() - start_time

        print(f"✅ Migration completed in {migration_time:.1f} seconds!")
        print(f"📊 Updated {len(migration_data):,} papers")

        # Get final statistics
        print("\n📊 Final Statistics:")
        final_target_stats = get_citation_stats(target_conn)

        print("🎯 Target DB (paperswithcode_hf) after migration:")
        print(f"   Total papers: {final_target_stats['total_papers']:,}")
        print(
            f"   With Semantic Scholar ID: {final_target_stats['papers_with_ss_id']:,}"
        )
        print(f"   With citations: {final_target_stats['papers_with_citations']:,}")
        print(f"   Max citations: {final_target_stats['max_citations']:,}")
        print(f"   Avg citations: {final_target_stats['avg_citations']:.1f}")

        # Calculate improvements
        ss_id_improvement = (
            final_target_stats["papers_with_ss_id"] - target_stats["papers_with_ss_id"]
        )
        citations_improvement = (
            final_target_stats["papers_with_citations"]
            - target_stats["papers_with_citations"]
        )

        print("\n📈 Improvements:")
        print(f"   Papers with SS ID: +{ss_id_improvement:,}")
        print(f"   Papers with citations: +{citations_improvement:,}")

        return {
            "papers_processed": len(migration_data),
            "papers_updated": len(migration_data),
            "migration_time": migration_time,
            "dry_run": False,
            "improvements": {
                "ss_id_improvement": ss_id_improvement,
                "citations_improvement": citations_improvement,
            },
        }

    except Exception as e:
        print(f"❌ Error during migration: {str(e)}")
        raise
    finally:
        try:
            source_conn.close()
            target_conn.close()
        except:  # noqa: E722
            pass


def main():
    """Main function with command line arguments."""
    parser = argparse.ArgumentParser(
        description="Migrate citation data from paperswithcode to paperswithcode_hf database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --dry-run     # Show what would be migrated (safe)
  %(prog)s --execute     # Actually perform the migration
        """,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without making changes",
    )
    parser.add_argument(
        "--execute", action="store_true", help="Actually perform the migration"
    )

    args = parser.parse_args()

    if not args.dry_run and not args.execute:
        print("❌ Please specify either --dry-run or --execute")
        parser.print_help()
        sys.exit(1)

    if args.dry_run and args.execute:
        print("❌ Cannot specify both --dry-run and --execute")
        sys.exit(1)

    try:
        result = migrate_citations(dry_run=args.dry_run)

        if result["papers_updated"] > 0:
            print("\n✅ Migration completed successfully!")
        elif result["papers_processed"] > 0:
            print("\n✅ Dry run completed - ready for migration!")
        else:
            print("\n✅ No migration needed!")

    except KeyboardInterrupt:
        print("\n⏹️  Migration interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Migration failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
