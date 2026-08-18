from __future__ import annotations

import base64
import gzip
import json
import uuid
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from backend.config import get_settings
from backend.services.benchmark_gap_service import BenchmarkGapService
from backend.services.codex_add_evals_service import CodexPaperJobService
from backend.services.curation_trace_service import CurationTraceService, redact_trace
from jobs import url_preflight


class _HeadResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def _context(*, project_page: bool = True) -> dict:
    return {
        "paper": {
            "id": 42,
            "arxiv_id": "2608.00042",
            "abstract": "A paper without inline links.",
            "repositories": [
                {
                    "url": "https://github.com/example/project",
                    "is_official": True,
                    "source": "hf_api",
                }
            ],
            "project_pages": (
                [
                    {
                        "url": "https://example.github.io/project",
                        "is_official": True,
                        "source": "hf_api",
                    }
                ]
                if project_page
                else []
            ),
        }
    }


def test_url_patterns_are_the_authoritative_design_patterns():
    assert url_preflight.GITHUB_URL_PATTERN == r"\bhttps?:\/\/github\.com[^\s]*\b"
    assert (
        url_preflight.PROJECT_PAGE_URL_PATTERN
        == r"\bhttps?:\/\/[^\s\/]+\.github\.io[^\s]*\b"
    )


def test_preflight_reuses_complete_importer_links_without_refetching_layers(
    monkeypatch,
):
    monkeypatch.setattr(
        url_preflight.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _HeadResponse(),
    )

    def unexpected_fetch(*_args):
        raise AssertionError(
            "complete stored HF metadata must skip HF Markdown and PDF"
        )

    result = url_preflight.extract_candidates(_context(), fetch=unexpected_fetch)

    assert result["complete"] is True
    assert {item["kind"] for item in result["candidates"]} == {"github", "project_page"}
    assert all("hf_api" in item["source_layers"][0] for item in result["candidates"])


def test_preflight_fetches_only_missing_metadata_layer_when_hf_detail_completes_it(
    monkeypatch,
):
    monkeypatch.setattr(
        url_preflight.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _HeadResponse(),
    )
    fetched = []

    def fetch(url: str, _limit: int):
        fetched.append(url)
        assert "/api/papers/" in url
        return json.dumps(
            {
                "githubRepo": "https://github.com/example/project",
                "projectPage": "https://example.github.io/project",
            }
        ).encode(), url

    result = url_preflight.extract_candidates(_context(project_page=False), fetch=fetch)

    assert result["complete"] is True
    assert fetched == ["https://huggingface.co/api/papers/2608.00042"]
    assert result["sources"][0]["sha256"]


def test_trace_redaction_removes_planted_credentials():
    redacted = redact_trace(
        b"Authorization: Bearer-secret\nOPENAI_API_KEY=sk-exampleexampleexample\nhf-exampleexampleexample"
    ).decode()

    assert "Bearer-secret" not in redacted
    assert "sk-example" not in redacted
    assert "hf-example" not in redacted
    assert redacted.count("<redacted>") >= 3


def test_checked_in_proposal_schema_requires_benchmark_gaps():
    schema = json.loads(Path("jobs/schemas/curation_proposal.schema.json").read_text())
    assert "benchmark_gaps" in schema["required"]
    assert "evaluation_removals" in schema["required"]
    assert "validation_evidence" in schema["required"]
    assert (
        schema["properties"]["benchmark_gaps"]["items"]["properties"]["reasoning"][
            "maxLength"
        ]
        == 2000
    )


def test_daily_schedule_avoids_the_organization_sync_minute():
    workflow = Path(
        ".github/workflows/cron-enqueue-hf-daily-paper-curation.yml"
    ).read_text()
    assert 'cron: "27 2 * * *"' in workflow
    assert 'cron: "20 2 * * *"' not in workflow


class _DispatchQuery:
    def __init__(self, database):
        self.database = database

    def join(self, *_args):
        return self

    def filter(self, *_args):
        return self

    def order_by(self, *args):
        self.database.orderings.append([str(value) for value in args])
        return self

    def first(self):
        return self.database.first_results.pop(0)


class _DispatchDatabase:
    def __init__(self, *first_results):
        self.first_results = list(first_results)
        self.orderings = []

    def query(self, *_args):
        return _DispatchQuery(self)


