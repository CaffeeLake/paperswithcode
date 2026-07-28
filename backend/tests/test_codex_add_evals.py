from __future__ import annotations

import json
import uuid
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from huggingface_hub.errors import HfHubHTTPError
from httpx import Request, Response

from backend.codex_add_evals_app import create_codex_add_evals_app
from backend.config import get_settings
from backend.database.connection import get_database_session
from backend.main import create_app
from backend.services.codex_add_evals_service import (
    CodexPaperJob,
    CodexPaperJobCounts,
    CodexPaperJobsResponse,
    CodexPaperJobService,
    CURATOR_BOOTSTRAP_COMMAND,
    _git_revision,
    _launch_error,
    _release_git_revision,
)
from backend.utils.auth import require_hf_admin
from jobs.curation_api import USER_AGENT as HELPER_USER_AGENT
from jobs import curation_api


def _job(kind: str = "add-evals") -> CodexPaperJob:
    return CodexPaperJob(
        id=uuid.UUID("00000000-0000-0000-0000-000000000042"),
        paper_id=42,
        paper_route="2601.00001",
        paper_title="A useful model",
        requested_by="niels",
        kind=kind,
        status="queued",
        created_at=datetime.now(UTC),
        attempt_count=0,
    )


def test_serializer_exposes_hf_job_url():
    row = SimpleNamespace(
        id=_job().id,
        paper_id=42,
        paper_route="2601.00001",
        paper_title="A useful model",
        requested_by="niels",
        kind="add-evals",
        status="running",
        hf_job_id="hf-job",
        created_at=datetime.now(UTC),
        started_at=None,
        finished_at=None,
        applied_at=None,
        report=None,
        error=None,
        attempt_count=1,
    )
    settings = get_settings().model_copy(update={"codex_jobs_namespace": "huggingface"})
    serialized = CodexPaperJobService._serialize(row, settings)
    assert serialized.hf_job_url == "https://huggingface.co/jobs/huggingface/hf-job"


def test_git_revision_can_be_pinned_for_remote_jobs(monkeypatch):
    monkeypatch.setenv("PWC_CODEX_JOBS_GIT_SHA", "published-curation-revision")
    assert _git_revision() == "published-curation-revision"


def test_release_manifest_pins_remote_worker_revision(tmp_path):
    revision = "a" * 40
    (tmp_path / "release.json").write_text(json.dumps({"git_sha": revision}))
    assert _release_git_revision(tmp_path) == revision


def test_remote_job_bootstrap_uses_public_image_and_pinned_runner():
    settings = get_settings()
    assert settings.codex_jobs_image == "node:22-bookworm"
    assert settings.codex_jobs_namespace == ""
    assert "${PWC_GIT_SHA}/jobs/run_paper_curation.py" in CURATOR_BOOTSTRAP_COMMAND
    assert "Authorization: Bearer ${GITHUB_TOKEN}" in CURATOR_BOOTSTRAP_COMMAND


def test_launch_error_keeps_hub_validation_message():
    response = Response(
        403,
        request=Request("POST", "https://huggingface.co/api/jobs/huggingface"),
        json={
            "error": "User does not have permission to create a Job in this namespace"
        },
    )
    error = HfHubHTTPError(
        "forbidden",
        response=response,
        server_message="User does not have permission to create a Job in this namespace",
    )

    message = _launch_error(error)

    assert "does not have permission" in message
    assert "HfHubHTTPError" not in message


def test_remote_callbacks_identify_the_service_to_cloudflare():
    assert HELPER_USER_AGENT.startswith("PapersWithCode-Curation/")
    runner = Path("jobs/run_paper_curation.py").read_text(encoding="utf-8")
    assert '"User-Agent": USER_AGENT' in runner


def test_remote_add_evals_requires_configured_leaderboard_search():
    skill = Path(".agents/skills/remote-paper-curation/SKILL.md").read_text(
        encoding="utf-8"
    )
    runner = Path("jobs/run_paper_curation.py").read_text(encoding="utf-8")
    normalized_skill = " ".join(skill.split())
    normalized_runner = " ".join(runner.split())

    assert "only after running the `leaderboards` command for every" in normalized_skill
    assert "Never use an empty taxonomy result" in normalized_skill
    assert "for every benchmark found in the source" in normalized_runner
    assert "taxonomy command returns only tasks and methods" in normalized_runner


