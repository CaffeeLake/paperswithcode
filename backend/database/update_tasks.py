#!/usr/bin/env python3
"""
Script to update the tasks table with annotated tasks from CSV,
ensuring exactly 30 unique tasks.
"""

import argparse
import csv
import os

import psycopg2
from psycopg2.extras import RealDictCursor


def get_connection():
    """Create and return a database connection."""
    return psycopg2.connect(
        host=os.getenv("PWC_DB_HOST", "localhost"),
        port=os.getenv("PWC_DB_PORT", "5432"),
        database=os.getenv("PWC_DB_NAME", "paperswithcode_hf"),
        user=os.getenv("PWC_DB_USER", "postgres"),
        password=os.getenv("PWC_DB_PASSWORD", "postgres"),
    )


def get_current_tasks():
    """Fetch all current tasks from the database."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, name, slug, area_id, parent_id, description, keywords, level
                FROM tasks
                ORDER BY id
            """)
            return cur.fetchall()


def load_tasks_from_csv(csv_path: str):
    """Load tasks from the CSV file."""
    tasks = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Convert empty strings to None
            task = {
                "id": int(row["id"]) if row["id"] else None,
                "name": row["name"].strip() if row["name"] else None,
                "description": row["description"].strip()
                if row["description"]
                else None,
                "slug": row["slug"].strip() if row["slug"] else None,
                "parent_id": int(row["parent_id"]) if row["parent_id"] else None,
                "area_id": int(row["area_id"]) if row["area_id"] else None,
                "level": int(row["level"]) if row["level"] else 0,
                "keywords": row["keywords"].strip() if row["keywords"] else None,
            }
            tasks.append(task)
    return tasks


def find_duplicates(tasks):
    """Find duplicate tasks by slug or name."""
    slugs_seen = {}
    names_seen = {}
    duplicates = []

    for task in tasks:
        slug = task["slug"]
        name = task["name"]

        if slug in slugs_seen:
            duplicates.append(
                {"type": "slug", "task": task, "duplicate_of": slugs_seen[slug]}
            )
        else:
            slugs_seen[slug] = task

        if name in names_seen:
            duplicates.append(
                {"type": "name", "task": task, "duplicate_of": names_seen[name]}
            )
        else:
            names_seen[name] = task

    return duplicates


def clear_tasks_table():
    """Clear all tasks from the tasks table."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            # First, clear paper_tasks junction table
            cur.execute("DELETE FROM paper_tasks")
            print("  Cleared paper_tasks junction table")

            # Then clear tasks table
            cur.execute("DELETE FROM tasks")
            print("  Cleared tasks table")

            # Reset the sequence
            cur.execute("SELECT setval('tasks_id_seq', 1, false)")
            print("  Reset tasks ID sequence")
        conn.commit()


def ensure_areas_exist(tasks):
    """Ensure all referenced areas exist in the database."""
    # Get unique area IDs from tasks
    area_ids = set()
    for task in tasks:
        if task.get("area_id"):
            area_ids.add(task["area_id"])

    if not area_ids:
        return

    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get existing areas
            cur.execute("SELECT id, name FROM areas")
            existing_areas = {row["id"]: row["name"] for row in cur.fetchall()}

            # Define area names for missing IDs (keep IDs aligned with the
            # current DB; see `backend/database/areas_setup/populate_areas.py`
            # for the canonical list).
            area_names = {
                1: "Vision",
                2: "Language",
                3: "General",
                4: "Time Series Forecasting",
                5: "Robotics",
                6: "Audio",
                7: "Time-series",
                8: "Other",
                9: "Video",
            }

            # Create missing areas
            for area_id in area_ids:
                if area_id not in existing_areas:
                    area_name = area_names.get(area_id, f"Area {area_id}")
                    cur.execute(
                        "INSERT INTO areas (id, name) VALUES (%s, %s)",
                        (area_id, area_name),
                    )
                    print(f"  Created missing area ID {area_id}: {area_name}")
        conn.commit()


def insert_tasks(tasks):
    """Insert tasks into the database."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            for task in tasks:
                cur.execute(
                    """
                    INSERT INTO tasks (name, description, slug, parent_id, area_id, level, keywords)
                    VALUES (%(name)s, %(description)s, %(slug)s, %(parent_id)s, %(area_id)s, %(level)s, %(keywords)s)
                    RETURNING id
                """,
                    task,
                )
                new_id = cur.fetchone()[0]
                print(f"  Inserted task ID {new_id}: {task['name']}")
        conn.commit()


