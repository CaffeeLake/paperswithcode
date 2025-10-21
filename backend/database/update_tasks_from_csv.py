#!/usr/bin/env python3
"""
Update tasks table from CSV file.

This script updates the tasks table in the PostgreSQL database based on the
updated_tasks.csv file. It adds new columns, updates existing tasks, and
removes tasks that are not in the CSV (only if they have no linked data).

Usage:
    python update_tasks_from_csv.py
"""

import os
import sys
import csv
import logging
from typing import Dict, List, Tuple
from datetime import datetime

import psycopg2
from psycopg2.extras import RealDictCursor

# Add the backend directory to the path so we can import modules
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))


# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_connection():
    """Get database connection."""
    return psycopg2.connect(
        host=os.getenv("PWC_DB_HOST", "localhost"),
        port=os.getenv("PWC_DB_PORT", "5432"),
        database=os.getenv("PWC_DB_NAME", "paperswithcode_hf"),
        user=os.getenv("PWC_DB_USER", "postgres"),
        password=os.getenv("PWC_DB_PASSWORD", "postgres"),
    )


def load_tasks_from_csv(csv_path: str) -> List[Dict]:
    """Load tasks from the CSV file."""
    tasks = []

    with open(csv_path, "r", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            # Clean up the data
            task = {
                "id": int(row["id"]) if row["id"] else None,
                "name": row["name"].strip(),
                "description": row["description"].strip()
                if row["description"]
                else None,
                "slug": row["slug"].strip() if row["slug"] else None,
                "parent_id": int(row["parent_id"]) if row["parent_id"] else None,
                "area_id": int(row["area_id"]) if row["area_id"] else None,
                "area_name": row["area_name"].strip() if row["area_name"] else None,
                "level": int(row["level"]) if row["level"] else 0,
                "image_url": row["image_url"].strip() if row["image_url"] else None,
                "image_source": row["image_source"].strip()
                if row["image_source"]
                else None,
                "useful_leaderboards": row["useful leaderboards"].strip()
                if row["useful leaderboards"]
                else None,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            tasks.append(task)

    return tasks


def get_current_tasks() -> Dict[str, Dict]:
    """Get all current tasks from the database, indexed by slug."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, name, slug, area_id, parent_id, description, level,
                       image_url, image_credit, useful_leaderboards, created_at, updated_at
                FROM tasks
                ORDER BY id
            """)
            results = cur.fetchall()

            # Index by slug for easy lookup
            tasks_by_slug = {}
            for task in results:
                if task["slug"]:
                    tasks_by_slug[task["slug"]] = dict(task)

            return tasks_by_slug


def check_task_has_linked_data(task_id: int) -> bool:
    """Check if a task has any linked data that would prevent deletion."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Check paper_tasks
            cur.execute(
                "SELECT COUNT(*) FROM paper_tasks WHERE task_id = %s", (task_id,)
            )
            paper_tasks_count = cur.fetchone()[0]

            # Check task_datasets
            cur.execute(
                "SELECT COUNT(*) FROM task_datasets WHERE task_id = %s", (task_id,)
            )
            task_datasets_count = cur.fetchone()[0]

            # Check evaluations
            cur.execute(
                "SELECT COUNT(*) FROM evaluations WHERE task_id = %s", (task_id,)
            )
            evaluations_count = cur.fetchone()[0]

            # Check child tasks
            cur.execute("SELECT COUNT(*) FROM tasks WHERE parent_id = %s", (task_id,))
            child_tasks_count = cur.fetchone()[0]

            total_linked = (
                paper_tasks_count
                + task_datasets_count
                + evaluations_count
                + child_tasks_count
            )
            return total_linked > 0


def update_task_from_csv(task_data: Dict, current_task: Dict) -> bool:
    """Update a task from CSV data. Returns True if updated, False if no changes needed."""
    changes = []

    # Check each field for changes
    if task_data["name"] != current_task["name"]:
        changes.append(("name", task_data["name"]))

    if task_data["description"] != current_task["description"]:
        changes.append(("description", task_data["description"]))

    if task_data["area_id"] != current_task["area_id"]:
        changes.append(("area_id", task_data["area_id"]))

    if task_data["parent_id"] != current_task["parent_id"]:
        changes.append(("parent_id", task_data["parent_id"]))

    if task_data["level"] != current_task["level"]:
        changes.append(("level", task_data["level"]))

    if task_data["image_url"] != current_task["image_url"]:
        changes.append(("image_url", task_data["image_url"]))

    if task_data["image_source"] != current_task["image_credit"]:
        changes.append(("image_credit", task_data["image_source"]))

    if task_data["useful_leaderboards"] != current_task["useful_leaderboards"]:
        changes.append(("useful_leaderboards", task_data["useful_leaderboards"]))

    if not changes:
        return False

    # Add updated_at timestamp
    changes.append(("updated_at", datetime.now()))

    # Update the task
    with get_connection() as conn:
        with conn.cursor() as cur:
            set_clause = ", ".join([f"{field} = %s" for field, _ in changes])
            values = [value for _, value in changes] + [current_task["id"]]

            cur.execute(
                f"""
                UPDATE tasks
                SET {set_clause}
                WHERE id = %s
            """,
                values,
            )

            conn.commit()

    logger.info(
        f"Updated task '{task_data['name']}' (slug: {task_data['slug']}) with {len(changes)} changes"
    )
    return True


def insert_new_task(task_data: Dict) -> bool:
    """Insert a new task from CSV data."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tasks (name, description, slug, parent_id, area_id, level,
                                 image_url, image_credit, useful_leaderboards, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
                (
                    task_data["name"],
                    task_data["description"],
                    task_data["slug"],
                    task_data["parent_id"],
                    task_data["area_id"],
                    task_data["level"],
                    task_data["image_url"],
                    task_data["image_source"],  # Map image_source to image_credit
                    task_data["useful_leaderboards"],
                    task_data["created_at"],
                    task_data["updated_at"],
                ),
            )
            conn.commit()

    logger.info(f"Inserted new task '{task_data['name']}' (slug: {task_data['slug']})")
    return True


