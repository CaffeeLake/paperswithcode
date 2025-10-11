#!/usr/bin/env python3
"""
Link papers to tasks based on keyword matching in titles and abstracts.

This script:
1. Loads all tasks that have keywords defined
2. Matches keywords against paper titles and abstracts
3. Uses case-sensitive matching for acronyms (VLM, OCR, ASR, etc.)
4. Uses case-insensitive matching for regular phrases
5. Links papers to tasks in the paper_tasks table
"""

import re
import os
from typing import Dict, List, Set, Tuple
from collections import defaultdict

import psycopg2
from psycopg2.extras import RealDictCursor, execute_batch


# Acronyms and terms that should use case-sensitive matching
CASE_SENSITIVE_TERMS = {
    "VLM",
    "MLLM",
    "LVLM",
    "OCR",
    "ASR",
    "NMT",
    "LLM",
    "GUI",
    "RLVR",
    "CoT",
    "VLA",
    "SWE",
    "CIFAR10",
    "ImageNet",
    "OSWorld",
    "NeRF",
    "DUSt3R",
    "VGGT",
    "FLUX1",
    "AI",
    "NLP",
    "CV",
}


def get_db_connection():
    """Get database connection."""
    return psycopg2.connect(
        host=os.getenv("PWC_DB_HOST", "localhost"),
        port=os.getenv("PWC_DB_PORT", "5432"),
        database=os.getenv("PWC_DB_NAME", "paperswithcode_hf"),
        user=os.getenv("PWC_DB_USER", "postgres"),
        password=os.getenv("PWC_DB_PASSWORD", "postgres"),
    )


def is_case_sensitive_keyword(keyword: str) -> bool:
    """
    Determine if a keyword should use case-sensitive matching.

    Args:
        keyword: The keyword to check

    Returns:
        True if case-sensitive matching should be used
    """
    # Check if keyword is in the explicit case-sensitive list
    if keyword in CASE_SENSITIVE_TERMS:
        return True

    # Check if keyword is all-caps (2+ chars) - likely an acronym
    if len(keyword) >= 2 and keyword.isupper():
        # Allow hyphens in acronyms (e.g., SWE-Bench)
        keyword_cleaned = keyword.replace("-", "")
        if keyword_cleaned.isupper() and keyword_cleaned.isalpha():
            return True

    return False


