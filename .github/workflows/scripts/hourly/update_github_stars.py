"""
Unified GitHub Stars Update CRON Job

This script fetches GitHub star counts and stores historical snapshots for trending analysis.
It runs two independent queues concurrently so frequent updates cannot starve
the weekly backlog:

- Fresh queue: hot/recent papers, using PWC_GITHUB_TOKEN
- Weekly queue: older and never-updated repositories, using the token from the
  separate aiconsultancynielsrogge GitHub account

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
Dependencies: PostgreSQL and one GitHub API token per queue
"""

import time
import gc
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Optional, Dict, List
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


def get_repository_groups(
    session,
    queue: str,
    limit: int,
    threshold_hours_recent: int = 2,
    threshold_days_regular: int = 7,
) -> List[Dict]:
    """
    Get an ordered batch of unique repositories that need updating.
    Each result contains all repository IDs that share the same owner/name.

    The fresh queue contains hot/recent repositories. The weekly queue contains
    older repositories, including never-updated backfill. Keeping these queues
    separate guarantees progress through both classes of work.

    Within each tier, the repository with the oldest update is processed first.

    Args:
        session: Database session
        threshold_hours_recent: Update threshold for recent papers (hours)
        threshold_days_regular: Update threshold for regular papers (days)

    Returns:
        Ordered repository groups
    """
    if queue not in {"fresh", "weekly"}:
        raise ValueError(f"Unknown GitHub stars queue: {queue}")

    try:
        threshold_recent = datetime.now() - timedelta(hours=threshold_hours_recent)
        threshold_regular = datetime.now() - timedelta(days=threshold_days_regular)
        six_months_ago = datetime.now() - timedelta(days=180)
        thirty_days_ago = datetime.now() - timedelta(days=HOT_PAPER_WINDOW_DAYS)

        if queue == "fresh":
            eligibility_clause = """
                linked.newest_paper_date >= :six_months_ago
                AND (
                    repo_groups.oldest_update IS NULL
                    OR repo_groups.oldest_update < :threshold_recent
                )
            """
        else:
            eligibility_clause = """
                linked.newest_paper_date < :six_months_ago
                AND (
                    repo_groups.oldest_update IS NULL
                    OR repo_groups.oldest_update < :threshold_regular
                )
            """

        # Oldest-update-first ordering prevents a busy tier from repeatedly
        # selecting the same newest repositories while older rows wait forever.
        # Group every duplicate owner/name row first, then use official paper
        # links only to determine eligibility. One API call therefore keeps all
        # duplicate repository rows consistent.
        query = text(f"""
            WITH repo_groups AS (
                SELECT
                    LOWER(r.owner) AS owner_key,
                    LOWER(r.name) AS name_key,
                    MIN(r.owner) AS owner,
                    MIN(r.name) AS name,
                    array_agg(r.id ORDER BY r.id) AS repository_ids,
                    COUNT(*) AS url_count,
                    MIN(r.num_stars_updated_at) AS oldest_update,
                    MAX(r.num_stars) AS current_stars
                FROM repositories r
                WHERE COALESCE(r.owner, '') != ''
                  AND COALESCE(r.name, '') != ''
                GROUP BY LOWER(r.owner), LOWER(r.name)
            ),
            linked AS (
                SELECT
                    LOWER(r.owner) AS owner_key,
                    LOWER(r.name) AS name_key,
                    MAX(p.date_published) AS newest_paper_date
                FROM repositories r
                JOIN paper_repositories pr ON r.id = pr.repository_id
                JOIN papers p ON pr.paper_id = p.id
                WHERE COALESCE(r.owner, '') != ''
                  AND COALESCE(r.name, '') != ''
                  AND pr.is_official = TRUE
                  AND p.is_latest_version = TRUE
                GROUP BY LOWER(r.owner), LOWER(r.name)
            )
            SELECT
                repo_groups.owner,
                repo_groups.name,
                repo_groups.repository_ids,
                repo_groups.url_count,
                repo_groups.oldest_update,
                repo_groups.current_stars,
                linked.newest_paper_date,
                CASE
                    WHEN linked.newest_paper_date >= :thirty_days_ago THEN 1
                    WHEN linked.newest_paper_date >= :six_months_ago THEN 2
                    WHEN repo_groups.oldest_update IS NULL THEN 3
                    ELSE 4
                END AS priority
            FROM repo_groups
            JOIN linked USING (owner_key, name_key)
            WHERE {eligibility_clause}
            ORDER BY
                priority ASC,
                repo_groups.oldest_update ASC NULLS FIRST,
                linked.newest_paper_date DESC,
                repo_groups.url_count DESC
            LIMIT :group_limit
        """)

        results = session.execute(
            query,
            {
                "group_limit": limit,
                "threshold_recent": threshold_recent,
                "threshold_regular": threshold_regular,
                "six_months_ago": six_months_ago,
                "thirty_days_ago": thirty_days_ago,
            },
        ).fetchall()

        return [
            {
                "owner": result[0],
                "name": result[1],
                "repository_ids": result[2],
                "url_count": result[3],
                "oldest_update": result[4],
                "current_stars": result[5] or 0,
                "newest_paper_date": result[6],
                "priority": result[7],
            }
            for result in results
        ]

    except Exception as e:
        log(f"Database error: {e}")
        raise
    finally:
        gc.collect()