def delete_orphaned_tasks(
    current_tasks: Dict[str, Dict], csv_tasks: List[Dict]
) -> Tuple[int, List[str]]:
    """Delete tasks that are in database but not in CSV (only if no linked data)."""
    csv_slugs = {task["slug"] for task in csv_tasks if task["slug"]}
    deleted_count = 0
    skipped_tasks = []

    for slug, task_data in current_tasks.items():
        if slug not in csv_slugs:
            task_id = task_data["id"]
            task_name = task_data["name"]

            # Check if task has linked data
            if check_task_has_linked_data(task_id):
                skipped_tasks.append(f"{task_name} (ID: {task_id}, slug: {slug})")
                logger.warning(
                    f"Skipped deletion of task '{task_name}' - has linked data"
                )
            else:
                # Safe to delete
                with get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("DELETE FROM tasks WHERE id = %s", (task_id,))
                        conn.commit()

                deleted_count += 1
                logger.info(f"Deleted task '{task_name}' (ID: {task_id}, slug: {slug})")

    return deleted_count, skipped_tasks


def main():
    """Main function to update tasks from CSV."""
    csv_path = "/root/python_projects/paperswithcode/data/updated_tasks.csv"

    if not os.path.exists(csv_path):
        logger.error(f"CSV file not found: {csv_path}")
        return 1

    logger.info("Starting tasks update from CSV...")

    # Load data
    logger.info("Loading tasks from CSV...")
    csv_tasks = load_tasks_from_csv(csv_path)
    logger.info(f"Loaded {len(csv_tasks)} tasks from CSV")

    logger.info("Loading current tasks from database...")
    current_tasks = get_current_tasks()
    logger.info(f"Found {len(current_tasks)} current tasks in database")

    # Process updates and insertions
    updated_count = 0
    inserted_count = 0

    for task_data in csv_tasks:
        if not task_data["slug"]:
            logger.warning(f"Skipping task '{task_data['name']}' - no slug")
            continue

        if task_data["slug"] in current_tasks:
            # Update existing task
            current_task = current_tasks[task_data["slug"]]
            if update_task_from_csv(task_data, current_task):
                updated_count += 1
        else:
            # Insert new task
            if insert_new_task(task_data):
                inserted_count += 1

    # Delete orphaned tasks
    logger.info("Checking for orphaned tasks to delete...")
    deleted_count, skipped_tasks = delete_orphaned_tasks(current_tasks, csv_tasks)

    # Summary report
    logger.info("=" * 50)
    logger.info("UPDATE SUMMARY")
    logger.info("=" * 50)
    logger.info(f"Tasks processed from CSV: {len(csv_tasks)}")
    logger.info(f"Tasks updated: {updated_count}")
    logger.info(f"Tasks inserted: {inserted_count}")
    logger.info(f"Tasks deleted: {deleted_count}")
    logger.info(f"Tasks skipped (had linked data): {len(skipped_tasks)}")

    if skipped_tasks:
        logger.info("\nSkipped tasks (had linked data):")
        for task in skipped_tasks:
            logger.info(f"  - {task}")

    logger.info("Tasks update completed successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
