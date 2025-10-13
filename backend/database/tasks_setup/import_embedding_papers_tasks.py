"""
Import embedding papers-tasks associations from legacy PwC data.

This script processes:
- data/paper_task_links_pwc/embedding_papers.json

And populates the paper_tasks table by matching arxiv_id.
"""

import os
from typing import Dict, List
import psycopg2
from psycopg2.extras import RealDictCursor, execute_batch
import ijson


def get_task_id_by_name(cursor, task_name: str) -> int | None:
    """Find task ID by name (case-insensitive)."""
    cursor.execute(
        """
        SELECT id
        FROM tasks
        WHERE LOWER(name) = LOWER(%s)
        LIMIT 1
        """,
        (task_name,),
    )
    result = cursor.fetchone()
    return result["id"] if result else None


def process_batch(cursor, arxiv_ids: List[str], task_id: int, stats: Dict[str, int]):
    """Process a batch of arxiv_ids and link them to the task."""
    # Find paper IDs for these arxiv_ids
    cursor.execute(
        """
        SELECT id, arxiv_id
        FROM papers
        WHERE arxiv_id = ANY(%s) AND is_latest_version
        """,
        (arxiv_ids,),
    )

    papers = cursor.fetchall()
    paper_id_mapping = {p["arxiv_id"]: p["id"] for p in papers}

    stats["papers_found"] += len(papers)
    stats["papers_not_found"] += len(arxiv_ids) - len(papers)

    if not papers:
        return

    # Prepare batch insert data
    paper_task_pairs = [(paper_id, task_id) for paper_id in paper_id_mapping.values()]

    # Insert with ON CONFLICT DO NOTHING to handle duplicates
    execute_batch(
        cursor,
        """
        INSERT INTO paper_tasks (paper_id, task_id)
        VALUES (%s, %s)
        ON CONFLICT (paper_id, task_id) DO NOTHING
        """,
        paper_task_pairs,
        page_size=1000,
    )

    # Count how many were actually inserted
    rows_affected = cursor.rowcount
    stats["tasks_added"] += rows_affected
    stats["tasks_already_exist"] += len(paper_task_pairs) - rows_affected


def process_json_file(conn, cursor, filepath: str, task_name: str) -> Dict[str, int]:
    """Process the JSON file and return statistics using streaming."""
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
            # Use ijson for streaming JSON parsing
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
                    print(f"  Processed {paper_count:,} papers...")
                    batch = []

            # Process remaining papers
            if batch:
                process_batch(cursor, batch, task_id, stats)
                conn.commit()
                print(f"  Processed {paper_count:,} papers (final batch)...")

    except Exception as e:
        print(f"❌ Error processing {filepath}: {e}")
        import traceback

        traceback.print_exc()
        return stats

    return stats


def main():
    # Database connection
    conn = psycopg2.connect(
        host=os.getenv("PWC_DB_HOST"),
        database=os.getenv("PWC_DB_NAME"),
        user=os.getenv("PWC_DB_USER"),
        password=os.getenv("PWC_DB_PASSWORD"),
    )

    # File to process
    base_path = "/root/python_projects/paperswithcode/data/paper_task_links_pwc"
    filepath = os.path.join(base_path, "embedding_papers.json")
    task_name = "Embedding models"

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            print(f"\n{'=' * 70}")
            print("Importing Embedding Papers-Tasks Associations")
            print(f"{'=' * 70}\n")

            if not os.path.exists(filepath):
                print(f"❌ File not found: {filepath}")
                return 1

            stats = process_json_file(conn, cur, filepath, task_name)

            # Commit all changes
            conn.commit()

            # Print final summary
            print(f"\n{'=' * 70}")
            print("📊 FINAL SUMMARY")
            print(f"{'=' * 70}")
            print(f"Total papers in file:   {stats['total_papers']:,}")
            print(f"Papers without arxiv:   {stats['papers_without_arxiv']:,}")
            print(f"Papers found in DB:     {stats['papers_found']:,}")
            print(f"Papers not found in DB: {stats['papers_not_found']:,}")
            print(f"New associations added: {stats['tasks_added']:,}")
            print(f"Already existed:        {stats['tasks_already_exist']:,}")
            print(f"{'=' * 70}")
            print("✅ All changes committed!")
            print(f"{'=' * 70}\n")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        conn.rollback()
        return 1

    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    exit(main())
