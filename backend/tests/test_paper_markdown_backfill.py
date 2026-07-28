from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

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


def test_arxiv_identity_and_markdown_key():
    assert MODULE.normalize_arxiv_id("2607.24653v2") == "2607.24653"
    assert MODULE.markdown_key("2607.24653") == "2607/2607.24653.md"
    assert MODULE.normalize_arxiv_id("hep-th/9901001") is None


def test_paid_dispatch_requires_confirmation(monkeypatch):
    job = object.__new__(MODULE.PaperMarkdownBackfillJob)
    job.settings = type(
        "Settings",
        (),
        {
            "paper_markdown_backfill_concurrency": 4,
            "paper_markdown_incremental_batch_size": 100,
            "paper_markdown_backfill_batch_size": 500,
        },
    )()
    job.full = False
    job.should_execute = True
    job.confirm = False
    job.max_jobs = None
    monkeypatch.setattr(job, "_active_jobs", list)
    with pytest.raises(ValueError, match="requires --confirm"):
        job._launch(
            [
                {
                    "arxiv_id": "2607.24653",
                    "version": "v1",
                    "title": "Kimi K3",
                    "output_key": "2607/2607.24653.md",
                }
            ]
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
    (stub / "2607.24653.md").write_text("OCR body " * 30)
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
    status = json.loads((content / "_jobs" / "status" / "2607.24653.json").read_text())
    assert status["status"] == "succeeded"
