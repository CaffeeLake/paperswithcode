"""Tests for the admin CRON dashboard API and health evaluation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
from unittest.mock import patch

import pytest
import yaml
from fastapi.testclient import TestClient

from backend.config import get_settings
from backend.main import create_app
from backend.services.cron_health import (
    _gh_json,
    evaluate_job_health,
    fetch_systemd_status,
    fetch_workflow_status,
)
from backend.services.cron_registry import get_cron_job, list_cron_jobs
from deploy.cron_launcher import COMMANDS


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


def test_registry_covers_workflows_systemd_and_allowlist_exactly():
    root = Path(__file__).resolve().parents[2]
    jobs = list(list_cron_jobs())
    by_id = {job.id: job for job in jobs}
    assert len(by_id) == len(jobs), "duplicate dashboard job IDs"

    scheduled_commands = set()
    workflow_owners = {}
    for path in sorted((root / ".github" / "workflows").glob("cron-*.yml")):
        document = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
        if not (document.get("on") or {}).get("schedule"):
            continue
        commands = set(re.findall(r"pwc-cron\s+([a-z0-9_]+)", path.read_text()))
        commands.discard("status")
        scheduled_commands.update(commands)
        for command in commands:
            assert command in by_id, (
                f"scheduled workflow command missing from registry: {command}"
            )
            owner = by_id[command]
            assert owner.workflow_file == path.name, (
                f"workflow ownership mismatch for {command}"
            )
            assert not (
                set(owner.workflow_jobs) - set((document.get("jobs") or {}).keys())
            )
            assert path.name not in workflow_owners, (
                f"duplicate workflow owner: {path.name}"
            )
            workflow_owners[path.name] = command

    systemd_commands = set()
    for service in sorted((root / "deploy" / "systemd").glob("pwc-*.service")):
        match = re.search(r"ExecStart=.*/pwc-cron\s+([a-z0-9_]+)", service.read_text())
        if not match:
            continue
        command = match.group(1)
        systemd_commands.add(command)
        assert command in by_id, f"systemd command missing from registry: {command}"
        assert by_id[command].systemd_service == service.name
        timer = service.with_suffix(".timer")
        assert timer.exists(), f"systemd timer missing for {command}"
        assert by_id[command].systemd_timer == timer.name

    helpers = {"extract_urls_select", "extract_urls_persist"}
    manual = {"extract_urls"}
    registered = set(by_id)
    assert set(COMMANDS) == registered | helpers
    assert manual == {job.id for job in jobs if job.scheduler == "manual"}
    assert scheduled_commands | systemd_commands == {
        job.id for job in jobs if job.scheduler != "manual"
    }


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
    assert gh_json.call_count == 2


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
        side_effect=[
            (list_payload, None),
            ([], None),
            (view_payload, None),
        ],
    ) as gh_json:
        status = fetch_workflow_status(
            "test-multi-job.yml",
            expected_jobs=("select", "discover", "persist"),
        )

    assert status["failed_jobs"] == ["persist"]
    assert gh_json.call_count == 3


def test_workflow_adapter_errors_are_sanitized():
    with patch(
        "backend.services.cron_health._gh_json",
        return_value=(None, "HTTP 401 token ghp_do_not_serialize"),
    ):
        status = fetch_workflow_status("test-sanitized-error.yml")
    assert status["available"] is False
    assert status["error"] == "GitHub Actions authentication was rejected"
    assert "ghp_do_not_serialize" not in str(status)


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
    assert "sync_tabarena" in job_ids
    assert "sync_open_asr" in job_ids
    assert "sync_deepswe" in job_ids
    assert "sync_artificial_analysis" in job_ids
    assert "sync_programbench" in job_ids
    assert "sync_frontiercode" in job_ids
    assert "sync_coarena" in job_ids
    assert "sync_arc_prize" in job_ids
    assert "calculate_organization_trending_scores" in job_ids
    assert "monitor_chat_operational_alerts" in job_ids
    assert "process_curation_thumbnails" in job_ids

    keyword_job = _job("backfill_method_keywords")
    assert "method_keyword_backfill_runs" in keyword_job.db_freshness_query
    assert "WITH current_run AS" in keyword_job.db_freshness_query
    assert "WHERE keyword_catalog_sha256 =" in keyword_job.db_freshness_query
    assert keyword_job.schedule.startswith("10 1")
    assert keyword_job.workflow_file == "cron-backfill-method-keywords.yml"
    reference_job = _job("backfill_method_references")
    assert "method_reference_backfill_months" in reference_job.db_freshness_query
    assert "WITH frontier AS" in reference_job.db_freshness_query
    assert "month_start = (SELECT month_start FROM frontier)" in (
        reference_job.db_freshness_query
    )
    assert reference_job.schedule.startswith("15 */6")
    assert reference_job.workflow_file == "cron-backfill-method-references.yml"


def test_registry_classifies_only_recurring_leaderboard_syncs():
    leaderboard_jobs = {
        job.id for job in list_cron_jobs() if job.dashboard_group == "leaderboard_sync"
    }

    assert leaderboard_jobs == {
        "sync_3d_arena",
        "sync_tabarena",
        "sync_open_asr",
        "sync_deepswe",
        "sync_artificial_analysis",
        "sync_programbench",
        "sync_frontiercode",
        "sync_coarena",
        "sync_arc_prize",
    }
    assert _job("sync_hf_organizations").dashboard_group == "operations"


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
    github_stars = _job("update_github_stars")
    thumbnails = _job("preload_thumbnails")

    assert paper_trending.workflow_file == "cron-calculate-paper-trending-scores.yml"
    assert github_stars.workflow_file == "cron-update-github-stars.yml"
    assert thumbnails.workflow_file == "cron-preload-thumbnails.yml"


def test_schedule_grace_transitions_are_deterministic():
    job = _job("update_hot_github_trending")
    log = {"status": "success_no_work", "is_running": False, "work_metrics": {}}
    db = {
        "hot_repository_count": 0,
        "recent_writes": 0,
        "oldest_eligible_wait_minutes": 0,
        "stale_paper_scores": 0,
        "one_snapshot_over_30m": 0,
    }
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        during_grace = evaluate_job_health(
            job,
            log,
            db_metrics=db,
            workflow_status={"available": True},
            now=datetime(2026, 8, 14, 12, 24, tzinfo=timezone.utc),
        )
        after_grace = evaluate_job_health(
            job,
            log,
            db_metrics=db,
            workflow_status={"available": True},
            now=datetime(2026, 8, 14, 12, 26, tzinfo=timezone.utc),
        )
    assert during_grace["execution_health"]["status"] == "degraded"
    assert after_grace["execution_health"]["status"] == "broken"


def test_failed_scheduled_run_wins_over_fresh_manual_recovery_output():
    job = _job("update_hot_github_trending")
    now = datetime(2026, 8, 14, 12, 20, tzinfo=timezone.utc)
    workflow = {
        "available": True,
        "scheduled_run": {
            "status": "completed",
            "conclusion": "failure",
            "createdAt": "2026-08-14T12:15:00Z",
            "updatedAt": "2026-08-14T12:17:00Z",
        },
        "manual_run": {
            "status": "completed",
            "conclusion": "success",
            "createdAt": "2026-08-14T12:18:00Z",
            "updatedAt": "2026-08-14T12:19:00Z",
        },
    }
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {"status": "success", "last_run": now, "is_running": False},
            db_metrics={
                "last_write": now,
                "recent_writes": 1,
                "hot_repository_count": 1,
                "oldest_eligible_wait_minutes": 0,
                "stale_paper_scores": 0,
                "one_snapshot_over_30m": 0,
            },
            workflow_status=workflow,
            now=now,
        )
    assert evaluated["execution_health"]["status"] == "broken"
    assert evaluated["output_health"]["status"] == "healthy"
    assert evaluated["status"] == "broken"


def test_unavailable_scheduler_evidence_fails_closed_to_unknown():
    job = _job("update_citations")
    now = datetime(2026, 8, 14, 12, 40, tzinfo=timezone.utc)
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {
                "status": "success",
                "last_run": now,
                "is_running": False,
                "work_metrics": {"papers_processed": 10},
            },
            db_metrics={"last_write": now, "recent_writes": 10},
            workflow_status={"available": False, "error": "permission denied"},
            now=now,
        )
    assert evaluated["execution_health"]["status"] == "unknown"
    assert evaluated["output_health"]["status"] == "healthy"
    assert evaluated["status"] == "unknown"


def test_systemd_timer_failure_and_success_are_independent_of_output():
    job = _job("monitor_chat_operational_alerts")
    now = datetime(2026, 8, 14, 12, 20, tzinfo=timezone.utc)
    common = {
        "available": True,
        "enabled": True,
        "timer_active": True,
        "service_result": "success",
        "exec_main_status": 0,
        "last_started_at": "2026-08-14T12:19:00Z",
        "last_completed_at": "2026-08-14T12:19:05Z",
        "next_trigger_at": "2026-08-14T12:20:05Z",
        "service_active": False,
    }
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        healthy = evaluate_job_health(
            job,
            {
                "status": "unknown",
                "is_running": False,
                "work_metrics": {
                    "monitor_record_available": True,
                    "monitor_status": "healthy",
                    "monitor_completed_at": "2026-08-14T12:19:05Z",
                    "undelivered_alert_events": 0,
                },
            },
            systemd_status=common,
            now=now,
        )
        disabled = evaluate_job_health(
            job,
            {
                "status": "unknown",
                "is_running": False,
                "work_metrics": {
                    "monitor_record_available": True,
                    "monitor_status": "healthy",
                    "monitor_completed_at": "2026-08-14T12:19:05Z",
                    "undelivered_alert_events": 0,
                },
            },
            systemd_status={**common, "enabled": False},
            now=now,
        )
    assert healthy["status"] == "healthy"
    assert disabled["execution_health"]["status"] == "broken"
    assert disabled["output_health"]["status"] == "healthy"
    assert disabled["status"] == "broken"


def test_systemd_adapter_reads_only_registry_units():
    responses = [
        type(
            "Result",
            (),
            {
                "returncode": 0,
                "stdout": "UnitFileState=enabled\nActiveState=active\nSubState=waiting\nLastTriggerUSec=Fri 2026-08-14 12:19:00 UTC\nNextElapseUSecRealtime=\n",
            },
        )(),
        type(
            "Result",
            (),
            {
                "returncode": 0,
                "stdout": "Result=success\nExecMainStatus=0\nActiveState=inactive\nExecMainStartTimestamp=Fri 2026-08-14 12:19:00 UTC\nExecMainExitTimestamp=Fri 2026-08-14 12:19:05 UTC\n",
            },
        )(),
    ]
    job = _job("monitor_chat_operational_alerts")
    with patch(
        "backend.services.cron_health.subprocess.run", side_effect=responses
    ) as run:
        status = fetch_systemd_status(job)
    assert status["available"] is True
    assert status["enabled"] is True
    assert status["service_result"] == "success"
    assert [call.args[0][2] for call in run.call_args_list] == [
        job.systemd_timer,
        job.systemd_service,
    ]


def test_chat_monitor_surfaces_dormant_and_undelivered_states():
    job = _job("monitor_chat_operational_alerts")
    now = datetime(2026, 8, 14, 12, 20, tzinfo=timezone.utc)
    systemd = {
        "available": True,
        "enabled": True,
        "timer_active": True,
        "service_result": "success",
        "exec_main_status": 0,
        "last_started_at": "2026-08-14T12:19:00Z",
        "last_completed_at": "2026-08-14T12:19:05Z",
        "service_active": False,
    }
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        dormant = evaluate_job_health(
            job,
            {
                "status": "unknown",
                "is_running": False,
                "work_metrics": {
                    "monitor_record_available": True,
                    "monitor_status": "dormant",
                    "monitor_completed_at": "2026-08-14T12:19:05Z",
                    "undelivered_alert_events": 0,
                },
            },
            systemd_status=systemd,
            now=now,
        )
        pending = evaluate_job_health(
            job,
            {
                "status": "unknown",
                "is_running": False,
                "work_metrics": {
                    "monitor_record_available": True,
                    "monitor_status": "degraded",
                    "monitor_completed_at": "2026-08-14T12:19:05Z",
                    "undelivered_alert_events": 2,
                },
            },
            systemd_status=systemd,
            now=now,
        )
    assert dormant["output_health"]["status"] == "healthy"
    assert "dormant" in dormant["output_health"]["reason"]
    assert pending["output_health"]["status"] == "broken"
    assert "2 operational alert" in pending["output_health"]["reason"]


def test_github_stars_health_identifies_failed_fresh_credential():
    job = _job("update_github_stars")
    recent = datetime.now(timezone.utc) - timedelta(minutes=5)
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {
                "status": "failed",
                "is_running": False,
                "work_metrics": {
                    "fresh_credential": "PWC_GITHUB_TOKEN",
                    "fresh_selected_groups": 2,
                    "fresh_successes": 0,
                    "fresh_failures": 2,
                    "fresh_credential_failures": 2,
                    "weekly_credential": (
                        "GITHUB_CLASSIC_TOKEN_AICONSULTANCYNIELSROGGE"
                    ),
                    "weekly_selected_groups": 2,
                    "weekly_successes": 2,
                    "weekly_failures": 0,
                    "weekly_credential_failures": 0,
                },
            },
            db_metrics={"last_write": recent, "recent_writes": 2},
            lock_state={"exists": False, "stale": False},
        )

    assert evaluated["status"] == "broken"
    assert "PWC_GITHUB_TOKEN was rejected" in evaluated["status_reason"]
    assert "weekly" not in evaluated["status_reason"]


def test_successful_workflow_is_health_evidence_without_logs_or_database():
    job = _job("preload_thumbnails")
    now = datetime(2026, 8, 14, 13, 1, tzinfo=timezone.utc)
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
            now=now,
        )

    assert evaluated["output_health"]["status"] == "healthy"
    assert evaluated["execution_health"]["status"] == "broken"


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
    assert evaluated["output_health"]["status"] == "healthy"
    assert evaluated["status"] == "unknown"


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
    assert evaluated["output_health"]["status"] == "healthy"
    assert evaluated["status"] == "unknown"


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
    with patch("backend.routers.cron.CronDashboardSnapshotService") as service:
        service.return_value.get_status.return_value = (
            {
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
                "snapshot_generated_at": "2026-06-25T12:00:00Z",
                "snapshot_age_seconds": 0.0,
                "snapshot_stale": False,
                "refreshing": False,
            },
            False,
        )
        response = client.get(
            "/api/v1/cron/status",
            headers={"X-Admin-Token": "test-admin-token"},
        )
    assert response.status_code == 200
    assert response.json()["summary"]["total_jobs"] == 0
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json()["snapshot_stale"] is False


def test_cron_status_schedules_stale_refresh_and_supports_force(client):
    payload = {
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
        "snapshot_generated_at": "2026-06-25T12:00:00Z",
        "snapshot_age_seconds": 61.0,
        "snapshot_stale": True,
        "refreshing": True,
    }
    with patch("backend.routers.cron.CronDashboardSnapshotService") as service:
        service.return_value.get_status.return_value = (payload, True)
        response = client.get(
            "/api/v1/cron/status?force_refresh=true",
            headers={"X-Admin-Token": "test-admin-token"},
        )

    assert response.status_code == 200
    service.return_value.get_status.assert_called_once_with(force_refresh=True)
    service.return_value.refresh_in_background.assert_called_once()


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
                "work_metrics": {"repos_updated": 0, "eligible_population": 45299},
            },
            db_metrics={
                "last_write": stale_time,
                "last_write_iso": stale_time.isoformat(),
                "recent_writes": 0,
                "eligible_population": 45299,
                "fresh_positive_scores": 0,
            },
            lock_state={"exists": False, "stale": False},
        )
        assert evaluated["status"] in {"broken", "degraded"}
        assert evaluated["status"] == "broken"
        assert "eligible population" in evaluated["status_reason"].lower()


def test_success_no_work_allowed_for_fresh_incremental_jobs():
    citations_job = _job("update_citations")
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        allowed = evaluate_job_health(
            citations_job,
            {"status": "success_no_work", "is_running": False, "work_metrics": {}},
            db_metrics={
                "last_write": datetime.now(timezone.utc) - timedelta(minutes=5),
                "recent_writes": 0,
            },
            lock_state={"exists": False, "stale": False},
        )
    assert allowed["output_health"]["status"] == "unknown"
    assert allowed["status"] == "unknown"

    trending_job = _job("calculate_trending_scores")
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        allowed_trending = evaluate_job_health(
            trending_job,
            {
                "status": "success_no_work",
                "is_running": False,
                "work_metrics": {"eligible_population": 45299},
            },
            db_metrics={
                "last_write": datetime.now(timezone.utc) - timedelta(minutes=30),
                "recent_writes": 100,
                "eligible_population": 45299,
                "fresh_positive_scores": 25,
            },
            lock_state={"exists": False, "stale": False},
        )
    assert allowed_trending["output_health"]["status"] == "healthy"


def test_trending_database_output_is_healthy_without_log_counters():
    job = _job("calculate_paper_trending_scores")
    fresh_time = datetime.now(timezone.utc) - timedelta(minutes=5)

    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {"status": "unknown", "is_running": False, "work_metrics": {}},
            db_metrics={
                "last_write": fresh_time,
                "recent_writes": 2135,
                "eligible_population": 31572,
                "fresh_github_component_scores": 1550,
            },
            lock_state={"exists": False, "stale": False},
        )

    assert evaluated["output_health"]["status"] == "healthy"
    assert "database confirms" in evaluated["output_health"]["reason"]


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
    assert evaluated["output_health"]["status"] == "healthy"
    assert evaluated["status"] == "unknown"
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
    assert evaluated["output_health"]["status"] == "running"
    assert evaluated["status"] == "unknown"


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
    assert evaluated["status"] == "healthy"
    assert evaluated["execution_health"]["scheduler"] == "manual"


def test_extract_urls_actions_unavailable_degrades_fresh_db():
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


def test_stale_successful_workflow_cannot_mask_fresh_database_writes():
    job = _job("update_citations")
    fresh_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    stale_workflow = datetime.now(timezone.utc) - timedelta(hours=3)
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {"status": "success", "last_run": fresh_time, "is_running": False},
            db_metrics={"last_write": fresh_time, "recent_writes": 10},
            lock_state={"exists": False, "stale": False},
            workflow_status={
                "available": True,
                "status": "completed",
                "conclusion": "success",
                "updated_at": stale_workflow.isoformat(),
            },
        )

    assert evaluated["status"] in {"degraded", "broken"}
    assert evaluated["execution_health"]["status"] in {"degraded", "broken"}


def test_import_hf_daily_papers_recent_log_is_healthy_without_false_db_provenance():
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

    assert evaluated["output_health"]["status"] == "healthy"
    assert evaluated["status"] == "unknown"
    assert job.db_freshness_query is None


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

    assert evaluated["output_health"]["status"] == "healthy"
    assert evaluated["status"] == "unknown"


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

    assert evaluated["output_health"]["status"] == "healthy"
    assert evaluated["status"] == "unknown"


@pytest.mark.parametrize(
    ("metrics", "expected", "reason"),
    [
        (
            {"budget_exhausted": True, "missing_after_upstream": 25},
            "degraded",
            "budget is exhausted",
        ),
        (
            {"terminal_shard_failures": 2},
            "broken",
            "remote OCR shard",
        ),
        (
            {"oldest_active_checkpoint_age_minutes": 45},
            "broken",
            "checkpoint is stale",
        ),
    ],
)
def test_paper_markdown_semantic_contract(metrics, expected, reason):
    job = _job("paper_markdown_backfill")
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {
                "status": "success",
                "last_run": datetime.now(timezone.utc),
                "is_running": False,
                "work_metrics": metrics,
            },
        )
    assert evaluated["output_health"]["status"] == expected
    assert reason in evaluated["output_health"]["reason"]


def test_embedding_no_work_is_broken_when_eligible_rows_are_missing():
    job = _job("refresh_paper_embeddings")
    now = datetime.now(timezone.utc)
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {
                "status": "success_no_work",
                "last_run": now,
                "is_running": False,
                "work_metrics": {"candidates": 0, "embeddings_updated": 0},
            },
            db_metrics={"last_write": now, "recent_writes": 0, "missing_embeddings": 8},
        )
    assert evaluated["output_health"]["status"] == "broken"
    assert "8 eligible embeddings" in evaluated["output_health"]["reason"]


def test_backfill_contract_separates_stale_run_and_provider_throttling():
    job = _job("backfill_method_references")
    now = datetime.now(timezone.utc)
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {
                "status": "success",
                "last_run": now,
                "is_running": False,
                "work_metrics": {"provider_rate_limit_hits": 3},
            },
            db_metrics={"last_write": now, "recent_writes": 1, "stale_running": 1},
        )
    assert evaluated["output_health"]["status"] == "broken"
    assert "stale database run" in evaluated["output_health"]["reason"]
    assert "provider throttled" in evaluated["output_health"]["reason"]


def test_managed_organization_snapshot_gap_degrades_output():
    job = _job("calculate_organization_trending_scores")
    now = datetime.now(timezone.utc)
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {
                "status": "success",
                "last_run": now,
                "is_running": False,
                "work_metrics": {"papers_processed": 23},
            },
            db_metrics={
                "last_write": now,
                "recent_writes": 23,
                "featured_organizations": 24,
                "missing_today_snapshots": 1,
            },
        )
    assert evaluated["output_health"]["status"] == "degraded"
    assert "managed organization" in evaluated["output_health"]["reason"]


def test_thumbnail_preload_bounded_failures_degrade_output():
    job = _job("preload_thumbnails")
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {
                "status": "success",
                "is_running": False,
                "work_metrics": {"failed_downloads": 2},
            },
            workflow_status={
                "available": True,
                "status": "completed",
                "conclusion": "success",
            },
        )
    assert evaluated["output_health"]["status"] == "degraded"
    assert "thumbnail download" in evaluated["output_health"]["reason"]
