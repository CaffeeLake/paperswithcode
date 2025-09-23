#!/usr/bin/env python3
"""
Clean up non-Computer Science papers from the database.

This script:
1. Identifies papers that are not in Computer Science categories
2. Optionally removes them from the database to focus on CS-only content
3. Provides detailed statistics and examples before removal

Usage:
    # Analyze what would be removed (safe)
    uv run cleanup_non_cs_papers.py --analyze-only

    # Actually remove non-CS papers (destructive!)
    uv run cleanup_non_cs_papers.py --remove-non-cs --confirm
"""

import argparse
from typing import Dict
from sqlalchemy import text

from backend.database.connection import get_database_session


def analyze_non_cs_papers(db) -> Dict:
    """Analyze non-CS papers in the database."""

    # Get papers by category group
    category_query = """
    SELECT
        CASE
            WHEN primary_category LIKE 'cs.%' THEN 'Computer Science'
            WHEN primary_category LIKE 'eess.%' THEN 'Electrical Engineering'
            WHEN primary_category LIKE 'stat.%' THEN 'Statistics'
            WHEN primary_category LIKE 'q-bio.%' THEN 'Biology'
            WHEN primary_category LIKE 'q-fin.%' THEN 'Finance'
            WHEN primary_category LIKE 'econ.%' THEN 'Economics'
            WHEN primary_category LIKE 'math.%' THEN 'Mathematics'
            WHEN primary_category LIKE 'physics.%' THEN 'Physics'
            WHEN primary_category LIKE 'quant-ph%' THEN 'Quantum Physics'
            WHEN primary_category LIKE 'cond-mat.%' THEN 'Condensed Matter'
            WHEN primary_category IS NULL THEN 'No Category'
            ELSE 'Other'
        END as category_group,
        COUNT(*) as paper_count,
        ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM papers), 2) as percentage
    FROM papers
    GROUP BY category_group
    ORDER BY paper_count DESC
    """

    result = db.execute(text(category_query)).fetchall()

    categories = {}
    total_papers = 0
    cs_papers = 0
    non_cs_papers = 0

    for row in result:
        categories[row.category_group] = {
            "count": row.paper_count,
            "percentage": row.percentage,
        }
        total_papers += row.paper_count

        if row.category_group == "Computer Science":
            cs_papers = row.paper_count
        else:
            non_cs_papers += row.paper_count

    # Get examples of non-CS papers
    examples_query = """
    SELECT
        arxiv_id,
        title,
        primary_category,
        date_published
    FROM papers
    WHERE primary_category IS NOT NULL
      AND NOT primary_category LIKE 'cs.%'
    ORDER BY date_published DESC NULLS LAST
    LIMIT 20
    """

    examples_result = db.execute(text(examples_query)).fetchall()
    examples = [
        {
            "arxiv_id": row.arxiv_id,
            "title": row.title[:100] + "..." if len(row.title) > 100 else row.title,
            "primary_category": row.primary_category,
            "date_published": row.date_published,
        }
        for row in examples_result
    ]

    # Get papers without categories
    no_category_query = """
    SELECT COUNT(*) as count
    FROM papers
    WHERE primary_category IS NULL
    """

    no_category_result = db.execute(text(no_category_query)).fetchone()
    no_category_count = no_category_result.count

    return {
        "categories": categories,
        "total_papers": total_papers,
        "cs_papers": cs_papers,
        "non_cs_papers": non_cs_papers,
        "no_category_count": no_category_count,
        "examples": examples,
    }


