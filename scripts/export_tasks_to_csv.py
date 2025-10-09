"""
Export the tasks table to a CSV file.

This script connects to the PostgreSQL database and exports all tasks
to a CSV file for manual completion and editing.
"""

import csv
import sys
import psycopg2

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


def export_tasks_to_csv(output_file: str = "tasks_export.csv"):
    """Export all tasks from the database to a CSV file."""

    conn = get_db_connection()

    try:
        with conn.cursor() as cur:
            # Get all tasks with area name for better context
            query = """
                SELECT
                    t.id,
                    t.name,
                    t.description,
                    t.slug,
                    t.parent_id,
                    t.area_id,
                    a.name as area_name,
                    t.level,
                    t.created_at,
                    t.updated_at
                FROM tasks t
                LEFT JOIN areas a ON t.area_id = a.id
                ORDER BY t.area_id NULLS LAST, t.level, t.name;
            """

            cur.execute(query)
            rows = cur.fetchall()

            if not rows:
                print("No tasks found in database.")
                return

            # Get column names from cursor description
            column_names = [desc[0] for desc in cur.description]

            # Write to CSV
            with open(output_file, "w", newline="", encoding="utf-8") as csvfile:
                writer = csv.writer(csvfile)

                # Write header
                writer.writerow(column_names)

                # Write data rows
                for row in rows:
                    writer.writerow(row)

            print(f"✓ Exported {len(rows)} tasks to {output_file}")

            # Also print some statistics
            cur.execute("SELECT COUNT(*) FROM tasks WHERE area_id IS NULL")
            unassigned = cur.fetchone()[0]

            cur.execute("""
                SELECT a.name, COUNT(t.id) as task_count
                FROM tasks t
                LEFT JOIN areas a ON t.area_id = a.id
                WHERE t.area_id IS NOT NULL
                GROUP BY a.name
                ORDER BY task_count DESC;
            """)
            area_stats = cur.fetchall()

            print("\nTask statistics:")
            print(f"  - Tasks without area assignment: {unassigned}")
            print("  - Tasks by area:")
            for area_name, count in area_stats:
                print(f"    • {area_name}: {count} tasks")

    finally:
        conn.close()


def main():
    """Main entry point."""
    output_file = "tasks_export.csv"

    # Allow custom output filename from command line
    if len(sys.argv) > 1:
        output_file = sys.argv[1]

    export_tasks_to_csv(output_file)


if __name__ == "__main__":
    main()
