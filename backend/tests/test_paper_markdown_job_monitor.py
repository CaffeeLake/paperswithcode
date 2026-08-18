from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from types import SimpleNamespace

from backend.services import paper_markdown_job_monitor as monitor


def test_cached_monitor_does_not_trigger_remote_collection(monkeypatch):
    monitor.clear_paper_markdown_job_monitor_cache()
    monkeypatch.setattr(
        monitor,
        "_fetch",
        lambda _settings: (_ for _ in ()).throw(AssertionError("remote fetch")),
    )

    result = monitor.get_cached_paper_markdown_job_monitor()

    assert result == {
        "available": False,
        "jobs": [],
        "summary": {},
        "error": None,
    }


def test_monitor_combines_hf_stage_with_compact_shard_progress(monkeypatch):
    settings = SimpleNamespace(
        hf_token="private-token",
        paper_markdown_hf_namespace="huggingface",
        paper_markdown_hf_bucket_id="huggingface/pwc-papers-content",
        paper_markdown_incremental_monthly_budget_usd=100.0,
        paper_markdown_backfill_budget_usd=750.0,
    )
    progress = {
        "status": "running",
        "total_papers": 500,
        "processed_papers": 123,
        "succeeded_papers": 120,
        "failed_papers": 3,
        "already_existed_papers": 0,
        "extracted_images": 87,
        "omitted_images": 2,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "error_samples": [{"arxiv_id": "2607.00001", "error": "invalid_pdf"}],
    }
    job = SimpleNamespace(
        id="job-123",
        url="https://huggingface.co/jobs/huggingface/job-123",
        status=SimpleNamespace(stage="RUNNING", message=None),
        labels={
            "app": "pwc-paper-markdown",
            "mode": "backfill",
            "run_id": "backfill-20260728T151500-a1b2c3d4",
            "shard_id": "00000",
        },
        flavor=SimpleNamespace(name="l40sx1"),
        created_at=datetime.now(timezone.utc),
        started_at=datetime.now(timezone.utc),
        finished_at=None,
        durations=SimpleNamespace(total_secs=240),
    )

    class FakeApi:
        def __init__(self, *, token):
            assert token == "private-token"

        def list_jobs(self, **kwargs):
            assert kwargs["namespace"] == "huggingface"
            assert kwargs["labels"] == {"app": "pwc-paper-markdown"}
            return iter([job])

    class FakeFileSystem:
        def __init__(self, *, token):
            assert token == "private-token"

        def open(self, path, mode, *, block_size):
            assert path.endswith(
                "_jobs/progress/backfill-20260728T151500-a1b2c3d4/00000.json"
            )
            assert mode == "rb"
            assert block_size == 0
            return io.BytesIO(json.dumps(progress).encode())

    monkeypatch.setattr(monitor, "get_settings", lambda: settings)
    monkeypatch.setattr(monitor, "HfApi", FakeApi)
    monkeypatch.setattr(monitor, "HfFileSystem", FakeFileSystem)
    monitor.clear_paper_markdown_job_monitor_cache()

    result = monitor.get_paper_markdown_job_monitor()

    assert result["available"] is True
    assert result["summary"]["active_jobs"] == 1
    assert result["summary"]["processed_papers"] == 123
    assert result["summary"]["extracted_images"] == 87
    assert result["summary"]["omitted_images"] == 2
    assert result["budgets"]["live"]["ceiling_usd"] == 100.0
    assert result["budgets"]["backfill"]["ceiling_usd"] == 750.0
    assert result["budgets"]["backfill"]["active_reserved_usd"] == 21.6
    assert result["budgets"]["backfill"]["desired_jobs"] == 3
    assert result["budgets"]["backfill"]["affordable_jobs"] == 3
    assert result["jobs"][0]["stage"] == "RUNNING"
    assert result["jobs"][0]["effective_outcome"] == "active"
    assert result["jobs"][0]["progress"]["failed_papers"] == 3
    assert result["jobs"][0]["progress"]["omitted_images"] == 2
    monitor.clear_paper_markdown_job_monitor_cache()


def test_complete_checkpoint_is_effective_success_despite_hf_error():
    progress = {
        "status": "completed",
        "total_papers": 100,
        "processed_papers": 100,
    }
    assert monitor._effective_outcome("ERROR", progress) == "success"
    assert (
        monitor._effective_outcome(
            "ERROR", {**progress, "status": "partial", "processed_papers": 80}
        )
        == "interrupted"
    )
    assert monitor._effective_outcome("ERROR", None) == "infrastructure_failure"
    assert (
        monitor._effective_outcome(
            "COMPLETED", {**progress, "status": "failed", "fatal_error": "boom"}
        )
        == "worker_failure"
    )
    assert monitor._failure_cause("interrupted", "Process exited 143", {}) == "exit_143"
    assert (
        monitor._failure_cause("infrastructure_failure", "Volume mount failed", None)
        == "volume_mount"
    )


def test_coverage_history_reports_seven_day_deltas(tmp_path, monkeypatch):
    monkeypatch.setenv("PWC_CRON_LOG_DIR", str(tmp_path))
    history = tmp_path / "paper_markdown_coverage.jsonl"
    history.write_text(
        "\n".join(
            json.dumps(row)
            for row in [
                {
                    "observed_at": "2026-08-10T00:00:00+00:00",
                    "scope": "full",
                    "eligible_papers": 100,
                    "canonical_markdown_count": 80,
                    "missing_count": 20,
                    "copied_from_upstream_count": 2,
                    "coverage_percentage": 80,
                },
                {
                    "observed_at": "2026-08-18T00:00:00+00:00",
                    "scope": "full",
                    "eligible_papers": 105,
                    "canonical_markdown_count": 90,
                    "missing_count": 15,
                    "copied_from_upstream_count": 1,
                    "coverage_percentage": 85.71,
                },
            ]
        )
        + "\n"
    )
    coverage = monitor._coverage_history(datetime(2026, 8, 18, tzinfo=timezone.utc))[
        "full"
    ]
    assert coverage["eligible_delta_7d"] == 5
    assert coverage["canonical_delta_7d"] == 10
    assert coverage["missing_delta_7d"] == -5


def test_monitor_is_unavailable_without_a_token(monkeypatch):
    settings = SimpleNamespace(
        hf_token="",
        paper_markdown_hf_namespace="huggingface",
        paper_markdown_hf_bucket_id="huggingface/pwc-papers-content",
    )
    monkeypatch.setattr(monitor, "get_settings", lambda: settings)
    monitor.clear_paper_markdown_job_monitor_cache()

    result = monitor.get_paper_markdown_job_monitor()

    assert result["available"] is False
    assert result["jobs"] == []
    assert "not configured" in result["error"]
    monitor.clear_paper_markdown_job_monitor_cache()
