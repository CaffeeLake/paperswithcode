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
- Where α = 0.75 (smoothing factor)

A high alpha (0.75) weights the latest observed velocity heavily (75%) versus
the previous trending score (25%), making rankings respond quickly to recent
changes while still retaining some smoothing.

Schedule: Hourly (every hour)
Dependencies: PostgreSQL, repository_star_history table with snapshots
"""

import sys
import time
import gc
from datetime import datetime, timedelta
from sqlalchemy import text

from backend.database.connection import db_manager
from scripts.utils.cron_helpers import DatabaseCronJob


# EMA smoothing factor (0.75 means 75% weight on new data, 25% on previous score)
ALPHA = 0.75

# Minimum hours between snapshots to calculate velocity (avoid division by very small numbers)
MIN_HOURS_BETWEEN_SNAPSHOTS = 0.5

# ``repositories.trending_score`` is NUMERIC(10, 4). Values below this are just
# old EMA decay residue and can trigger PostgreSQL numeric underflow in batch math.
MIN_PREVIOUS_SCORE = 0.000001
MAX_TRENDING_SCORE = 999999.9999


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

        # Query to find repositories that need trending score updates. Recent
        # official paper repos go first so hot launches do not sit behind a
        # large stale backlog.
        query = text("""
            SELECT r.id
            FROM repositories r
            LEFT JOIN paper_repositories pr
                ON pr.repository_id = r.id
                AND pr.is_official = TRUE
            LEFT JOIN papers p
                ON p.id = pr.paper_id
                AND p.is_latest_version
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
            GROUP BY r.id, r.trending_score_updated_at, r.num_stars
            ORDER BY
                CASE
                    WHEN MAX(p.date_published) >= NOW() - INTERVAL '30 days'
                    THEN 0
                    ELSE 1
                END,
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


def process_repository_batch(session, repository_ids: list, logger=None) -> dict:
    """Calculate and persist trending scores for a whole batch in one SQL pass.

    Replaces the previous per-repository approach (three queries plus a commit
    for every repository), which made the hourly job CPU/IO bound for ~20
    minutes against the 4.6M-row star-history table. The EMA maths is expressed
    directly in SQL using a LATERAL top-2 lookup that rides the
    ``(repository_id, snapshot_at DESC)`` index:

        raw_velocity = (current_stars - previous_stars) / hours_between_snapshots
        new_score    = alpha * raw_velocity + (1 - alpha) * previous_score
                       (or raw_velocity when there is no previous score)

    A repository with a single snapshot is seeded to 0.0; a repository whose two
    latest snapshots are < MIN_HOURS_BETWEEN_SNAPSHOTS apart is left untouched
    (matching the original behaviour).

    Returns a dict with ``updated`` (EMA scores written) and ``insufficient``
    (single-snapshot repos seeded to 0.0) counts.
    """
    if not repository_ids:
        return {"updated": 0, "insufficient": 0}

    query = text("""
        WITH candidates AS (
            SELECT
                id,
                CASE
                    WHEN trending_score IS NULL THEN NULL
                    WHEN trending_score::text = 'NaN' THEN NULL
                    WHEN trending_score < 0 THEN 0.0
                    WHEN trending_score < :min_prev_score THEN 0.0
                    WHEN trending_score > :max_score THEN :max_score
                    ELSE trending_score::float8
                END AS prev_score
            FROM repositories
            WHERE id = ANY(:repo_ids)
        ),
        snap2 AS (
            SELECT c.id AS repository_id, c.prev_score, s.num_stars,
                   s.snapshot_at, s.rn
            FROM candidates c
            CROSS JOIN LATERAL (
                SELECT num_stars, snapshot_at,
                       ROW_NUMBER() OVER (ORDER BY snapshot_at DESC) AS rn
                FROM repository_star_history rsh
                WHERE rsh.repository_id = c.id
                ORDER BY snapshot_at DESC
                LIMIT 2
            ) s
        ),
        pivoted AS (
            SELECT
                repository_id,
                MAX(prev_score) AS prev_score,
                COUNT(*) AS snap_count,
                MAX(num_stars) FILTER (WHERE rn = 1) AS current_stars,
                MAX(snapshot_at) FILTER (WHERE rn = 1) AS current_at,
                MAX(num_stars) FILTER (WHERE rn = 2) AS previous_stars,
                MAX(snapshot_at) FILTER (WHERE rn = 2) AS previous_at
            FROM snap2
            GROUP BY repository_id
        ),
        raw_scores AS (
            SELECT
                repository_id,
                snap_count,
                CASE
                    WHEN snap_count = 1 THEN 0.0
                    WHEN snap_count >= 2
                         AND EXTRACT(EPOCH FROM (current_at - previous_at))
                             / 3600.0 >= :min_hours
                    THEN
                        CASE
                            WHEN prev_score IS NULL
                            THEN GREATEST(
                                (current_stars - previous_stars)
                                / (EXTRACT(EPOCH FROM (current_at - previous_at))
                                   / 3600.0),
                                0.0
                            )
                            ELSE :alpha * ((current_stars - previous_stars)
                                 / (EXTRACT(EPOCH FROM (current_at - previous_at))
                                    / 3600.0))
                                 + (1 - :alpha) * prev_score
                        END
                    ELSE NULL
                END AS new_score
            FROM pivoted
        ),
        computed AS (
            SELECT
                repository_id,
                snap_count,
                LEAST(GREATEST(new_score, 0.0), :max_score)::numeric(10, 4)
                    AS new_score
            FROM raw_scores
            WHERE new_score IS NOT NULL
        ),
        updated AS (
            UPDATE repositories r
            SET trending_score = c.new_score,
                trending_score_updated_at = NOW(),
                updated_at = NOW()
            FROM computed c
            WHERE r.id = c.repository_id
              AND c.new_score IS NOT NULL
            RETURNING r.id, c.snap_count
        )
        SELECT
            COUNT(*) FILTER (WHERE snap_count >= 2) AS updated_count,
            COUNT(*) FILTER (WHERE snap_count = 1) AS insufficient_count
        FROM updated
    """)

    try:
        row = session.execute(
            query,
            {
                "repo_ids": repository_ids,
                "min_hours": MIN_HOURS_BETWEEN_SNAPSHOTS,
                "min_prev_score": MIN_PREVIOUS_SCORE,
                "max_score": MAX_TRENDING_SCORE,
                "alpha": ALPHA,
            },
        ).fetchone()
        session.commit()
        return {
            "updated": int(row[0] or 0),
            "insufficient": int(row[1] or 0),
        }
    except Exception as e:
        session.rollback()
        if logger:
            logger.error(f"Error processing trending batch: {e}")
        raise
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

                batch_result = process_repository_batch(
                    session, repository_ids, logger=self.logger
                )
                batch_updated = batch_result["updated"]
                batch_insufficient = batch_result["insufficient"]

                if batch_updated == 0 and batch_insufficient == 0:
                    raise RuntimeError(
                        "Trending batch made no progress for "
                        f"{len(repository_ids)} queued repositories"
                    )

                total_updated += batch_updated
                total_insufficient_history += batch_insufficient
                total_processed += batch_updated + batch_insufficient

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
