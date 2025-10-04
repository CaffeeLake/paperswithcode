"""
Add papers from annotated CSV to their corresponding tasks.

This script:
1. Reads the annotated areas CSV file
2. Extracts arxiv IDs from Hugging Face URLs
3. Finds papers in the database
4. Associates them with the appropriate tasks
"""

import os
import csv
import re
from typing import List, Set
import psycopg2
from psycopg2.extras import RealDictCursor


def extract_arxiv_id(url: str) -> str | None:
    """Extract arxiv ID from Hugging Face URL."""
    # Pattern: https://huggingface.co/papers/YYMM.NNNNN
    match = re.search(r"/papers/(\d{4}\.\d{5})", url)
    if match:
        return match.group(1)
    return None


def normalize_task_name(task_name: str) -> str:
    """Normalize task name for matching."""
    # Remove extra spaces, convert to lowercase for comparison
    return task_name.strip().lower()


def parse_tasks(tasks_str: str) -> List[str]:
    """Parse comma-separated task names."""
    if not tasks_str or tasks_str.strip() == "":
        return []
    return [task.strip() for task in tasks_str.split(",") if task.strip()]


def get_task_id_by_name(cursor, task_name: str) -> int | None:
    """Find task ID by name (case-insensitive)."""
    normalized = normalize_task_name(task_name)
    cursor.execute("SELECT id, name FROM tasks WHERE LOWER(name) = %s", (normalized,))
    result = cursor.fetchone()
    return result["id"] if result else None


def get_paper_id_by_arxiv(cursor, arxiv_id: str) -> int | None:
    """Find paper ID by arxiv ID."""
    cursor.execute(
        "SELECT id FROM papers WHERE arxiv_id = %s AND is_latest_version", (arxiv_id,)
    )
    result = cursor.fetchone()
    return result["id"] if result else None


def paper_task_exists(cursor, paper_id: int, task_id: int) -> bool:
    """Check if paper-task association already exists."""
    cursor.execute(
        "SELECT 1 FROM paper_tasks WHERE paper_id = %s AND task_id = %s",
        (paper_id, task_id),
    )
    return cursor.fetchone() is not None


def add_paper_task(cursor, paper_id: int, task_id: int) -> bool:
    """Add paper-task association if it doesn't exist."""
    if paper_task_exists(cursor, paper_id, task_id):
        return False

    cursor.execute(
        "INSERT INTO paper_tasks (paper_id, task_id) VALUES (%s, %s)",
        (paper_id, task_id),
    )
    return True


def main():
    # Database connection
    conn = psycopg2.connect(
        host=os.getenv("PWC_DB_HOST"),
        database=os.getenv("PWC_DB_NAME"),
        user=os.getenv("PWC_DB_USER"),
        password=os.getenv("PWC_DB_PASSWORD"),
    )

    csv_path = "/root/python_projects/paperswithcode/data/Methods, areas and tasks - Annotated areas.csv"

    # Statistics
    stats = {
        "total_rows": 0,
        "papers_found": 0,
        "papers_not_found": 0,
        "tasks_added": 0,
        "tasks_already_exist": 0,
        "tasks_not_found": 0,
        "rows_without_arxiv": 0,
    }

    papers_not_found = []
    tasks_not_found_set: Set[str] = set()

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Read CSV file
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)

                for row in reader:
                    stats["total_rows"] += 1

                    # Extract arxiv ID from URL
                    paper_url = row["Paper"]
                    arxiv_id = extract_arxiv_id(paper_url)

                    if not arxiv_id:
                        stats["rows_without_arxiv"] += 1
                        print(f"⚠️  Could not extract arxiv ID from: {paper_url}")
                        continue

                    # Find paper in database
                    paper_id = get_paper_id_by_arxiv(cur, arxiv_id)

                    if not paper_id:
                        stats["papers_not_found"] += 1
                        papers_not_found.append(arxiv_id)
                        print(f"❌ Paper not found: {arxiv_id}")
                        continue

                    stats["papers_found"] += 1

                    # Parse tasks
                    tasks_str = row["Relevant areas"]
                    tasks = parse_tasks(tasks_str)

                    if not tasks:
                        print(f"ℹ️  No tasks specified for paper {arxiv_id}")
                        continue

                    # Process each task
                    for task_name in tasks:
                        # Find task ID
                        task_id = get_task_id_by_name(cur, task_name)

                        if not task_id:
                            stats["tasks_not_found"] += 1
                            tasks_not_found_set.add(task_name)
                            print(
                                f"⚠️  Task not found: '{task_name}' for paper {arxiv_id}"
                            )
                            continue

                        # Add paper-task association
                        if add_paper_task(cur, paper_id, task_id):
                            stats["tasks_added"] += 1
                            print(f"✅ Added {arxiv_id} to task '{task_name}'")
                        else:
                            stats["tasks_already_exist"] += 1
                            print(
                                f"ℹ️  {arxiv_id} already associated with '{task_name}'"
                            )

                # Commit all changes
                conn.commit()
                print("\n" + "=" * 60)
                print("✅ All changes committed!")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ Error occurred: {e}")
        raise
    finally:
        conn.close()

    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total rows processed:        {stats['total_rows']}")
    print(f"Papers found in database:    {stats['papers_found']}")
    print(f"Papers not found:            {stats['papers_not_found']}")
    print(f"New task associations:       {stats['tasks_added']}")
    print(f"Already existing:            {stats['tasks_already_exist']}")
    print(f"Tasks not found in DB:       {stats['tasks_not_found']}")
    print(f"Rows without arxiv ID:       {stats['rows_without_arxiv']}")

    if papers_not_found:
        print(f"\n📋 Papers not in database ({len(papers_not_found)}):")
        for arxiv_id in papers_not_found[:10]:  # Show first 10
            print(f"  - {arxiv_id}")
        if len(papers_not_found) > 10:
            print(f"  ... and {len(papers_not_found) - 10} more")

    if tasks_not_found_set:
        print(f"\n⚠️  Tasks not found in database ({len(tasks_not_found_set)}):")
        for task_name in sorted(tasks_not_found_set):
            print(f"  - {task_name}")


if __name__ == "__main__":
    main()