def test_codex_endpoint_enqueues_exact_paper(monkeypatch):
    from backend.routers import codex_add_evals

    settings = get_settings().model_copy(update={"codex_jobs_enabled": True})
    paper = SimpleNamespace(
        id=42, source="arxiv", arxiv_id="2601.00001", title="A useful model"
    )

    class Query:
        def filter(self, *_args):
            return self

        def one_or_none(self):
            return paper

    class Database:
        def query(self, _model):
            return Query()

    def fake_enqueue(db, **kwargs):
        assert db is not None
        assert kwargs["kind"] == "add-evals"
        assert kwargs["paper_id"] == 42
        assert kwargs["paper_route"] == "2601.00001"
        assert kwargs["requested_by"] == "niels"
        return _job()

    monkeypatch.setattr(
        codex_add_evals.codex_paper_job_service, "enqueue", fake_enqueue
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[require_hf_admin] = lambda: {"username": "niels"}
    app.dependency_overrides[get_database_session] = lambda: Database()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/admin/codex-add-evals/jobs", json={"paper_id": 42}
        )
    assert response.status_code == 202
    assert response.json()["kind"] == "add-evals"


def test_codex_endpoint_is_hidden_when_jobs_disabled():
    settings = get_settings().model_copy(update={"codex_jobs_enabled": False})
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[require_hf_admin] = lambda: {"username": "niels"}
    app.dependency_overrides[get_database_session] = lambda: SimpleNamespace()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/admin/codex-add-evals/jobs", json={"paper_id": 42}
        )
    assert response.status_code == 404


def test_dedicated_app_exposes_remote_callback_routes():
    paths = {route.path for route in create_codex_add_evals_app().routes}
    assert "/api/v1/admin/codex-add-evals/jobs" in paths
    assert "/api/v1/admin/codex-enrich-paper/jobs" in paths
    assert "/api/v1/admin/codex-curation/jobs" in paths
    assert "/api/v1/admin/codex-curation/jobs/{job_id}/context" in paths
    assert "/api/v1/admin/codex-curation/jobs/{job_id}/leaderboards" in paths
    assert "/api/v1/admin/codex-curation/jobs/{job_id}/thumbnail" in paths
    assert "/api/v1/chat/models" not in paths


def test_scoped_worker_can_search_configured_leaderboards(monkeypatch):
    from backend.routers import codex_curation_callbacks

    settings = get_settings().model_copy(update={"codex_jobs_enabled": True})
    inventory = [
        {
            "dataset": {"id": 340, "name": "GenEval", "slug": "geneval"},
            "task": {"id": 19, "name": "Image generation", "slug": "image-generation"},
            "supports_harness": False,
            "metrics": [
                {
                    "id": 101,
                    "name": "GenEval Score",
                    "direction": "higher_is_better",
                    "scale": "0-1",
                    "recent_values": [{"model_name": "Example", "value": "0.90"}],
                }
            ],
        }
    ]
    monkeypatch.setattr(
        codex_curation_callbacks, "_callback_job", lambda *_args: object()
    )
    monkeypatch.setattr(
        codex_curation_callbacks,
        "_leaderboard_inventory",
        lambda _db, query: inventory if query == "GenEval" else [],
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_database_session] = lambda: SimpleNamespace()

    with TestClient(app) as client:
        response = client.get(
            f"/api/v1/admin/codex-curation/jobs/{_job().id}/leaderboards?q=GenEval",
            headers={"Authorization": "Bearer scoped-token"},
        )

    assert response.status_code == 200
    assert response.json()["leaderboards"] == inventory


def test_curation_helper_exposes_leaderboard_search(monkeypatch):
    calls = []
    monkeypatch.setattr(curation_api, "request", lambda path: calls.append(path))
    monkeypatch.setattr(sys, "argv", ["curation_api.py", "leaderboards", "DPG-Bench"])

    curation_api.main()

    assert calls == ["leaderboards?q=DPG-Bench"]


