#!/usr/bin/env python3
"""
Annotate all object detection papers in the database with the "Object Detection" task.

This script:
1. Loads the object detection papers from JSON
2. Finds the "Object Detection" task ID in the database
3. Links all matching papers to this task in the paper_tasks table
"""

import json
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import List, Set, Dict
import os
from pathlib import Path


def load_object_detection_papers(json_path: str) -> Set[str]:
    """Load papers from JSON and extract arxiv_ids."""
    print(f"Loading papers from {json_path}...")
    with open(json_path, "r", encoding="utf-8") as f:
        papers = json.load(f)

    # Extract arxiv_ids
    arxiv_ids = set()
    for paper in papers:
        arxiv_id = paper.get("arxiv_id")
        if arxiv_id:
            # Clean the arxiv_id - remove version suffix if present
            base_arxiv_id = arxiv_id.split("v")[0] if "v" in arxiv_id else arxiv_id
            arxiv_ids.add(base_arxiv_id)

    print(f"Extracted {len(arxiv_ids):,} unique arxiv_ids from JSON")
    return arxiv_ids


def get_or_create_object_detection_task(conn) -> int:
    """Get or create the Object Detection task and return its ID."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # First, try to find the Object Detection task
        cur.execute(
            """
            SELECT id, name, description, area_id, parent_id
            FROM tasks
            WHERE LOWER(name) = LOWER(%s)
        """,
            ("Object Detection",),
        )

        task = cur.fetchone()

        if task:
            print(f"✅ Found existing 'Object Detection' task (ID: {task['id']})")
            print(f"   - Name: {task['name']}")
            print(
                f"   - Description: {task['description'][:100] if task['description'] else 'None'}..."
            )
            print(f"   - Area ID: {task['area_id']}")
            print(f"   - Parent ID: {task['parent_id']}")
            return task["id"]
        else:
            print("❌ 'Object Detection' task not found in database")
            print("   Creating new 'Object Detection' task...")

            # Check if Computer Vision area exists
            cur.execute("SELECT id FROM areas WHERE LOWER(name) = 'computer vision'")
            area = cur.fetchone()
            area_id = area["id"] if area else None

            # Create the task
            cur.execute(
                """
                INSERT INTO tasks (name, description, area_id, slug, level)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """,
                (
                    "Object Detection",
                    "Detecting and localizing objects in images",
                    area_id,
                    "object-detection",
                    0,
                ),
            )

            task_id = cur.fetchone()["id"]
            conn.commit()
            print(f"✅ Created new 'Object Detection' task (ID: {task_id})")
            return task_id


def get_paper_ids_for_arxiv_ids(conn, arxiv_ids: Set[str]) -> Dict[str, int]:
    """Get paper IDs for all arxiv_ids that exist in database."""
    print(f"\nFetching paper IDs for {len(arxiv_ids):,} arxiv_ids...")

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        arxiv_id_list = list(arxiv_ids)

        # Get paper IDs for matching arxiv_ids (latest versions only)
        cur.execute(
            """
            SELECT id, arxiv_id, title
            FROM papers
            WHERE arxiv_id = ANY(%s) AND is_latest_version
        """,
            (arxiv_id_list,),
        )

        papers = cur.fetchall()

        # Create mapping of arxiv_id -> paper_id
        arxiv_to_paper_id = {paper["arxiv_id"]: paper["id"] for paper in papers}

        print(f"✅ Found {len(arxiv_to_paper_id):,} papers in database")

        return arxiv_to_paper_id


def annotate_papers_with_task(
    conn, paper_ids: List[int], task_id: int
) -> Dict[str, int]:
    """
    Annotate papers with the object detection task.
    Returns statistics on added and skipped records.
    """
    print(f"\n{'=' * 80}")
    print("ANNOTATING PAPERS WITH OBJECT DETECTION TASK")
    print(f"{'=' * 80}")
    print(f"Task ID: {task_id}")
    print(f"Papers to annotate: {len(paper_ids):,}")

    added_count = 0
    already_exists_count = 0
    error_count = 0

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Check which papers already have this task
        cur.execute(
            """
            SELECT paper_id
            FROM paper_tasks
            WHERE paper_id = ANY(%s) AND task_id = %s
        """,
            (paper_ids, task_id),
        )

        existing_paper_ids = set(row["paper_id"] for row in cur.fetchall())
        already_exists_count = len(existing_paper_ids)

        if already_exists_count > 0:
            print(f"⚠️  {already_exists_count:,} papers already have this task assigned")

        # Filter out papers that already have this task
        papers_to_add = [pid for pid in paper_ids if pid not in existing_paper_ids]

        if not papers_to_add:
            print("✅ All papers already have the Object Detection task assigned!")
            return {
                "added": 0,
                "already_exists": already_exists_count,
                "errors": 0,
                "total_processed": len(paper_ids),
            }

        print(f"📝 Adding Object Detection task to {len(papers_to_add):,} papers...")

        # Batch insert papers with the task
        # Use INSERT ... ON CONFLICT to handle any race conditions
        for i, paper_id in enumerate(papers_to_add, 1):
            try:
                cur.execute(
                    """
                    INSERT INTO paper_tasks (paper_id, task_id)
                    VALUES (%s, %s)
                    ON CONFLICT (paper_id, task_id) DO NOTHING
                """,
                    (paper_id, task_id),
                )

                added_count += 1

                # Progress indicator
                if i % 100 == 0:
                    print(
                        f"   Progress: {i:,}/{len(papers_to_add):,} papers processed..."
                    )
                    conn.commit()  # Commit in batches

            except Exception as e:
                print(f"❌ Error adding paper_id {paper_id}: {e}")
                error_count += 1
                conn.rollback()

        # Final commit
        conn.commit()
        print(f"✅ Successfully added {added_count:,} new paper-task relationships")

    stats = {
        "added": added_count,
        "already_exists": already_exists_count,
        "errors": error_count,
        "total_processed": len(paper_ids),
    }

    return stats


def verify_annotations(conn, paper_ids: List[int], task_id: int) -> None:
    """Verify that all papers are now annotated with the task."""
    print(f"\n{'=' * 80}")
    print("VERIFICATION")
    print(f"{'=' * 80}")

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Check how many papers now have the task
        cur.execute(
            """
            SELECT COUNT(*) as count
            FROM paper_tasks
            WHERE paper_id = ANY(%s) AND task_id = %s
        """,
            (paper_ids, task_id),
        )

        count = cur.fetchone()["count"]

        print(
            f"✅ Total papers with Object Detection task: {count:,} / {len(paper_ids):,}"
        )

        if count == len(paper_ids):
            print("🎉 All papers successfully annotated!")
        else:
            missing = len(paper_ids) - count
            print(f"⚠️  Warning: {missing:,} papers still missing the task annotation")

        # Get some sample papers with their tasks
        cur.execute(
            """
            SELECT p.id, p.title, p.arxiv_id, COUNT(pt.task_id) as task_count
            FROM papers p
            LEFT JOIN paper_tasks pt ON p.id = pt.paper_id
            WHERE p.id = ANY(%s)
            GROUP BY p.id, p.title, p.arxiv_id
            ORDER BY p.id
            LIMIT 5
        """,
            (paper_ids[:5],),
        )

        sample_papers = cur.fetchall()

        print("\n📄 Sample annotated papers:")
        for paper in sample_papers:
            print(
                f"   - {paper['arxiv_id']}: {paper['title'][:60]}... ({paper['task_count']} tasks)"
            )


def print_summary(stats: Dict[str, int]) -> None:
    """Print a summary of the annotation process."""
    print(f"\n{'=' * 80}")
    print("ANNOTATION SUMMARY")
    print(f"{'=' * 80}")
    print(f"Total papers processed:      {stats['total_processed']:>10,}")
    print(f"New annotations added:       {stats['added']:>10,}")
    print(f"Already annotated:           {stats['already_exists']:>10,}")
    print(f"Errors:                      {stats['errors']:>10,}")
    print(f"{'=' * 80}")


def main():
    """Main function to run the annotation process."""
    # Get the project root directory
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    json_path = project_root / "data" / "object_detection_papers.json"

    # Check if file exists
    if not json_path.exists():
        print(f"Error: File not found at {json_path}")
        return

    # Load arxiv_ids from JSON
    arxiv_ids = load_object_detection_papers(str(json_path))

    # Connect to database
    print("\n📡 Connecting to PostgreSQL database...")
    conn = None

    try:
        conn = psycopg2.connect(
            database=os.getenv("DB_NAME", "paperswithcode_hf"),
            user=os.getenv("DB_USER", "paperswithcode_user"),
            password=os.getenv("DB_PASSWORD", "paperswithcode123"),
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", "5432"),
        )
        print("✅ Connected to database")

        # Get or create the Object Detection task
        task_id = get_or_create_object_detection_task(conn)

        # Get paper IDs for all arxiv_ids
        arxiv_to_paper_id = get_paper_ids_for_arxiv_ids(conn, arxiv_ids)
        paper_ids = list(arxiv_to_paper_id.values())

        if not paper_ids:
            print("❌ No papers found in database to annotate")
            return

        # Annotate papers with the task
        stats = annotate_papers_with_task(conn, paper_ids, task_id)

        # Verify annotations
        verify_annotations(conn, paper_ids, task_id)

        # Print summary
        print_summary(stats)

        print("\n✅ Annotation process completed successfully!")

    except Exception as e:
        print(f"❌ Error: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()
            print("📡 Database connection closed")


if __name__ == "__main__":
    main()
