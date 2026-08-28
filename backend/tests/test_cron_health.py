from __future__ import annotations

import json
from datetime import UTC, datetime

from backend.config import get_settings
from backend.services.autonomous_cron_probe import (
    FindingState,
    build_job_findings,
)
from backend.services.cron_health import (
    evaluate_job_health,
    fetch_submission_review_output,
)
from backend.services.cron_registry import get_cron_job


NOW = datetime(2026, 8, 28, 12, 15, tzinfo=UTC)


def test_submission_review_uses_content_free_health_record(monkeypatch, tmp_path):
    record = tmp_path / "autonomous-submission-review-health.json"
    record.write_text(
        json.dumps(
            {
                "status": "healthy",
                "completed_at": "2026-08-28T12:10:00Z",
                "claimed": 3,
                "dry_run": False,
                "remote_launch": True,
            }
        )
    )
    monkeypatch.setenv("PWC_CRON_LOG_DIR", str(tmp_path))
    get_settings.cache_clear()
    try:
        metrics = fetch_submission_review_output()
    finally:
        get_settings.cache_clear()

    assert metrics == {
        "review_record_available": True,
        "review_status": "healthy",
        "review_completed_at": "2026-08-28T12:10:00Z",
        "submissions_claimed": 3,
        "review_dry_run": False,
        "review_remote_launch": True,
        "review_error_class": None,
    }


def test_systemd_health_record_satisfies_independent_probe_contracts():
    job = get_cron_job("review_submissions")
    assert job is not None
    systemd = {
        "available": True,
        "enabled": True,
        "timer_active": True,
        "service_result": "success",
        "last_started_at": "2026-08-28T12:05:00Z",
        "last_completed_at": "2026-08-28T12:05:10Z",
    }
    evaluated = evaluate_job_health(
        job,
        {
            "status": "unknown",
            "last_run": "2026-08-28T12:05:00Z",
            "is_running": False,
            "work_metrics": {
                "review_record_available": True,
                "review_status": "healthy",
                "review_completed_at": "2026-08-28T12:05:10Z",
                "submissions_claimed": 0,
            },
        },
        lock_state={"exists": False, "held": False, "stale": False},
        systemd_status=systemd,
        process_running=False,
        now=NOW,
    )
    findings = build_job_findings(job, evaluated, NOW)

    assert {finding.state for finding in findings} == {FindingState.HEALTHY}
    assert job.evidence_contract.log_source == "health_record"
    assert job.evidence_contract.throughput_source == "health_record"
    assert job.evidence_contract.semantic_source == "health_record"


def test_database_telemetry_loss_never_asserts_cross_plane_failures():
    job = get_cron_job("update_citations")
    assert job is not None
    payload = {
        "job_name": job.id,
        "status": "broken",
        "log_status": "success",
        "last_run": "2026-08-28T12:05:00Z",
        "is_running": False,
        "execution_health": {"status": "healthy", "reason": "ran"},
        "output_health": {
            "status": "broken",
            "reason": "database freshness query failed",
        },
        "lock_state": {"exists": False, "held": False, "stale": False},
        "workflow_status": {"available": True, "run_id": 1},
        "db_metrics": {"freshness_error": "database freshness unavailable"},
        "work_metrics": {"papers_processed": 10},
    }

    findings = build_job_findings(job, payload, NOW)
    by_contract = {finding.contract: finding.state for finding in findings}

    assert by_contract["durable_data_freshness"] is FindingState.UNKNOWN
    assert by_contract["throughput_backlog"] is FindingState.UNKNOWN
    assert by_contract["semantic_correctness"] is FindingState.UNKNOWN


def test_trending_semantic_failure_uses_typed_evaluator_outcome():
    job = get_cron_job("calculate_trending_scores")
    assert job is not None
    evaluated = evaluate_job_health(
        job,
        {
            "status": "success",
            "last_run": "2026-08-28T12:16:00Z",
            "is_running": False,
            "work_metrics": {"repositories_processed": 20},
        },
        db_metrics={
            "last_write": NOW,
            "last_write_iso": "2026-08-28T12:15:00Z",
            "recent_writes": 20,
            "eligible_population": 20,
            "fresh_positive_scores": 0,
        },
        lock_state={"exists": False, "held": False, "stale": False},
        workflow_status={
            "available": True,
            "run_id": 4,
            "status": "completed",
            "conclusion": "success",
        },
        process_running=False,
        now=NOW,
    )
    findings = build_job_findings(job, evaluated, NOW)
    by_contract = {finding.contract: finding.state for finding in findings}

    assert by_contract["durable_data_freshness"] is FindingState.HEALTHY
    assert by_contract["throughput_backlog"] is FindingState.HEALTHY
    assert by_contract["semantic_correctness"] is FindingState.DEGRADED
