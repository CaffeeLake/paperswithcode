"""Tests for the admin CRON dashboard API and health evaluation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.config import get_settings
from backend.main import create_app
from backend.services.cron_health import (
    _gh_json,
    evaluate_job_health,
    fetch_workflow_status,
)
from backend.services.cron_registry import get_cron_job, list_cron_jobs


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PWC_ADMIN_API_TOKEN", "test-admin-token")
    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


def _job(job_id: str):
    job = get_cron_job(job_id)
    assert job is not None
    return job


def test_gh_json_uses_configured_token_and_explicit_repository(monkeypatch):
    monkeypatch.setenv("PWC_GITHUB_TOKEN", "test-github-token")
    get_settings.cache_clear()
    completed = type(
        "CompletedProcess",
        (),
        {"returncode": 0, "stdout": "[]", "stderr": ""},
    )()

    with patch(
        "backend.services.cron_health.subprocess.run", return_value=completed
    ) as run:
        payload, error = _gh_json(["run", "list"])

    assert payload == []
    assert error is None
    command = run.call_args.args[0]
    environment = run.call_args.kwargs["env"]
    assert command == ["gh", "run", "list"]
    assert run.call_args.kwargs["check"] is False
    assert "test-github-token" not in command
    assert environment["GH_TOKEN"] == "test-github-token"
    assert environment["GH_REPO"] == "huggingface/paperswithcode"
    get_settings.cache_clear()


def test_single_job_workflow_does_not_fetch_job_details():
    list_payload = [
        {
            "databaseId": 123,
            "status": "completed",
            "conclusion": "success",
            "updatedAt": "2026-07-28T15:00:00Z",
        }
    ]

    with patch(
        "backend.services.cron_health._gh_json",
        return_value=(list_payload, None),
    ) as gh_json:
        status = fetch_workflow_status(
            "test-single-job.yml",
            expected_jobs=("run",),
        )

    assert status["available"] is True
    assert status["conclusion"] == "success"
    assert status["updated_at"] == "2026-07-28T15:00:00Z"
    gh_json.assert_called_once()


def test_multi_job_workflow_fetches_job_details():
    list_payload = [
        {
            "databaseId": 456,
            "status": "completed",
            "conclusion": "failure",
        }
    ]
    view_payload = {
        "jobs": [
            {"name": "select", "status": "completed", "conclusion": "success"},
            {"name": "persist", "status": "completed", "conclusion": "failure"},
        ]
    }

    with patch(
        "backend.services.cron_health._gh_json",
        side_effect=[(list_payload, None), (view_payload, None)],
    ) as gh_json:
        status = fetch_workflow_status(
            "test-multi-job.yml",
            expected_jobs=("select", "discover", "persist"),
        )

    assert status["failed_jobs"] == ["persist"]
    assert gh_json.call_count == 2


def test_registry_includes_hf_artifacts_embeddings_and_method_backfills():
    job_ids = {job.id for job in list_cron_jobs()}
    assert "update_hot_github_trending" in job_ids
    assert "update_hf_artifacts" in job_ids
    assert "refresh_paper_embeddings" in job_ids
    assert "paper_markdown_backfill" in job_ids
    assert "backfill_method_keywords" in job_ids
    assert "backfill_method_references" in job_ids
    assert "sync_hf_organizations" in job_ids
    assert "sync_3d_arena" in job_ids
    assert "sync_open_asr" in job_ids
    assert "calculate_organization_trending_scores" in job_ids
    assert len(job_ids) == 20

    keyword_job = _job("backfill_method_keywords")
    assert "method_keyword_backfill_runs" in keyword_job.db_freshness_query
    assert keyword_job.schedule.startswith("10 1")
    assert keyword_job.workflow_file == "cron-backfill-method-keywords.yml"
    reference_job = _job("backfill_method_references")
    assert "method_reference_backfill_months" in reference_job.db_freshness_query
    assert reference_job.schedule.startswith("15 */6")
    assert reference_job.workflow_file == "cron-backfill-method-references.yml"


def test_hot_job_has_dedicated_lock_and_operational_metrics():
    job = _job("update_hot_github_trending")
    assert job.schedule.startswith("*/15")
    assert job.category == "hourly"
    assert job.critical is False
    assert job.lock_file.endswith("/update_hot_github_trending.lock")
    assert "one_snapshot_over_30m" in job.db_freshness_query
    assert "stale_paper_scores" in job.db_freshness_query
    assert "r.trending_score > 0" in job.db_freshness_query
    assert "r.trending_score IS NOT NULL" not in job.db_freshness_query
    assert "COALESCE(r.owner, '') != ''" in job.db_freshness_query
    assert "COALESCE(r.name, '') != ''" in job.db_freshness_query
    assert "p.date_published >= CURRENT_DATE - INTERVAL '365 days'" in (
        job.db_freshness_query
    )
    assert job.workflow_file == "cron-update-hot-github-trending.yml"


def test_action_backed_jobs_expose_workflow_health():
    paper_trending = _job("calculate_paper_trending_scores")
    thumbnails = _job("preload_thumbnails")

    assert paper_trending.workflow_file == "cron-calculate-paper-trending-scores.yml"
    assert thumbnails.workflow_file == "cron-preload-thumbnails.yml"


def test_successful_workflow_is_health_evidence_without_logs_or_database():
    job = _job("preload_thumbnails")
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {"status": "unknown", "is_running": False},
            db_metrics={},
            workflow_status={
                "available": True,
                "status": "completed",
                "conclusion": "success",
            },
            lock_state={"exists": False, "stale": False},
        )

    assert evaluated["status"] == "healthy"
    assert evaluated["status_reason"] == "latest GitHub Actions workflow succeeded"


def test_hot_health_allows_recent_no_work_when_population_is_empty():
    job = _job("update_hot_github_trending")
    recent = datetime.now(timezone.utc) - timedelta(minutes=5)
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {
                "status": "success_no_work",
                "last_run": recent,
                "is_running": False,
                "work_metrics": {"repositories_processed": 0},
            },
            db_metrics={
                "last_write": None,
                "recent_writes": 0,
                "hot_repository_count": 0,
                "one_snapshot_over_30m": 0,
                "stale_paper_scores": 0,
                "oldest_eligible_wait_minutes": 0,
            },
            lock_state={"exists": False, "stale": False},
        )
    assert evaluated["status"] == "healthy"


def test_hot_zero_seed_does_not_mark_paper_propagation_stale():
    job = _job("update_hot_github_trending")
    recent = datetime.now(timezone.utc) - timedelta(minutes=5)
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {
                "status": "success",
                "last_run": recent,
                "is_running": False,
                "work_metrics": {},
            },
            db_metrics={
                "last_write": recent,
                "recent_writes": 1,
                "hot_repository_count": 1,
                "one_snapshot_over_30m": 0,
                # The SQL excludes the repository's one-snapshot 0.0 seed.
                "stale_paper_scores": 0,
                "oldest_eligible_wait_minutes": 0,
            },
            lock_state={"exists": False, "stale": False},
        )
    assert evaluated["status"] == "healthy"


def test_hot_health_alerts_on_rate_reserve_violation():
    job = _job("update_hot_github_trending")
    recent = datetime.now(timezone.utc) - timedelta(minutes=5)
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {
                "status": "success",
                "last_run": recent,
                "is_running": False,
                "work_metrics": {
                    "rate_limit_remaining": 499,
                    "rate_limit_reserve": 500,
                },
            },
            db_metrics={
                "last_write": recent,
                "recent_writes": 1,
                "hot_repository_count": 1,
                "one_snapshot_over_30m": 0,
                "stale_paper_scores": 0,
                "oldest_eligible_wait_minutes": 0,
            },
            lock_state={"exists": False, "stale": False},
        )
    assert evaluated["status"] == "broken"
    assert "reserve violated" in evaluated["status_reason"]


def test_cron_status_requires_admin(client):
    response = client.get("/api/v1/cron/status")
    assert response.status_code == 401


def test_cron_status_accepts_admin_token(client):
    with patch("backend.routers.cron.build_cron_dashboard") as build_dashboard:
        build_dashboard.return_value = {
            "timestamp": "2026-06-25T12:00:00Z",
            "jobs": [],
            "summary": {
                "total_jobs": 0,
                "healthy": 0,
                "degraded": 0,
                "broken": 0,
                "running": 0,
                "stuck": 0,
                "unknown": 0,
                "health_score": 0,
                "critical_issues": [],
                "what_to_check_next": "All monitored jobs look healthy",
            },
        }
        response = client.get(
            "/api/v1/cron/status",
            headers={"X-Admin-Token": "test-admin-token"},
        )
    assert response.status_code == 200
    assert response.json()["summary"]["total_jobs"] == 0


def test_paper_markdown_jobs_requires_admin(client):
    response = client.get("/api/v1/cron/paper-markdown-jobs")
    assert response.status_code == 401


def test_paper_markdown_jobs_returns_remote_snapshot(client):
    payload = {
        "available": True,
        "namespace": "huggingface",
        "updated_at": "2026-07-28T15:20:00Z",
        "jobs": [{"id": "job-123", "stage": "RUNNING"}],
        "summary": {"active_jobs": 1},
        "error": None,
    }
    with patch(
        "backend.routers.cron.get_paper_markdown_job_monitor",
        return_value=payload,
    ):
        response = client.get(
            "/api/v1/cron/paper-markdown-jobs",
            headers={"X-Admin-Token": "test-admin-token"},
        )

    assert response.status_code == 200
    assert response.json()["jobs"][0]["id"] == "job-123"
    assert response.json()["summary"]["active_jobs"] == 1


def test_log_success_with_stale_db_is_broken_for_critical_writer():
    job = _job("calculate_trending_scores")
    stale_time = datetime.now(timezone.utc) - timedelta(hours=8)
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {
                "status": "success_no_work",
                "last_run": "2026-06-25 10:00:00",
                "is_running": False,
                "work_metrics": {"repos_updated": 0},
            },
            db_metrics={
                "last_write": stale_time,
                "last_write_iso": stale_time.isoformat(),
                "recent_writes": 0,
                "fresh_positive_scores": 0,
            },
            lock_state={"exists": False, "stale": False},
        )
        assert evaluated["status"] in {"broken", "degraded"}
        assert evaluated["status"] == "broken"
        assert "database" in evaluated["status_reason"].lower()


def test_success_no_work_allowed_only_for_explicit_jobs():
    citations_job = _job("update_citations")
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        allowed = evaluate_job_health(
            citations_job,
            {"status": "success_no_work", "is_running": False, "work_metrics": {}},
            db_metrics={
                "last_write": datetime.now(timezone.utc) - timedelta(minutes=30),
                "recent_writes": 0,
            },
            lock_state={"exists": False, "stale": False},
        )
    assert allowed["status"] == "healthy"

    trending_job = _job("calculate_trending_scores")
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        not_allowed = evaluate_job_health(
            trending_job,
            {"status": "success_no_work", "is_running": False, "work_metrics": {}},
            db_metrics={
                "last_write": datetime.now(timezone.utc) - timedelta(minutes=30),
                "recent_writes": 0,
                "fresh_positive_scores": 0,
            },
            lock_state={"exists": False, "stale": False},
        )
    assert not_allowed["status"] in {"degraded", "broken"}


def test_stale_lock_with_fresh_db_is_healthy():
    job = _job("update_github_stars")
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {"status": "unknown", "is_running": False, "work_metrics": {}},
            db_metrics={
                "last_write": datetime.now(timezone.utc) - timedelta(hours=1),
                "last_write_iso": (
                    datetime.now(timezone.utc) - timedelta(hours=1)
                ).isoformat(),
                "recent_writes": 10,
            },
            lock_state={
                "exists": True,
                "stale": True,
                "age_minutes": 120,
                "path": "/tmp/github_stars.lock",
            },
        )
    assert evaluated["status"] == "healthy"
    assert evaluated["lock_stale"] is True


def test_stale_lock_with_stale_db_is_broken():
    job = _job("update_github_stars")
    stale_time = datetime.now(timezone.utc) - timedelta(hours=8)
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {"status": "unknown", "is_running": False, "work_metrics": {}},
            db_metrics={
                "last_write": stale_time,
                "last_write_iso": stale_time.isoformat(),
                "recent_writes": 0,
            },
            lock_state={
                "exists": True,
                "stale": True,
                "age_minutes": 120,
                "path": "/tmp/github_stars.lock",
            },
        )
    assert evaluated["status"] == "broken"
    assert evaluated["lock_stale"] is True


def test_running_process_within_expected_runtime():
    job = _job("calculate_trending_scores")
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {
                "status": "running",
                "last_run": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                "is_running": True,
                "work_metrics": {},
            },
            db_metrics={
                "last_write": datetime.now(timezone.utc) - timedelta(minutes=20),
                "recent_writes": 100,
            },
            lock_state={"exists": True, "stale": False},
        )
    assert evaluated["status"] == "running"


def test_extract_urls_actions_failure_degrades_fresh_writer():
    job = _job("extract_urls")
    fresh_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {
                "status": "success",
                "last_run": fresh_time.strftime("%Y-%m-%d %H:%M:%S"),
                "is_running": False,
                "work_metrics": {"papers_processed": 53},
            },
            db_metrics={
                "last_write": fresh_time,
                "last_write_iso": fresh_time.isoformat(),
                "recent_writes": 1200,
            },
            lock_state={"exists": False, "stale": False},
            workflow_status={
                "available": True,
                "workflow_file": "cron-extract-urls.yml",
                "run_id": 123,
                "status": "completed",
                "conclusion": "failure",
                "failed_jobs": ["persist"],
            },
        )
    assert evaluated["status"] == "degraded"
    assert "GitHub Actions workflow failed (persist)" in evaluated["status_reason"]
    assert "gh run view 123 --log-failed" in evaluated["diagnostics"]


def test_extract_urls_actions_unavailable_does_not_override_fresh_db():
    job = _job("extract_urls")
    fresh_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {
                "status": "success",
                "last_run": fresh_time.strftime("%Y-%m-%d %H:%M:%S"),
                "is_running": False,
                "work_metrics": {"papers_processed": 53},
            },
            db_metrics={
                "last_write": fresh_time,
                "last_write_iso": fresh_time.isoformat(),
                "recent_writes": 1200,
            },
            lock_state={"exists": False, "stale": False},
            workflow_status={
                "available": False,
                "workflow_file": "cron-extract-urls.yml",
                "error": "gh is not authenticated",
            },
        )
    assert evaluated["status"] == "healthy"
    assert evaluated["workflow_status"]["available"] is False


def test_import_hf_daily_papers_recent_no_work_log_is_healthy_with_stale_created_at():
    job = _job("import_hf_daily_papers")
    stale_time = datetime.now(timezone.utc) - timedelta(hours=9)
    recent_log_time = datetime.now(timezone.utc) - timedelta(minutes=15)
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {
                "status": "success",
                "last_run": recent_log_time.strftime("%Y-%m-%d %H:%M:%S"),
                "is_running": False,
                "work_metrics": {"papers_processed": 0},
            },
            db_metrics={
                "last_write": stale_time,
                "last_write_iso": stale_time.isoformat(),
                "recent_writes": 0,
            },
            lock_state={"exists": False, "stale": False},
        )

    assert evaluated["status"] == "healthy"
    assert "no new papers imported" in evaluated["status_reason"]


def test_recent_weekly_task_keyword_log_is_healthy_without_db_timestamp():
    job = _job("link_papers_by_task_keywords")
    recent_log_time = datetime.now(timezone.utc) - timedelta(days=6)
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {
                "status": "success",
                "last_run": recent_log_time.strftime("%Y-%m-%d %H:%M:%S"),
                "is_running": False,
                "work_metrics": {"papers_processed": 100},
            },
            db_metrics={},
            lock_state={"exists": False, "stale": False},
        )

    assert evaluated["status"] == "healthy"


def test_hf_artifacts_fresh_db_metrics_are_healthy():
    job = _job("update_hf_artifacts")
    fresh_time = datetime.now(timezone.utc) - timedelta(minutes=20)
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {
                "status": "success",
                "last_run": fresh_time.strftime("%Y-%m-%d %H:%M:%S"),
                "is_running": False,
                "work_metrics": {"papers_processed": 50},
            },
            db_metrics={
                "last_write": fresh_time,
                "last_write_iso": fresh_time.isoformat(),
                "recent_writes": 30,
                "papers_scanned": 50,
                "links_created": 2,
            },
            lock_state={"exists": False, "stale": False},
        )

    assert evaluated["status"] == "healthy"
