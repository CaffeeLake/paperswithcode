#!/usr/bin/env python3
"""
Fix LVBench to be linked to Video-Language Models instead of Vision-Language Models.
"""

import sys
from sqlalchemy import text
from backend.database.connection import db_manager


def fix_lvbench():
    """Fix LVBench task association."""
    with db_manager.session_local() as db:
        # Get LVBench dataset
        dataset_query = text("SELECT id, name FROM datasets WHERE slug = 'lvbench'")
        dataset_result = db.execute(dataset_query)
        dataset_row = dataset_result.fetchone()

        if not dataset_row:
            print("❌ LVBench dataset not found")
            return

        dataset_id, dataset_name = dataset_row

        # Get Video-Language Models task ID
        task_query = text("SELECT id FROM tasks WHERE name = 'Video-Language Models'")
        task_result = db.execute(task_query)
        task_row = task_result.fetchone()

        if not task_row:
            print("❌ Video-Language Models task not found")
            return

        video_task_id = task_row[0]

        # Get current task associations
        current_query = text("""
            SELECT td.task_id, t.name
            FROM task_datasets td
            INNER JOIN tasks t ON td.task_id = t.id
            WHERE td.dataset_id = :dataset_id
        """)
        current_result = db.execute(current_query, {"dataset_id": dataset_id})
        current_tasks = current_result.fetchall()

        print(f"📦 Fixing {dataset_name} (ID: {dataset_id})")
        print(f"   Current tasks: {', '.join([name for _, name in current_tasks])}")

        # Remove all current tasks
        for task_id, task_name in current_tasks:
            delete_query = text("""
                DELETE FROM task_datasets
                WHERE dataset_id = :dataset_id AND task_id = :task_id
            """)
            db.execute(delete_query, {"dataset_id": dataset_id, "task_id": task_id})
            print(f"   Removed: {task_name}")

        # Add Video-Language Models
        insert_query = text("""
            INSERT INTO task_datasets (dataset_id, task_id)
            VALUES (:dataset_id, :task_id)
        """)
        db.execute(insert_query, {"dataset_id": dataset_id, "task_id": video_task_id})
        print("   Added: Video-Language Models")

        db.commit()
        print("✅ LVBench fixed!")


if __name__ == "__main__":
    try:
        fix_lvbench()
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)