def load_tasks_with_keywords(conn) -> List[Dict]:
    """Load all tasks that have keywords defined."""
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT id, name, keywords
        FROM tasks
        WHERE keywords IS NOT NULL AND keywords != ''
        ORDER BY id
    """)

    tasks = []
    for row in cur.fetchall():
        # Parse comma-separated keywords
        keywords_list = [k.strip() for k in row["keywords"].split(",") if k.strip()]

        if not keywords_list:
            continue

        # Categorize keywords by case sensitivity
        case_sensitive_keywords = []
        case_insensitive_keywords = []

        for keyword in keywords_list:
            if is_case_sensitive_keyword(keyword):
                case_sensitive_keywords.append(keyword)
            else:
                case_insensitive_keywords.append(keyword)

        tasks.append(
            {
                "id": row["id"],
                "name": row["name"],
                "keywords": keywords_list,
                "case_sensitive_keywords": case_sensitive_keywords,
                "case_insensitive_keywords": case_insensitive_keywords,
            }
        )

    cur.close()
    return tasks


def create_keyword_patterns(
    tasks: List[Dict],
) -> Tuple[Dict[str, List[int]], Dict[str, List[int]]]:
    """
    Create lookup structures for keyword matching.

    Returns:
        (case_sensitive_patterns, case_insensitive_patterns)
        Each pattern dict maps keyword -> list of task IDs
    """
    case_sensitive = defaultdict(list)
    case_insensitive = defaultdict(list)

    for task in tasks:
        task_id = task["id"]

        # Add case-sensitive keywords
        for keyword in task["case_sensitive_keywords"]:
            case_sensitive[keyword].append(task_id)

        # Add case-insensitive keywords (store in lowercase)
        for keyword in task["case_insensitive_keywords"]:
            case_insensitive[keyword.lower()].append(task_id)

    return dict(case_sensitive), dict(case_insensitive)


def find_matching_tasks(
    text: str,
    case_sensitive_patterns: Dict[str, List[int]],
    case_insensitive_patterns: Dict[str, List[int]],
) -> Set[int]:
    """
    Find all tasks whose keywords appear in the text.

    Args:
        text: The text to search (title + abstract)
        case_sensitive_patterns: Case-sensitive keyword patterns
        case_insensitive_patterns: Case-insensitive keyword patterns

    Returns:
        Set of task IDs that match
    """
    if not text:
        return set()

    matched_tasks = set()

    # Find case-sensitive matches
    for keyword, task_ids in case_sensitive_patterns.items():
        # Use word boundary matching for better accuracy
        pattern = r"\b" + re.escape(keyword) + r"\b"
        if re.search(pattern, text):
            matched_tasks.update(task_ids)

    # Find case-insensitive matches
    text_lower = text.lower()
    for keyword_lower, task_ids in case_insensitive_patterns.items():
        pattern = r"\b" + re.escape(keyword_lower) + r"\b"
        if re.search(pattern, text_lower):
            matched_tasks.update(task_ids)

    return matched_tasks


def link_papers_by_task_keywords():
    """Main function to link papers to tasks based on keyword matching."""

    try:
        print("=" * 80)
        print("Linking Papers to Tasks Based on Keywords")
        print("=" * 80)

        # Connect to database
        conn = get_db_connection()

        # Load tasks and create keyword patterns
        print("\n1. Loading tasks with keywords...")
        tasks = load_tasks_with_keywords(conn)
        print(f"   ✓ Loaded {len(tasks)} tasks with keywords")

        # Count case-sensitive vs case-insensitive
        total_case_sensitive = sum(len(t["case_sensitive_keywords"]) for t in tasks)
        total_case_insensitive = sum(len(t["case_insensitive_keywords"]) for t in tasks)
        print(f"   - {total_case_sensitive} case-sensitive keywords")
        print(f"   - {total_case_insensitive} case-insensitive keywords")

        print("\n2. Building keyword patterns...")
        case_sensitive_patterns, case_insensitive_patterns = create_keyword_patterns(
            tasks
        )
        total_keywords = len(case_sensitive_patterns) + len(case_insensitive_patterns)
        print(f"   ✓ Built patterns for {total_keywords} unique keywords")
        print(f"   - {len(case_sensitive_patterns)} unique case-sensitive keywords")
        print(f"   - {len(case_insensitive_patterns)} unique case-insensitive keywords")

        # Check current state of paper_tasks
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT COUNT(*) as count FROM paper_tasks")
        initial_count = cur.fetchone()["count"]
        print(f"\n3. Current paper_tasks relationships: {initial_count:,}")

        # Process papers in batches
        print("\n4. Processing papers...")
        print("   (Streaming through papers and matching keywords...)")

        cur.execute("""
            SELECT id, title, abstract
            FROM papers
            WHERE is_latest_version
            ORDER BY id
        """)

        papers_processed = 0
        papers_matched = 0
        new_relationships = 0
        batch = []
        batch_size = 1000

        # Track statistics
        task_match_counts = defaultdict(int)

        for paper in cur:
            papers_processed += 1

            if papers_processed % 5000 == 0:
                print(
                    f"   Processed {papers_processed:,} papers, "
                    f"matched {papers_matched:,}, "
                    f"found {new_relationships:,} new relationships..."
                )

            # Combine title and abstract for matching
            text = ""
            if paper["title"]:
                text = paper["title"]
            if paper["abstract"]:
                text += " " + paper["abstract"]

            if not text.strip():
                continue

            # Find matching tasks
            matching_task_ids = find_matching_tasks(
                text, case_sensitive_patterns, case_insensitive_patterns
            )

            if matching_task_ids:
                papers_matched += 1

                for task_id in matching_task_ids:
                    batch.append({"paper_id": paper["id"], "task_id": task_id})
                    new_relationships += 1
                    task_match_counts[task_id] += 1

            # Insert batch
            if len(batch) >= batch_size:
                cur2 = conn.cursor()
                execute_batch(
                    cur2,
                    """
                    INSERT INTO paper_tasks (paper_id, task_id)
                    VALUES (%(paper_id)s, %(task_id)s)
                    ON CONFLICT (paper_id, task_id) DO NOTHING
                """,
                    batch,
                )
                conn.commit()
                cur2.close()
                batch = []

        # Insert remaining batch
        if batch:
            cur2 = conn.cursor()
            execute_batch(
                cur2,
                """
                INSERT INTO paper_tasks (paper_id, task_id)
                VALUES (%(paper_id)s, %(task_id)s)
                ON CONFLICT (paper_id, task_id) DO NOTHING
            """,
                batch,
            )
            conn.commit()
            cur2.close()

        cur.close()

        # Final statistics
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT COUNT(*) as count FROM paper_tasks")
        final_count = cur.fetchone()["count"]

        print(f"\n   ✓ Finished processing {papers_processed:,} papers")

        print("\n" + "=" * 80)
        print("Import Statistics")
        print("=" * 80)
        print(f"Papers processed:              {papers_processed:>10,}")
        print(f"Papers with keyword matches:   {papers_matched:>10,}")
        print(f"New relationships found:       {new_relationships:>10,}")
        print(f"Initial paper_tasks count:     {initial_count:>10,}")
        print(f"Final paper_tasks count:       {final_count:>10,}")
        print(f"Relationships actually added:  {final_count - initial_count:>10,}")

        # Show top tasks by new matches
        print("\n" + "=" * 80)
        print("Top 20 Tasks by New Keyword Matches")
        print("=" * 80)

        # Get task names for the matched IDs
        task_id_to_name = {}
        for task in tasks:
            task_id_to_name[task["id"]] = task["name"]

        # Sort by match count
        sorted_tasks = sorted(
            task_match_counts.items(), key=lambda x: x[1], reverse=True
        )[:20]

        for task_id, count in sorted_tasks:
            task_name = task_id_to_name.get(task_id, f"Unknown (ID {task_id})")
            print(f"{task_name:40} {count:>8,} matches")

        # Show overall top tasks in database
        print("\n" + "=" * 80)
        print("Top 20 Tasks by Total Paper Count (after keyword linking)")
        print("=" * 80)

        cur.execute("""
            SELECT t.name, COUNT(pt.paper_id) as paper_count
            FROM tasks t
            LEFT JOIN paper_tasks pt ON t.id = pt.task_id
            GROUP BY t.id, t.name
            ORDER BY paper_count DESC
            LIMIT 20
        """)

        for row in cur.fetchall():
            print(f"{row['name']:40} {row['paper_count']:>8,} papers")

        cur.close()
        conn.close()

        print("\n✅ Successfully linked papers to tasks based on keywords!")

    except Exception as e:
        print(f"\n❌ Error linking papers by keywords: {str(e)}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(link_papers_by_task_keywords())
