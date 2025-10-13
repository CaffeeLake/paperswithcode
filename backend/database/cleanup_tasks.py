"""
Clean up tasks table by removing tasks without descriptions.

This script:
1. Identifies tasks without descriptions
2. Checks if they have any linked papers
3. Removes tasks without descriptions (they are not displayed in the frontend anyway)
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.config import get_settings


def get_connection():
    """Get database connection."""
    settings = get_settings()
    return psycopg2.connect(
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
        user=settings.db_user,
        password=settings.db_password,
    )


def analyze_tasks_without_descriptions():
    """Analyze tasks that don't have descriptions."""
    conn = get_connection()

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get tasks without descriptions
            cur.execute("""
                SELECT
                    t.id,
                    t.name,
                    t.description,
                    t.slug,
                    t.area_id,
                    a.name as area_name,
                    t.parent_id,
                    t.level,
                    COUNT(DISTINCT pt.paper_id) as paper_count
                FROM tasks t
                LEFT JOIN areas a ON t.area_id = a.id
                LEFT JOIN paper_tasks pt ON t.id = pt.task_id
                WHERE t.description IS NULL OR TRIM(t.description) = ''
                GROUP BY t.id, t.name, t.description, t.slug, t.area_id, a.name, t.parent_id, t.level
                ORDER BY paper_count DESC, t.name
            """)

            tasks_without_desc = cur.fetchall()

            print(f"\n{'=' * 80}")
            print(f"Found {len(tasks_without_desc)} tasks without descriptions")
            print(f"{'=' * 80}\n")

            # Statistics
            total_papers = sum(t["paper_count"] for t in tasks_without_desc)
            tasks_with_papers = sum(
                1 for t in tasks_without_desc if t["paper_count"] > 0
            )
            tasks_without_papers = len(tasks_without_desc) - tasks_with_papers

            print("Summary:")
            print(f"  - Tasks without descriptions: {len(tasks_without_desc)}")
            print(f"  - Tasks with linked papers: {tasks_with_papers}")
            print(f"  - Tasks without linked papers: {tasks_without_papers}")
            print(f"  - Total papers linked: {total_papers}")
            print()

            if tasks_with_papers > 0:
                print("Tasks WITH linked papers (top 10):")
                print(f"{'-' * 80}")
                for task in tasks_without_desc[:10]:
                    if task["paper_count"] > 0:
                        print(
                            f"  ID: {task['id']:<5} | Name: {task['name']:<40} | Papers: {task['paper_count']:<5} | Area: {task['area_name'] or 'N/A'}"
                        )
                print()

            if tasks_without_papers > 0:
                print("Tasks WITHOUT linked papers (showing first 20):")
                print(f"{'-' * 80}")
                count = 0
                for task in tasks_without_desc:
                    if task["paper_count"] == 0:
                        print(
                            f"  ID: {task['id']:<5} | Name: {task['name']:<50} | Area: {task['area_name'] or 'N/A'}"
                        )
                        count += 1
                        if count >= 20:
                            if tasks_without_papers > 20:
                                print(f"  ... and {tasks_without_papers - 20} more")
                            break

            return tasks_without_desc

    finally:
        conn.close()


def delete_tasks_without_descriptions(dry_run=True):
    """
    Delete tasks without descriptions.

    Args:
        dry_run: If True, only show what would be deleted without actually deleting
    """
    conn = get_connection()

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get count of tasks to delete
            cur.execute("""
                SELECT COUNT(*) as count
                FROM tasks
                WHERE description IS NULL OR TRIM(description) = ''
            """)
            count = cur.fetchone()["count"]

            if count == 0:
                print("No tasks without descriptions found.")
                return

            if dry_run:
                print(f"\n[DRY RUN] Would delete {count} tasks without descriptions")
                print("Run with --execute to actually delete them.")
            else:
                print(f"\nDeleting {count} tasks without descriptions...")

                # Delete tasks without descriptions
                # Note: CASCADE will also delete entries in paper_tasks
                cur.execute("""
                    DELETE FROM tasks
                    WHERE description IS NULL OR TRIM(description) = ''
                """)

                conn.commit()
                print(f"✓ Successfully deleted {count} tasks")

                # Show updated count
                cur.execute("SELECT COUNT(*) as count FROM tasks")
                remaining = cur.fetchone()["count"]
                print(f"✓ Remaining tasks in database: {remaining}")

    except Exception as e:
        conn.rollback()
        print(f"Error: {e}")
        raise
    finally:
        conn.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Clean up tasks without descriptions")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete the tasks (default is dry-run)",
    )
    parser.add_argument(
        "--analyze-only", action="store_true", help="Only analyze, do not delete"
    )

    args = parser.parse_args()

    print("\n" + "=" * 80)
    print("TASKS CLEANUP SCRIPT")
    print("=" * 80)

    # Analyze first
    tasks = analyze_tasks_without_descriptions()

    if args.analyze_only:
        print("\n[ANALYZE ONLY MODE] - No changes made")
        return

    # Ask for confirmation if there are tasks with papers
    tasks_with_papers = sum(1 for t in tasks if t["paper_count"] > 0)

    if tasks_with_papers > 0:
        print(f"\n⚠️  WARNING: {tasks_with_papers} tasks have linked papers!")
        print("Deleting these tasks will also remove their paper associations.")

        if args.execute:
            response = input("\nAre you sure you want to proceed? (yes/no): ")
            if response.lower() != "yes":
                print("Aborted.")
                return

    # Delete tasks
    delete_tasks_without_descriptions(dry_run=not args.execute)

    print("\n" + "=" * 80)
    print("DONE")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