def remove_non_cs_papers(db, dry_run: bool = True) -> Dict:
    """Remove non-CS papers from the database."""

    stats = {
        "papers_removed": 0,
        "repositories_removed": 0,
        "project_pages_removed": 0,
        "authors_cleaned": 0,
    }

    if dry_run:
        print("🔍 DRY RUN MODE - No actual deletions will be performed")

    # Get non-CS papers
    non_cs_query = """
    SELECT id, arxiv_id, title, primary_category
    FROM papers
    WHERE primary_category IS NOT NULL
      AND NOT primary_category LIKE 'cs.%'
    """

    non_cs_papers = db.execute(text(non_cs_query)).fetchall()

    print(f"Found {len(non_cs_papers)} non-CS papers to remove")

    if not dry_run:
        # Remove related data first (due to foreign key constraints)

        # Remove repositories
        repo_delete_query = """
        DELETE FROM repositories
        WHERE paper_id IN (
            SELECT id FROM papers
            WHERE primary_category IS NOT NULL
              AND NOT primary_category LIKE 'cs.%'
        )
        """
        repo_result = db.execute(text(repo_delete_query))
        stats["repositories_removed"] = repo_result.rowcount

        # Remove project pages
        pages_delete_query = """
        DELETE FROM project_pages
        WHERE paper_id IN (
            SELECT id FROM papers
            WHERE primary_category IS NOT NULL
              AND NOT primary_category LIKE 'cs.%'
        )
        """
        pages_result = db.execute(text(pages_delete_query))
        stats["project_pages_removed"] = pages_result.rowcount

        # Remove paper-author relationships
        paper_authors_delete_query = """
        DELETE FROM paper_authors
        WHERE paper_id IN (
            SELECT id FROM papers
            WHERE primary_category IS NOT NULL
              AND NOT primary_category LIKE 'cs.%'
        )
        """
        db.execute(text(paper_authors_delete_query))

        # Remove paper-task relationships
        paper_tasks_delete_query = """
        DELETE FROM paper_tasks
        WHERE paper_id IN (
            SELECT id FROM papers
            WHERE primary_category IS NOT NULL
              AND NOT primary_category LIKE 'cs.%'
        )
        """
        db.execute(text(paper_tasks_delete_query))

        # Remove paper-method relationships
        paper_methods_delete_query = """
        DELETE FROM paper_methods
        WHERE paper_id IN (
            SELECT id FROM papers
            WHERE primary_category IS NOT NULL
              AND NOT primary_category LIKE 'cs.%'
        )
        """
        db.execute(text(paper_methods_delete_query))

        # Remove paper-dataset relationships
        paper_datasets_delete_query = """
        DELETE FROM paper_datasets
        WHERE paper_id IN (
            SELECT id FROM papers
            WHERE primary_category IS NOT NULL
              AND NOT primary_category LIKE 'cs.%'
        )
        """
        db.execute(text(paper_datasets_delete_query))

        # Finally, remove the papers themselves
        papers_delete_query = """
        DELETE FROM papers
        WHERE primary_category IS NOT NULL
          AND NOT primary_category LIKE 'cs.%'
        """
        papers_result = db.execute(text(papers_delete_query))
        stats["papers_removed"] = papers_result.rowcount

        # Clean up orphaned authors (authors with no papers)
        orphaned_authors_query = """
        DELETE FROM authors
        WHERE id NOT IN (
            SELECT DISTINCT author_id FROM paper_authors
        )
        """
        authors_result = db.execute(text(orphaned_authors_query))
        stats["authors_cleaned"] = authors_result.rowcount

        db.commit()
        print("✅ Database cleanup completed")

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Clean up non-Computer Science papers from the database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze what would be removed (safe)
  uv run cleanup_non_cs_papers.py --analyze-only

  # Actually remove non-CS papers (destructive!)
  uv run cleanup_non_cs_papers.py --remove-non-cs --confirm
        """,
    )
    parser.add_argument(
        "--analyze-only",
        action="store_true",
        help="Only analyze and show statistics, don't remove anything",
    )
    parser.add_argument(
        "--remove-non-cs",
        action="store_true",
        help="Actually remove non-CS papers from database",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Confirm that you want to perform destructive operations",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be removed but don't actually remove",
    )

    args = parser.parse_args()

    # Safety checks
    if args.remove_non_cs and not args.confirm and not args.dry_run:
        print("❌ ERROR: --remove-non-cs requires --confirm flag for safety")
        print("   Use --dry-run to see what would be removed first")
        return

    # Get database session
    db_session_gen = get_database_session()
    db = next(db_session_gen)

    try:
        print("🔍 Analyzing papers in database...")
        analysis = analyze_non_cs_papers(db)

        # Print analysis results
        print("\n" + "=" * 80)
        print("📊 DATABASE CATEGORY ANALYSIS")
        print("=" * 80)

        print(f"📄 Total Papers: {analysis['total_papers']:,}")
        print(
            f"🔬 CS Papers: {analysis['cs_papers']:,} ({analysis['cs_papers'] / analysis['total_papers'] * 100:.1f}%)"
        )
        print(
            f"📄 Non-CS Papers: {analysis['non_cs_papers']:,} ({analysis['non_cs_papers'] / analysis['total_papers'] * 100:.1f}%)"
        )
        print(f"❓ Papers without categories: {analysis['no_category_count']:,}")

        print("\n📊 BREAKDOWN BY CATEGORY:")
        for category, data in analysis["categories"].items():
            print(
                f"  {category:>20}: {data['count']:>7,} papers ({data['percentage']:>5.1f}%)"
            )

        print("\n📝 EXAMPLES OF NON-CS PAPERS:")
        for example in analysis["examples"][:10]:
            print(f"  • {example['arxiv_id']} ({example['primary_category']})")
            print(f"    {example['title']}")

        if args.analyze_only:
            print("\n💡 ANALYSIS COMPLETE")
            print("   To remove non-CS papers, run with --remove-non-cs --confirm")
            return

        if args.remove_non_cs:
            print(
                f"\n⚠️  WARNING: About to remove {analysis['non_cs_papers']:,} non-CS papers!"
            )
            print(
                "   This will also remove associated repositories, project pages, etc."
            )

            if not args.dry_run:
                response = input(
                    "\n❓ Are you absolutely sure? Type 'DELETE' to confirm: "
                )
                if response != "DELETE":
                    print("❌ Operation cancelled")
                    return

            # Perform removal
            removal_stats = remove_non_cs_papers(db, dry_run=args.dry_run)

            print("\n" + "=" * 60)
            print("🗑️  CLEANUP RESULTS")
            print("=" * 60)
            print(f"📄 Papers Removed: {removal_stats['papers_removed']:,}")
            print(f"📦 Repositories Removed: {removal_stats['repositories_removed']:,}")
            print(
                f"🌐 Project Pages Removed: {removal_stats['project_pages_removed']:,}"
            )
            print(f"👤 Orphaned Authors Cleaned: {removal_stats['authors_cleaned']:,}")

            if not args.dry_run:
                # Show final stats
                final_analysis = analyze_non_cs_papers(db)
                print("\n📊 FINAL DATABASE STATS:")
                print(f"📄 Total Papers: {final_analysis['total_papers']:,}")
                print(
                    f"🔬 CS Papers: {final_analysis['cs_papers']:,} ({final_analysis['cs_papers'] / final_analysis['total_papers'] * 100:.1f}%)"
                )

                space_saved = analysis["non_cs_papers"]
                print(f"💾 Space Saved: ~{space_saved:,} papers removed")

    except Exception as e:
        print(f"❌ Error during analysis/cleanup: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
