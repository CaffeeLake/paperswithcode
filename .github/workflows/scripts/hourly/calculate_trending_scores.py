"""
Calculate Trending Scores using Exponential Moving Average (EMA)

This script calculates trending scores for GitHub repositories based on historical
star count snapshots. It uses an Exponential Moving Average (EMA) to smooth out
fluctuations and weight recent trends more heavily.

Algorithm:
1. For each repository with star history:
   - Get the current star count and previous snapshot
   - Calculate raw stars per hour (velocity)
   - Apply EMA: trendingScore = α × rawStarsPerHour + (1 - α) × previousTrendingScore
   - Store the updated trending score

EMA Formula:
- rawStarsPerHour = (currentStars - previousStars) / hoursSinceLastSync
- trendingScore = α × rawStarsPerHour + (1 - α) × previousTrendingScore
- Where α = 0.15 (smoothing factor)

The low alpha (0.15) means the score changes gradually, preventing sudden spikes
from dominating the ranking while still being responsive to recent changes.

Schedule: Hourly (every hour)
Dependencies: PostgreSQL, repository_star_history table with snapshots
"""

import sys
import time
import gc
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import text

from backend.database.connection import db_manager
from scripts.utils.cron_helpers import DatabaseCronJob


# EMA smoothing factor (0.15 means 85% weight on previous score, 15% on new data)
ALPHA = 0.15

# Minimum hours between snapshots to calculate velocity (avoid division by very small numbers)
MIN_HOURS_BETWEEN_SNAPSHOTS = 0.5


def get_repositories_needing_trending_update(
    session, batch_size: int = 100, update_threshold_hours: int = 1, logger=None
) -> list:
    """
    Get repositories that need trending score updates.

    Prioritizes:
    1. Repositories with snapshots but no trending score
    2. Repositories with outdated trending scores (> threshold_hours old)
    3. Repositories with recent star activity

    Args:
        session: Database session
        batch_size: Number of repositories to process
        update_threshold_hours: Only update if last update was more than N hours ago
        logger: Optional logger instance

    Returns:
        List of repository IDs
    """
    try:
        threshold_date = datetime.now() - timedelta(hours=update_threshold_hours)

        # Query to find repositories that need trending score updates
        query = text("""
            SELECT r.id
            FROM repositories r
            WHERE EXISTS (
                SELECT 1
                FROM repository_star_history rsh
                WHERE rsh.repository_id = r.id
            )
            AND (
                r.trending_score IS NULL
                OR r.trending_score_updated_at IS NULL
                OR r.trending_score_updated_at <= :threshold_date
            )
            ORDER BY
                r.trending_score_updated_at NULLS FIRST,
                r.num_stars DESC
            LIMIT :batch_size
        """)

        result = session.execute(
            query,
            {
                "threshold_date": threshold_date,
                "batch_size": batch_size,
            },
        ).fetchall()

        return [row[0] for row in result]

    except Exception as e:
        if logger:
            logger.error(f"Error fetching repositories needing update: {e}")
        return []
    finally:
        gc.collect()


def get_repository_snapshots(
    session, repository_id: int, limit: int = 2, logger=None
) -> list:
    """
    Get the most recent snapshots for a repository.

    Args:
        session: Database session
        repository_id: Repository ID
        limit: Number of snapshots to retrieve (default 2: current + previous)
        logger: Optional logger instance

    Returns:
        List of snapshot tuples (num_stars, snapshot_at)
    """
    try:
        query = text("""
            SELECT num_stars, snapshot_at
            FROM repository_star_history
            WHERE repository_id = :repository_id
            ORDER BY snapshot_at DESC
            LIMIT :limit
        """)

        result = session.execute(
            query,
            {
                "repository_id": repository_id,
                "limit": limit,
            },
        ).fetchall()

        return result

    except Exception as e:
        if logger:
            logger.error(
                f"Error fetching snapshots for repository {repository_id}: {e}"
            )
        return []
    finally:
        gc.collect()


def get_current_trending_score(
    session, repository_id: int, logger=None
) -> Optional[float]:
    """
    Get the current trending score for a repository.

    Args:
        session: Database session
        repository_id: Repository ID
        logger: Optional logger instance

    Returns:
        Current trending score or None
    """
    try:
        query = text("""
            SELECT trending_score
            FROM repositories
            WHERE id = :repository_id
        """)

        result = session.execute(
            query,
            {"repository_id": repository_id},
        ).fetchone()

        return float(result[0]) if result and result[0] is not None else None

    except Exception as e:
        if logger:
            logger.error(
                f"Error fetching trending score for repository {repository_id}: {e}"
            )
        return None
    finally:
        gc.collect()


