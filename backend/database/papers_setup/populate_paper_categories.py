#!/usr/bin/env python3
"""
Populate category fields for existing papers in the database.

This script:
1. Fetches papers that don't have categories populated
2. Calls arXiv API to get their categories
3. Updates the database with category information
4. Provides progress tracking and statistics

Usage:
    uv run populate_paper_categories.py --limit 1000 --batch-size 50
"""

import argparse
import requests
import xml.etree.ElementTree as ET
import time
from typing import Dict, List, Optional, Tuple
from sqlalchemy import text

from backend.database.connection import get_database_session


def fetch_arxiv_categories(
    arxiv_id: str, retry_count: int = 3
) -> Optional[Tuple[str, List[str]]]:
    """Fetch categories for a paper from arXiv API."""

    for attempt in range(retry_count):
        url = f"http://export.arxiv.org/api/query?id_list={arxiv_id}"

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()

            # Parse XML
            root = ET.fromstring(response.content)
            ns = {
                "atom": "http://www.w3.org/2005/Atom",
                "arxiv": "http://arxiv.org/schemas/atom",
            }

            entries = root.findall("atom:entry", ns)
            if not entries:
                if attempt < retry_count - 1:
                    time.sleep(2)
                    continue
                else:
                    return None

            entry = entries[0]

            # Extract categories
            categories = [cat.get("term") for cat in entry.findall("atom:category", ns)]
            primary_category = categories[0] if categories else None

            return primary_category, categories

        except Exception as e:
            if attempt < retry_count - 1:
                time.sleep(5)
                continue
            else:
                print(f"    Error fetching {arxiv_id}: {e}")
                return None

    return None


def get_papers_without_categories(db, limit: Optional[int] = None) -> List[Dict]:
    """Get papers that don't have categories populated."""

    query = """
    SELECT id, arxiv_id, title
    FROM papers
    WHERE arxiv_id IS NOT NULL
      AND arxiv_id != ''
      AND primary_category IS NULL
    ORDER BY id DESC
    """

    if limit:
        query += f" LIMIT {limit}"

    result = db.execute(text(query)).fetchall()

    return [
        {
            "id": row.id,
            "arxiv_id": row.arxiv_id,
            "title": row.title,
        }
        for row in result
    ]


def update_paper_categories(
    db, paper_id: int, primary_category: str, all_categories: List[str]
):
    """Update paper with category information."""

    query = """
    UPDATE papers
    SET primary_category = :primary_category,
        all_categories = :all_categories,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = :paper_id
    """

    db.execute(
        text(query),
        {
            "paper_id": paper_id,
            "primary_category": primary_category,
            "all_categories": all_categories,
        },
    )
    db.commit()


def process_papers_batch(db, papers: List[Dict]) -> Dict:
    """Process a batch of papers and update their categories."""

    stats = {
        "processed": 0,
        "successful": 0,
        "failed": 0,
        "cs_papers": 0,
        "non_cs_papers": 0,
    }

    for paper in papers:
        paper_id = paper["id"]
        arxiv_id = paper["arxiv_id"]

        print(f"  Processing {arxiv_id}...")

        # Fetch categories
        category_data = fetch_arxiv_categories(arxiv_id)
        stats["processed"] += 1

        if category_data is None:
            stats["failed"] += 1
            print("    ❌ Failed to fetch categories")
            continue

        primary_category, all_categories = category_data

        if not primary_category:
            stats["failed"] += 1
            print("    ❌ No primary category found")
            continue

        # Update database
        try:
            update_paper_categories(db, paper_id, primary_category, all_categories)
            stats["successful"] += 1

            # Track CS vs non-CS
            if primary_category.startswith("cs."):
                stats["cs_papers"] += 1
                print(f"    ✅ CS: {primary_category}")
            else:
                stats["non_cs_papers"] += 1
                print(f"    📄 Non-CS: {primary_category}")

        except Exception as e:
            stats["failed"] += 1
            print(f"    ❌ Database update failed: {e}")

        # Rate limiting
        time.sleep(0.2)  # Be nice to arXiv API

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Populate category fields for papers in the database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of papers to process",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Number of papers to process in each batch (default: 50)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't update database, just show what would be done",
    )

    args = parser.parse_args()

    # Get database session
    db_session_gen = get_database_session()
    db = next(db_session_gen)

    try:
        print("🔍 Finding papers without categories...")
        papers = get_papers_without_categories(db, args.limit)

        if not papers:
            print("✅ All papers already have categories!")
            return

        print(f"📄 Found {len(papers)} papers needing category information")

        if args.dry_run:
            print("🔍 DRY RUN MODE - No database updates will be made")
            # Just show first few papers
            for paper in papers[:5]:
                print(
                    f"  Would process: {paper['arxiv_id']} - {paper['title'][:80]}..."
                )
            return

        # Process in batches
        total_stats = {
            "processed": 0,
            "successful": 0,
            "failed": 0,
            "cs_papers": 0,
            "non_cs_papers": 0,
        }

        for i in range(0, len(papers), args.batch_size):
            batch = papers[i : i + args.batch_size]
            batch_num = (i // args.batch_size) + 1
            total_batches = (len(papers) + args.batch_size - 1) // args.batch_size

            print(
                f"\n📦 Processing batch {batch_num}/{total_batches} ({len(batch)} papers)"
            )

            batch_stats = process_papers_batch(db, batch)

            # Update totals
            for key in total_stats:
                total_stats[key] += batch_stats[key]

            # Print batch summary
            print(
                f"  Batch {batch_num} complete: {batch_stats['successful']}/{batch_stats['processed']} successful"
            )

            # Brief pause between batches
            if batch_num < total_batches:
                time.sleep(1)

        # Final summary
        print("\n" + "=" * 60)
        print("📊 CATEGORY POPULATION COMPLETE")
        print("=" * 60)
        print(f"📄 Total Papers Processed: {total_stats['processed']}")
        print(f"✅ Successful Updates: {total_stats['successful']}")
        print(f"❌ Failed Updates: {total_stats['failed']}")

        if total_stats["successful"] > 0:
            cs_percentage = total_stats["cs_papers"] / total_stats["successful"] * 100
            print(f"🔬 CS Papers: {total_stats['cs_papers']} ({cs_percentage:.1f}%)")
            print(
                f"📄 Non-CS Papers: {total_stats['non_cs_papers']} ({100 - cs_percentage:.1f}%)"
            )

        # Show updated database stats
        print("\n📈 Updated Database Statistics:")
        stats_query = """
        SELECT
            CASE
                WHEN primary_category LIKE 'cs.%' THEN 'Computer Science'
                WHEN primary_category LIKE 'eess.%' THEN 'Electrical Engineering'
                WHEN primary_category LIKE 'stat.%' THEN 'Statistics'
                WHEN primary_category LIKE 'q-bio.%' THEN 'Biology'
                WHEN primary_category LIKE 'q-fin.%' THEN 'Finance'
                WHEN primary_category LIKE 'econ.%' THEN 'Economics'
                ELSE 'Other'
            END as category_group,
            COUNT(*) as paper_count
        FROM papers
        WHERE primary_category IS NOT NULL
        GROUP BY category_group
        ORDER BY paper_count DESC
        LIMIT 10
        """

        result = db.execute(text(stats_query)).fetchall()
        for row in result:
            print(f"  {row.category_group}: {row.paper_count:,} papers")

    except Exception as e:
        print(f"❌ Error during processing: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
