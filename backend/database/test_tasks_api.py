"""
Test script for Tasks API endpoints.

This script verifies that the Tasks API is working correctly by testing
all implemented endpoints.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.models.database import Area
from backend.services.task_service import TaskService
from backend.config import get_settings


def test_tasks_api():
    """Test all Tasks API functionality."""
    print("=" * 70)
    print("Testing Tasks API")
    print("=" * 70)

    # Get database connection
    settings = get_settings()
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        task_service = TaskService(db)

        # Test 1: Get all tasks
        print("\n1. Testing get_tasks() - List all tasks:")
        tasks = task_service.get_tasks(page=1, page_size=10)
        print(f"   ✓ Found {tasks.count} total tasks")
        print(f"   ✓ Showing {len(tasks.results)} tasks on page 1")
        if tasks.results:
            print(f"   ✓ First task: {tasks.results[0].name}")

        # Test 2: Get task by ID
        if tasks.results:
            print("\n2. Testing get_task_by_id():")
            task_id = tasks.results[0].id
            task = task_service.get_task_by_id(task_id)
            print(f"   ✓ Retrieved task: {task.name}")
            print(f"   ✓ Description: {task.description[:100]}...")
            print(f"   ✓ Paper count: {task.paper_count}")

        # Test 3: Search tasks
        print("\n3. Testing search_tasks():")
        search_results = task_service.search_tasks(
            query="classification", page=1, page_size=10
        )
        print(f"   ✓ Found {search_results.count} tasks matching 'classification'")
        for task in search_results.results:
            print(f"   ✓ - {task.name}")

        # Test 4: Filter by area
        print("\n4. Testing get_tasks_by_area():")
        # Get Computer Vision area ID
        cv_area = db.query(Area).filter(Area.name == "Computer Vision").first()
        if cv_area:
            cv_tasks = task_service.get_tasks_by_area(
                area_id=str(cv_area.id), page=1, page_size=10
            )
            print(f"   ✓ Found {cv_tasks.count} tasks in Computer Vision area")
            for task in cv_tasks.results:
                print(f"   ✓ - {task.name}")

        # Test 5: Test hierarchy (if any child tasks exist)
        print("\n5. Testing task hierarchy:")
        for task in tasks.results:
            if task.parent_id:
                parents = task_service.get_task_parents(task.id)
                print(f"   ✓ Task '{task.name}' has {len(parents)} parent(s)")
                break
        else:
            print("   ℹ No tasks with parents found (all are top-level)")

        # Test 6: Get children (if any)
        for task in tasks.results:
            children = task_service.get_task_children(task.id, page=1, page_size=10)
            if children.count > 0:
                print("\n6. Testing get_task_children():")
                print(f"   ✓ Task '{task.name}' has {children.count} child task(s)")
                for child in children.results:
                    print(f"   ✓ - {child.name}")
                break
        else:
            print("\n6. Testing get_task_children():")
            print("   ℹ No tasks with children found")

        print("\n" + "=" * 70)
        print("All Tasks API tests passed! ✓")
        print("=" * 70)

    except Exception as e:
        print(f"\n✗ Error during testing: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    test_tasks_api()
