#!/usr/bin/env python3
"""
Add papers that mention "DUSt3r" (case-sensitive) in their title or abstract
to the paper_methods table, linking them to the DUSt3r method.
"""

import psycopg2
from psycopg2.extras import RealDictCursor


def get_db_connection():
    """Get database connection using environment variables."""
    db_params = {
        "host": "localhost",
        "port": "5432",
        "database": "paperswithcode_hf",
        "user": "postgres",
        "password": "postgres",
    }

    return psycopg2.connect(**db_params)


def find_and_add_dust3r_papers():
    """Find papers mentioning DUSt3r and add them to paper_methods table."""

    conn = get_db_connection()

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # First, check if DUSt3r method exists
            print("1. Checking for DUSt3r method in database...")
            cur.execute("SELECT id, name, full_name FROM methods WHERE name = 'DUSt3r'")
            method = cur.fetchone()

            if not method:
                print("❌ DUSt3r method not found in database")
                print("   Please add the DUSt3r method to the methods table first")
                return

            dust3r_method_id = method["id"]
            print(f"✓ Found DUSt3r method (ID: {dust3r_method_id})")
            if method["full_name"]:
                print(f"   Full name: {method['full_name']}")

            # Check current count of papers linked to DUSt3r
            cur.execute(
                "SELECT COUNT(*) as count FROM paper_methods WHERE method_id = %s",
                (dust3r_method_id,),
            )
            current_count = cur.fetchone()["count"]
            print(f"\n2. Current papers linked to DUSt3r: {current_count}")

            # Find papers mentioning "DUSt3r" variations in title or abstract
            # Only consider latest versions
            print("\n3. Searching for papers mentioning 'DUSt3r' variations...")
            print(
                "   (Looking for case variations: DUSt3r, Dust3r, dust3r, DUST3R, Dust3R)"
            )

            # Search for all case variations
            variations = ["DUSt3r", "Dust3r", "dust3r", "DUST3R", "Dust3R"]
            all_papers = set()

            for variation in variations:
                cur.execute(
                    """
                    SELECT id, title, arxiv_id, version
                    FROM papers
                    WHERE is_latest_version = TRUE
                    AND (
                        title LIKE %s
                        OR abstract LIKE %s
                    )
                    ORDER BY id
                    """,
                    (f"%{variation}%", f"%{variation}%"),
                )
                papers_batch = cur.fetchall()
                for paper in papers_batch:
                    all_papers.add(
                        (
                            paper["id"],
                            paper["title"],
                            paper["arxiv_id"],
                            paper["version"],
                        )
                    )

            papers = [
                {"id": p[0], "title": p[1], "arxiv_id": p[2], "version": p[3]}
                for p in all_papers
            ]
            print(f"✓ Found {len(papers)} papers mentioning 'DUSt3r' variations")

            if not papers:
                print("\n✅ No papers found to add")
                return

            # Display papers found
            print("\n4. Papers found:")
            for i, paper in enumerate(papers):
                title_snippet = (
                    paper["title"][:80] + "..."
                    if len(paper["title"]) > 80
                    else paper["title"]
                )
                print(
                    f"   {i + 1}. [{paper['arxiv_id']}{paper['version']}] {title_snippet}"
                )

            # Check which papers already have the DUSt3r method association
            paper_ids = [p["id"] for p in papers]
            placeholders = ",".join(["%s"] * len(paper_ids))
            cur.execute(
                f"""
                SELECT paper_id
                FROM paper_methods
                WHERE method_id = %s
                AND paper_id IN ({placeholders})
                """,
                [dust3r_method_id] + paper_ids,
            )
            existing_paper_ids = {row["paper_id"] for row in cur.fetchall()}

            new_papers = [p for p in papers if p["id"] not in existing_paper_ids]
            print(f"\n5. Papers to add: {len(new_papers)}")
            print(f"   Papers already linked: {len(existing_paper_ids)}")

            if not new_papers:
                print("\n✅ All papers are already linked to DUSt3r method")
                return

            # Add new paper-method relationships
            print("\n6. Adding papers to paper_methods table...")
            added_count = 0

            for paper in new_papers:
                try:
                    cur.execute(
                        "INSERT INTO paper_methods (paper_id, method_id) VALUES (%s, %s)",
                        (paper["id"], dust3r_method_id),
                    )
                    added_count += 1
                    print(
                        f"   ✓ Added [{paper['arxiv_id']}{paper['version']}] {paper['title'][:50]}..."
                    )
                except psycopg2.IntegrityError:
                    print(
                        f"   ⚠ Skipped [{paper['arxiv_id']}{paper['version']}] (already exists)"
                    )
                    conn.rollback()
                    continue

            # Commit the changes
            conn.commit()

            # Final count
            cur.execute(
                "SELECT COUNT(*) as count FROM paper_methods WHERE method_id = %s",
                (dust3r_method_id,),
            )
            final_count = cur.fetchone()["count"]

            print(f"\n{'=' * 80}")
            print("Summary")
            print("=" * 80)
            print(f"DUSt3r method ID: {dust3r_method_id}")
            print(f"Papers found mentioning 'DUSt3r': {len(papers)}")
            print(f"New papers added: {added_count}")
            print(f"Total papers now linked to DUSt3r: {final_count}")
            print("=" * 80)

    except Exception as e:
        print(f"❌ Error: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    print("=" * 80)
    print("Adding Papers that Mention 'DUSt3r' to paper_methods")
    print("=" * 80)

    find_and_add_dust3r_papers()
