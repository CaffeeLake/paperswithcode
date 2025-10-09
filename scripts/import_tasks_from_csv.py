"""
Import updated tasks from a CSV file back into the database.

This script reads the updated tasks_export.csv file and updates the tasks
in the database with new descriptions and area assignments.
"""

import csv
import sys
import psycopg2
from psycopg2.extras import RealDictCursor

# Database connection settings
DB_CONFIG = {
    "dbname": "paperswithcode_hf",
    "user": "paperswithcode_user",
    "password": "paperswithcode123",
    "host": "localhost",
    "port": "5432",
}


def get_db_connection():
    """Create and return a database connection."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except psycopg2.Error as e:
        print(f"Error connecting to database: {e}")
        sys.exit(1)


def import_tasks_from_csv(
    input_file: str = "data/tasks_export.csv", dry_run: bool = False
):
    """Import tasks from CSV and update the database."""

    conn = get_db_connection()

    try:
        # Read the CSV file
        tasks_to_update = []
        with open(input_file, "r", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                tasks_to_update.append(row)

        print(f"Read {len(tasks_to_update)} tasks from {input_file}")

        # Update each task in the database
        updated_count = 0
        skipped_count = 0

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            for task in tasks_to_update:
                task_id = int(task["id"])
                name = task["name"]
                description = task["description"] if task["description"] else None
                area_id = (
                    int(task["area_id"])
                    if task["area_id"] and task["area_id"].lower() != "null"
                    else None
                )

                # Check if task exists
                cur.execute(
                    "SELECT id, name, description, area_id FROM tasks WHERE id = %s",
                    (task_id,),
                )
                existing_task = cur.fetchone()

                if not existing_task:
                    print(
                        f"⚠️  Task ID {task_id} ({name}) does not exist in database - skipping"
                    )
                    skipped_count += 1
                    continue

                # Check if anything changed
                changed = False
                changes = []

                if existing_task["description"] != description:
                    changed = True
                    changes.append(
                        f"description: {existing_task['description'][:50] if existing_task['description'] else 'NULL'} → {description[:50] if description else 'NULL'}"
                    )

                if existing_task["area_id"] != area_id:
                    changed = True
                    changes.append(f"area_id: {existing_task['area_id']} → {area_id}")

                if not changed:
                    continue

                # Update the task
                update_query = """
                    UPDATE tasks
                    SET description = %s,
                        area_id = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """

                if dry_run:
                    print(f"[DRY RUN] Would update task ID {task_id} ({name}):")
                    for change in changes:
                        print(f"  - {change}")
                else:
                    cur.execute(update_query, (description, area_id, task_id))
                    print(f"✓ Updated task ID {task_id} ({name}):")
                    for change in changes:
                        print(f"  - {change}")

                updated_count += 1

            if not dry_run:
                conn.commit()
                print(f"\n✅ Successfully updated {updated_count} tasks")
            else:
                print(f"\n[DRY RUN] Would update {updated_count} tasks")

            if skipped_count > 0:
                print(f"⚠️  Skipped {skipped_count} tasks (not found in database)")

    except Exception as e:
        conn.rollback()
        print(f"Error importing tasks: {e}")
        raise
    finally:
        conn.close()


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Import updated tasks from CSV")
    parser.add_argument(
        "--input",
        "-i",
        default="data/tasks_export.csv",
        help="Input CSV file path (default: data/tasks_export.csv)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform a dry run without actually updating the database",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("Tasks Import Script")
    print("=" * 70)
    print()

    if args.dry_run:
        print("🔍 DRY RUN MODE - No changes will be made to the database")
        print()

    import_tasks_from_csv(args.input, args.dry_run)

    print()
    print("=" * 70)
    print("Import completed!")
    print("=" * 70)


if __name__ == "__main__":
    main()