def test_overdue_dispatch_reserves_only_one_slot_before_newest_first():
    oldest_overdue = object()
    newest = object()
    first_slot = _DispatchDatabase(None, oldest_overdue)
    remaining_slot = _DispatchDatabase(object(), newest)

    assert CodexPaperJobService._next_scheduled_row(first_slot) is oldest_overdue
    assert CodexPaperJobService._next_scheduled_row(remaining_slot) is newest
    assert any(
        "cohort_order" in value
        for ordering in remaining_slot.orderings
        for value in ordering
    )


def test_newest_first_fallback_when_no_overdue_workflow_exists():
    newest = object()
    database = _DispatchDatabase(None, None, newest)

    assert CodexPaperJobService._next_scheduled_row(database) is newest


def test_benchmark_gap_validation_isolates_malformed_entries():
    class Database:
        def get(self, _model, task_id):
            return SimpleNamespace(id=task_id)

    valid = {
        "reasoning": "A reusable public benchmark blocks a paper-native result.",
        "gap_type": "dataset_missing",
        "proposed_benchmark": {
            "name": "ExampleBench",
            "aliases": ["Example Bench"],
            "task_candidates": [{"task_id": 19}],
            "canonical_sources": [{"url": "https://example.org/benchmark"}],
        },
        "blocked_evaluations": [{"model_name": "Introduced Model"}],
        "evidence": [{"source_kind": "paper_pdf", "page": 7}],
        "catalog_search": {"queries": ["ExampleBench"]},
    }

    accepted, rejected = BenchmarkGapService(Database()).validate(
        [valid, {"gap_type": "dataset_missing"}]
    )

    assert len(accepted) == 1
    assert accepted[0]["_normalized"]["task_ids"] == [19]
    assert rejected == [{"index": 1, "error": "reasoning is required"}]


def test_trace_bundle_manifest_hashes_every_uploaded_object(tmp_path):
    class Database:
        def commit(self):
            pass

        def get(self, *_args):
            return None

    class Hub:
        def __init__(self):
            self.objects = {}

        def create_bucket(self, *_args, **_kwargs):
            pass

        def batch_bucket_files(self, _bucket, *, add):
            self.objects.update({path: data for data, path in add})

    settings = get_settings().model_copy(
        update={
            "codex_curation_trace_upload_enabled": True,
            "codex_curation_trace_hf_bucket_id": "example/curate-papers-traces",
            "codex_add_evals_spool_dir": str(tmp_path),
        }
    )
    row = SimpleNamespace(
        id=uuid.uuid4(),
        paper_id=42,
        cohort_date=date(2026, 8, 18),
        policy_version="hf-daily-v1",
        parent_workflow_id=uuid.uuid4(),
        repository_sha="a" * 40,
        skill_sha256="b" * 64,
        prompt_sha256=None,
        model="gpt5.6-Sol",
        reasoning_effort="medium",
        codex_cli_version="0.75.0",
        proposal=None,
        url_candidates=None,
        trace_attempt_count=0,
        trace_uri=None,
    )
    hub = Hub()
    service = CurationTraceService(Database(), settings, hf_api=hub)
    events = base64.b64encode(gzip.compress(b'{"type":"done"}\n')).decode()
    service.preapply(
        row,
        proposal={"evaluations": [], "benchmark_gaps": []},
        events_gzip_b64=events,
        prompt="curate paper 42",
        url_candidates={"complete": True, "candidates": [], "sources": []},
    )
    service.finalize(
        row,
        {
            "events_gzip_b64": events,
            "result": {"status": "no_changes"},
            "benchmark_gaps": [],
            "report": "No eligible changes.",
            "usage": {"input_tokens": 10, "output_tokens": 2},
            "duration_ms": 50,
        },
    )

    manifest_path = next(path for path in hub.objects if path.endswith("manifest.json"))
    manifest = json.loads(hub.objects[manifest_path])
    assert row.trace_status == "complete"
    assert {"events.jsonl.gz", "prompt.txt", "proposal.json", "result.json"} <= set(
        manifest["objects"]
    )
    assert not (tmp_path / "curation-traces" / f"{row.id}.json").exists()
