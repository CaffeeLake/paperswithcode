#!/usr/bin/env python3
"""
Link papers to the "Vision-Language Models" task based on keyword matching.

Keywords (case-sensitive):
- VLM, MLLM, LVLM

Keywords (case-insensitive):
- Vision-Language Model, vision language model, Multimodal Large Language Model, Multimodal LLM
"""

import re
from typing import List, Set
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


def build_patterns() -> tuple[List[re.Pattern], List[re.Pattern]]:
    """
    Build regex patterns for case-sensitive and case-insensitive keywords.

    Returns:
        Tuple of (case_sensitive_patterns, case_insensitive_patterns)
    """
    # Case-sensitive keywords
    case_sensitive_keywords = ["VLM", "MLLM", "LVLM"]

    # Case-insensitive keywords
    case_insensitive_keywords = [
        "Vision-Language Model",
        "vision language model",
        "Multimodal Large Language Model",
        "Multimodal LLM",
    ]

    case_sensitive_patterns = []
    for keyword in case_sensitive_keywords:
        # Match as whole word or part of compound words (e.g., VLM-based, MLLM+)
        pattern = re.compile(r"\b" + re.escape(keyword) + r"(?:[s\-+]|\b)")
        case_sensitive_patterns.append(pattern)

    case_insensitive_patterns = []
    for keyword in case_insensitive_keywords:
        # Match as whole word or part of compound words
        pattern = re.compile(
            r"\b" + re.escape(keyword) + r"(?:[s\-+]|\b)", re.IGNORECASE
        )
        case_insensitive_patterns.append(pattern)

    return case_sensitive_patterns, case_insensitive_patterns


def find_matching_papers(
    conn,
    case_sensitive_patterns: List[re.Pattern],
    case_insensitive_patterns: List[re.Pattern],
) -> Set[int]:
    """
    Find all papers that match any of the keywords in title or abstract.

    Args:
        conn: Database connection
        case_sensitive_patterns: List of case-sensitive regex patterns
        case_insensitive_patterns: List of case-insensitive regex patterns

    Returns:
        Set of paper IDs that match
    """
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Fetch all papers with latest version only
    cur.execute("""
        SELECT id, title, abstract
        FROM papers
        WHERE is_latest_version
        ORDER BY id
    """)

    matching_paper_ids = set()
    processed = 0

    print("   Searching papers for keyword matches...")

    for row in cur:
        processed += 1
        if processed % 10000 == 0:
            print(
                f"   - Processed {processed:,} papers, found {len(matching_paper_ids):,} matches so far..."
            )

        paper_id = row["id"]
        title = row["title"] or ""
        abstract = row["abstract"] or ""
        text = f"{title} {abstract}"

        # Skip if text is empty
        if not text.strip():
            continue

        # Check case-sensitive patterns
        for pattern in case_sensitive_patterns:
            if pattern.search(text):
                matching_paper_ids.add(paper_id)
                break

        # If not already matched, check case-insensitive patterns
        if paper_id not in matching_paper_ids:
            for pattern in case_insensitive_patterns:
                if pattern.search(text):
                    matching_paper_ids.add(paper_id)
                    break

    cur.close()
    print(
        f"   ✓ Processed {processed:,} papers, found {len(matching_paper_ids):,} total matches"
    )

    return matching_paper_ids


def link_papers_to_task(conn, task_id: int, paper_ids: Set[int]) -> int:
    """
    Link papers to the task by inserting into paper_tasks table.

    Args:
        conn: Database connection
        task_id: ID of the Vision-Language Models task
        paper_ids: Set of paper IDs to link

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
    new_paper_ids = paper_ids - existing_paper_ids
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


def link_vlm_papers() -> int:
    """
    Main function to link papers to Vision-Language Models task.

    Returns:
        Exit code (0 for success, 1 for error)
    """
    try:
        print("=" * 80)
        print("Linking Papers to Vision-Language Models Task")
        print("=" * 80)

        # Connect to database
        print("\n1. Connecting to database...")
        conn = get_db_connection()
        print("   ✓ Connected successfully")

        # Get task ID
        print("\n2. Finding Vision-Language Models task...")
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT id, name, keywords
            FROM tasks
            WHERE name = 'Vision-Language Models' AND keywords IS NOT NULL
            LIMIT 1
        """)
        task = cur.fetchone()
        cur.close()

        if not task:
            print("   ❌ Vision-Language Models task not found or has no keywords")
            conn.close()
            return 1

        task_id = task["id"]
        print(f"   ✓ Found task: {task['name']} (ID: {task_id})")
        print(f"   Keywords: {task['keywords']}")

        # Build patterns
        print("\n3. Building search patterns...")
        case_sensitive_patterns, case_insensitive_patterns = build_patterns()
        total_keywords = len(case_sensitive_patterns) + len(case_insensitive_patterns)
        print(f"   ✓ Built patterns for {total_keywords} keywords")
        print(f"   - {len(case_sensitive_patterns)} case-sensitive")
        print(f"   - {len(case_insensitive_patterns)} case-insensitive")

        # Find matching papers
        print("\n4. Finding matching papers...")
        matching_paper_ids = find_matching_papers(
            conn, case_sensitive_patterns, case_insensitive_patterns
        )

        # Link papers to task
        print("\n5. Linking papers to task...")
        new_links = link_papers_to_task(conn, task_id, matching_paper_ids)

        # Print summary
        print("\n" + "=" * 80)
        print("Summary")
        print("=" * 80)
        print(f"Task: Vision-Language Models (ID: {task_id})")
        print(f"Papers matching keywords: {len(matching_paper_ids):,}")
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
    exit(link_vlm_papers())
