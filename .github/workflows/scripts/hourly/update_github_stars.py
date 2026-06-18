"""
Unified GitHub Stars Update CRON Job

This script fetches GitHub star counts and stores historical snapshots for trending analysis.
It replaces the previous separate scripts (update_github_stars_optimized.py and
update_github_stars_trending.py) with a unified approach.

Key Features:
- Fetches GitHub star counts via GitHub API
- Stores historical snapshots in repository_star_history table
- Groups repositories by owner/name to avoid duplicate API calls
- Prioritizes recent papers (published within last 6 months) for frequent updates
- Memory efficient processing for 4GB RAM systems

Update Strategy:
- Hot papers (any linked paper < 30 days old): Update every hour, processed
  first by newest paper date. Uses MAX(date_published) so a new paper on a
  repo shared with older work is not downgraded.
- Recent papers (any linked paper < 6 months old): Update every hour, after hot
- Never-updated old repos: Backfill tier, after hot/recent
- Regular papers: Update every 7 days
- Each update stores a historical snapshot for trending calculations

Schedule: Hourly (every hour)
Dependencies: PostgreSQL, GitHub API token (PWC_GITHUB_TOKEN)
"""

import sys
import time
import gc
import os
from datetime import datetime, timedelta
from typing import Optional, Dict
import requests

from backend.database.connection import db_manager
from backend.services.repository_service import RepositoryService
from sqlalchemy import text

# Repos with any linked paper newer than this get hourly updates and jump the
# queue ahead of older work sharing the same GitHub repo.
HOT_PAPER_WINDOW_DAYS = 30


