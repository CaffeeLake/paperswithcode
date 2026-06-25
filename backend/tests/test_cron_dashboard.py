"""Tests for the admin CRON dashboard API and health evaluation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.config import get_settings
from backend.main import create_app
from backend.services.cron_health import evaluate_job_health
from backend.services.cron_registry import get_cron_job


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


def test_log_success_with_stale_db_is_broken_for_critical_writer():
    job = _job("calculate_trending_scores")
    stale_time = datetime.now(timezone.utc) - timedelta(hours=8)
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


def test_stale_lock_without_process_is_broken():
    job = _job("update_github_stars")
    evaluated = evaluate_job_health(
        job,
        {"status": "unknown", "is_running": False, "work_metrics": {}},
        db_metrics={
            "last_write": datetime.now(timezone.utc) - timedelta(hours=1),
            "recent_writes": 10,
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
