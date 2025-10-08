#!/usr/bin/env python3
"""
Link papers to the "Machine Translation" task based on arxiv_ids from JSON file.

Reads data/machine_translation_papers.json and links papers by matching arxiv_id.
"""

import json
import os
from typing import Set, Dict, List
import psycopg2
from psycopg2.extras import RealDictCursor, execute_batch


def get_db_connection():
    """Get database connection using postgres user."""
    return psycopg2.connect(
        host="localhost",
        port="5432",
        database="paperswithcode_hf",
        user="postgres",
        password="postgres",
    )


def load_arxiv_ids_from_json(json_file: str) -> Set[str]:
    """
    Load arxiv_ids from the JSON file.

    Args:
        json_file: Path to the JSON file containing machine translation papers

    Returns:
        Set of arxiv_ids to link
    """
    print(f"   Loading JSON file: {json_file}")

    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    arxiv_ids = set()
    for paper in data:
        arxiv_id = paper.get("arxiv_id")
        if arxiv_id:
            # Normalize arxiv_id - remove version suffix if present
            # e.g., "1806.00187v3" -> "1806.00187"
            if "v" in arxiv_id:
                base_id = arxiv_id.split("v")[0]
            else:
                base_id = arxiv_id
            arxiv_ids.add(base_id)

    print(f"   ✓ Found {len(arxiv_ids):,} unique arxiv_ids in JSON file")
    return arxiv_ids


def find_paper_ids_by_arxiv_ids(conn, arxiv_ids: Set[str]) -> Dict[str, int]:
    """
    Find paper IDs in the database that match the arxiv_ids.

    Args:
        conn: Database connection
        arxiv_ids: Set of arxiv_ids to search for

    Returns:
        Dictionary mapping arxiv_id -> paper_id
    """
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Query papers with matching arxiv_ids (latest version only)
    # We'll use batches to avoid hitting parameter limits
    batch_size = 1000
    arxiv_id_list = list(arxiv_ids)

    paper_mapping = {}
    total_batches = (len(arxiv_id_list) + batch_size - 1) // batch_size

    print(f"   Searching for papers in {total_batches} batches...")

    for i in range(0, len(arxiv_id_list), batch_size):
        batch = arxiv_id_list[i : i + batch_size]

        # Create placeholders for the IN clause
        placeholders = ",".join(["%s"] * len(batch))

        query = f"""
            SELECT id, arxiv_id
            FROM papers
            WHERE arxiv_id IN ({placeholders})
              AND is_latest_version
        """

        cur.execute(query, batch)

        for row in cur.fetchall():
            paper_mapping[row["arxiv_id"]] = row["id"]

        if (i // batch_size + 1) % 10 == 0:
            print(
                f"   - Processed {i // batch_size + 1}/{total_batches} batches, found {len(paper_mapping):,} papers so far..."
            )

    cur.close()
    print(
        f"   ✓ Found {len(paper_mapping):,} papers in database matching the arxiv_ids"
    )

    return paper_mapping


def link_papers_to_task(conn, task_id: int, paper_ids: List[int]) -> int:
    """
    Link papers to the task by inserting into paper_tasks table.

    Args:
        conn: Database connection
        task_id: ID of the Machine Translation task
        paper_ids: List of paper IDs to link

    Returns:
        Number of new links created
    """
    cur = conn.cursor()

    # Get existing links
    cur.execute(
        """
        SELECT paper_id
        FROM paper_tasks
        WHERE task_id = %s
    """,
        (task_id,),
    )

    existing_paper_ids = {row[0] for row in cur.fetchall()}
    print(f"   - Found {len(existing_paper_ids):,} existing links")

    # Find new links to create
    paper_ids_set = set(paper_ids)
    new_paper_ids = paper_ids_set - existing_paper_ids
    print(f"   - Will create {len(new_paper_ids):,} new links")

    if not new_paper_ids:
        cur.close()
        return 0

    # Insert new links in batches
    batch_size = 1000
    new_links = [(paper_id, task_id) for paper_id in new_paper_ids]

    print("   Inserting new links...")
    execute_batch(
        cur,
        "INSERT INTO paper_tasks (paper_id, task_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        new_links,
        page_size=batch_size,
    )

    conn.commit()
    cur.close()

    return len(new_paper_ids)


def link_machine_translation_papers() -> int:
    """
    Main function to link papers to Machine Translation task.

    Returns:
        Exit code (0 for success, 1 for error)
    """
    try:
        print("=" * 80)
        print("Linking Papers to Machine Translation Task")
        print("=" * 80)

        # Connect to database
        print("\n1. Connecting to database...")
        conn = get_db_connection()
        print("   ✓ Connected successfully")

        # Get task ID
        print("\n2. Finding Machine Translation task...")
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT id, name, slug
            FROM tasks
            WHERE slug = 'machine-translation'
            LIMIT 1
        """)
        task = cur.fetchone()
        cur.close()

        if not task:
            print("   ❌ Machine Translation task not found")
            conn.close()
            return 1

        task_id = task["id"]
        print(f"   ✓ Found task: {task['name']} (ID: {task_id})")

        # Load arxiv_ids from JSON
        print("\n3. Loading arxiv_ids from JSON file...")
        json_file = "data/machine_translation_papers.json"

        if not os.path.exists(json_file):
            print(f"   ❌ JSON file not found: {json_file}")
            conn.close()
            return 1

        arxiv_ids = load_arxiv_ids_from_json(json_file)

        # Find matching papers in database
        print("\n4. Finding matching papers in database...")
        paper_mapping = find_paper_ids_by_arxiv_ids(conn, arxiv_ids)

        if not paper_mapping:
            print("   ⚠️  No matching papers found in database")
            conn.close()
            return 0

        # Link papers to task
        print("\n5. Linking papers to task...")
        paper_ids = list(paper_mapping.values())
        new_links = link_papers_to_task(conn, task_id, paper_ids)

        # Calculate statistics
        not_found = len(arxiv_ids) - len(paper_mapping)

        # Print summary
        print("\n" + "=" * 80)
        print("Summary")
        print("=" * 80)
        print(f"Task: Machine Translation (ID: {task_id})")
        print(f"ArXiv IDs in JSON file: {len(arxiv_ids):,}")
        print(f"Papers found in database: {len(paper_mapping):,}")
        print(f"Papers not found: {not_found:,}")
        print(f"New links created: {new_links:,}")
        print("=" * 80)

        conn.close()
        print("\n✅ Successfully completed!")

        return 0

    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(link_machine_translation_papers())