def log(message: str):
    """Memory-efficient logging - print and flush immediately."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{timestamp} - {message}", flush=True)


def get_repository_service():
    """Get a repository service instance with database session."""
    session = db_manager.session_local()
    return session, RepositoryService(session)


def get_next_repository_group(
    session, threshold_hours_recent: int = 2, threshold_days_regular: int = 7
) -> Optional[Dict]:
    """
    Get the next unique repository (by owner/name) that needs updating.
    Returns all repository IDs that share the same owner/name.

    Priority system (uses MAX linked paper date, not MIN):
    1. Hot: any linked paper published within HOT_PAPER_WINDOW_DAYS
    2. Recent: any linked paper published within 6 months
    3. Never-updated repositories (old papers only — backfill tier)
    4. Regular: older papers, 7-day cadence

    Within each tier, newest linked paper is processed first so fresh releases
    are not stuck behind stale backfill work.

    Args:
        session: Database session
        threshold_hours_recent: Update threshold for recent papers (hours)
        threshold_days_regular: Update threshold for regular papers (days)

    Returns:
        Dictionary with repository group information
    """
    try:
        threshold_recent = datetime.now() - timedelta(hours=threshold_hours_recent)
        threshold_regular = datetime.now() - timedelta(days=threshold_days_regular)
        six_months_ago = datetime.now() - timedelta(days=180)
        thirty_days_ago = datetime.now() - timedelta(days=HOT_PAPER_WINDOW_DAYS)

        # Query to find repositories that need updating, grouped by owner/name.
        # Eligibility and priority use MAX(p.date_published): a brand-new paper
        # linked to a repo that also backs older work must not inherit the old
        # paper's refresh cadence.
        query = text("""
            SELECT
                r.owner,
                r.name,
                array_agg(DISTINCT r.id) as repository_ids,
                COUNT(DISTINCT r.id) as url_count,
                MIN(r.num_stars_updated_at) as oldest_update,
                MAX(r.num_stars) as current_stars,
                MAX(p.date_published) as newest_paper_date,
                CASE
                    WHEN MAX(p.date_published) >= :thirty_days_ago THEN 1
                    WHEN MAX(p.date_published) >= :six_months_ago THEN 2
                    WHEN MIN(r.num_stars_updated_at) IS NULL THEN 3
                    ELSE 4
                END as priority
            FROM repositories r
            JOIN paper_repositories pr ON r.id = pr.repository_id
            JOIN papers p ON pr.paper_id = p.id
            WHERE r.owner IS NOT NULL
            AND r.name IS NOT NULL
            AND r.owner != ''
            AND r.name != ''
            AND pr.is_official = TRUE
            AND p.is_latest_version = TRUE
            GROUP BY r.owner, r.name
            HAVING (
                MIN(r.num_stars_updated_at) IS NULL
                OR (
                    MAX(p.date_published) >= :six_months_ago
                    AND MIN(r.num_stars_updated_at) < :threshold_recent
                )
                OR (
                    MAX(p.date_published) < :six_months_ago
                    AND MIN(r.num_stars_updated_at) < :threshold_regular
                )
            )
            ORDER BY
                priority ASC,
                MAX(p.date_published) DESC,
                MIN(r.num_stars_updated_at) ASC NULLS FIRST,
                COUNT(DISTINCT r.id) DESC
            LIMIT 1
        """)

        result = session.execute(
            query,
            {
                "threshold_recent": threshold_recent,
                "threshold_regular": threshold_regular,
                "six_months_ago": six_months_ago,
                "thirty_days_ago": thirty_days_ago,
            },
        ).fetchone()

        if result:
            return {
                "owner": result[0],
                "name": result[1],
                "repository_ids": result[2],
                "url_count": result[3],
                "oldest_update": result[4],
                "current_stars": result[5] or 0,
                "newest_paper_date": result[6],
                "priority": result[7],
            }

        return None

    except Exception as e:
        log(f"Database error: {e}")
        return None
    finally:
        gc.collect()


def fetch_github_stars(owner: str, name: str, github_token: str) -> Optional[int]:
    """
    Fetch star count from GitHub API with minimal memory usage.

    Args:
        owner: Repository owner
        name: Repository name
        github_token: GitHub API token

    Returns:
        Star count or None if API call failed
    """
    url = f"https://api.github.com/repos/{owner}/{name}"

    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "PapersWithCode-Stars/1.0",
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


def store_star_snapshot(
    session, repository_ids: list, num_stars: int, snapshot_time: datetime = None
) -> int:
    """
    Store a historical snapshot of star counts for trending analysis.

    Args:
        session: Database session
        repository_ids: List of repository IDs to snapshot
        num_stars: Current star count
        snapshot_time: Time of snapshot (defaults to now)

    Returns:
        Number of snapshots stored
    """
    if snapshot_time is None:
        snapshot_time = datetime.now()

    try:
        # Insert snapshot for each repository ID
        for repo_id in repository_ids:
            insert_query = text("""
                INSERT INTO repository_star_history
                    (repository_id, num_stars, snapshot_at)
                VALUES (:repo_id, :num_stars, :snapshot_at)
                ON CONFLICT (repository_id, snapshot_at)
                DO UPDATE SET num_stars = :num_stars
            """)

            session.execute(
                insert_query,
                {
                    "repo_id": repo_id,
                    "num_stars": num_stars,
                    "snapshot_at": snapshot_time,
                },
            )

        session.commit()
        return len(repository_ids)

    except Exception as e:
        session.rollback()
        log(f"Error storing star snapshot: {e}")
        return 0
    finally:
        gc.collect()


def update_repository_group_stars(
    repo_service: RepositoryService, session, repository_ids: list, num_stars: int
) -> int:
    """
    Update repository stars and store historical snapshot.

    Args:
        repo_service: Repository service instance
        session: Database session
        repository_ids: List of repository IDs to update
        num_stars: New star count

    Returns:
        Number of repositories updated
    """
    try:
        # Update current star counts
        updated_count = repo_service.update_repository_stars_batch(
            repository_ids, num_stars
        )

        # Store historical snapshot
        store_star_snapshot(session, repository_ids, num_stars)

        return updated_count

    except Exception as e:
        log(f"Update error for repo group {repository_ids}: {e}")
        return 0
    finally:
        gc.collect()


def mark_repository_group_as_processed(
    repo_service: RepositoryService, repository_ids: list
) -> int:
    """
    Mark repositories as processed even if API call failed.
    This prevents infinite loops for repositories that can't be fetched.

    Args:
        repo_service: Repository service instance
        repository_ids: List of repository IDs to mark as processed

    Returns:
        Number of repositories marked
    """
    try:
        return repo_service.mark_repositories_as_processed(repository_ids)
    except Exception as e:
        log(f"Failed to mark repo group as processed {repository_ids}: {e}")
        return 0
    finally:
        gc.collect()


def check_memory_usage() -> int:
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
    """Main execution function for unified GitHub stars update."""
    log("=" * 80)
    log("Starting Unified GitHub Stars Update")
    log("=" * 80)

    # Check GitHub token
    github_token = os.getenv("PWC_GITHUB_TOKEN")
    if not github_token:
        log("ERROR: PWC_GITHUB_TOKEN not set")
        sys.exit(1)

    # Initialize database session and service
    session = None
    repo_service = None

    try:
        session, repo_service = get_repository_service()
        log("Database session and repository service initialized")

        # Configuration
        delay = 1.0  # 1 second between API calls (3600 calls/hour max)
        max_updates = 3000  # Process up to 3000 repositories per hour (safe margin for 5K GitHub rate limit)
        threshold_hours_recent = (
            1  # Update recent papers every 1 hour (for accurate velocity tracking)
        )
        threshold_days_regular = 7  # Update regular papers every 7 days
        min_memory_mb = 200  # Stop if less than 200MB available

        processed_groups = 0
        updated_repositories = 0
        snapshots_stored = 0
        api_calls = 0
        start_time = time.time()
        max_runtime = 55 * 60  # 55 minutes max (leave 5 min buffer)

        log("Configuration:")
        log(f"  - Max updates per hour: {max_updates}")
        log(f"  - Recent papers update threshold: {threshold_hours_recent} hours")
        log(f"  - Regular papers update threshold: {threshold_days_regular} days")
        log(f"  - API call delay: {delay}s")

        while processed_groups < max_updates:
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
            repo_group = get_next_repository_group(
                session, threshold_hours_recent, threshold_days_regular
            )
            if not repo_group:
                log("No more repositories to process")
                break

            owner = repo_group["owner"]
            name = repo_group["name"]
            repository_ids = repo_group["repository_ids"]
            url_count = repo_group["url_count"]
            current_stars = repo_group.get("current_stars", 0)
            newest_paper_date = repo_group.get("newest_paper_date")
            priority = repo_group.get("priority", 4)

            # Calculate age of the newest linked paper (drives queue tier).
            if newest_paper_date:
                paper_age_days = (datetime.now().date() - newest_paper_date).days
            else:
                paper_age_days = 0

            # Determine priority label
            if priority == 1:
                priority_label = "HOT"
            elif priority == 2:
                priority_label = "RECENT"
            elif priority == 3:
                priority_label = "NEW"
            else:
                priority_label = "REGULAR"

            # Fetch stars for this unique repository
            stars = fetch_github_stars(owner, name, github_token)
            api_calls += 1

            if stars is not None:
                # Update ALL repositories and store snapshot
                updated_count = update_repository_group_stars(
                    repo_service, session, repository_ids, stars
                )
                updated_repositories += updated_count
                snapshots_stored += url_count

                stars_change = stars - current_stars
                change_indicator = (
                    f"(+{stars_change})"
                    if stars_change > 0
                    else f"({stars_change})"
                    if stars_change < 0
                    else ""
                )

                log(
                    f"[{priority_label}] {owner}/{name} ({url_count} URLs, {paper_age_days}d old): "
                    f"{current_stars} → {stars} stars {change_indicator}"
                )
            else:
                # API call failed - mark as processed to prevent infinite loops
                mark_repository_group_as_processed(repo_service, repository_ids)
                log(
                    f"[{priority_label}] API failed for {owner}/{name} - marked as processed"
                )

            processed_groups += 1

            # Progress update every 50 repositories
            if processed_groups % 50 == 0:
                elapsed = (time.time() - start_time) / 60
                memory = check_memory_usage()
                efficiency = updated_repositories / api_calls if api_calls > 0 else 0
                log(
                    f"Progress: {processed_groups} repos, {updated_repositories} URLs updated, "
                    f"{snapshots_stored} snapshots, {api_calls} API calls, "
                    f"{efficiency:.1f} URLs/call efficiency, {elapsed:.1f}min elapsed, {memory}MB memory"
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

        log("=" * 80)
        log("GitHub Stars Update Completed")
        log("=" * 80)
        log(f"Repositories processed: {processed_groups}")
        log(f"Repository URLs updated: {updated_repositories}")
        log(f"Historical snapshots stored: {snapshots_stored}")
        log(f"API calls: {api_calls}")
        log(f"Efficiency: {efficiency:.1f} URLs per API call")
        log(f"Runtime: {elapsed:.1f} minutes")
        log(f"Final memory available: {final_memory}MB")
        log("=" * 80)

    finally:
        # Clean up database session
        if session:
            session.close()
            log("Database session closed")


if __name__ == "__main__":
    main()
