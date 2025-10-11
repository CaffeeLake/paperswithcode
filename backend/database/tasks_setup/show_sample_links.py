#!/usr/bin/env python3
"""Show sample paper-task links to verify quality."""

import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    database="paperswithcode_hf",
    user="postgres",
    password="postgres",
    host="localhost",
    port="5432",
)

cur = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 80)
print("Sample Paper-Task Links (Quality Check)")
print("=" * 80)

# Get a few sample papers with their tasks
cur.execute("""
    SELECT
        p.id,
        p.title,
        p.arxiv_id,
        ARRAY_AGG(t.name ORDER BY t.name) as tasks
    FROM papers p
    JOIN paper_tasks pt ON p.id = pt.paper_id
    JOIN tasks t ON pt.task_id = t.id
    WHERE p.is_latest_version
    GROUP BY p.id, p.title, p.arxiv_id
    HAVING COUNT(pt.task_id) >= 2
    ORDER BY p.date_published DESC
    LIMIT 10
""")

rows = cur.fetchall()

for i, row in enumerate(rows, 1):
    print(f"\n{i}. {row['title'][:70]}...")
    print(f"   ArXiv: {row['arxiv_id']}")
    print(f"   Tasks: {', '.join(row['tasks'])}")

# Show statistics
print("\n" + "=" * 80)
print("Overall Statistics")
print("=" * 80)

cur.execute("""
    SELECT
        COUNT(DISTINCT paper_id) as papers_with_tasks,
        COUNT(*) as total_links,
        ROUND(AVG(task_count), 2) as avg_tasks_per_paper
    FROM (
        SELECT paper_id, COUNT(task_id) as task_count
        FROM paper_tasks
        GROUP BY paper_id
    ) subquery
""")

stats = cur.fetchone()
print(f"Papers with tasks: {stats['papers_with_tasks']:,}")
print(f"Total paper-task links: {stats['total_links']:,}")
print(f"Average tasks per paper: {stats['avg_tasks_per_paper']}")

# Show distribution of tasks per paper
print("\n" + "=" * 80)
print("Distribution of Tasks per Paper")
print("=" * 80)

cur.execute("""
    SELECT
        task_count,
        COUNT(*) as paper_count,
        ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) as percentage
    FROM (
        SELECT paper_id, COUNT(task_id) as task_count
        FROM paper_tasks
        GROUP BY paper_id
    ) subquery
    GROUP BY task_count
    ORDER BY task_count
    LIMIT 10
""")

for row in cur.fetchall():
    print(
        f"{row['task_count']} task(s): {row['paper_count']:>6,} papers ({row['percentage']:>5}%)"
    )

cur.close()
conn.close()
