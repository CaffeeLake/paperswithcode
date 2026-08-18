from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock

import pytest
from PIL import Image

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"
sys.path.insert(0, str(WORKFLOWS))
SCRIPT = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "scripts"
    / "hourly"
    / "backfill_paper_markdown.py"
)
SPEC = importlib.util.spec_from_file_location("backfill_paper_markdown", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
WORKER_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "generate_missing_paper_markdown.py"
)
WORKER_SPEC = importlib.util.spec_from_file_location(
    "generate_missing_paper_markdown", WORKER_SCRIPT
)
assert WORKER_SPEC and WORKER_SPEC.loader
WORKER = importlib.util.module_from_spec(WORKER_SPEC)
WORKER_SPEC.loader.exec_module(WORKER)


def test_arxiv_identity_and_markdown_key():
    assert MODULE.normalize_arxiv_id("2607.24653v2") == "2607.24653"
    assert MODULE.markdown_key("2607.24653") == "2607/2607.24653.md"
    assert MODULE.normalize_arxiv_id("hep-th/9901001") is None


def _scheduler(*, execute: bool, confirm: bool, full: bool = True):
    job = object.__new__(MODULE.PaperMarkdownBackfillJob)
    job.settings = type(
        "Settings",
        (),
        {
            "paper_markdown_backfill_concurrency": 4,
            "paper_markdown_incremental_batch_size": 100,
            "paper_markdown_backfill_batch_size": 100,
        },
    )()
    job.full = full
    job.should_execute = execute
    job.confirm = confirm
    job.max_jobs = None
    job.batch_size = None
    job.logger = Mock()
    job.budget_desired_jobs = 0
    job.budget_affordable_jobs = 0
    job.budget_projected_usd = None
    job.budget_ceiling_usd = None
    job._remote_jobs = lambda: []
    return job


def _candidates(count: int):
    return [
        {
            "arxiv_id": f"2607.{index:05d}",
            "version": "v1",
            "title": f"Paper {index}",
            "output_key": f"2607/2607.{index:05d}.md",
        }
        for index in range(count)
    ]


def test_paid_dispatch_requires_confirmation(monkeypatch):
    job = _scheduler(execute=True, confirm=False, full=False)
    monkeypatch.setattr(
        job,
        "_budget_decision",
        lambda desired, _jobs: {"affordable_jobs": desired},
    )
    with pytest.raises(ValueError, match="requires --confirm"):
        job._launch(_candidates(1))


def test_budget_exhaustion_is_a_successful_noop(monkeypatch):
    job = _scheduler(execute=True, confirm=True, full=False)
    monkeypatch.setattr(
        job, "_budget_decision", lambda _desired, _jobs: {"affordable_jobs": 0}
    )
    assert job._launch(_candidates(1)) == []


@pytest.mark.parametrize("affordable", [0, 1, 3, 4])
def test_scheduler_launches_exact_affordable_prefix(monkeypatch, affordable):
    job = _scheduler(execute=False, confirm=False)
    monkeypatch.setattr(
        job,
        "_budget_decision",
        lambda _desired, _jobs: {"affordable_jobs": affordable},
    )
    launched = job._launch(_candidates(400))
    assert len(launched) == affordable
    assert sum(int(item["papers"]) for item in launched) == affordable * 100


def test_retry_disposition_uses_persisted_fields():
    now = MODULE.datetime(2026, 8, 18, tzinfo=MODULE.UTC)
    assert (
        MODULE.status_disposition({"status": "failed", "error": "legacy"}, now=now)
        == "retryable_due"
    )
    assert (
        MODULE.status_disposition(
            {"schema_version": 2, "status": "failed", "retryable": True}, now=now
        )
        == "retryable_due"
    )
    assert (
        MODULE.status_disposition(
            {
                "schema_version": 2,
                "status": "failed",
                "retryable": True,
                "next_retry_at": "2026-08-19T00:00:00Z",
            },
            now=now,
        )
        == "retryable_deferred"
    )
    assert (
        MODULE.status_disposition(
            {
                "schema_version": 2,
                "status": "failed",
                "retryable": True,
                "attempt_count": 3,
            },
            now=now,
        )
        == "attempts_exhausted"
    )
    assert (
        MODULE.status_disposition(
            {"schema_version": 2, "status": "failed", "retryable": False},
            now=now,
        )
        == "permanent_failure"
    )