def test_empty_add_evals_apply_is_an_explicit_no_op(monkeypatch):
    from backend.routers import codex_curation_callbacks

    settings = get_settings().model_copy(update={"codex_jobs_enabled": True})
    row = SimpleNamespace(
        kind="add-evals", status="running", applied_at=None, paper_id=42
    )

    class Database:
        commits = 0

        def commit(self):
            self.commits += 1

    database = Database()
    monkeypatch.setattr(codex_curation_callbacks, "_callback_job", lambda *_args: row)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_database_session] = lambda: database

    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/admin/codex-curation/jobs/{_job().id}/apply",
            headers={"Authorization": "Bearer scoped-token"},
            json={"evaluations": []},
        )

    assert response.status_code == 200
    assert response.json() == {
        "status": "no_changes",
        "evaluations_created": 0,
        "evaluations_updated": 0,
    }
    assert row.applied_at is None
    assert row.submitted_at is not None
    assert database.commits == 1


def test_scoped_worker_can_apply_discovered_evaluation(monkeypatch):
    from backend.routers import codex_curation_callbacks

    settings = get_settings().model_copy(update={"codex_jobs_enabled": True})
    row = SimpleNamespace(
        kind="add-evals", status="running", applied_at=None, paper_id=42
    )
    created = []

    class Query:
        def filter(self, *_args):
            return self

        def one_or_none(self):
            return None

    class Database:
        commits = 0

        def query(self, _model):
            return Query()

        def commit(self):
            self.commits += 1

    class FakeEvaluationService:
        def __init__(self, _db):
            pass

        def create_evaluation(self, **values):
            created.append(values)

    database = Database()
    monkeypatch.setattr(codex_curation_callbacks, "_callback_job", lambda *_args: row)
    monkeypatch.setattr(
        codex_curation_callbacks, "EvaluationService", FakeEvaluationService
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_database_session] = lambda: database

    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/admin/codex-curation/jobs/{_job().id}/apply",
            headers={"Authorization": "Bearer scoped-token"},
            json={
                "evaluations": [
                    {
                        "paper_id": 42,
                        "task_id": 19,
                        "dataset_id": 340,
                        "model_name": "Useful Model",
                        "metrics": {"GenEval Score": 0.9},
                        "best_metric": "GenEval Score",
                        "source_url": "https://arxiv.org/abs/2601.00001",
                    }
                ]
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "status": "applied",
        "evaluations_created": 1,
        "evaluations_updated": 0,
    }
    assert created[0]["dataset_id"] == 340
    assert row.applied_at is not None
    assert database.commits == 1


def test_scoped_enrichment_queues_thumbnail_without_web_process_mutation(monkeypatch):
    from backend.routers import codex_curation_callbacks

    settings = get_settings().model_copy(update={"codex_jobs_enabled": True})
    row = SimpleNamespace(
        kind="enrich-paper", status="running", applied_at=None, paper_id=42
    )
    paper = SimpleNamespace(thumbnail_url=None, urls_extracted=False)

    class Database:
        commits = 0

        def get(self, _model, paper_id):
            assert paper_id == 42
            return paper

        def commit(self):
            self.commits += 1

    database = Database()
    monkeypatch.setattr(codex_curation_callbacks, "_callback_job", lambda *_args: row)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_database_session] = lambda: database

    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/admin/codex-curation/jobs/{_job().id}/apply",
            headers={"Authorization": "Bearer scoped-token"},
            json={
                "enrich": {
                    "regenerate_thumbnail": True,
                    "urls_extracted": True,
                }
            },
        )

    assert response.status_code == 200
    assert response.json()["thumbnail"] | {
        "requested_at": None,
    } == {
        "requested": True,
        "status": "queued",
        "attempt_count": 0,
        "requested_at": None,
        "claimed_at": None,
        "finished_at": None,
        "thumbnail_url": None,
        "previous_dimensions": None,
        "generated_dimensions": None,
        "success": None,
        "warnings": [],
        "error": None,
    }
    assert paper.urls_extracted
    assert row.applied_at is not None
    router_source = Path(codex_curation_callbacks.__file__).read_text()
    assert "regenerate_paper_thumbnail" not in router_source
    assert "ThumbnailService" not in router_source


