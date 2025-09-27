"""
Fixed GitHub Stars Update CRON Job

Designed for low-memory VPS environments (4GB RAM, no swap).
Fixes the hanging/OOM issues in the original script.

Key optimizations:
- Processes one repository at a time to minimize memory usage
- Immediate cleanup of objects after use
- Frequent garbage collection
- Memory monitoring with automatic stopping
- Conservative processing limits

Schedule: Hourly (every hour)
Dependencies: PostgreSQL, GitHub API token
"""

import sys
import time
import gc
import os
from datetime import datetime, timedelta
from typing import Optional
import requests
import psycopg2
from psycopg2.extras import RealDictCursor


def log(message: str):
    """Memory-efficient logging - print and flush immediately."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{timestamp} - {message}", flush=True)


def get_db_connection():
    """Get a lightweight database connection with minimal memory footprint."""
    return psycopg2.connect(
        host=os.getenv("PWC_DB_HOST", "localhost"),
        port=os.getenv("PWC_DB_PORT", "5432"),
        database=os.getenv("PWC_DB_NAME", "paperswithcode_hf"),
        user=os.getenv("PWC_DB_USER", "postgres"),
        password=os.getenv("PWC_DB_PASSWORD", ""),
        connect_timeout=10,
        options="-c statement_timeout=15000",
    )


def get_next_repository():
    """Get one repository at a time to minimize memory usage."""
    threshold_date = datetime.now() - timedelta(days=7)

    query = """
    SELECT id, owner, name, num_stars
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
    ORDER BY num_stars_updated_at ASC NULLS FIRST, id ASC
    LIMIT 1
    """

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, (threshold_date,))
            result = cursor.fetchone()
            return dict(result) if result else None
    except Exception as e:
        log(f"Database error: {e}")
        return None
    finally:
        if conn:
            conn.close()
        # Force garbage collection after database operation
        gc.collect()


def fetch_github_stars(owner: str, name: str, github_token: str) -> Optional[int]:
    """Fetch star count with minimal memory usage."""
    url = f"https://api.github.com/repos/{owner}/{name}"

    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "PapersWithCode-Fixed/1.0",
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code == 200:
            data = response.json()
            stars = data.get("stargazers_count", 0)
            # Clean up response data immediately
            del data, response
            gc.collect()
            return stars
        elif response.status_code == 404:
            return 0
        elif response.status_code == 403:
            if "rate limit" in response.text.lower():
                log(f"Rate limit hit for {owner}/{name} - waiting 60s")
                time.sleep(60)
            return None
        else:
            return None

    except Exception as e:
        log(f"API error for {owner}/{name}: {e}")
        return None
    finally:
        # Force cleanup
        gc.collect()


def update_repository_stars(repo_id: int, num_stars: int):
    """Update repository with minimal memory footprint."""
    query = """
    UPDATE repositories
    SET num_stars = %s,
        num_stars_updated_at = CURRENT_TIMESTAMP,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = %s
    """

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute(query, (num_stars, repo_id))
            conn.commit()
    except Exception as e:
        log(f"Update error for repo {repo_id}: {e}")
    finally:
        if conn:
            conn.close()
        gc.collect()


def check_memory_usage():
    """Check current memory usage and return available memory in MB."""
    try:
        with open("/proc/meminfo", "r") as f:
            meminfo = f.read()

        for line in meminfo.split("\n"):
            if "MemAvailable:" in line:
                # Extract available memory in kB and convert to MB
                available_kb = int(line.split()[1])
                available_mb = available_kb // 1024
                return available_mb
    except:  # noqa: E722
        return 1000  # Default fallback


def main():
    """Main execution function."""
    log("Starting fixed GitHub stars update")

    # Check GitHub token
    github_token = os.getenv("PWC_GITHUB_TOKEN")
    if not github_token:
        log("ERROR: PWC_GITHUB_TOKEN not set")
        sys.exit(1)

    # Conservative limits - optimized for 4GB VPS
    # 40% of GitHub API limit
    delay = 1.5
    max_repos = 2000  # Conservative limit (40% of API capacity)
    min_memory_mb = 200  # Stop if less than 200MB available

    processed = 0
    updated = 0
    start_time = time.time()
    max_runtime = 35 * 60  # 35 minutes max

    log(f"Starting processing with {max_repos} repo limit (~2000 repos/hour capacity)")

    while processed < max_repos:
        # Check runtime limit
        if time.time() - start_time > max_runtime:
            log("Runtime limit reached - stopping")
            break

        # Check memory availability
        available_memory = check_memory_usage()
        if available_memory < min_memory_mb:
            log(f"Low memory ({available_memory}MB) - stopping to prevent OOM")
            break

        # Get next repository
        repo = get_next_repository()
        if not repo:
            log("No more repositories to process")
            break

        repo_id = repo["id"]
        owner = repo["owner"]
        name = repo["name"]
        current_stars = repo.get("num_stars", 0)

        # Process repository
        stars = fetch_github_stars(owner, name, github_token)

        if stars is not None:
            update_repository_stars(repo_id, stars)
            updated += 1

            if stars != current_stars:
                log(f"Updated {owner}/{name}: {current_stars} → {stars} stars")

        processed += 1

        # Progress update every 50 repos
        if processed % 50 == 0:
            elapsed = (time.time() - start_time) / 60
            memory = check_memory_usage()
            log(
                f"Progress: {processed} processed, {updated} updated, "
                f"{elapsed:.1f}min elapsed, {memory}MB memory available"
            )

        # Conservative rate limiting
        time.sleep(delay)

        # Force garbage collection every 10 repos
        if processed % 10 == 0:
            gc.collect()

    # Final summary
    elapsed = (time.time() - start_time) / 60
    final_memory = check_memory_usage()
    log(f"Completed: {processed} processed, {updated} updated in {elapsed:.1f}min")
    log(f"Final memory available: {final_memory}MB")


if __name__ == "__main__":
    main()
