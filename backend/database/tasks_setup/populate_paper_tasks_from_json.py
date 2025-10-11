"""
Populate paper_tasks table from JSON files in paper_task_links_pwc folder.

This script:
1. Reads all JSON files from paper_task_links_pwc/
2. Extracts task name from filename (e.g., "automatic_speech_recognition_papers.json")
3. For each paper, finds the paper_id and task_id
4. Creates paper-task associations
"""

import os
from typing import Dict, List
import psycopg2
from psycopg2.extras import RealDictCursor
import ijson


def normalize_task_name(task_name: str) -> str:
    """Convert filename task name to normalized form."""
    # Remove _papers.json suffix and convert underscores to spaces
    name = task_name.replace("_papers.json", "").replace("_", " ")
    # Capitalize each word for display
    return name.title()


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


def process_json_file(conn, cursor, filepath: str, task_name: str) -> Dict[str, int]:
    """Process a single JSON file and return statistics using streaming."""
    stats = {
        "total_papers": 0,
        "papers_found": 0,
        "papers_not_found": 0,
        "papers_without_arxiv": 0,
        "tasks_added": 0,
        "tasks_already_exist": 0,
    }

    # Get task ID
    task_id = get_task_id_by_name(cursor, task_name)
    if not task_id:
        print(f"❌ Task '{task_name}' not found in database!")
        return stats

    print(f"📖 Processing {task_name} (task_id: {task_id})...")

    # Process JSON file in streaming fashion to save memory
    batch_size = 1000
    batch = []
    paper_count = 0

    try:
        with open(filepath, "rb") as f:
            # Use ijson for streaming JSON parsing - only keep arxiv_ids in memory
            parser = ijson.items(f, "item")

            for paper in parser:
                paper_count += 1
                stats["total_papers"] += 1

                arxiv_id = paper.get("arxiv_id")

                if not arxiv_id:
                    stats["papers_without_arxiv"] += 1
                    continue

                batch.append(arxiv_id)

                # Process batch
                if len(batch) >= batch_size:
                    process_batch(cursor, batch, task_id, stats)
                    conn.commit()  # Commit after each batch
                    print(f"  Processed {paper_count} papers...")
                    batch = []

            # Process remaining papers
            if batch:
                process_batch(cursor, batch, task_id, stats)
                conn.commit()
                print(f"  Processed {paper_count} papers (final batch)...")

    except Exception as e:
        print(f"❌ Error processing {filepath}: {e}")
        import traceback

        traceback.print_exc()
        return stats

    return stats


def process_batch(cursor, arxiv_ids: List[str], task_id: int, stats: Dict[str, int]):
    """Process a batch of arxiv IDs."""
    for arxiv_id in arxiv_ids:
        # Find paper in database
        paper_id = get_paper_id_by_arxiv(cursor, arxiv_id)

        if not paper_id:
            stats["papers_not_found"] += 1
            continue

        stats["papers_found"] += 1

        # Add paper-task association
        if add_paper_task(cursor, paper_id, task_id):
            stats["tasks_added"] += 1
        else:
            stats["tasks_already_exist"] += 1


def main():
    # Database connection
    conn = psycopg2.connect(
        host=os.getenv("PWC_DB_HOST"),
        database=os.getenv("PWC_DB_NAME"),
        user=os.getenv("PWC_DB_USER"),
        password=os.getenv("PWC_DB_PASSWORD"),
    )

    # Path to JSON files
    json_folder = "/root/python_projects/paperswithcode/paper_task_links_pwc"

    # Aggregate statistics
    total_stats = {
        "files_processed": 0,
        "total_papers": 0,
        "papers_found": 0,
        "papers_not_found": 0,
        "papers_without_arxiv": 0,
        "tasks_added": 0,
        "tasks_already_exist": 0,
    }

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get all JSON files
            json_files = sorted(
                [f for f in os.listdir(json_folder) if f.endswith(".json")]
            )

            print(f"\n{'=' * 60}")
            print(f"Found {len(json_files)} JSON files to process")
            print(f"{'=' * 60}\n")

            # Process each file
            for filename in json_files:
                filepath = os.path.join(json_folder, filename)
                task_name = normalize_task_name(filename)

                file_stats = process_json_file(conn, cur, filepath, task_name)

                # Update total stats
                total_stats["files_processed"] += 1
                for key, value in file_stats.items():
                    if key in total_stats:
                        total_stats[key] += value

                # Print file summary
                print(
                    f"  ✅ Added: {file_stats['tasks_added']}, "
                    f"Already existed: {file_stats['tasks_already_exist']}, "
                    f"Not found: {file_stats['papers_not_found']}"
                )
                print()

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
    print(f"Files processed:             {total_stats['files_processed']}")
    print(f"Total papers in JSON files:  {total_stats['total_papers']}")
    print(f"Papers found in database:    {total_stats['papers_found']}")
    print(f"Papers not found:            {total_stats['papers_not_found']}")
    print(f"Papers without arxiv ID:     {total_stats['papers_without_arxiv']}")
    print(f"New task associations:       {total_stats['tasks_added']}")
    print(f"Already existing:            {total_stats['tasks_already_exist']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
