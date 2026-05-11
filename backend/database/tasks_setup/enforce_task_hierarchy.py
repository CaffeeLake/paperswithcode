#!/usr/bin/env python3
"""
Enforce task hierarchy in the paper_tasks table.

Hierarchy (from most general to most specific):
1. Omni models (top level)
2. Video Understanding
3. Image Understanding
4. Language Modeling (bottom level)

Rule: If a paper has a higher-level task, remove all lower-level tasks.
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import os
from typing import List, Dict
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Task hierarchy (ordered from most general to most specific)
TASK_HIERARCHY = [
    "omni models",
    "video understanding",
    "image understanding",
    "language modeling",
]


def get_db_connection():
    """Create and return a database connection."""
    return psycopg2.connect(
        host=os.getenv("PWC_DB_HOST", "localhost"),
        database=os.getenv("PWC_DB_NAME", "paperswithcode_hf"),
        user=os.getenv("PWC_DB_USER", "postgres"),
        password=os.getenv("PWC_DB_PASSWORD", ""),
        port=os.getenv("PWC_DB_PORT", "5432"),
    )


def get_papers_with_conflicting_tasks(conn) -> List[Dict]:
    """
    Find papers that have tasks violating the hierarchy.
    Returns papers with their task lists and task IDs.
    """
    query = """
    SELECT
        pt.paper_id,
        array_agg(DISTINCT t.name) as tasks,
        array_agg(DISTINCT t.id) as task_ids
    FROM paper_tasks pt
    JOIN tasks t ON pt.task_id = t.id
    WHERE LOWER(t.name) IN ('omni models', 'video understanding',
                          'image understanding', 'language modeling')
    GROUP BY pt.paper_id
    HAVING COUNT(DISTINCT LOWER(t.name)) > 1
    """

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query)
        return cur.fetchall()


def get_highest_priority_task(tasks: List[str]) -> str:
    """
    Given a list of tasks, return the highest priority task according to hierarchy.
    """
    tasks_lower = [t.lower() for t in tasks]

    for hierarchy_task in TASK_HIERARCHY:
        if hierarchy_task in tasks_lower:
            # Find the original case version
            for task in tasks:
                if task.lower() == hierarchy_task:
                    return task

    return tasks[0]  # Fallback


def get_tasks_to_remove(highest_task: str, all_tasks: List[str]) -> List[str]:
    """
    Given the highest priority task, return all lower-priority tasks that should be removed.
    """
    highest_task_lower = highest_task.lower()

    try:
        hierarchy_index = TASK_HIERARCHY.index(highest_task_lower)
    except ValueError:
        return []

    # All tasks below this in the hierarchy should be removed
    tasks_to_remove = []
    for task in all_tasks:
        task_lower = task.lower()
        if task_lower in TASK_HIERARCHY:
            task_index = TASK_HIERARCHY.index(task_lower)
            if task_index > hierarchy_index:
                tasks_to_remove.append(task)

    return tasks_to_remove


def get_task_ids_by_names(conn, task_names: List[str]) -> List[int]:
    """
    Get task IDs for given task names.
    """
    if not task_names:
        return []

    query = """
    SELECT id FROM tasks
    WHERE name = ANY(%s)
    """

    with conn.cursor() as cur:
        cur.execute(query, (task_names,))
        return [row[0] for row in cur.fetchall()]


def remove_conflicting_tasks(conn, paper_id: str, tasks_to_remove: List[str]) -> int:
    """
    Remove specified tasks from a paper.
    Returns the number of tasks removed.
    """
    if not tasks_to_remove:
        return 0

    # Get task IDs for the task names
    task_ids = get_task_ids_by_names(conn, tasks_to_remove)

    if not task_ids:
        return 0

    query = """
    DELETE FROM paper_tasks
    WHERE paper_id = %s AND task_id = ANY(%s)
    """

    with conn.cursor() as cur:
        cur.execute(query, (paper_id, task_ids))
        return cur.rowcount


def enforce_hierarchy(dry_run: bool = True) -> Dict[str, int]:
    """
    Main function to enforce task hierarchy.

    Args:
        dry_run: If True, only report what would be changed without making changes

    Returns:
        Dictionary with statistics about the operation
    """
    stats = {"papers_checked": 0, "papers_modified": 0, "tasks_removed": 0}

    conn = get_db_connection()

    try:
        # Get all papers with potential conflicts
        conflicting_papers = get_papers_with_conflicting_tasks(conn)
        stats["papers_checked"] = len(conflicting_papers)

        logger.info(
            f"Found {len(conflicting_papers)} papers with multiple hierarchy tasks"
        )

        for paper_data in conflicting_papers:
            paper_id = paper_data["paper_id"]
            tasks = paper_data["tasks"]

            # Determine which task to keep (highest priority)
            highest_task = get_highest_priority_task(tasks)

            # Determine which tasks to remove
            tasks_to_remove = get_tasks_to_remove(highest_task, tasks)

            if tasks_to_remove:
                logger.info(
                    f"Paper {paper_id}: "
                    f"Keeping '{highest_task}', "
                    f"removing {tasks_to_remove}"
                )

                if not dry_run:
                    removed = remove_conflicting_tasks(conn, paper_id, tasks_to_remove)
                    stats["tasks_removed"] += removed
                else:
                    stats["tasks_removed"] += len(tasks_to_remove)

                stats["papers_modified"] += 1

        if not dry_run:
            conn.commit()
            logger.info("Changes committed to database")
        else:
            logger.info("DRY RUN - No changes made to database")

    except Exception as e:
        conn.rollback()
        logger.error(f"Error enforcing hierarchy: {e}")
        raise
    finally:
        conn.close()

    return stats


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Enforce task hierarchy in paper_tasks table"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually apply changes (default is dry-run mode)",
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Task Hierarchy Enforcement")
    logger.info("=" * 60)
    logger.info(f"Hierarchy: {' > '.join(TASK_HIERARCHY)}")
    logger.info("=" * 60)

    if not args.apply:
        logger.warning("Running in DRY RUN mode - no changes will be made")
        logger.warning("Use --apply flag to actually make changes")

    stats = enforce_hierarchy(dry_run=not args.apply)

    logger.info("=" * 60)
    logger.info("Summary:")
    logger.info(f"  Papers with conflicts: {stats['papers_checked']}")
    logger.info(f"  Papers to be modified: {stats['papers_modified']}")
    logger.info(f"  Tasks to be removed: {stats['tasks_removed']}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
