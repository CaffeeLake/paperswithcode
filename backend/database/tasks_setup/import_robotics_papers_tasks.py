"""
Import paper-task associations from robotics_papers.json.

This script:
1. Reads robotics_papers.json file
2. For each paper, extracts all tasks from the 'tasks' array
3. For each task, finds or creates it in the tasks table
4. Creates paper-task associations for all tasks
"""

import os
from typing import Dict
import psycopg2
from psycopg2.extras import RealDictCursor
import ijson


def get_task_id_by_name(cursor, task_name: str) -> int | None:
    """Find task ID by name (case-insensitive)."""
    # Try exact match first
    cursor.execute(
        "SELECT id, name FROM tasks WHERE LOWER(name) = %s", (task_name.lower(),)
    )
    result = cursor.fetchone()
    if result:
        return result["id"]

    # Try slug match
    slug = task_name.lower().replace(" ", "-")
    cursor.execute("SELECT id, name FROM tasks WHERE slug = %s", (slug,))
    result = cursor.fetchone()
    return result["id"] if result else None


def create_task_if_not_exists(cursor, task_name: str) -> int:
    """Create a new task if it doesn't exist, return the task ID."""
    # First check if it exists
    task_id = get_task_id_by_name(cursor, task_name)
    if task_id:
        return task_id

    # Create slug from name
    slug = task_name.lower().replace(" ", "-")

    # Insert new task
    cursor.execute(
        """
        INSERT INTO tasks (name, slug, level)
        VALUES (%s, %s, 0)
        ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name
        RETURNING id
        """,
        (task_name, slug),
    )
    result = cursor.fetchone()
    return result["id"]


def get_paper_id_by_arxiv(cursor, arxiv_id: str) -> int | None:
    """Find paper ID by arxiv ID (latest version only)."""
    if not arxiv_id:
        return None

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


def process_robotics_json(conn, cursor, filepath: str) -> Dict[str, int]:
    """Process robotics_papers.json file and return statistics."""
    stats = {
        "total_papers": 0,
        "papers_found": 0,
        "papers_not_found": 0,
        "papers_without_arxiv": 0,
        "total_tasks_in_papers": 0,
        "tasks_created": 0,
        "tasks_found": 0,
        "associations_added": 0,
        "associations_already_exist": 0,
    }

    print(f"📖 Processing {filepath}...")

    # Keep track of unique tasks we've seen
    unique_tasks = set()
    tasks_cache = {}  # Cache task lookups

    batch_size = 1000
    paper_count = 0
    batch = []

    try:
        with open(filepath, "rb") as f:
            # Use ijson for streaming JSON parsing
            parser = ijson.items(f, "item")

            for paper in parser:
                paper_count += 1
                stats["total_papers"] += 1

                arxiv_id = paper.get("arxiv_id")

                if not arxiv_id:
                    stats["papers_without_arxiv"] += 1
                    continue

                # Extract tasks from the paper
                tasks = paper.get("tasks", [])
                if not tasks:
                    continue

                batch.append({"arxiv_id": arxiv_id, "tasks": tasks})

                # Process batch
                if len(batch) >= batch_size:
                    process_batch(cursor, batch, stats, unique_tasks, tasks_cache)
                    conn.commit()  # Commit after each batch
                    print(
                        f"  Processed {paper_count} papers, "
                        f"added {stats['associations_added']} associations..."
                    )
                    batch = []

            # Process remaining papers
            if batch:
                process_batch(cursor, batch, stats, unique_tasks, tasks_cache)
                conn.commit()
                print(
                    f"  Processed {paper_count} papers (final batch), "
                    f"added {stats['associations_added']} associations..."
                )

    except Exception as e:
        print(f"❌ Error processing {filepath}: {e}")
        import traceback

        traceback.print_exc()
        return stats

    print(f"\n📊 Unique tasks found: {len(unique_tasks)}")
    print(f"Sample tasks: {list(unique_tasks)[:10]}")

    return stats


def process_batch(
    cursor, batch, stats: Dict[str, int], unique_tasks: set, tasks_cache: dict
):
    """Process a batch of papers with their tasks."""
    for item in batch:
        arxiv_id = item["arxiv_id"]
        tasks = item["tasks"]

        # Find paper in database
        paper_id = get_paper_id_by_arxiv(cursor, arxiv_id)

        if not paper_id:
            stats["papers_not_found"] += 1
            continue

        stats["papers_found"] += 1

        # Process each task for this paper
        for task_name in tasks:
            if not task_name or not task_name.strip():
                continue

            stats["total_tasks_in_papers"] += 1
            unique_tasks.add(task_name)

            # Check cache first
            if task_name in tasks_cache:
                task_id = tasks_cache[task_name]
            else:
                # Find or create task
                existing_id = get_task_id_by_name(cursor, task_name)
                if existing_id:
                    task_id = existing_id
                    stats["tasks_found"] += 1
                else:
                    task_id = create_task_if_not_exists(cursor, task_name)
                    stats["tasks_created"] += 1
                    print(f"  ✨ Created new task: {task_name} (id: {task_id})")

                tasks_cache[task_name] = task_id

            # Add paper-task association
            if add_paper_task(cursor, paper_id, task_id):
                stats["associations_added"] += 1
            else:
                stats["associations_already_exist"] += 1


def main():
    # Database connection
    conn = psycopg2.connect(
        host=os.getenv("PWC_DB_HOST"),
        database=os.getenv("PWC_DB_NAME"),
        user=os.getenv("PWC_DB_USER"),
        password=os.getenv("PWC_DB_PASSWORD"),
    )

    # Path to robotics JSON file
    json_file = "/root/python_projects/paperswithcode/data/paper_task_links_pwc/robotics_papers.json"

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            print(f"\n{'=' * 60}")
            print("Processing robotics papers tasks")
            print(f"{'=' * 60}\n")

            # Process the file
            stats = process_robotics_json(conn, cur, json_file)

            # Commit all changes
            conn.commit()
            print(f"\n{'=' * 60}")
            print("✅ All changes committed!")
            print(f"{'=' * 60}")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ Error occurred: {e}")
        raise
    finally:
        conn.close()

    # Print summary
    print("\n" + "=" * 60)
    print("FINAL SUMMARY")
    print("=" * 60)
    print(f"Total papers in JSON file:        {stats['total_papers']}")
    print(f"Papers found in database:         {stats['papers_found']}")
    print(f"Papers not found:                 {stats['papers_not_found']}")
    print(f"Papers without arxiv ID:          {stats['papers_without_arxiv']}")
    print(f"Total task mentions in papers:    {stats['total_tasks_in_papers']}")
    print(f"Tasks found (existing):           {stats['tasks_found']}")
    print(f"Tasks created (new):              {stats['tasks_created']}")
    print(f"New paper-task associations:      {stats['associations_added']}")
    print(f"Already existing associations:    {stats['associations_already_exist']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
