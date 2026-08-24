from __future__ import annotations

import base64
import gzip
import hashlib
import json
import urllib.error
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from jsonschema import Draft202012Validator

from backend.config import get_settings
from backend.models.database import (
    BenchmarkCurationCandidate,
    BenchmarkCurationEvidence,
    Dataset,
    Metric,
    Paper,
    Task,
    TaskDataset,
)
from backend.services.benchmark_gap_service import BenchmarkGapService
from backend.services.codex_add_evals_service import (
    CodexPaperJobService,
    _is_callback_validation_rejection,
)
from backend.services.codex_curation_callback_service import (
    CodexCurationCallbackService,
)
from backend.services.curation_trace_service import (
    CurationTraceService,
    redact_trace,
    trace_json,
)
from backend.services.hf_daily_curation_service import (
    HFDailyCurationService,
    _dispatched_canary_workflows,
)
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


def test_normalize_candidate_ignores_malformed_markdown_link_url():
    assert (
        url_preflight.normalize_candidate(
            "https://odensenlp.github.io](https://odensenlp.github.io"
        )
        is None
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


def test_preflight_uses_discovered_project_candidate_for_conditional_html(
    monkeypatch,
):
    monkeypatch.setattr(
        url_preflight.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _HeadResponse(),
    )
    context = _context(project_page=False)
    context["paper"]["repositories"] = []
    context["paper"]["abstract"] = "Project: https://demo.github.io/paper"
    fetched = []

    def fetch(url: str, _limit: int):
        fetched.append(url)
        if "/api/papers/" in url:
            return b"{}", url
        if url.endswith(".md"):
            return b"", url
        if "/pdf/" in url:
            raise ValueError("fixture has no PDF")
        assert url == "https://demo.github.io/paper"
        return b'<a href="https://github.com/example/discovered">code</a>', url

    result = url_preflight.extract_candidates(context, fetch=fetch)

    assert "https://demo.github.io/paper" in fetched
    assert any(
        item["normalized_url"] == "https://github.com/example/discovered"
        and "project_page_html" in item["source_layers"]
        for item in result["candidates"]
    )


def test_preflight_uses_ocr_markdown_when_public_markdown_is_unavailable(
    monkeypatch,
):
    monkeypatch.setenv(url_preflight.OCR_MARKDOWN_TOKEN_ENV, "hf-test")
    monkeypatch.setattr(
        url_preflight.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _HeadResponse(),
    )
    fetched = []

    def fetch(url: str, _limit: int):
        fetched.append(url)
        if "/api/papers/" in url:
            return b"{}", url
        if url.endswith(".md"):
            raise urllib.error.HTTPError(url, 404, "not found", {}, None)
        raise AssertionError("OCR Markdown must avoid the PDF fallback")

    def fetch_ocr_markdown(arxiv_id: str, _limit: int, *, token: str):
        assert arxiv_id == "2608.00042"
        assert token == "hf-test"
        return (
            b"Code: https://github.com/example/project\n"
            b"Project: https://example.github.io/project\n",
            "https://signed.example/markdown",
        )

    result = url_preflight.extract_candidates(
        _context(project_page=False),
        fetch=fetch,
        fetch_ocr_markdown=fetch_ocr_markdown,
    )

    assert result["complete"] is True
    assert {source["source"] for source in result["sources"]} == {
        "hf_api",
        "ocr_markdown",
    }
    assert not result["errors"]
    assert not any("/pdf/" in url for url in fetched)


def test_fetch_ocr_markdown_uses_authenticated_bucket_download(monkeypatch):
    captured = {}

    class Response:
        headers = {"Content-Length": "2"}

        def geturl(self):
            return "https://signed.example/markdown"

        def read(self, _size):
            return b"#\n"

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def open(request, *, timeout):
        captured["url"] = request.full_url
        captured["authorization"] = request.get_header("Authorization")
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(
        url_preflight.urllib.request,
        "build_opener",
        lambda *_handlers: type("Opener", (), {"open": staticmethod(open)})(),
    )

    body, final_url = url_preflight._fetch_ocr_markdown(
        "2608.00042v3", 10, token="hf-test"
    )

    assert body == b"#\n"
    assert final_url == (
        "https://huggingface.co/buckets/huggingface/pwc-papers-content/resolve/"
        "2608%2F2608.00042.md"
    )
    assert captured == {
        "url": "https://huggingface.co/buckets/huggingface/pwc-papers-content/resolve/2608%2F2608.00042.md",
        "authorization": "Bearer hf-test",
        "timeout": url_preflight.TIMEOUT_SECONDS,
    }


def test_ocr_bucket_redirect_strips_authorization_for_cdn_request():
    request = url_preflight.urllib.request.Request(
        "https://huggingface.co/buckets/huggingface/pwc-papers-content/resolve/file",
        headers={"Authorization": "Bearer hf-test"},
    )

    redirected = url_preflight._BucketRedirectHandler().redirect_request(
        request,
        None,
        302,
        "Found",
        {},
        "https://cdn.example/signed-file",
    )

    assert redirected is not None
    assert redirected.full_url == "https://cdn.example/signed-file"
    assert redirected.get_header("Authorization") is None


def test_ocr_bucket_redirect_strips_authorization_for_scheme_downgrade():
    request = url_preflight.urllib.request.Request(
        "https://huggingface.co/buckets/huggingface/pwc-papers-content/resolve/file",
        headers={"Authorization": "Bearer hf-test"},
    )

    redirected = url_preflight._BucketRedirectHandler().redirect_request(
        request,
        None,
        302,
        "Found",
        {},
        "http://huggingface.co/buckets/huggingface/pwc-papers-content/resolve/file",
    )

    assert redirected is not None
    assert redirected.get_header("Authorization") is None


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
    Draft202012Validator.check_schema(schema)
    assert "benchmark_gaps" in schema["required"]
    assert "evaluation_removals" in schema["required"]
    assert "validation_evidence" in schema["required"]
    assert (
        schema["properties"]["benchmark_gaps"]["items"]["properties"]["reasoning"][
            "maxLength"
        ]
        == 2000
    )


def test_trace_json_keeps_gap_reasoning_first_with_deterministic_nested_keys():
    encoded = trace_json(
        {
            "benchmark_gaps": [
                {
                    "gap_type": "dataset_missing",
                    "reasoning": "Evidence-based summary.",
                    "assessment": {"why": "reusable", "confidence": "high"},
                }
            ]
        }
    ).decode()

    gap = encoded[encoded.index("[{") + 2 : encoded.index("}]")]
    assert gap.startswith('"reasoning":"Evidence-based summary."')
    assert '"assessment":{"confidence":"high","why":"reusable"}' in encoded


def test_daily_schedule_avoids_the_organization_sync_minute():
    workflow = Path(
        ".github/workflows/cron-enqueue-hf-daily-paper-curation.yml"
    ).read_text()
    assert 'cron: "27 2 * * *"' in workflow
    assert 'cron: "20 2 * * *"' not in workflow


def test_canary_gate_excludes_durable_deferred_overflow():
    completed = SimpleNamespace(status="completed", deferred_reason=None)
    deferred = SimpleNamespace(status="deferred", deferred_reason="canary_cap")

    assert _dispatched_canary_workflows([completed, deferred]) == [completed]


def test_scheduled_job_retry_uses_the_shared_durable_queue():
    job_id = uuid.uuid4()
    row = SimpleNamespace(id=job_id, trigger="hf-daily-cron", status="failed")
    serialized = {
        "id": str(uuid.uuid4()),
        "retry_of_id": str(job_id),
        "status": "queued",
    }

    class Database:
        def get(self, _model, key):
            return row if key == job_id else None

        def query(self, *_args):
            return SimpleNamespace(
                filter=lambda *_args: SimpleNamespace(
                    order_by=lambda *_args: SimpleNamespace(first=lambda: None)
                )
            )

    class JobService:
        def retry(self, db, selected, settings, *, priority):
            assert isinstance(db, Database)
            assert selected is row
            assert settings is configuration
            assert priority == 50
            return SimpleNamespace(model_dump=lambda **_kwargs: serialized)

    configuration = SimpleNamespace()
    result = HFDailyCurationService(
        Database(),
        configuration,
        job_service=JobService(),
    ).retry_scheduled_job(job_id)

    assert result == serialized


def test_callback_validation_rejection_is_not_classified_as_transient():
    rejected = SimpleNamespace(
        error="Remote job completed without an accepted apply.",
        validation_summary={"status": "rejected", "error": "bad payload"},
    )
    transient = SimpleNamespace(
        error="Codex process timed out",
        validation_summary=None,
    )

    assert _is_callback_validation_rejection(rejected) is True
    assert _is_callback_validation_rejection(transient) is False


def test_validator_replay_uses_saved_proposal_without_writes(monkeypatch):
    from backend.services import hf_daily_curation_service

    job_id = uuid.uuid4()
    row = SimpleNamespace(
        id=job_id,
        kind="add-evals",
        paper_id=42,
        trigger="hf-daily-cron",
        url_candidates=None,
        proposal={
            "evaluations": [],
            "evaluation_removals": [],
            "benchmark_gaps": [],
            "validation_evidence": [],
        },
    )
    paper = SimpleNamespace(id=42)

    class Database:
        def get(self, model, key):
            if model is hf_daily_curation_service.PaperCurationJob and key == job_id:
                return row
            if model is hf_daily_curation_service.Paper and key == 42:
                return paper
            return None

    class Gaps:
        def __init__(self, db):
            assert isinstance(db, Database)

        def validate(self, gaps, *, paper):
            assert gaps == []
            assert paper is None
            return [], []

    class Callback:
        def __init__(self, db):
            assert isinstance(db, Database)

        def _validate_mutation(self, replay_row, body):
            assert replay_row.status == "running"
            assert replay_row.trace_status == "disabled"
            assert body.evaluations == []

        def _validate_scheduled_policy(self, _replay_row, _body):
            return {"policy": "scheduled-add-evals-v1", "evaluations": 0}

    monkeypatch.setattr(hf_daily_curation_service, "BenchmarkGapService", Gaps)
    monkeypatch.setattr(
        hf_daily_curation_service, "CodexCurationCallbackService", Callback
    )

    result = HFDailyCurationService(
        Database(), SimpleNamespace(), job_service=SimpleNamespace()
    ).validator_replay(job_id)

    assert result == {
        "job_id": str(job_id),
        "valid": True,
        "validation": {"policy": "scheduled-add-evals-v1", "evaluations": 0},
        "benchmark_gaps_accepted": 0,
        "benchmark_gaps_rejected": [],
    }


def test_queued_operator_retry_is_prioritized_without_duplication():
    job_id = uuid.uuid4()
    row = SimpleNamespace(
        id=job_id,
        trigger="hf-daily-cron",
        status="queued",
        priority=100,
    )

    class Database:
        committed = False

        def get(self, _model, _key):
            return row

        def query(self, *_args):
            return SimpleNamespace(
                filter=lambda *_args: SimpleNamespace(
                    order_by=lambda *_args: SimpleNamespace(first=lambda: None)
                )
            )

        def commit(self):
            self.committed = True

    class JobService:
        dispatched = False

        def dispatch_next(self, *_args):
            self.dispatched = True

        def serialize(self, selected, _settings):
            assert selected is row
            return SimpleNamespace(
                model_dump=lambda **_kwargs: {
                    "id": str(job_id),
                    "priority": row.priority,
                }
            )

        def retry(self, *_args, **_kwargs):
            raise AssertionError("queued jobs must not be duplicated")

    database = Database()
    jobs = JobService()
    result = HFDailyCurationService(
        database,
        SimpleNamespace(),
        job_service=jobs,
    ).retry_scheduled_job(job_id)

    assert result == {"id": str(job_id), "priority": 50}
    assert database.committed is True
    assert jobs.dispatched is True


def test_repeating_operator_retry_returns_active_child_attempt():
    job_id = uuid.uuid4()
    failed = SimpleNamespace(id=job_id, trigger="hf-daily-cron", status="failed")
    active = SimpleNamespace(id=uuid.uuid4(), status="running", priority=100)

    class Query:
        def filter(self, *_args):
            return self

        def order_by(self, *_args):
            return self

        def first(self):
            return active

    class Database:
        committed = False

        def get(self, *_args):
            return failed

        def query(self, *_args):
            return Query()

        def commit(self):
            self.committed = True

    class Jobs:
        dispatched = False

        def dispatch_next(self, *_args):
            self.dispatched = True

        def serialize(self, row, _settings):
            assert row is active
            return SimpleNamespace(
                model_dump=lambda **_kwargs: {
                    "id": str(active.id),
                    "status": active.status,
                    "priority": active.priority,
                }
            )

        def retry(self, *_args, **_kwargs):
            raise AssertionError("an active child retry must be reused")

    database = Database()
    jobs = Jobs()
    result = HFDailyCurationService(
        database, SimpleNamespace(), job_service=jobs
    ).retry_scheduled_job(job_id)

    assert result == {"id": str(active.id), "status": "running", "priority": 50}
    assert database.committed is True
    assert jobs.dispatched is True


def test_operator_retry_rejects_admin_jobs():
    job_id = uuid.uuid4()

    class Database:
        def get(self, _model, _key):
            return SimpleNamespace(trigger="admin")

    with pytest.raises(ValueError, match="Only scheduled HF daily"):
        HFDailyCurationService(
            Database(),
            SimpleNamespace(),
            job_service=SimpleNamespace(),
        ).retry_scheduled_job(job_id)


def test_dispatch_acknowledgement_starts_a_fresh_failure_window():
    state = SimpleNamespace(
        dispatch_enabled=True,
        paused_at=datetime.now(UTC),
        pause_reason="Historical failures",
        pause_condition="terminal_failure_rate",
        acknowledged_at=None,
        first_enabled_at=datetime.now(UTC),
        consecutive_trace_failures=3,
        consecutive_apply_failures=3,
        canary_released=True,
    )

    class Query:
        def filter(self, *_args):
            return self

        def scalar(self):
            return None

    class Database:
        def get(self, *_args):
            return state

        def query(self, *_args):
            return Query()

        def commit(self):
            pass

    jobs = SimpleNamespace(dispatch_next=lambda *_args: None)
    result = HFDailyCurationService(
        Database(),
        get_settings(),
        job_service=jobs,
    ).set_dispatch(True)

    assert result["paused_at"] is None
    assert state.acknowledged_at is not None
    assert state.consecutive_trace_failures == 0
    assert state.consecutive_apply_failures == 0


def test_scheduled_usage_snapshot_exposes_enforced_threshold(monkeypatch):
    from backend.services import codex_add_evals_service

    now = datetime(2026, 8, 18, 12, tzinfo=UTC)
    monkeypatch.setattr(codex_add_evals_service, "_now", lambda: now)
    rows = [
        SimpleNamespace(
            finished_at=now,
            input_tokens=400,
            output_tokens=200,
        )
    ] + [
        SimpleNamespace(
            finished_at=now - codex_add_evals_service.timedelta(days=offset),
            input_tokens=80,
            output_tokens=20,
        )
        for offset in range(1, 8)
    ]

    class Query:
        def filter(self, *_args):
            return self

        def all(self):
            return rows

    class Database:
        def query(self, *_args):
            return Query()

    snapshot = CodexPaperJobService._scheduled_usage_snapshot(
        Database(),
        SimpleNamespace(
            first_enabled_at=now - codex_add_evals_service.timedelta(days=8)
        ),
    )

    assert snapshot == {
        "mode": "enforced",
        "current_day_tokens": 600,
        "trailing_seven_day_median_tokens": 100,
        "pause_threshold_tokens": 200,
    }


def test_cross_job_callback_token_pauses_scheduled_dispatch(monkeypatch):
    from backend.routers import codex_curation_callbacks

    added = []

    class Database:
        def get(self, *_args):
            return None

        def add(self, value):
            added.append(value)

        def commit(self):
            pass

    monkeypatch.setattr(
        codex_curation_callbacks.codex_paper_job_service,
        "authenticate",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        codex_curation_callbacks.codex_paper_job_service,
        "token_owner_for_other_job",
        lambda *_args: object(),
    )

    with pytest.raises(HTTPException) as error:
        codex_curation_callbacks._callback_job(
            uuid.uuid4(), "Bearer valid-for-another-job", Database()
        )

    assert error.value.status_code == 401
    assert added[0].pause_condition == "cross_paper_authorization"
    assert added[0].paused_at is not None


@pytest.mark.parametrize(
    ("scale", "value"),
    [("0-1", 1.01), ("0-100", 100.01), ("0-1000", 1000.01)],
)
def test_metric_scale_guard_rejects_out_of_range_values(scale, value):
    with pytest.raises(ValueError, match="outside configured scale"):
        CodexCurationCallbackService._validate_metric_scale(scale, value)


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


def test_hf_dispatch_retries_with_bounded_exponential_backoff(monkeypatch):
    calls = []
    sleeps = []

    class Hub:
        def run_job(self, **values):
            calls.append(values)
            if len(calls) < 3:
                raise OSError("transient dispatch failure")
            return SimpleNamespace(id="hf-job")

    service = CodexPaperJobService()
    monkeypatch.setattr(service, "_api", lambda _settings: Hub())
    monkeypatch.setattr(
        "backend.services.codex_add_evals_service.time.sleep", sleeps.append
    )
    row = SimpleNamespace(
        id=uuid.uuid4(),
        kind="enrich-paper",
        paper_id=42,
        retry_of_id=None,
        repository_sha="a" * 40,
        trigger="hf-daily-cron",
        model="gpt-5.6-sol",
        reasoning_effort="medium",
        codex_cli_version="0.75.0",
    )
    settings = get_settings().model_copy(
        update={
            "codex_jobs_namespace": "example",
            "codex_jobs_openai_api_key": "test-openai",
            "github_token": "test-github",
            "hf_token": "test-hf",
        }
    )

    remote = service._run_job_with_retry(
        settings=settings,
        row=row,
        callback_token="callback",
        image="example/image:sha",
    )

    assert remote.id == "hf-job"
    assert len(calls) == 3
    assert sleeps == [1, 2]
    assert all("GITHUB_TOKEN" not in call["secrets"] for call in calls)
    assert all(
        call["secrets"]["PWC_PAPER_MARKDOWN_HF_TOKEN"] == "test-hf" for call in calls
    )
    assert all(call["image"] == "example/image:sha" for call in calls)


def test_space_image_revision_is_verified_and_mismatch_pauses_daily_dispatch(
    monkeypatch,
):
    expected = "a" * 40
    state = SimpleNamespace(
        paused_at=None,
        pause_condition=None,
        pause_reason=None,
    )

    class Hub:
        observed = expected

        def space_info(self, *, repo_id):
            assert repo_id == "example/curator-0123456789ab"
            return SimpleNamespace(sha=self.observed)

    class Database:
        commits = 0

        def get(self, *_args):
            return state

        def commit(self):
            self.commits += 1

    service = CodexPaperJobService()
    hub = Hub()
    monkeypatch.setattr(service, "_api", lambda _settings: hub)
    settings = get_settings().model_copy(
        update={
            "codex_jobs_image": "hf.co/spaces/example/curator-0123456789ab",
            "codex_jobs_image_revision": expected,
        }
    )
    row = SimpleNamespace(trigger="hf-daily-cron", repository_sha="b" * 40)
    database = Database()

    assert service._verified_job_image(database, settings, row) == (
        "hf.co/spaces/example/curator-0123456789ab"
    )

    hub.observed = "c" * 40
    with pytest.raises(RuntimeError, match="Curator Space revision mismatch"):
        service._verified_job_image(database, settings, row)
    assert state.pause_condition == "curator_image_revision_mismatch"
    assert state.paused_at is not None


def test_dispatch_does_not_append_registry_tag_to_verified_space(monkeypatch):
    launched = {}

    class Database:
        def commit(self):
            pass

    service = CodexPaperJobService()
    monkeypatch.setattr(
        service,
        "_verified_job_image",
        lambda _db, _settings, _row: "hf.co/spaces/example/curator-0123456789ab",
    )
    monkeypatch.setattr(
        service,
        "_run_job_with_retry",
        lambda **values: launched.update(values) or SimpleNamespace(id="hf-job"),
    )
    row = SimpleNamespace(
        id=uuid.uuid4(),
        kind="enrich-paper",
        paper_id=42,
        trigger="hf-daily-cron",
        retry_of_id=None,
        repository_sha="b" * 40,
        model="gpt-5.6-sol",
        reasoning_effort="medium",
        codex_cli_version="0.75.0",
        status="queued",
        callback_token_hash=None,
        attempt_count=0,
        hf_job_id=None,
        started_at=None,
    )
    settings = get_settings().model_copy(
        update={
            "codex_jobs_namespace": "example",
            "codex_jobs_token": "hf-token",
            "codex_jobs_openai_api_key": "openai-token",
        }
    )

    service._dispatch_row(Database(), settings, row)

    assert launched["image"] == "hf.co/spaces/example/curator-0123456789ab"
    assert row.status == "running"
    assert row.hf_job_id == "hf-job"


def test_bootstrap_bundle_is_allowlisted_hashed_and_release_bound(monkeypatch):
    from backend.services import codex_add_evals_service as service_module

    revision = "d" * 40
    monkeypatch.setattr(service_module, "_git_revision", lambda: revision)
    service = CodexPaperJobService()

    bundle = service.bootstrap_bundle(SimpleNamespace(repository_sha=revision))

    assert bundle["revision"] == revision
    assert {item["path"] for item in bundle["files"]} == set(
        service_module.CURATOR_BOOTSTRAP_PATHS
    )
    for item in bundle["files"]:
        content = base64.b64decode(item["content_b64"], validate=True)
        assert hashlib.sha256(content).hexdigest() == item["sha256"]
    with pytest.raises(ValueError, match="active immutable release"):
        service.bootstrap_bundle(SimpleNamespace(repository_sha="e" * 40))

    persisted = service_module._curator_bootstrap_bundle(revision)
    monkeypatch.setattr(service_module, "_git_revision", lambda: "f" * 40)
    assert (
        service.bootstrap_bundle(
            SimpleNamespace(repository_sha=revision, bootstrap_bundle=persisted)
        )
        == persisted
    )

    persisted["files"][0]["content_b64"] = base64.b64encode(b"tampered").decode()
    with pytest.raises(ValueError, match="hash mismatch"):
        service.bootstrap_bundle(
            SimpleNamespace(repository_sha=revision, bootstrap_bundle=persisted)
        )


def test_benchmark_gap_validation_isolates_malformed_entries():
    class Database:
        def get(self, _model, task_id):
            return SimpleNamespace(id=task_id)

    valid = {
        "reasoning": "A reusable public benchmark blocks a paper-native result.",
        "local_ref": "gap-1",
        "gap_type": "dataset_missing",
        "proposed_benchmark": {
            "name": "ExampleBench",
            "aliases": ["Example Bench"],
            "description": "A reusable public benchmark.",
            "task_candidates": [
                {
                    "task_id": 19,
                    "task_name": "Example Task",
                    "confidence": "high",
                    "reason": "The paper evaluates this task.",
                }
            ],
            "canonical_sources": [
                {
                    "kind": "homepage",
                    "url": "https://example.org/benchmark",
                    "title": "ExampleBench",
                }
            ],
        },
        "protocol": {
            "dataset_version": "v1",
            "splits": ["test"],
            "evaluation_protocol": "Evaluate on the public test split.",
            "metrics": [
                {
                    "name": "Accuracy",
                    "direction": "higher_is_better",
                    "unit": "percent",
                    "native_scale": "0-100",
                    "definition": "Exact-match accuracy.",
                }
            ],
            "supports_harness": False,
        },
        "blocked_evaluations": [
            {
                "local_ref": "blocked-1",
                "model_name": "Introduced Model",
                "harness": None,
                "split": "test",
                "metrics": {"Accuracy": 87.4},
                "best_metric": "Accuracy",
                "methodology": "Official test split.",
                "uses_additional_data": False,
                "is_open": True,
                "num_parameters": 7_000_000_000,
                "hf_model_url": "https://huggingface.co/example/model",
                "evidence_ids": ["e1"],
            }
        ],
        "evidence": [
            {
                "evidence_id": "e1",
                "source_kind": "paper_pdf",
                "source_url": "https://arxiv.org/pdf/2608.00042",
                "page": 7,
                "section": "4.2",
                "table": "Table 3",
                "snippet": "ExampleBench test results.",
                "supports": ["blocked-1"],
            }
        ],
        "catalog_search": {
            "queries": ["ExampleBench"],
            "near_matches": [],
            "conclusion": "No configured benchmark matches.",
        },
        "assessment": {
            "recommendation": "add_candidate",
            "confidence": "high",
            "why_worth_adding": "The protocol is public and reusable.",
            "ambiguities": [],
        },
    }

    accepted, rejected = BenchmarkGapService(Database()).validate(
        [valid, {"gap_type": "dataset_missing"}]
    )

    assert len(accepted) == 1
    assert accepted[0]["_normalized"]["task_ids"] == [19]
    assert rejected == [{"index": 1, "error": "reasoning is required"}]

    html_evidence = {
        **valid,
        "evidence": [
            {
                **valid["evidence"][0],
                "source_kind": "paper_markdown",
                "source_url": "https://arxiv.org/html/2608.00042",
            }
        ],
    }
    accepted, rejected = BenchmarkGapService(Database()).validate(
        [html_evidence],
        paper=SimpleNamespace(
            source_url="https://arxiv.org/abs/2608.00042",
            arxiv_id="2608.00042",
        ),
    )

    assert len(accepted) == 1
    assert rejected == []

    eprint_evidence = {
        **valid,
        "evidence": [
            {
                **valid["evidence"][0],
                "source_kind": "paper_source",
                "source_url": "https://export.arxiv.org/e-print/2608.00042",
            }
        ],
    }
    accepted, rejected = BenchmarkGapService(Database()).validate(
        [eprint_evidence],
        paper=SimpleNamespace(
            source_url="https://arxiv.org/abs/2608.00042",
            arxiv_id="2608.00042",
        ),
    )

    assert rejected == []
    assert accepted[0]["evidence"][0]["source_url"] == (
        "https://arxiv.org/html/2608.00042"
    )


def test_benchmark_gap_rejects_server_owned_fields():
    class Database:
        def get(self, _model, task_id):
            return SimpleNamespace(id=task_id)

    invalid = {
        "reasoning": "A gap.",
        "candidate_id": "agent-invented",
        "gap_type": "dataset_missing",
    }

    accepted, rejected = BenchmarkGapService(Database()).validate([invalid])

    assert accepted == []
    assert rejected == [
        {"index": 0, "error": "agent proposal contains server-owned fields"}
    ]


def test_reviewed_benchmark_promotion_requeues_only_evidence_papers():
    candidate_id = uuid.uuid4()
    candidate = SimpleNamespace(
        id=candidate_id,
        task_ids=[19],
        status="candidate",
        promoted_at=None,
    )
    evidence = SimpleNamespace(
        candidate_id=candidate_id,
        paper_id=42,
        created_at=datetime(2026, 8, 18, tzinfo=UTC),
        payload={"protocol": {"metrics": [{"name": "Accuracy"}]}},
    )
    paper = SimpleNamespace(
        id=42,
        source="arxiv",
        arxiv_id="2608.00042",
        title="Evidence paper",
    )

    class Query:
        def __init__(self, model):
            self.model = model

        def join(self, *_args):
            return self

        def filter(self, *_args):
            return self

        def order_by(self, *_args):
            return self

        def one_or_none(self):
            if self.model is Metric:
                return SimpleNamespace(id=7, name="Accuracy")
            return None

        def all(self):
            return [evidence] if self.model is BenchmarkCurationEvidence else []

        def first(self):
            return None

    class Database:
        def __init__(self):
            self.commits = 0

        def get(self, model, key):
            values = {
                (BenchmarkCurationCandidate, candidate_id): candidate,
                (Dataset, 8): SimpleNamespace(id=8),
                (Task, 19): SimpleNamespace(id=19),
                (TaskDataset, (19, 8)): SimpleNamespace(task_id=19, dataset_id=8),
                (Paper, 42): paper,
            }
            return values.get((model, key))

        def query(self, model):
            return Query(model)

        def commit(self):
            self.commits += 1

    class Jobs:
        def __init__(self):
            self.enqueued = []
            self.dispatched = False

        def enqueue(self, db, **values):
            self.enqueued.append((db, values))
            return SimpleNamespace(id=uuid.uuid4())

        def dispatch_next(self, *_args):
            self.dispatched = True

    database = Database()
    jobs = Jobs()
    result = BenchmarkGapService(database).promote_and_enqueue(
        candidate_id=candidate_id,
        dataset_id=8,
        task_id=19,
        best_metric="Accuracy",
        settings=get_settings(),
        job_service=jobs,
    )

    assert result["skipped_active_paper_ids"] == []
    assert len(result["enqueued_job_ids"]) == 1
    assert jobs.enqueued[0][1] | {"settings": None} == {
        "kind": "add-evals",
        "paper_id": 42,
        "paper_route": "2608.00042",
        "paper_title": "Evidence paper",
        "requested_by": f"benchmark-promotion:{candidate_id}",
        "trigger": "benchmark-promotion",
        "policy_version": f"benchmark-promotion-{str(candidate_id)[:12]}",
        "priority": 50,
        "dispatch": False,
        "commit": False,
        "settings": None,
    }
    assert candidate.status == "promoted"
    assert candidate.promoted_at is not None
    assert jobs.dispatched is True


def test_trace_bundle_manifest_hashes_every_uploaded_object(tmp_path):
    scheduler = SimpleNamespace(consecutive_trace_failures=2)

    class Database:
        def commit(self):
            pass

        def get(self, model, *_args):
            from backend.models.database import PaperCurationSchedulerState

            return scheduler if model is PaperCurationSchedulerState else None

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
        model="gpt-5.6-sol",
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
    assert scheduler.consecutive_trace_failures == 0
    assert {"events.jsonl.gz", "prompt.txt", "proposal.json", "result.json"} <= set(
        manifest["objects"]
    )
    assert not (tmp_path / "curation-traces" / f"{row.id}.json").exists()