def calculate_raw_stars_per_hour(
    current_stars: int, previous_stars: int, hours_elapsed: float
) -> float:
    """
    Calculate raw stars per hour (velocity).

    Args:
        current_stars: Current star count
        previous_stars: Previous star count
        hours_elapsed: Time elapsed between snapshots (in hours)

    Returns:
        Stars per hour (velocity)
    """
    if hours_elapsed < MIN_HOURS_BETWEEN_SNAPSHOTS:
        return 0.0

    stars_gained = current_stars - previous_stars
    return stars_gained / hours_elapsed


def calculate_ema_trending_score(
    raw_stars_per_hour: float,
    previous_trending_score: Optional[float],
    alpha: float = ALPHA,
) -> float:
    """
    Calculate trending score using Exponential Moving Average (EMA).

    Formula:
    trendingScore = α × rawStarsPerHour + (1 - α) × previousTrendingScore

    If this is the first calculation (no previous score), use raw value directly.

    Args:
        raw_stars_per_hour: Current velocity (stars/hour)
        previous_trending_score: Previous EMA trending score (None if first calculation)
        alpha: Smoothing factor (0.15 by default)

    Returns:
        New trending score
    """
    if previous_trending_score is None:
        # First calculation - use raw value directly
        return raw_stars_per_hour

    # Apply EMA formula
    return alpha * raw_stars_per_hour + (1 - alpha) * previous_trending_score


def update_repository_trending_score(
    session, repository_id: int, trending_score: float, logger=None
) -> bool:
    """
    Update the trending score for a repository.

    Args:
        session: Database session
        repository_id: Repository ID
        trending_score: New trending score
        logger: Optional logger instance

    Returns:
        True if successful, False otherwise
    """
    try:
        query = text("""
            UPDATE repositories
            SET
                trending_score = :trending_score,
                trending_score_updated_at = NOW(),
                updated_at = NOW()
            WHERE id = :repository_id
        """)

        session.execute(
            query,
            {
                "repository_id": repository_id,
                "trending_score": trending_score,
            },
        )

        session.commit()
        return True

    except Exception as e:
        session.rollback()
        if logger:
            logger.error(
                f"Error updating trending score for repository {repository_id}: {e}"
            )
        return False
    finally:
        gc.collect()


def process_repository_trending(
    session, repository_id: int, logger=None
) -> Optional[dict]:
    """
    Process trending score calculation for a single repository.

    Args:
        session: Database session
        repository_id: Repository ID
        logger: Optional logger instance

    Returns:
        Dictionary with calculation results or None if failed
    """
    try:
        # Get the two most recent snapshots
        snapshots = get_repository_snapshots(
            session, repository_id, limit=2, logger=logger
        )

        if len(snapshots) < 2:
            # Not enough history to calculate velocity
            # If we have 1 snapshot, initialize trending score to 0
            if len(snapshots) == 1:
                update_repository_trending_score(
                    session, repository_id, 0.0, logger=logger
                )
                return {
                    "repository_id": repository_id,
                    "trending_score": 0.0,
                    "raw_stars_per_hour": 0.0,
                    "reason": "insufficient_history",
                }
            return None

        # Extract snapshot data
        current_stars, current_time = snapshots[0]
        previous_stars, previous_time = snapshots[1]

        # Calculate time elapsed in hours
        time_diff = current_time - previous_time
        hours_elapsed = time_diff.total_seconds() / 3600

        if hours_elapsed < MIN_HOURS_BETWEEN_SNAPSHOTS:
            # Snapshots too close together
            return None

        # Calculate raw stars per hour (velocity)
        raw_stars_per_hour = calculate_raw_stars_per_hour(
            current_stars, previous_stars, hours_elapsed
        )

        # Get previous trending score
        previous_trending_score = get_current_trending_score(
            session, repository_id, logger=logger
        )

        # Calculate new EMA trending score
        new_trending_score = calculate_ema_trending_score(
            raw_stars_per_hour, previous_trending_score, ALPHA
        )

        # Update database
        success = update_repository_trending_score(
            session, repository_id, new_trending_score, logger=logger
        )

        if success:
            return {
                "repository_id": repository_id,
                "current_stars": current_stars,
                "previous_stars": previous_stars,
                "hours_elapsed": hours_elapsed,
                "raw_stars_per_hour": raw_stars_per_hour,
                "previous_trending_score": previous_trending_score,
                "new_trending_score": new_trending_score,
                "stars_gained": current_stars - previous_stars,
            }
        else:
            return None

    except Exception as e:
        if logger:
            logger.error(f"Error processing repository {repository_id}: {e}")
        return None
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


