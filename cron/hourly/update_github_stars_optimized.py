"""
Optimized GitHub Stars Update CRON Job

This version is optimized for the normalized database structure where multiple URLs
can point to the same GitHub repository (e.g., different subdirectories).

Key optimizations:
- Groups repositories by owner/name to avoid duplicate API calls
- Updates all URLs for the same repository with a single API call
- Processes unique repositories only, dramatically reducing API usage
- Memory efficient processing for 4GB VPS environments

Schedule: Hourly (every hour)
Dependencies: PostgreSQL, GitHub API token
"""

import sys
import time
import gc
import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict
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


def get_next_repository_group() -> Optional[Dict]:
    """
    Get the next unique repository (by owner/name) that needs updating.
    Returns all repository IDs that share the same owner/name.
    """
    threshold_date = datetime.now() - timedelta(days=7)

    query = """
    SELECT
        owner,
        name,
        ARRAY_AGG(id) as repository_ids,
        COUNT(*) as url_count,
        MIN(num_stars_updated_at) as oldest_update,
        MAX(num_stars) as current_stars
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
        MIN(num_stars_updated_at) ASC NULLS FIRST,
        COUNT(*) DESC  -- Process repositories with more URLs first
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
        gc.collect()


def fetch_github_stars(owner: str, name: str, github_token: str) -> Optional[int]:
    """Fetch star count with minimal memory usage."""
    url = f"https://api.github.com/repos/{owner}/{name}"

    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "PapersWithCode-Optimized/1.0",
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
            log(f"API error {response.status_code} for {owner}/{name}")
            return None

    except Exception as e:
        log(f"API error for {owner}/{name}: {e}")
        return None
    finally:
        gc.collect()


def update_repository_group_stars(repository_ids: List[int], num_stars: int):
    """Update all repositories in a group with the same star count."""
    query = """
    UPDATE repositories
    SET num_stars = %s,
        num_stars_updated_at = CURRENT_TIMESTAMP,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = ANY(%s)
    """

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute(query, (num_stars, repository_ids))
            conn.commit()
            return cursor.rowcount
    except Exception as e:
        log(f"Update error for repo group {repository_ids}: {e}")
        return 0
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
                available_kb = int(line.split()[1])
                available_mb = available_kb // 1024
                return available_mb
    except:  # noqa: E722
        return 1000  # Default fallback


def main():
    """Main execution function."""
    log("Starting optimized GitHub stars update")

    # Check GitHub token
    github_token = os.getenv("PWC_GITHUB_TOKEN")
    if not github_token:
        log("ERROR: PWC_GITHUB_TOKEN not set")
        sys.exit(1)

    # Optimized limits - much more efficient due to deduplication
    delay = 1.0  # 1 second between API calls (3600 calls/hour max)
    max_unique_repos = 3000  # Process up to 3000 unique repositories per hour
    min_memory_mb = 200  # Stop if less than 200MB available

    processed_groups = 0
    updated_repositories = 0
    api_calls = 0
    start_time = time.time()
    max_runtime = 50 * 60  # 50 minutes max (leave 10 min buffer)

    log(
        f"Starting optimized processing - targeting {max_unique_repos} unique repositories"
    )

    while processed_groups < max_unique_repos:
        # Check runtime limit
        if time.time() - start_time > max_runtime:
            log("Runtime limit reached - stopping")
            break

        # Check memory availability
        available_memory = check_memory_usage()
        if available_memory < min_memory_mb:
            log(f"Low memory ({available_memory}MB) - stopping to prevent OOM")
            break

        # Get next repository group
        repo_group = get_next_repository_group()
        if not repo_group:
            log("No more repository groups to process")
            break

        owner = repo_group["owner"]
        name = repo_group["name"]
        repository_ids = repo_group["repository_ids"]
        url_count = repo_group["url_count"]
        current_stars = repo_group.get("current_stars", 0)

        # Fetch stars for this unique repository
        stars = fetch_github_stars(owner, name, github_token)
        api_calls += 1

        if stars is not None:
            # Update ALL repositories that share this owner/name
            updated_count = update_repository_group_stars(repository_ids, stars)
            updated_repositories += updated_count

            if stars != current_stars:
                log(
                    f"Updated {owner}/{name} ({url_count} URLs): {current_stars} → {stars} stars"
                )
            else:
                log(
                    f"Confirmed {owner}/{name} ({url_count} URLs): {stars} stars (no change)"
                )

        processed_groups += 1

        # Progress update every 25 unique repositories
        if processed_groups % 25 == 0:
            elapsed = (time.time() - start_time) / 60
            memory = check_memory_usage()
            efficiency = updated_repositories / api_calls if api_calls > 0 else 0
            log(
                f"Progress: {processed_groups} unique repos, {updated_repositories} URLs updated, "
                f"{api_calls} API calls, {efficiency:.1f} URLs/call efficiency, "
                f"{elapsed:.1f}min elapsed, {memory}MB memory available"
            )

        # Rate limiting
        time.sleep(delay)

        # Garbage collection every 10 groups
        if processed_groups % 10 == 0:
            gc.collect()

    # Final summary
    elapsed = (time.time() - start_time) / 60
    final_memory = check_memory_usage()
    efficiency = updated_repositories / api_calls if api_calls > 0 else 0

    log(f"Completed: {processed_groups} unique repositories processed")
    log(f"Updated: {updated_repositories} repository URLs")
    log(f"API calls: {api_calls} (efficiency: {efficiency:.1f} URLs per call)")
    log(f"Runtime: {elapsed:.1f} minutes")
    log(f"Final memory available: {final_memory}MB")

    # Calculate potential savings
    if url_count > 0:
        old_api_calls = updated_repositories  # Old method: 1 call per URL
        savings = old_api_calls - api_calls
        savings_percent = (savings / old_api_calls * 100) if old_api_calls > 0 else 0
        log(f"API call savings: {savings} calls ({savings_percent:.1f}% reduction)")


if __name__ == "__main__":
    main()