def test_enrichment_relations_and_thumbnail_enqueue_commit_atomically(monkeypatch):
    from backend.routers import codex_curation_callbacks

    settings = get_settings().model_copy(update={"codex_jobs_enabled": True})
    row = SimpleNamespace(
        kind="enrich-paper", status="running", applied_at=None, paper_id=42
    )
    paper = SimpleNamespace(thumbnail_url=None, urls_extracted=False)
    calls = []

    class Database:
        commits = 0

        def get(self, _model, _paper_id):
            return paper

        def commit(self):
            self.commits += 1

    class FakePaperService:
        def __init__(self, _db):
            pass

        def update_paper_tasks(self, paper_id, values, *, commit):
            calls.append(("tasks", paper_id, values, commit))

        def update_paper_methods(self, paper_id, values, *, commit):
            calls.append(("methods", paper_id, values, commit))

    database = Database()
    monkeypatch.setattr(codex_curation_callbacks, "_callback_job", lambda *_args: row)
    monkeypatch.setattr(codex_curation_callbacks, "PaperService", FakePaperService)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_database_session] = lambda: database

    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/admin/codex-curation/jobs/{_job().id}/apply",
            headers={"Authorization": "Bearer scoped-token"},
            json={
                "enrich": {
                    "task_ids": [19],
                    "method_ids": [59],
                    "regenerate_thumbnail": True,
                }
            },
        )

    assert response.status_code == 200
    assert calls == [
        ("tasks", 42, [19], False),
        ("methods", 42, [59], False),
    ]
    assert row.thumbnail_status == "queued"
    assert row.submitted_at == row.applied_at
    assert database.commits == 1


def test_late_invalid_enrichment_input_rolls_back_before_enqueue(monkeypatch):
    from backend.routers import codex_curation_callbacks

    settings = get_settings().model_copy(update={"codex_jobs_enabled": True})
    row = SimpleNamespace(
        kind="enrich-paper", status="running", applied_at=None, paper_id=42
    )
    paper = SimpleNamespace(
        thumbnail_url=None, urls_extracted=False, tasks_changed=False
    )

    class Database:
        commits = 0
        rollbacks = 0

        def get(self, _model, _paper_id):
            return paper

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1
            paper.tasks_changed = False

    class FakePaperService:
        def __init__(self, db):
            self.db = db

        def update_paper_tasks(self, _paper_id, _values, *, commit):
            assert commit is False
            paper.tasks_changed = True

        def update_paper_methods(self, _paper_id, _values, *, commit):
            assert commit is False
            self.db.rollback()
            raise ValueError("Invalid method IDs: {999}")

    database = Database()
    monkeypatch.setattr(codex_curation_callbacks, "_callback_job", lambda *_args: row)
    monkeypatch.setattr(codex_curation_callbacks, "PaperService", FakePaperService)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_database_session] = lambda: database

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            f"/api/v1/admin/codex-curation/jobs/{_job().id}/apply",
            headers={"Authorization": "Bearer scoped-token"},
            json={
                "enrich": {
                    "task_ids": [19],
                    "method_ids": [999],
                    "regenerate_thumbnail": True,
                }
            },
        )

    assert response.status_code == 500
    assert database.rollbacks == 1
    assert database.commits == 0
    assert paper.tasks_changed is False
    assert not hasattr(row, "thumbnail_status")
    assert not hasattr(row, "submitted_at")


def test_admin_can_list_curation_queue(monkeypatch):
    from backend.routers import codex_curation_callbacks

    settings = get_settings().model_copy(update={"codex_jobs_enabled": True})
    expected = CodexPaperJobsResponse(
        timestamp=datetime.now(UTC),
        jobs=[_job()],
        summary=CodexPaperJobCounts(total=1, queued=1),
    )

    def fake_list_jobs(db, supplied_settings, *, limit):
        assert db is not None
        assert supplied_settings is settings
        assert limit == 25
        return expected

    monkeypatch.setattr(
        codex_curation_callbacks.codex_paper_job_service, "list_jobs", fake_list_jobs
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[require_hf_admin] = lambda: {"username": "niels"}
    app.dependency_overrides[get_database_session] = lambda: SimpleNamespace()
    with TestClient(app) as client:
        response = client.get("/api/v1/admin/codex-curation/jobs?limit=25")

    assert response.status_code == 200
    assert response.json()["jobs"][0]["paper_id"] == 42
    assert response.json()["summary"]["queued"] == 1