def get_next_repository_group(
    session,
    queue: str,
    threshold_hours_recent: int = 2,
    threshold_days_regular: int = 7,
) -> Optional[Dict]:
    """Return the first eligible group; retained for focused diagnostics."""
    groups = get_repository_groups(
        session,
        queue,
        1,
        threshold_hours_recent,
        threshold_days_regular,
    )
    return groups[0] if groups else None


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


def run_queue(
    queue: str,
    github_token: str,
    max_updates: int,
    max_runtime_seconds: int,
) -> Dict[str, int]:
    """Process one star-update queue with its own token and DB session."""
    log("=" * 80)
    log(f"Starting GitHub Stars Update [{queue.upper()}]")
    log("=" * 80)

    # Initialize database session and service
    session = None
    repo_service = None

    try:
        session, repo_service = get_repository_service()
        log("Database session and repository service initialized")

        # Configuration
        delay = 1.0  # 1 second between API calls (3600 calls/hour max)
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
        log(f"Configuration [{queue.upper()}]:")
        log(f"  - Max updates per hour: {max_updates}")
        log(f"  - Recent papers update threshold: {threshold_hours_recent} hours")
        log(f"  - Regular papers update threshold: {threshold_days_regular} days")
        log(f"  - API call delay: {delay}s")

        repository_groups = get_repository_groups(
            session,
            queue,
            max_updates,
            threshold_hours_recent,
            threshold_days_regular,
        )
        if not repository_groups:
            log(f"[{queue.upper()}] No repositories eligible at run start")

        for repo_group in repository_groups:
            # Check runtime limit
            if time.time() - start_time > max_runtime_seconds:
                log(f"[{queue.upper()}] Runtime limit reached - stopping")
                break

            # Check memory availability
            available_memory = check_memory_usage()
            if available_memory < min_memory_mb:
                log(f"Low memory ({available_memory}MB) - stopping to prevent OOM")
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
        log(f"GitHub Stars Update Completed [{queue.upper()}]")
        log("=" * 80)
        log(f"Repositories processed: {processed_groups}")
        log(f"Repository URLs updated: {updated_repositories}")
        log(f"Historical snapshots stored: {snapshots_stored}")
        log(f"API calls: {api_calls}")
        log(f"Efficiency: {efficiency:.1f} URLs per API call")
        log(f"Runtime: {elapsed:.1f} minutes")
        log(f"Final memory available: {final_memory}MB")
        log("=" * 80)

        return {
            "processed_groups": processed_groups,
            "updated_repositories": updated_repositories,
            "api_calls": api_calls,
        }

    finally:
        # Clean up database session
        if session:
            session.close()
            log(f"Database session closed [{queue.upper()}]")


def main():
    """Run fresh and weekly queues concurrently with independent rate limits."""
    token_config = {
        "fresh": os.getenv("PWC_GITHUB_TOKEN"),
        "weekly": os.getenv("GITHUB_CLASSIC_TOKEN_AICONSULTANCYNIELSROGGE"),
    }
    missing = [queue for queue, token in token_config.items() if not token]
    if missing:
        missing_names = ", ".join(missing)
        raise RuntimeError(f"Missing GitHub token for queue(s): {missing_names}")

    # The fresh queue retains the existing 3,000-call budget. One thousand
    # weekly calls/hour clears the initial backlog quickly and comfortably
    # exceeds the ~213/hour needed to cover 35k repositories every seven days.
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(run_queue, "fresh", token_config["fresh"], 3000, 48 * 60),
            executor.submit(run_queue, "weekly", token_config["weekly"], 1000, 40 * 60),
        ]
        for future in futures:
            future.result()


if __name__ == "__main__":
    main()
