#!/usr/bin/env python3
"""
Add papers mentioning MCP to the paper_methods table.

This script finds all papers that mention "MCP" or "Model Context Protocol"
(case-sensitive) in their title or abstract and associates them with the
MCP method in the paper_methods table.

Usage:
    uv run --env-file backend/keys.env backend/database/methods_setup/add_mcp_papers.py
"""

import sys
import os
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))


def get_db_connection():
    """Get database connection using environment variables."""
    db_params = {
        "dbname": os.getenv("DB_NAME", "paperswithcode_hf"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", "postgres"),
        "host": os.getenv("DB_HOST", "localhost"),
        "port": os.getenv("DB_PORT", "5432"),
    }
    return psycopg2.connect(**db_params)


def find_and_add_mcp_papers():
    """Find papers mentioning MCP and add them to paper_methods table."""

    conn = get_db_connection()

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # First, get the MCP method ID
            cur.execute("SELECT id FROM methods WHERE name = 'MCP'")
            method = cur.fetchone()

            if not method:
                print("❌ MCP method not found in database")
                return

            mcp_method_id = method["id"]
            print(f"✓ Found MCP method (ID: {mcp_method_id})")

            # Find papers mentioning "MCP" or "Model Context Protocol" (case-sensitive)
            # Only consider latest versions
            print("\nSearching for papers mentioning MCP...")
            cur.execute(
                """
                SELECT id, title, arxiv_id, version
                FROM papers
                WHERE is_latest_version = TRUE
                AND (
                    title LIKE %s
                    OR title LIKE %s
                    OR abstract LIKE %s
                    OR abstract LIKE %s
                )
                ORDER BY id
                """,
                (
                    "%MCP%",
                    "%Model Context Protocol%",
                    "%MCP%",
                    "%Model Context Protocol%",
                ),
            )

            papers = cur.fetchall()
            print(
                f"✓ Found {len(papers)} papers mentioning MCP or Model Context Protocol"
            )

            if not papers:
                print("\n✓ No papers found to add")
                return

            # Display papers found
            print("\nPapers found:")
            for paper in papers:
                print(
                    f"  - [{paper['arxiv_id']}{paper['version']}] {paper['title'][:80]}..."
                )

            # Check which papers already have the MCP method association
            paper_ids = [p["id"] for p in papers]
            cur.execute(
                """
                SELECT paper_id
                FROM paper_methods
                WHERE method_id = %s AND paper_id = ANY(%s)
                """,
                (mcp_method_id, paper_ids),
            )
            existing_associations = {row["paper_id"] for row in cur.fetchall()}

            if existing_associations:
                print(
                    f"\n⊘ {len(existing_associations)} papers already associated with MCP method"
                )

            # Add new associations
            new_papers = [p for p in papers if p["id"] not in existing_associations]

            if not new_papers:
                print("\n✓ All papers are already associated with MCP method")
                return

            print(f"\n✓ Adding {len(new_papers)} new paper-method associations...")

            # Insert new associations
            insert_data = [(paper["id"], mcp_method_id) for paper in new_papers]

            cur.executemany(
                """
                INSERT INTO paper_methods (paper_id, method_id)
                VALUES (%s, %s)
                ON CONFLICT (paper_id, method_id) DO NOTHING
                """,
                insert_data,
            )

            conn.commit()

            print(f"✅ Successfully added {len(new_papers)} papers to MCP method!")

            # Final statistics
            print("\n" + "=" * 80)
            print("SUMMARY")
            print("=" * 80)
            print(f"Total papers mentioning MCP: {len(papers)}")
            print(f"Already associated: {len(existing_associations)}")
            print(f"Newly added: {len(new_papers)}")

            # Show sample of newly added papers
            if new_papers:
                print("\nSample of newly added papers:")
                for paper in new_papers[:5]:
                    print(
                        f"  - [{paper['arxiv_id']}{paper['version']}] {paper['title'][:70]}..."
                    )
                if len(new_papers) > 5:
                    print(f"  ... and {len(new_papers) - 5} more")

    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        import traceback

        traceback.print_exc()
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    find_and_add_mcp_papers()
