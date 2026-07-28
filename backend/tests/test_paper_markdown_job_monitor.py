from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from types import SimpleNamespace

from backend.services import paper_markdown_job_monitor as monitor


def test_monitor_combines_hf_stage_with_compact_shard_progress(monkeypatch):
    settings = SimpleNamespace(
        hf_token="private-token",
        paper_markdown_hf_namespace="huggingface",
        paper_markdown_hf_bucket_id="huggingface/pwc-papers-content",
    )
    progress = {
        "status": "running",
        "total_papers": 500,
        "processed_papers": 123,
        "succeeded_papers": 120,
        "failed_papers": 3,
        "already_existed_papers": 0,
        "extracted_images": 87,
        "updated_at": "2026-07-28T15:20:00Z",
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
        created_at=datetime(2026, 7, 28, 15, 15, tzinfo=timezone.utc),
        started_at=datetime(2026, 7, 28, 15, 16, tzinfo=timezone.utc),
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
    assert result["jobs"][0]["stage"] == "RUNNING"
    assert result["jobs"][0]["progress"]["failed_papers"] == 3
    monitor.clear_paper_markdown_job_monitor_cache()


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