def main():
    parser = argparse.ArgumentParser(
        description="Update tasks table with annotated tasks from CSV"
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip confirmation prompt and proceed automatically",
    )
    args = parser.parse_args()

    csv_path = (
        "/root/python_projects/paperswithcode/data/tasks_export - tasks_export.csv"
    )

    print("=" * 80)
    print("TASKS TABLE UPDATE")
    print("=" * 80)

    # 1. Check current state
    print("\n1. Checking current tasks in database...")
    current_tasks = get_current_tasks()
    print(f"   Found {len(current_tasks)} tasks in database")

    # 2. Load CSV tasks
    print("\n2. Loading tasks from CSV...")
    csv_tasks = load_tasks_from_csv(csv_path)
    print(f"   Found {len(csv_tasks)} tasks in CSV")

    # 3. Find duplicates in CSV
    print("\n3. Checking for duplicates in CSV...")
    duplicates = find_duplicates(csv_tasks)
    if duplicates:
        print(f"   Found {len(duplicates)} duplicates:")
        for dup in duplicates:
            print(
                f"   - {dup['type'].upper()}: '{dup['task']['name']}' (ID {dup['task']['id']}) is duplicate"
            )
    else:
        print("   No duplicates found in CSV")

    # 4. Decide which tasks to keep
    print("\n4. Preparing final task list...")

    # Remove tasks with duplicate slugs - keep first occurrence
    seen_slugs = set()
    unique_tasks = []
    for task in csv_tasks:
        if task["slug"] not in seen_slugs:
            seen_slugs.add(task["slug"])
            unique_tasks.append(task)
        else:
            print(f"   Removing duplicate: {task['name']} (ID {task['id']})")

    print(f"   Final count: {len(unique_tasks)} unique tasks")

    # Check if we have exactly 30 tasks
    if len(unique_tasks) != 30:
        print(f"\n   WARNING: Expected 30 tasks, but have {len(unique_tasks)}")
        print(f"   The CSV has {len(csv_tasks)} total tasks.")

        if len(unique_tasks) > 30:
            print("   Keeping only the first 30 tasks...")
            unique_tasks = unique_tasks[:30]
        elif len(unique_tasks) < 30:
            print("   ERROR: Not enough unique tasks! Cannot proceed.")
            return

    print(f"\n   Final task list ({len(unique_tasks)} tasks):")
    for i, task in enumerate(unique_tasks, 1):
        print(f"   {i:2d}. {task['name']} ({task['slug']})")

    # 5. Confirm update
    print("\n5. Ready to update database")
    print("   This will:")
    print("   - Clear all existing tasks")
    print(f"   - Insert {len(unique_tasks)} new tasks")

    if not args.yes:
        try:
            response = input("\n   Proceed? (yes/no): ").strip().lower()
            if response != "yes":
                print("\n   Aborted by user.")
                return
        except (EOFError, KeyboardInterrupt):
            print("\n\n   Aborted.")
            return
    else:
        print("\n   Auto-proceeding with --yes flag...")

    # 6. Clear and insert
    print("\n6. Updating database...")

    # Remove the id field from tasks before insertion (let DB auto-generate)
    tasks_to_insert = []
    for task in unique_tasks:
        task_copy = task.copy()
        task_copy.pop("id", None)  # Remove id if it exists
        tasks_to_insert.append(task_copy)

    # Ensure areas exist first
    ensure_areas_exist(tasks_to_insert)

    # Clear tasks table
    clear_tasks_table()

    # Insert new tasks
    insert_tasks(tasks_to_insert)

    # 7. Verify
    print("\n7. Verifying...")
    final_tasks = get_current_tasks()
    print(f"   Database now contains {len(final_tasks)} tasks")

    print("\n" + "=" * 80)
    print("UPDATE COMPLETE!")
    print("=" * 80)


if __name__ == "__main__":
    main()