class TrendingScoresCalculationJob(DatabaseCronJob):
    """Hourly job to calculate trending scores for GitHub repositories using EMA."""

    def __init__(self):
        super().__init__(job_name="calculate_trending_scores", log_level="INFO")

    def run(self):
        """Main execution logic for trending score calculation."""
        self.logger.info("=" * 80)
        self.logger.info("Starting Trending Score Calculation (EMA)")
        self.logger.info("=" * 80)

        # Initialize database session
        session = None

        try:
            session = db_manager.session_local()
            self.logger.info("Database session initialized")

            # Configuration
            batch_size = 500  # Process 500 repositories per batch
            update_threshold_hours = 1  # Only update if last update was > 1 hour ago
            max_batches = 100  # Maximum number of batches to process
            min_memory_mb = 200  # Stop if less than 200MB available

            self.logger.info("Configuration:")
            self.logger.info(f"  - Batch size: {batch_size}")
            self.logger.info(f"  - Update threshold: {update_threshold_hours} hours")
            self.logger.info(f"  - Alpha (smoothing factor): {ALPHA}")
            self.logger.info(
                f"  - Min hours between snapshots: {MIN_HOURS_BETWEEN_SNAPSHOTS}"
            )

            total_processed = 0
            total_updated = 0
            total_insufficient_history = 0
            start_time = time.time()
            max_runtime = 55 * 60  # 55 minutes max

            for batch_num in range(max_batches):
                # Check runtime limit
                if time.time() - start_time > max_runtime:
                    self.logger.info("Runtime limit reached - stopping")
                    break

                # Check memory availability
                available_memory = check_memory_usage()
                if available_memory < min_memory_mb:
                    self.logger.warning(
                        f"Low memory ({available_memory}MB) - stopping to prevent OOM"
                    )
                    break

                # Get repositories needing update
                repository_ids = get_repositories_needing_trending_update(
                    session, batch_size, update_threshold_hours, logger=self.logger
                )

                if not repository_ids:
                    self.logger.info("No more repositories to process")
                    break

                self.logger.info(
                    f"Batch {batch_num + 1}: Processing {len(repository_ids)} repositories"
                )

                batch_updated = 0
                batch_insufficient = 0

                for repo_id in repository_ids:
                    result = process_repository_trending(
                        session, repo_id, logger=self.logger
                    )

                    if result:
                        total_processed += 1

                        if result.get("reason") == "insufficient_history":
                            batch_insufficient += 1
                            total_insufficient_history += 1
                        else:
                            batch_updated += 1
                            total_updated += 1

                            # Log detailed update for interesting changes
                            if (
                                result.get("stars_gained", 0) > 0
                                or result.get("new_trending_score", 0) > 0.1
                            ):
                                prev_score = result.get("previous_trending_score")
                                prev_score_str = (
                                    f"{prev_score:.4f}"
                                    if prev_score is not None
                                    else "N/A"
                                )
                                self.logger.info(
                                    f"  Repo {repo_id}: {result['previous_stars']} → {result['current_stars']} stars "
                                    f"({result['stars_gained']:+d} in {result['hours_elapsed']:.1f}h) | "
                                    f"Velocity: {result['raw_stars_per_hour']:.4f} stars/h | "
                                    f"Trending: {prev_score_str} → {result['new_trending_score']:.4f}"
                                )

                self.logger.info(
                    f"Batch {batch_num + 1} complete: {batch_updated} updated, {batch_insufficient} insufficient history"
                )

                # If batch was not full, we've processed all available repositories
                if len(repository_ids) < batch_size:
                    self.logger.info("All available repositories processed")
                    break

                # Garbage collection between batches
                gc.collect()

                # Small delay to prevent overloading
                time.sleep(0.1)

            # Final summary
            elapsed = (time.time() - start_time) / 60
            final_memory = check_memory_usage()

            self.logger.info("=" * 80)
            self.logger.info("Trending Score Calculation Completed")
            self.logger.info("=" * 80)
            self.logger.info(f"Total repositories processed: {total_processed}")
            self.logger.info(f"Trending scores updated: {total_updated}")
            self.logger.info(f"Insufficient history: {total_insufficient_history}")
            self.logger.info(f"Runtime: {elapsed:.1f} minutes")
            self.logger.info(f"Final memory available: {final_memory}MB")
            self.logger.info("=" * 80)

        except Exception as e:
            self.logger.error(f"Fatal error: {e}")
            raise
        finally:
            # Clean up database session
            if session:
                session.close()
                self.logger.info("Database session closed")


if __name__ == "__main__":
    job = TrendingScoresCalculationJob()
    success = job.execute()
    sys.exit(0 if success else 1)
