#!/usr/bin/env python3
"""
Find datasets that are linked to more than one task.

This script queries the database to find datasets that have multiple task associations,
which should be rare (only large datasets like ImageNet should be linked to multiple tasks).
"""

import sys
from sqlalchemy import text
from backend.database.connection import get_engine


def find_multi_task_datasets():
    """Find all datasets linked to more than one task."""
    engine = get_engine()

    # Query to find datasets with multiple tasks
    query = text("""
        SELECT
            d.id,
            d.name,
            d.slug,
            d.full_name,
            COUNT(td.task_id) as task_count,
            STRING_AGG(t.name, ', ' ORDER BY t.name) as task_names,
            STRING_AGG(t.id::text, ', ' ORDER BY t.name) as task_ids
        FROM datasets d
        INNER JOIN task_datasets td ON d.id = td.dataset_id
        INNER JOIN tasks t ON td.task_id = t.id
        GROUP BY d.id, d.name, d.slug, d.full_name
        HAVING COUNT(td.task_id) > 1
        ORDER BY task_count DESC, d.name ASC
    """)

    with engine.connect() as conn:
        result = conn.execute(query)
        rows = result.fetchall()

        if not rows:
            print("✅ No datasets found with multiple task associations.")
            return

        print(f"\n📊 Found {len(rows)} datasets linked to more than one task:\n")
        print("=" * 100)
        print(f"{'Dataset Name':<40} {'Tasks':<8} {'Task Names':<50}")
        print("=" * 100)

        for row in rows:
            dataset_id, name, slug, full_name, task_count, task_names, task_ids = row
            display_name = full_name if full_name else name
            print(f"{display_name:<40} {task_count:<8} {task_names:<50}")

        print("=" * 100)
        print(f"\nTotal: {len(rows)} datasets")

        # Also show detailed breakdown
        print("\n" + "=" * 100)
        print("DETAILED BREAKDOWN:")
        print("=" * 100)

        for row in rows:
            dataset_id, name, slug, full_name, task_count, task_names, task_ids = row
            display_name = full_name if full_name else name
            print(f"\n📦 {display_name} (ID: {dataset_id}, Slug: {slug})")
            print(f"   Linked to {task_count} tasks:")

            # Get individual task details
            task_query = text("""
                SELECT t.id, t.name, t.level, a.name as area_name
                FROM tasks t
                INNER JOIN task_datasets td ON t.id = td.task_id
                LEFT JOIN areas a ON t.area_id = a.id
                WHERE td.dataset_id = :dataset_id
                ORDER BY t.name
            """)

            task_result = conn.execute(task_query, {"dataset_id": dataset_id})
            tasks = task_result.fetchall()

            for task_id, task_name, task_level, area_name in tasks:
                area_str = f" ({area_name})" if area_name else ""
                print(
                    f"   - {task_name} (ID: {task_id}, Level: {task_level}){area_str}"
                )


if __name__ == "__main__":
    try:
        find_multi_task_datasets()
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)
