"""
Examples of using the Tasks API.

This script demonstrates common usage patterns for the Tasks API endpoints.
"""

import requests
from typing import Dict, Any

# Base API URL (adjust if needed)
BASE_URL = "http://localhost:8000/api/v1"


def print_section(title: str):
    """Print a section header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_task(task: Dict[str, Any]):
    """Pretty print a task object."""
    print(f"\n  ID: {task['id']}")
    print(f"  Name: {task['name']}")
    if task.get("description"):
        desc = (
            task["description"][:100] + "..."
            if len(task["description"]) > 100
            else task["description"]
        )
        print(f"  Description: {desc}")
    if task.get("area_id"):
        print(f"  Area ID: {task['area_id']}")
    if task.get("parent_id"):
        print(f"  Parent ID: {task['parent_id']}")
    print(f"  Level: {task['level']}")
    print(f"  Papers: {task.get('paper_count', 0)}")
    print(f"  Slug: {task.get('slug', 'N/A')}")


def example_list_all_tasks():
    """Example 1: List all tasks with pagination."""
    print_section("Example 1: List All Tasks")

    response = requests.get(f"{BASE_URL}/tasks/", params={"page": 1, "page_size": 10})

    if response.status_code == 200:
        data = response.json()
        print(f"\n  Total tasks: {data['count']}")
        print(f"  Showing: {len(data['results'])} tasks")
        print(f"  Next page: {data.get('next_page', 'None')}")

        for task in data["results"]:
            print_task(task)
    else:
        print(f"  Error: {response.status_code}")


def example_get_specific_task():
    """Example 2: Get a specific task by ID."""
    print_section("Example 2: Get Specific Task")

    task_id = "1"  # Image Classification
    response = requests.get(f"{BASE_URL}/tasks/{task_id}")

    if response.status_code == 200:
        task = response.json()
        print_task(task)
    else:
        print(f"  Error: {response.status_code}")


def example_search_tasks():
    """Example 3: Search tasks by keyword."""
    print_section("Example 3: Search Tasks")

    search_query = "language"
    response = requests.get(
        f"{BASE_URL}/tasks/", params={"q": search_query, "page": 1, "page_size": 10}
    )

    if response.status_code == 200:
        data = response.json()
        print(f"\n  Search query: '{search_query}'")
        print(f"  Found: {data['count']} tasks")

        for task in data["results"]:
            print_task(task)
    else:
        print(f"  Error: {response.status_code}")


def example_filter_by_area():
    """Example 4: Get tasks for a specific area."""
    print_section("Example 4: Filter Tasks by Area")

    # Get Computer Vision area tasks
    area_id = "1"  # Computer Vision
    response = requests.get(
        f"{BASE_URL}/areas/{area_id}/tasks", params={"page": 1, "page_size": 10}
    )

    if response.status_code == 200:
        data = response.json()
        print(f"\n  Area ID: {area_id}")
        print(f"  Total tasks: {data['count']}")

        for task in data["results"]:
            print_task(task)
    else:
        print(f"  Error: {response.status_code}")


def example_get_task_children():
    """Example 5: Get child tasks (subtasks)."""
    print_section("Example 5: Get Task Children")

    task_id = "1"
    response = requests.get(
        f"{BASE_URL}/tasks/{task_id}/children", params={"page": 1, "page_size": 10}
    )

    if response.status_code == 200:
        data = response.json()
        print(f"\n  Parent task ID: {task_id}")
        print(f"  Child tasks: {data['count']}")

        if data["count"] > 0:
            for task in data["results"]:
                print_task(task)
        else:
            print("  No child tasks found")
    else:
        print(f"  Error: {response.status_code}")


def example_get_task_parents():
    """Example 6: Get parent tasks (hierarchy)."""
    print_section("Example 6: Get Task Parents")

    task_id = "1"
    response = requests.get(f"{BASE_URL}/tasks/{task_id}/parents")

    if response.status_code == 200:
        parents = response.json()
        print(f"\n  Task ID: {task_id}")
        print(f"  Parent count: {len(parents)}")

        if parents:
            for parent in parents:
                print_task(parent)
        else:
            print("  No parent tasks (this is a top-level task)")
    else:
        print(f"  Error: {response.status_code}")


def example_filter_with_ordering():
    """Example 7: List tasks with custom ordering."""
    print_section("Example 7: Custom Ordering")

    response = requests.get(
        f"{BASE_URL}/tasks/",
        params={
            "page": 1,
            "page_size": 10,
            "ordering": "name",  # or "-name" for descending
        },
    )

    if response.status_code == 200:
        data = response.json()
        print("\n  Ordered by: name (ascending)")
        print(f"  Total tasks: {data['count']}")

        for task in data["results"]:
            print(f"  - {task['name']}")
    else:
        print(f"  Error: {response.status_code}")


def example_filter_by_level():
    """Example 8: Filter tasks by hierarchy level."""
    print_section("Example 8: Filter by Hierarchy Level")

    response = requests.get(
        f"{BASE_URL}/tasks/",
        params={
            "level": 0,  # Top-level tasks only
            "page": 1,
            "page_size": 10,
        },
    )

    if response.status_code == 200:
        data = response.json()
        print("\n  Level: 0 (top-level)")
        print(f"  Found: {data['count']} tasks")

        for task in data["results"]:
            print(f"  - {task['name']} (Level {task['level']})")
    else:
        print(f"  Error: {response.status_code}")


def main():
    """Run all examples."""
    print("\n" + "=" * 70)
    print("  Tasks API Examples")
    print("  Make sure the API server is running on http://localhost:8000")
    print("=" * 70)

    try:
        # Test if server is running
        response = requests.get(f"{BASE_URL}/tasks/?page=1&page_size=1", timeout=2)
        if response.status_code != 200:
            print("\n⚠ Warning: API server may not be running or responding correctly")
            return
    except requests.exceptions.RequestException:
        print("\n✗ Error: Cannot connect to API server")
        print("  Please start the server with: uv run backend/main.py")
        return

    # Run examples
    example_list_all_tasks()
    example_get_specific_task()
    example_search_tasks()
    example_filter_by_area()
    example_get_task_children()
    example_get_task_parents()
    example_filter_with_ordering()
    example_filter_by_level()

    print("\n" + "=" * 70)
    print("  All examples completed!")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
