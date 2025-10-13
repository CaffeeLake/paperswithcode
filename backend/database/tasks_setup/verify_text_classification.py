"""
Verify text classification paper-task associations in the database.
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor


def main():
    # Database connection
    conn = psycopg2.connect(
        host=os.getenv("PWC_DB_HOST"),
        database=os.getenv("PWC_DB_NAME"),
        user=os.getenv("PWC_DB_USER"),
        password=os.getenv("PWC_DB_PASSWORD"),
    )

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get text classification task info
            cur.execute(
                """
                SELECT id, name, slug, description
                FROM tasks
                WHERE LOWER(name) = LOWER('Text classification')
                """
            )
            task = cur.fetchone()

            if not task:
                print("❌ Text classification task not found!")
                return 1

            print(f"\n{'=' * 70}")
            print("Text Classification Task Info")
            print(f"{'=' * 70}")
            print(f"Task ID:     {task['id']}")
            print(f"Name:        {task['name']}")
            print(f"Slug:        {task['slug']}")
            print(f"Description: {task['description']}")

            # Count paper-task associations
            cur.execute(
                """
                SELECT COUNT(*) as count
                FROM paper_tasks
                WHERE task_id = %s
                """,
                (task["id"],),
            )
            count = cur.fetchone()["count"]

            print(f"\nTotal papers linked to Text Classification: {count:,}")

            # Get some sample papers
            cur.execute(
                """
                SELECT p.id, p.arxiv_id, p.title, p.date_published
                FROM papers p
                JOIN paper_tasks pt ON p.id = pt.paper_id
                WHERE pt.task_id = %s
                ORDER BY p.date_published DESC
                LIMIT 10
                """,
                (task["id"],),
            )
            sample_papers = cur.fetchall()

            print(f"\n{'=' * 70}")
            print("Sample Papers (10 most recent)")
            print(f"{'=' * 70}")
            for i, paper in enumerate(sample_papers, 1):
                print(f"{i}. [{paper['arxiv_id']}] {paper['title'][:80]}...")
                print(f"   Published: {paper['date_published']}")

            print(f"{'=' * 70}\n")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return 1

    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    exit(main())
