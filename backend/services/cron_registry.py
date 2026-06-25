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


CRON_JOBS: Tuple[CronJobDefinition, ...] = (
    CronJobDefinition(
        id="update_github_stars",
        display_name="Update GitHub Stars",
        category="hourly",
        schedule="0 * * * * (hourly)",
        script_path="hourly/update_github_stars.py",
        log_name="github_stars_cron",
        process_patterns=("update_github_stars", "github_stars"),
        lock_file="/tmp/github_stars.lock",
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
        lock_file="/tmp/citations.lock",
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
        category="hourly",
        schedule="45 * * * * (hourly)",
        script_path="hourly/extract_urls.py",
        log_name="extract_urls_hourly",
        process_patterns=("extract_urls",),
        lock_file="/tmp/extract_urls.lock",
        expected_runtime_minutes=110,
        stale_after_minutes=120,
        critical=True,
        healthy_no_work_allowed=True,
        db_freshness_query="""
            SELECT max(updated_at) AS last_write,
                   count(*) FILTER (
                     WHERE urls_extracted = true
                       AND updated_at > now() - interval '24 hours'
                   ) AS recent_writes
            FROM papers
        """,
    ),
    CronJobDefinition(
        id="calculate_trending_scores",
        display_name="Calculate Repo Trending Scores",
        category="hourly",
        schedule="15 * * * * (hourly)",
        script_path="hourly/calculate_trending_scores.py",
        log_name="calculate_trending_scores",
        process_patterns=("calculate_trending_scores",),
        lock_file="/tmp/trending_scores.lock",
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
        lock_file="/tmp/paper_trending_scores.lock",
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
        db_freshness_query="""
            SELECT max(pt.created_at) AS last_write,
                   count(*) FILTER (
                     WHERE pt.created_at > now() - interval '8 days'
                   ) AS recent_writes
            FROM paper_tasks pt
            WHERE pt.source = 'auto'
        """,
    ),
)


def get_cron_job(job_id: str) -> Optional[CronJobDefinition]:
    for job in CRON_JOBS:
        if job.id == job_id:
            return job
    return None


def list_cron_jobs() -> Sequence[CronJobDefinition]:
    return CRON_JOBS
