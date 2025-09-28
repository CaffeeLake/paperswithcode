#!/usr/bin/env python3
"""Debug script to check repository prioritization."""

import psycopg2
from psycopg2.extras import RealDictCursor
import os
from datetime import datetime, timedelta

conn = psycopg2.connect(
    host=os.getenv("PWC_DB_HOST", "localhost"),
    port=os.getenv("PWC_DB_PORT", "5432"),
    database=os.getenv("PWC_DB_NAME", "paperswithcode_hf"),
    user=os.getenv("PWC_DB_USER", "postgres"),
    password=os.getenv("PWC_DB_PASSWORD", ""),
)

with conn.cursor(cursor_factory=RealDictCursor) as cur:
    # Check total repos with 0 stars
    cur.execute("SELECT COUNT(*) FROM repositories WHERE num_stars = 0")
    zero_stars = cur.fetchone()["count"]
    print(f"Repositories with 0 stars: {zero_stars}")

    # Check repos with 0 stars that have owner/name
    cur.execute(
        "SELECT COUNT(*) FROM repositories WHERE num_stars = 0 AND owner IS NOT NULL AND name IS NOT NULL AND owner != '' AND name != ''"
    )
    zero_stars_valid = cur.fetchone()["count"]
    print(f"Repositories with 0 stars and valid owner/name: {zero_stars_valid}")

    # Check repos with 0 stars that have never been updated
    cur.execute(
        "SELECT COUNT(*) FROM repositories WHERE num_stars = 0 AND num_stars_updated_at IS NULL AND owner IS NOT NULL AND name IS NOT NULL AND owner != '' AND name != ''"
    )
    zero_stars_never_updated = cur.fetchone()["count"]
    print(f"Repositories with 0 stars never updated: {zero_stars_never_updated}")

    # Check what the priority query would return
    threshold_date = datetime.now() - timedelta(days=7)

    priority_query = """
    SELECT
        owner,
        name,
        COUNT(*) as url_count,
        MIN(num_stars_updated_at) as oldest_update,
        MAX(num_stars) as current_stars,
        CASE
            WHEN MIN(num_stars_updated_at) IS NULL AND MAX(num_stars) = 0 THEN 1
            ELSE 2
        END as priority
    FROM repositories
    WHERE owner IS NOT NULL
      AND name IS NOT NULL
      AND owner != ''
      AND name != ''
      AND (
          num_stars_updated_at IS NULL
          OR num_stars_updated_at < %s
          OR num_stars IS NULL
      )
    GROUP BY owner, name
    ORDER BY
        CASE
            WHEN MIN(num_stars_updated_at) IS NULL AND MAX(num_stars) = 0 THEN 1
            ELSE 2
        END ASC,
        MIN(num_stars_updated_at) ASC NULLS FIRST,
        COUNT(*) DESC
    LIMIT 10
    """

    cur.execute(priority_query, (threshold_date,))
    results = cur.fetchall()
    print("\nNext 10 repositories in priority queue:")
    for i, repo in enumerate(results, 1):
        print(
            f"{i}. {repo['owner']}/{repo['name']} - {repo['url_count']} URLs, {repo['current_stars']} stars, priority {repo['priority']}, last_update: {repo['oldest_update']}"
        )

    # Check if there are any high priority repos (priority 1)
    cur.execute("""
    SELECT COUNT(*)
    FROM (
        SELECT DISTINCT owner, name
        FROM repositories
        WHERE owner IS NOT NULL
          AND name IS NOT NULL
          AND owner != ''
          AND name != ''
          AND num_stars_updated_at IS NULL
          AND num_stars = 0
    ) AS distinct_repos
    """)
    high_priority_count = cur.fetchone()["count"]
    print(
        f"\nHigh priority repositories (never updated, 0 stars): {high_priority_count}"
    )

conn.close()