def test_chandra_worker_stub_writes_canonical_markdown_and_checkpoint(tmp_path):
    content = tmp_path / "content"
    stub = tmp_path / "stub"
    manifest = content / "_jobs" / "manifests" / "run-1" / "00000.jsonl"
    manifest.parent.mkdir(parents=True)
    stub.mkdir()
    entry = {
        "arxiv_id": "2607.24653",
        "version": "v1",
        "title": "Kimi K3",
        "output_key": "2607/2607.24653.md",
    }
    manifest.write_text(json.dumps(entry) + "\n")
    (stub / "2607.24653.md").write_text(
        "Before image.\n\n![figure](figure.webp)\n\nAfter image. " * 20
    )
    asset_dir = stub / "2607.24653"
    asset_dir.mkdir()
    image_buffer = BytesIO()
    Image.new("RGB", (16, 12), "navy").save(image_buffer, format="WEBP")
    (asset_dir / "figure.webp").write_bytes(image_buffer.getvalue())
    worker = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "generate_missing_paper_markdown.py"
    )

    subprocess.run(
        [
            sys.executable,
            str(worker),
            "--manifest",
            str(manifest),
            "--content-root",
            str(content),
            "--stub-root",
            str(stub),
        ],
        check=True,
    )

    markdown = (content / entry["output_key"]).read_text()
    assert markdown.startswith("Title: Kimi K3\n\nURL Source:")
    assert "https://paperswithcode.co/paper-assets/2607/2607.24653/images/" in markdown
    assert "figure.webp" not in markdown
    status = json.loads((content / "_jobs" / "status" / "2607.24653.json").read_text())
    assert status["status"] == "succeeded"
    assert status["schema_version"] == 2
    assert status["attempt_count"] == 1
    assert status["retryable"] is False
    assert status["model_id"] == "datalab-to/chandra-ocr-2"
    assert status["image_count"] == 1
    assert len(status["asset_keys"]) == 1
    assert (content / status["asset_keys"][0]).is_file()
    progress = json.loads(
        (content / "_jobs" / "progress" / "run-1" / "00000.json").read_text()
    )
    assert progress["status"] == "completed"
    assert progress["total_papers"] == 1
    assert progress["processed_papers"] == 1
    assert progress["succeeded_papers"] == 1
    assert progress["failed_papers"] == 0
    assert progress["extracted_images"] == 1


def _write_stub_manifest(tmp_path: Path, count: int = 2):
    content = tmp_path / "content"
    stub = tmp_path / "stub"
    manifest = content / "_jobs" / "manifests" / "run-2" / "00000.jsonl"
    manifest.parent.mkdir(parents=True)
    stub.mkdir()
    entries = _candidates(count)
    manifest.write_text("".join(json.dumps(item) + "\n" for item in entries))
    for entry in entries:
        (stub / f"{entry['arxiv_id']}.md").write_text("Valid Markdown body. " * 20)
    return content, stub, manifest, entries


def test_worker_soft_deadline_before_first_paper_is_clean_partial(tmp_path):
    content, stub, manifest, entries = _write_stub_manifest(tmp_path, 1)
    subprocess.run(
        [
            sys.executable,
            str(WORKER_SCRIPT),
            "--manifest",
            str(manifest),
            "--content-root",
            str(content),
            "--stub-root",
            str(stub),
            "--soft-deadline-seconds",
            "0",
        ],
        check=True,
    )
    progress = json.loads(
        (content / "_jobs" / "progress" / "run-2" / "00000.json").read_text()
    )
    assert progress["status"] == "partial"
    assert progress["processed_papers"] == 0
    assert not (content / entries[0]["output_key"]).exists()


def test_worker_partial_checkpoint_resumes_from_result_jsonl(tmp_path):
    content, stub, manifest, entries = _write_stub_manifest(tmp_path, 2)
    command = [
        sys.executable,
        str(WORKER_SCRIPT),
        "--manifest",
        str(manifest),
        "--content-root",
        str(content),
        "--stub-root",
        str(stub),
    ]
    subprocess.run(
        [*command, "--soft-deadline-seconds", "1", "--stub-delay-seconds", "1.1"],
        check=True,
    )
    progress_path = content / "_jobs" / "progress" / "run-2" / "00000.json"
    progress = json.loads(progress_path.read_text())
    assert progress["status"] == "partial"
    assert progress["processed_papers"] == 1

    subprocess.run([*command, "--soft-deadline-seconds", "30"], check=True)
    progress = json.loads(progress_path.read_text())
    assert progress["status"] == "completed"
    assert progress["processed_papers"] == 2
    results = (
        (content / "_jobs" / "results" / "run-2" / "00000.jsonl")
        .read_text()
        .splitlines()
    )
    assert len(results) == 2
    assert all((content / entry["output_key"]).exists() for entry in entries)


def test_worker_failure_classification_and_forced_cleanup():
    missing = ValueError("missing_extracted_image:figure.webp")
    assert WORKER.classify_failure(missing, 1) == ("missing_extracted_image", True)
    assert WORKER.classify_failure(missing, 3) == ("missing_extracted_image", False)
    assert WORKER.classify_failure(ValueError("immutable_asset_conflict:key"), 1) == (
        "immutable_asset_conflict",
        False,
    )

    class StubbornProcess:
        def __init__(self):
            self.killed = False
            self.waits = 0

        def poll(self):
            return None

        def terminate(self):
            return None

        def wait(self, timeout):
            self.waits += 1
            if self.waits == 1:
                raise subprocess.TimeoutExpired("vllm", timeout)
            return 0

        def kill(self):
            self.killed = True

    process = StubbornProcess()
    assert WORKER.stop_vllm(process) == "killed"
    assert process.killed is True
