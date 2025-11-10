#!/usr/bin/env python3
"""
Add "object counting" keyword to the object counting task and link papers.
"""

import sys
from backend.database.connection import get_database_session
from backend.models.database import Task
from backend.services.task_service import TaskService


def find_object_counting_task(db):
    """Find the object counting task."""
    # Try different variations
    task = db.query(Task).filter(Task.name.ilike("%object counting%")).first()
    if task:
        return task

    task = db.query(Task).filter(Task.name.ilike("%counting%")).first()
    if task:
        return task

    # List all tasks with "count" in the name
    tasks = db.query(Task).filter(Task.name.ilike("%count%")).all()
    if tasks:
        print("\nFound tasks with 'count' in name:")
        for t in tasks:
            print(f"  ID: {t.id}, Name: {t.name}, Keywords: {t.keywords}")

    return None


def main():
    print("=" * 80)
    print("Adding 'object counting' keyword to Object Counting task")
    print("=" * 80)

    db_session_gen = get_database_session()
    db = next(db_session_gen)

    try:
        # Find the object counting task
        print("\n1. Finding object counting task...")
        task = find_object_counting_task(db)

        if not task:
            print("\n❌ Error: Could not find 'Object Counting' task in database")
            print("   Please check the task name or create the task first.")
            return 1

        print(f"   ✓ Found task: {task.name} (ID: {task.id})")
        print(f"   Current keywords: {task.keywords or '(none)'}")

        # Add the keyword using the service
        print("\n2. Adding 'object counting' keyword...")
        service = TaskService(db)

        try:
            updated_task = service.add_keywords(str(task.id), ["object counting"])
            print("   ✓ Added keyword 'object counting'")
            print(f"   Updated keywords: {updated_task.keywords}")
        except Exception as e:
            print(f"   ❌ Error adding keyword: {e}")
            return 1

        print("\n✅ Successfully added keyword!")
        print("\nNext step: Run the keyword matching script to link papers:")
        print(
            "  uv run --env-file backend/keys.env python backend/database/tasks_setup/link_papers_by_task_keywords.py"
        )

        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
