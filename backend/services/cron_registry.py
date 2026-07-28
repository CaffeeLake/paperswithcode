"""Production CRON job registry for the admin health dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple


@dataclass(frozen=True)
class CronJobDefinition:
    id: str
    display_name: str
    category: str
    schedule: str
    script_path: str
    log_name: str
    process_patterns: Tuple[str, ...]
    lock_file: Optional[str]
    expected_runtime_minutes: int
    stale_after_minutes: int
    critical: bool
    healthy_no_work_allowed: bool
    db_freshness_query: Optional[str] = None
    workflow_file: Optional[str] = None
    workflow_jobs: Tuple[str, ...] = ()


CRON_JOBS: Tuple[CronJobDefinition, ...] = (
    CronJobDefinition(
        id="paper_markdown_backfill",
        display_name="Paper Markdown Backfill",
        category="hourly",
        schedule="17 * * * * (live); 43 2 * * * (full backfill reconciliation)",
        script_path="hourly/backfill_paper_markdown.py",
        log_name="paper_markdown_backfill",
        process_patterns=("backfill_paper_markdown",),
        lock_file=(
            "/var/lib/paperswithcode/production/cron-locks/paper_markdown_backfill.lock"
        ),
        expected_runtime_minutes=45,
        stale_after_minutes=150,
        critical=True,
        healthy_no_work_allowed=True,
        workflow_file="cron-paper-markdown.yml",
        workflow_jobs=("run",),
    ),
    CronJobDefinition(
        id="update_hot_github_trending",
        display_name="Update Hot GitHub Trending",
        category="hourly",
        schedule="*/15 * * * * (every 15 minutes)",
        script_path="hourly/update_hot_github_trending.py",
        log_name="update_hot_github_trending",
        process_patterns=("update_hot_github_trending",),
        lock_file=(
            "/var/lib/paperswithcode/production/cron-locks/"
            "update_hot_github_trending.lock"
        ),
        expected_runtime_minutes=12,
        stale_after_minutes=45,
        critical=False,
        healthy_no_work_allowed=True,
        db_freshness_query="""
            WITH hot_repositories AS (
                SELECT DISTINCT r.id, r.created_at AS repository_created_at
                FROM repositories r
                JOIN paper_repositories pr
                  ON pr.repository_id = r.id
                 AND pr.is_official = TRUE
                JOIN papers p
                  ON p.id = pr.paper_id
                 AND p.is_latest_version = TRUE
                WHERE p.date_published >= now() - INTERVAL '30 days'
                  AND COALESCE(r.owner, '') != ''
                  AND COALESCE(r.name, '') != ''
            ),
            history AS (
                SELECT
                    hr.id,
                    hr.repository_created_at,
                    count(rsh.id) AS snapshot_count,
                    min(rsh.snapshot_at) AS first_snapshot_at,
                    max(rsh.snapshot_at) AS last_snapshot_at
                FROM hot_repositories hr
                LEFT JOIN repository_star_history rsh
                  ON rsh.repository_id = hr.id
                GROUP BY hr.id, hr.repository_created_at
            ),
            stale_papers AS (
                SELECT count(DISTINCT p.id) AS count
                FROM papers p
                JOIN paper_repositories pr
                  ON pr.paper_id = p.id
                 AND pr.is_official = TRUE
                JOIN hot_repositories hr ON hr.id = pr.repository_id
                JOIN repositories r ON r.id = hr.id
                WHERE p.is_latest_version = TRUE
                  AND p.date_published >= CURRENT_DATE - INTERVAL '365 days'
                  AND r.trending_score > 0
                  AND (
                    p.trending_score IS NULL
                    OR p.trending_score_updated_at < r.trending_score_updated_at
                  )
            )
            SELECT
                max(last_snapshot_at) AS last_write,
                count(*) AS hot_repository_count,
                count(*) FILTER (
                  WHERE last_snapshot_at > now() - interval '30 minutes'
                ) AS recent_writes,
                count(*) FILTER (
                  WHERE snapshot_count = 1
                    AND first_snapshot_at < now() - interval '30 minutes'
                ) AS one_snapshot_over_30m,
                (SELECT count FROM stale_papers) AS stale_paper_scores,
                COALESCE(
                  EXTRACT(EPOCH FROM (
                    now() - min(
                      COALESCE(last_snapshot_at, repository_created_at)
                    )
                      FILTER (
                        WHERE COALESCE(last_snapshot_at, repository_created_at)
                              < now() - interval '15 minutes'
                      )
                  )) / 60,
                  0
                )::bigint AS oldest_eligible_wait_minutes
            FROM history
        """,
        workflow_file="cron-update-hot-github-trending.yml",
        workflow_jobs=("run",),
    ),
    CronJobDefinition(
        id="update_github_stars",
        display_name="Update GitHub Stars",
        category="hourly",
        schedule="0 * * * * (hourly)",
        script_path="hourly/update_github_stars.py",
        log_name="github_stars_cron",
        process_patterns=("update_github_stars", "github_stars"),
        lock_file="/var/lib/paperswithcode/production/cron-locks/update_github_stars.lock",
        expected_runtime_minutes=55,
        stale_after_minutes=120,
        critical=True,
        healthy_no_work_allowed=False,
        db_freshness_query="""
            SELECT max(num_stars_updated_at) AS last_write,
                   count(*) FILTER (
                     WHERE num_stars_updated_at > now() - interval '6 hours'
                   ) AS recent_writes
            FROM repositories
            WHERE num_stars_updated_at IS NOT NULL
        """,
    ),
    CronJobDefinition(
        id="update_citations",
        display_name="Update Citations",
        category="hourly",
        schedule="30 * * * * (hourly)",
        script_path="hourly/update_citations.py",
        log_name="update_citations_hourly",
        process_patterns=("update_citations",),
        lock_file="/var/lib/paperswithcode/production/cron-locks/update_citations.lock",
        expected_runtime_minutes=170,
        stale_after_minutes=120,
        critical=True,
        healthy_no_work_allowed=True,
        db_freshness_query="""
            SELECT max(citation_updated_at) AS last_write,
                   count(*) FILTER (
                     WHERE citation_updated_at > now() - interval '6 hours'
                   ) AS recent_writes
            FROM papers
        """,
    ),
    CronJobDefinition(
        id="extract_urls",
        display_name="Extract URLs",
        category="manual",
        schedule="paused (manual dispatch only; hourly schedule disabled)",
        script_path="cron-extract-urls.yml",
        log_name="extract_urls_hourly",
        process_patterns=("url_extraction_agent.database",),
        lock_file=None,
        expected_runtime_minutes=110,
        stale_after_minutes=120,
        critical=False,
        healthy_no_work_allowed=True,
        db_freshness_query="""
            SELECT max(updated_at) AS last_write,
                   count(*) FILTER (
                     WHERE urls_extracted = true
                       AND updated_at > now() - interval '24 hours'
                   ) AS recent_writes
            FROM papers
        """,
        workflow_file="cron-extract-urls.yml",
        workflow_jobs=("select", "discover", "persist"),
    ),
    CronJobDefinition(
        id="calculate_trending_scores",
        display_name="Calculate Repo Trending Scores",
        category="hourly",
        schedule="15 * * * * (hourly)",
        script_path="hourly/calculate_trending_scores.py",
        log_name="calculate_trending_scores",
        process_patterns=("calculate_trending_scores",),
        lock_file="/var/lib/paperswithcode/production/cron-locks/calculate_trending_scores.lock",
        expected_runtime_minutes=50,
        stale_after_minutes=120,
        critical=True,
        healthy_no_work_allowed=False,
        db_freshness_query="""
            SELECT max(trending_score_updated_at) AS last_write,
                   count(*) FILTER (
                     WHERE trending_score_updated_at > now() - interval '6 hours'
                   ) AS recent_writes,
                   count(*) FILTER (
                     WHERE trending_score > 0
                       AND trending_score_updated_at > now() - interval '24 hours'
                   ) AS fresh_positive_scores
            FROM repositories
        """,
    ),
    CronJobDefinition(
        id="calculate_paper_trending_scores",
        display_name="Calculate Paper Trending Scores",
        category="hourly",
        schedule="45 * * * * (hourly)",
        script_path="hourly/calculate_paper_trending_scores.py",
        log_name="calculate_paper_trending_scores",
        process_patterns=("calculate_paper_trending_scores",),
        lock_file="/var/lib/paperswithcode/production/cron-locks/calculate_paper_trending_scores.lock",
        expected_runtime_minutes=50,
        stale_after_minutes=120,
        critical=True,
        healthy_no_work_allowed=False,
        db_freshness_query="""
            SELECT max(trending_score_updated_at) AS last_write,
                   count(*) FILTER (
                     WHERE trending_score_updated_at > now() - interval '6 hours'
                   ) AS recent_writes,
                   count(*) FILTER (
                     WHERE github_trending_component > 0
                       AND trending_score_updated_at > now() - interval '24 hours'
                   ) AS fresh_github_component_scores
            FROM papers
        """,
        workflow_file="cron-calculate-paper-trending-scores.yml",
        workflow_jobs=("run",),
    ),
    CronJobDefinition(
        id="update_hf_artifacts",
        display_name="Update Hugging Face Artifacts",
        category="hourly",
        schedule="30 * * * * (hourly)",
        script_path="hourly/update_hf_artifacts.py",
        log_name="update_hf_artifacts",
        process_patterns=("update_hf_artifacts",),
        lock_file="/var/lib/paperswithcode/production/cron-locks/update_hf_artifacts.lock",
        expected_runtime_minutes=50,
        stale_after_minutes=120,
        critical=True,
        healthy_no_work_allowed=True,
        db_freshness_query="""
            SELECT GREATEST(
                     COALESCE((SELECT max(fetched_at) FROM hf_artifacts), '-infinity'::timestamp),
                     COALESCE((SELECT max(hf_artifacts_scanned_at) FROM papers), '-infinity'::timestamp),
                     COALESCE((SELECT max(created_at) FROM paper_hf_artifacts), '-infinity'::timestamp)
                   ) AS last_write,
                   (
                     SELECT count(*)
                     FROM hf_artifacts
                     WHERE fetched_at > now() - interval '6 hours'
                   ) AS recent_writes,
                   (
                     SELECT count(*)
                     FROM papers
                     WHERE hf_artifacts_scanned_at > now() - interval '6 hours'
                   ) AS papers_scanned,
                   (
                     SELECT count(*)
                     FROM paper_hf_artifacts
                     WHERE created_at > now() - interval '24 hours'
                   ) AS links_created
        """,
    ),
    CronJobDefinition(
        id="import_hf_daily_papers",
        display_name="Import HF Daily Papers",
        category="daily",
        schedule="0 * * * * (hourly)",
        script_path="daily/import_hf_daily_papers.py",
        log_name="import_hf_daily_papers",
        process_patterns=("import_hf_daily_papers",),
        lock_file=None,
        expected_runtime_minutes=110,
        stale_after_minutes=180,
        critical=True,
        healthy_no_work_allowed=True,
        db_freshness_query="""
            SELECT max(created_at) AS last_write,
                   count(*) FILTER (
                     WHERE created_at > now() - interval '36 hours'
                   ) AS recent_writes
            FROM papers
        """,
    ),
    CronJobDefinition(
        id="refresh_paper_embeddings",
        display_name="Refresh Paper Embeddings",
        category="hourly",
        schedule="15 * * * * (hourly)",
        script_path="hourly/refresh_paper_embeddings.py",
        log_name="refresh_paper_embeddings",
        process_patterns=("refresh_paper_embeddings",),
        lock_file="/var/lib/paperswithcode/production/cron-locks/refresh_paper_embeddings.lock",
        expected_runtime_minutes=20,
        stale_after_minutes=120,
        critical=True,
        healthy_no_work_allowed=True,
        db_freshness_query="""
            WITH active_generation AS (
                SELECT id
                FROM paper_embedding_generations
                WHERE status = 'active'
            )
            SELECT max(e.created_at) AS last_write,
                   count(*) FILTER (
                     WHERE e.created_at > now() - interval '6 hours'
                   ) AS recent_writes,
                   (
                     SELECT count(*)
                     FROM papers p
                     CROSS JOIN active_generation g
                     LEFT JOIN paper_embeddings missing
                       ON missing.paper_id = p.id
                      AND missing.generation_id = g.id
                     WHERE p.is_latest_version
                       AND missing.paper_id IS NULL
                   ) AS missing_embeddings
            FROM paper_embeddings e
            JOIN active_generation g ON g.id = e.generation_id
        """,
        workflow_file="cron-refresh-paper-embeddings.yml",
        workflow_jobs=("run",),
    ),
    CronJobDefinition(
        id="preload_thumbnails",
        display_name="Preload Thumbnails",
        category="daily",
        schedule="0 */3 * * *; daily 04:00–04:45 UTC",
        script_path="daily/preload_thumbnails.py",
        log_name="preload_thumbnails",
        process_patterns=("preload_thumbnails",),
        lock_file=None,
        expected_runtime_minutes=180,
        stale_after_minutes=240,
        critical=False,
        healthy_no_work_allowed=True,
        db_freshness_query=None,
        workflow_file="cron-preload-thumbnails.yml",
        workflow_jobs=("run",),
    ),
    CronJobDefinition(
        id="mirror_thumbnails_to_disk",
        display_name="Mirror Thumbnails To Disk",
        category="daily",
        schedule="0 5 * * * (daily)",
        script_path="daily/mirror_thumbnails_to_disk.py",
        log_name="mirror_thumbnails_to_disk",
        process_patterns=("mirror_thumbnails_to_disk",),
        lock_file=None,
        expected_runtime_minutes=120,
        stale_after_minutes=1560,
        critical=False,
        healthy_no_work_allowed=True,
        db_freshness_query=None,
    ),
    CronJobDefinition(
        id="link_methods_by_references",
        display_name="Link Methods By References",
        category="weekly",
        schedule="0 4 * * 0 (Sun 04:00 UTC)",
        script_path="weekly/link_methods_by_references.py",
        log_name="link_methods_by_references_weekly",
        process_patterns=("link_methods_by_references",),
        lock_file=None,
        expected_runtime_minutes=360,
        stale_after_minutes=11520,
        critical=False,
        healthy_no_work_allowed=True,
        db_freshness_query="""
            SELECT max(methods_scanned_at) AS last_write,
                   count(*) FILTER (
                     WHERE methods_scanned_at > now() - interval '8 days'
                   ) AS recent_writes
            FROM papers
        """,
    ),
    CronJobDefinition(
        id="link_papers_by_task_keywords",
        display_name="Link Papers By Task Keywords",
        category="weekly",
        schedule="0 5 * * 0 (Sun 05:00 UTC)",
        script_path="weekly/link_papers_by_task_keywords.py",
        log_name="link_papers_by_task_keywords_weekly",
        process_patterns=("link_papers_by_task_keywords",),
        lock_file=None,
        expected_runtime_minutes=360,
        stale_after_minutes=11520,
        critical=False,
        healthy_no_work_allowed=True,
        db_freshness_query=None,
    ),
)


def get_cron_job(job_id: str) -> Optional[CronJobDefinition]:
    for job in CRON_JOBS:
        if job.id == job_id:
            return job
    return None


def list_cron_jobs() -> Sequence[CronJobDefinition]:
    return CRON_JOBS
