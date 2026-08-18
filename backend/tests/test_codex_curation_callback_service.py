from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.config import get_settings
from backend.database.connection import get_database_session
from backend.main import create_app
from backend.models.api import ApplyMutationRequest, EvaluationCreateRequest
from backend.services.codex_curation_callback_service import (
    CodexCurationCallbackService,
    CodexCurationEvaluationPaperMismatchError,
    CodexCurationPaperNotFoundError,
)


def _evaluation(*, paper_id: int = 42, model_name: str) -> EvaluationCreateRequest:
    return EvaluationCreateRequest(
        paper_id=paper_id,
        task_id=19,
        dataset_id=340,
        model_name=model_name,
        metrics={"GenEval Score": 0.9},
        best_metric="GenEval Score",
        source_url="https://arxiv.org/abs/2601.00001",
    )


class _ResultQuery:
    def __init__(self, result):
        self.result = result

    def filter(self, *_args):
        return self

    def one_or_none(self):
        return self.result


class _ListQuery:
    def __init__(self, rows):
        self.rows = rows

    def join(self, *_args):
        return self

    def filter(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def limit(self, _limit):
        return self

    def all(self):
        return self.rows

    def __iter__(self):
        return iter(self.rows)


class _MutationDatabase:
    def __init__(self, existing=()):
        self.existing = iter(existing)
        self.commits = 0
        self.rollbacks = 0
        self.refreshes = []
        self.queries = 0
        self.pending = []

    def refresh(self, row, *, with_for_update):
        self.refreshes.append((row, with_for_update))

    def query(self, _model):
        self.queries += 1
        return _ResultQuery(next(self.existing))

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1
        self.pending.clear()


def _service(db, evaluation_service) -> CodexCurationCallbackService:
    return CodexCurationCallbackService(
        db,
        evaluation_service=evaluation_service,
        paper_service=SimpleNamespace(),
    )


def _stored_evaluation(**overrides):
    values = {
        "id": 77,
        "paper_id": 42,
        "task_id": 19,
        "dataset_id": 340,
        "model_name": "Existing Model",
        "harness": None,
        "methodology": "Older evidence.",
        "metrics": {"GenEval Score": 0.8},
        "uses_additional_data": False,
        "is_open": True,
        "best_rank": None,
        "best_metric": "GenEval Score",
        "evaluated_on": None,
        "source_url": "https://arxiv.org/abs/2601.00001",
        "external_source_url": None,
        "num_parameters": None,
        "hf_model_url": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_context_projection_preserves_the_worker_payload():
    task = SimpleNamespace(id=19, name="Image generation", slug="image-generation")
    method = SimpleNamespace(id=59, name="Diffusion", slug="diffusion")
    page = SimpleNamespace(url="https://example.com/project", is_official=True)
    repository = SimpleNamespace(url="https://github.com/example/model")
    paper = SimpleNamespace(
        id=42,
        title="A useful model",
        abstract="Abstract",
        arxiv_id="2601.00001",
        source="arxiv",
        source_url=None,
        date_published=datetime(2026, 1, 1, tzinfo=UTC),
        urls_extracted=True,
        thumbnail_url="/thumbnails/42.jpg",
        tasks=[task],
        methods=[method],
        project_pages=[page],
    )

    class Database:
        def get(self, *_args):
            return paper

        def query(self, *_args):
            return _ListQuery([(repository, True)])

    class SerializedJob:
        def model_dump(self, *, mode):
            assert mode == "json"
            return {"id": "job-42", "kind": "enrich-paper"}

    class JobService:
        def serialize(self, row, settings):
            assert row.paper_id == 42
            assert settings.codex_jobs_enabled
            return SerializedJob()

    service = CodexCurationCallbackService(
        Database(),
        job_service=JobService(),
        evaluation_service=SimpleNamespace(),
        paper_service=SimpleNamespace(),
    )

    result = service.context(
        SimpleNamespace(paper_id=42),
        get_settings().model_copy(update={"codex_jobs_enabled": True}),
    )

    assert result["job"] == {"id": "job-42", "kind": "enrich-paper"}
    assert result["paper"] == {
        "id": 42,
        "title": "A useful model",
        "abstract": "Abstract",
        "arxiv_id": "2601.00001",
        "source": "arxiv",
        "source_url": None,
        "date_published": datetime(2026, 1, 1, tzinfo=UTC),
        "urls_extracted": True,
        "thumbnail_url": "/thumbnails/42.jpg",
        "tasks": [
            {
                "id": 19,
                "name": "Image generation",
                "slug": "image-generation",
                "source": "unknown",
            }
        ],
        "methods": [
            {"id": 59, "name": "Diffusion", "slug": "diffusion", "evidence": []}
        ],
        "repositories": [
            {
                "url": "https://github.com/example/model",
                "is_official": True,
                "source": None,
            }
        ],
        "project_pages": [
            {"url": "https://example.com/project", "is_official": True, "source": None}
        ],
        "hf_models": [],
        "hf_datasets": [],
        "hf_spaces": [],
        "method_exclusions": [],
        "evaluations": [],
    }


def test_context_reports_a_missing_scoped_paper():
    class Database:
        def get(self, *_args):
            return None

    service = CodexCurationCallbackService(
        Database(),
        evaluation_service=SimpleNamespace(),
        paper_service=SimpleNamespace(),
    )

    with pytest.raises(CodexCurationPaperNotFoundError, match="Paper not found"):
        service.context(SimpleNamespace(paper_id=42), get_settings())


def test_leaderboard_inventory_preserves_match_and_recent_score_evidence():
    dataset = SimpleNamespace(
        id=340,
        name="GenEval",
        slug="geneval",
        full_name="GenEval benchmark",
        split_name=None,
        variant_type=None,
        short_description="Image-generation alignment.",
        description="Long description",
        warning=None,
    )
    task = SimpleNamespace(id=19, name="Image generation", slug="image-generation")
    task_dataset = SimpleNamespace(supports_harness=False)
    metric = SimpleNamespace(
        id=101,
        name="GenEval Score",
        direction="higher_is_better",
        scale="0-1",
    )
    examples = [
        SimpleNamespace(model_name="Useful Model", metrics={"GenEval Score": 0.9}),
        SimpleNamespace(model_name="Missing Metric", metrics={"Other": 1.0}),
    ]

    class Database:
        def query(self, *models):
            if len(models) == 4:
                return _ListQuery([(dataset, task, task_dataset, metric)])
            return _ListQuery(examples)

    service = CodexCurationCallbackService(
        Database(),
        evaluation_service=SimpleNamespace(),
        paper_service=SimpleNamespace(),
    )

    assert service.leaderboard_inventory("Gen-Eval") == [
        {
            "dataset": {
                "id": 340,
                "name": "GenEval",
                "slug": "geneval",
                "full_name": "GenEval benchmark",
                "split_name": None,
                "variant_type": None,
                "description": "Image-generation alignment.",
                "warning": None,
            },
            "task": {
                "id": 19,
                "name": "Image generation",
                "slug": "image-generation",
            },
            "match_quality": "exact",
            "supports_harness": False,
            "metrics": [
                {
                    "id": 101,
                    "name": "GenEval Score",
                    "direction": "higher_is_better",
                    "scale": "0-1",
                    "recent_values": [{"model_name": "Useful Model", "value": 0.9}],
                }
            ],
        }
    ]


def test_leaderboard_inventory_orders_exact_matches_before_close_matches():
    exact = SimpleNamespace(
        id=1,
        name="GenEval",
        slug="geneval",
        full_name=None,
        split_name=None,
        variant_type=None,
        short_description=None,
        description=None,
        warning=None,
    )
    close = SimpleNamespace(
        id=2,
        name="GenEval Extended",
        slug="geneval-extended",
        full_name=None,
        split_name=None,
        variant_type=None,
        short_description=None,
        description=None,
        warning=None,
    )
    task = SimpleNamespace(id=19, name="Image generation", slug="image-generation")
    link = SimpleNamespace(supports_harness=False)
    metric = SimpleNamespace(
        id=101, name="Score", direction="higher_is_better", scale=None
    )

    class Database:
        def query(self, *models):
            if len(models) == 4:
                return _ListQuery(
                    [(close, task, link, metric), (exact, task, link, metric)]
                )
            return _ListQuery([])

    service = CodexCurationCallbackService(
        Database(),
        evaluation_service=SimpleNamespace(),
        paper_service=SimpleNamespace(),
    )

    inventory = service.leaderboard_inventory("GenEval")

    assert [item["dataset"]["id"] for item in inventory] == [1, 2]
    assert [item["match_quality"] for item in inventory] == ["exact", "close"]


def test_mixed_evaluation_apply_uses_one_final_transaction():
    database = _MutationDatabase(existing=[None, _stored_evaluation()])
    calls = []

    class Evaluations:
        def create_evaluation(self, **values):
            calls.append(("create", values))

        def update_evaluation(self, evaluation_id, **values):
            calls.append(("update", evaluation_id, values))

    row = SimpleNamespace(
        kind="add-evals",
        status="running",
        submitted_at=None,
        applied_at=None,
        paper_id=42,
    )

    result = _service(database, Evaluations()).apply(
        row,
        ApplyMutationRequest(
            evaluations=[
                _evaluation(model_name="New Model"),
                _evaluation(model_name="Existing Model"),
            ]
        ),
    )

    assert result == {
        "status": "applied",
        "evaluations_created": 1,
        "evaluations_updated": 1,
    }
    assert database.refreshes == [(row, True)]
    assert database.commits == 1
    assert database.rollbacks == 0
    assert calls[0][0] == "create"
    assert calls[0][1]["commit"] is False
    assert calls[1][0:2] == ("update", 77)
    assert calls[1][2]["commit"] is False
    assert calls[1][2]["harness_set"] is True
    assert calls[1][2]["source_url_set"] is True
    assert calls[1][2]["num_parameters_set"] is True
    assert calls[1][2]["hf_model_url_set"] is True
    assert row.submitted_at == row.applied_at


def test_exact_existing_evaluation_is_a_true_no_op():
    existing = _stored_evaluation(
        methodology=None,
        metrics={"GenEval Score": 0.9},
    )
    database = _MutationDatabase(existing=[existing])

    class Evaluations:
        def create_evaluation(self, **_values):
            raise AssertionError("exact duplicate must not be created")

        def update_evaluation(self, *_args, **_values):
            raise AssertionError("exact duplicate must not be rewritten")

    row = SimpleNamespace(
        kind="add-evals",
        status="running",
        submitted_at=None,
        applied_at=None,
        paper_id=42,
    )

    result = _service(database, Evaluations()).apply(
        row,
        ApplyMutationRequest(evaluations=[_evaluation(model_name="Existing Model")]),
    )

    assert result == {
        "status": "no_changes",
        "evaluations_created": 0,
        "evaluations_updated": 0,
    }
    assert row.applied_at is None


def test_late_evaluation_failure_rolls_back_the_whole_apply():
    database = _MutationDatabase(existing=[None, None])

    class Evaluations:
        def create_evaluation(self, **values):
            assert values["commit"] is False
            database.pending.append(values["model_name"])
            if len(database.pending) == 2:
                raise ValueError("second result is invalid")

    row = SimpleNamespace(
        kind="add-evals", status="running", applied_at=None, paper_id=42
    )

    with pytest.raises(ValueError, match="second result is invalid"):
        _service(database, Evaluations()).apply(
            row,
            ApplyMutationRequest(
                evaluations=[
                    _evaluation(model_name="First Model"),
                    _evaluation(model_name="Invalid Model"),
                ]
            ),
        )

    assert database.pending == []
    assert database.commits == 0
    assert database.rollbacks == 1
    assert not hasattr(row, "submitted_at")
    assert row.applied_at is None


def test_all_evaluation_paper_ids_are_checked_before_the_first_write():
    database = _MutationDatabase()

    class Evaluations:
        def create_evaluation(self, **_values):
            raise AssertionError("prevalidation must happen before mutation")

    row = SimpleNamespace(
        kind="add-evals", status="running", applied_at=None, paper_id=42
    )

    with pytest.raises(
        CodexCurationEvaluationPaperMismatchError,
        match="Evaluation paper does not match job",
    ):
        _service(database, Evaluations()).apply(
            row,
            ApplyMutationRequest(
                evaluations=[
                    _evaluation(model_name="Scoped Model"),
                    _evaluation(paper_id=99, model_name="Wrong Paper"),
                ]
            ),
        )

    assert database.queries == 0
    assert database.commits == 0
    assert database.rollbacks == 1
    assert not hasattr(row, "submitted_at")


@pytest.mark.parametrize(
    ("row", "payload", "status_code", "detail"),
    [
        (
            SimpleNamespace(
                kind="add-evals",
                status="completed",
                submitted_at=None,
                applied_at=None,
                paper_id=42,
            ),
            {"evaluations": []},
            409,
            "This job may no longer apply mutations",
        ),
        (
            SimpleNamespace(
                kind="enrich-paper",
                status="running",
                submitted_at=None,
                applied_at=None,
                paper_id=42,
            ),
            {},
            422,
            "Enrichment payload is required",
        ),
    ],
)
def test_apply_rejections_keep_http_contract(
    monkeypatch, row, payload, status_code, detail
):
    from backend.routers import codex_curation_callbacks

    settings = get_settings().model_copy(update={"codex_jobs_enabled": True})
    database = _MutationDatabase()
    monkeypatch.setattr(codex_curation_callbacks, "_callback_job", lambda *_args: row)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_database_session] = lambda: database

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/admin/codex-curation/jobs/"
            "00000000-0000-0000-0000-000000000042/apply",
            headers={"Authorization": "Bearer scoped-token"},
            json=payload,
        )

    assert response.status_code == status_code
    assert response.json() == {"detail": detail}
    assert database.commits == 0
    assert database.rollbacks == 1


def test_callback_auth_errors_and_disabled_precedence_are_stable():
    enabled = get_settings().model_copy(update={"codex_jobs_enabled": True})
    disabled = enabled.model_copy(update={"codex_jobs_enabled": False})

    class Database:
        def get(self, *_args):
            return None

    app = create_app()
    app.dependency_overrides[get_database_session] = lambda: Database()
    app.dependency_overrides[get_settings] = lambda: enabled
    path = (
        "/api/v1/admin/codex-curation/jobs/00000000-0000-0000-0000-000000000042/context"
    )
    with TestClient(app) as client:
        missing = client.get(path)
        invalid = client.get(path, headers={"Authorization": "Bearer invalid"})
        app.dependency_overrides[get_settings] = lambda: disabled
        hidden = client.get(path)

    assert missing.status_code == 401
    assert missing.json() == {"detail": "Missing job bearer token"}
    assert invalid.status_code == 401
    assert invalid.json() == {"detail": "Invalid job bearer token"}
    assert hidden.status_code == 404
    assert hidden.json() == {"detail": "Not found"}
