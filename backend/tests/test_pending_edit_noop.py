"""
Regression tests for `PendingEditService.submit()` no-op detection.

Submissions that match the paper's current state must be rejected with a
`PendingEditError` so the /submissions admin dashboard isn't cluttered with
"empty" review cards. See `backend/services/pending_edit_service.py`.
"""

import json

import pytest
from fastapi import HTTPException
from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.models.database import (
    Base,
    Method as DBMethod,
    Paper as DBPaper,
    PaperMethod,
    PaperProjectPage,
    PaperRepository,
    PaperTask,
    PendingPaperEdit,
    ProjectPage as DBProjectPage,
    Repository as DBRepository,
    Task as DBTask,
    Dataset as DBDataset,
    Metric as DBMetric,
    Conference as DBConference,
    TaskDataset,
    TaskDatasetMetric,
    CatalogMutationEvent,
)
from backend.routers.pending_edits import _to_response
from backend.services.pending_edit_service import (
    PendingEditError,
    PendingEditAlreadyReviewedError,
    PendingEditConflictError,
    PendingEditService,
    SubmissionRateLimitError,
    SubmissionSuspendedError,
)
from backend.config import Settings
from backend.models.database import UserProfile
from backend.services.submission_rollback_service import SubmissionRollbackService


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_element, _compiler, **_kw):
    return "TEXT"


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_element, _compiler, **_kw):
    return "TEXT"


SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(engine, "connect")
def _register_jsonb_typeof(connection, _record):
    def jsonb_typeof(value):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return None
        return "array" if isinstance(parsed, list) else "object"

    connection.create_function("jsonb_typeof", 1, jsonb_typeof)


TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def paper_fixture(db_session):
    """Paper #1 with two tasks, one method, one repo, one project page, and an
    external source URL — enough state to exercise every edit_type."""

    db_session.add(
        DBPaper(
            id=1,
            title="Paper",
            abstract="Abstract",
            source="external",
            source_url="https://example.com/paper",
            arxiv_id=None,
        )
    )
    db_session.add_all(
        [
            DBTask(id=1, name="Task A", slug="task-a", level=0),
            DBTask(id=2, name="Task B", slug="task-b", level=0),
            DBTask(id=3, name="Task C", slug="task-c", level=0),
            DBMethod(id=10, name="Method X", slug="method-x"),
            DBMethod(id=11, name="Method Y", slug="method-y"),
            DBRepository(id=100, url="https://github.com/owner/repo"),
            # `is_official` lives on ProjectPage itself (not the junction),
            # so the snapshot reads it from this column.
            DBProjectPage(id=200, url="https://example.com/project", is_official=False),
        ]
    )
    db_session.add_all(
        [
            PaperTask(paper_id=1, task_id=1),
            PaperTask(paper_id=1, task_id=2),
            PaperMethod(paper_id=1, method_id=10),
            PaperRepository(paper_id=1, repository_id=100, is_official=True),
            PaperProjectPage(paper_id=1, project_page_id=200),
        ]
    )
    db_session.commit()


def _no_rows_created(db_session) -> None:
    assert db_session.query(PendingPaperEdit).count() == 0


def test_submit_tasks_noop_rejects(db_session, paper_fixture):
    service = PendingEditService(db_session)
    with pytest.raises(PendingEditError, match="does not contain any changes"):
        service.submit(
            paper_id=1,
            hf_username="alice",
            edit_type="tasks",
            proposed_payload={"task_ids": [2, 1]},  # same set, different order
        )
    _no_rows_created(db_session)


def test_submit_tasks_change_succeeds(db_session, paper_fixture):
    row = PendingEditService(db_session).submit(
        paper_id=1,
        hf_username="alice",
        edit_type="tasks",
        proposed_payload={"task_ids": [1, 2, 3]},
    )
    assert row.id is not None
    assert row.status == "pending"
    assert row.proposed_payload == {"task_ids": [1, 2, 3]}


def test_approve_tasks_rebases_compatible_live_addition(db_session):
    db_session.add(
        DBPaper(
            id=2,
            title="P2",
            source="external",
            source_url="https://example.com/p2",
        )
    )
    db_session.add_all(
        [
            DBTask(id=1, name="Task A", slug="task-a", level=0),
            DBTask(id=2, name="Task B", slug="task-b", level=0),
            DBTask(id=3, name="Task C", slug="task-c", level=0),
        ]
    )
    db_session.commit()
    service = PendingEditService(db_session)
    row = service.submit(
        paper_id=2,
        hf_username="alice",
        edit_type="tasks",
        proposed_payload={"task_ids": [1, 2, 3]},
    )

    db_session.add(PaperTask(paper_id=2, task_id=1))
    db_session.commit()

    reviewed = service.approve(edit_id=row.id, reviewer_username="admin")

    task_ids = {
        item.task_id
        for item in db_session.query(PaperTask).filter(PaperTask.paper_id == 2)
    }
    assert task_ids == {1, 2, 3}
    assert reviewed.applied_payload == {"task_ids": [1, 2, 3]}
    assert reviewed.conflict_payload is None


def test_approve_tasks_rebase_preserves_unrelated_live_change(
    db_session, paper_fixture
):
    service = PendingEditService(db_session)
    row = service.submit(
        paper_id=1,
        hf_username="alice",
        edit_type="tasks",
        proposed_payload={"task_ids": [2]},
    )
    db_session.add(PaperTask(paper_id=1, task_id=3))
    db_session.commit()

    reviewed = service.approve(edit_id=row.id, reviewer_username="admin")

    task_ids = {
        item.task_id
        for item in db_session.query(PaperTask).filter(PaperTask.paper_id == 1)
    }
    assert task_ids == {2, 3}
    assert reviewed.applied_payload == {"task_ids": [2, 3]}


def test_approve_non_membership_edit_still_rejects_stale_snapshot(
    db_session, paper_fixture
):
    service = PendingEditService(db_session)
    row = service.submit(
        paper_id=1,
        hf_username="alice",
        edit_type="source_url",
        proposed_payload={"source_url": "https://example.com/submitted"},
    )
    paper = db_session.get(DBPaper, 1)
    paper.source_url = "https://example.com/intervening"
    db_session.commit()

    with pytest.raises(
        PendingEditConflictError, match="Canonical state changed after submission"
    ):
        service.approve(edit_id=row.id, reviewer_username="admin")

    assert db_session.get(PendingPaperEdit, row.id).conflict_payload == {
        "submitted_snapshot": {
            "source_url": "https://example.com/paper",
            "source": "external",
        },
        "current_snapshot": {
            "source_url": "https://example.com/intervening",
            "source": "external",
        },
    }


def test_submit_methods_noop_rejects(db_session, paper_fixture):
    service = PendingEditService(db_session)
    with pytest.raises(PendingEditError, match="does not contain any changes"):
        service.submit(
            paper_id=1,
            hf_username="alice",
            edit_type="methods",
            proposed_payload={"method_ids": [10]},
        )
    _no_rows_created(db_session)


def test_submit_methods_change_succeeds(db_session, paper_fixture):
    row = PendingEditService(db_session).submit(
        paper_id=1,
        hf_username="alice",
        edit_type="methods",
        proposed_payload={"method_ids": [10, 11]},
    )
    assert row.id is not None


def test_submit_directory_taxonomy_suggestion_without_paper_succeeds(db_session):
    service = PendingEditService(db_session)
    row = service.submit(
        paper_id=None,
        hf_username="alice",
        edit_type="new_task",
        proposed_payload={
            "name": "Long-context Retrieval",
            "description": "Retrieving evidence from very long contexts.",
        },
    )

    assert row.id is not None
    assert row.paper_id is None
    assert row.is_author is False
    assert row.current_payload == {}

    reviewed = service.approve(edit_id=row.id, reviewer_username="admin")
    assert reviewed.status == "approved"


def test_submit_task_suggestion_allows_omitted_description(db_session):
    row = PendingEditService(db_session).submit(
        paper_id=None,
        hf_username="alice",
        edit_type="new_task",
        proposed_payload={"name": "Long-context Retrieval"},
    )

    assert row.proposed_payload == {"name": "Long-context Retrieval"}


def test_submit_method_suggestion_accepts_image_and_sources(db_session):
    image_data_url = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4"
        "//8/AAX+Av4N70a4AAAAAElFTkSuQmCC"
    )
    row = PendingEditService(db_session).submit(
        paper_id=None,
        hf_username="alice",
        edit_type="new_method",
        proposed_payload={
            "name": "New Attention",
            "description": " ",
            "image": {
                "file_name": " attention.png ",
                "mime_type": "image/png",
                "data_url": image_data_url,
            },
            "image_credit": " Example Research Group ",
            "source_url": " https://example.org/new-attention ",
        },
    )

    assert row.proposed_payload == {
        "name": "New Attention",
        "image": {
            "file_name": "attention.png",
            "mime_type": "image/png",
            "data_url": image_data_url,
        },
        "image_credit": "Example Research Group",
        "source_url": "https://example.org/new-attention",
    }
    response = _to_response(row)
    assert response.proposed_payload["image"] == {
        "file_name": "attention.png",
        "mime_type": "image/png",
        "url": f"/api/v1/admin/paper-edits/{row.id}/image",
    }
    assert row.proposed_payload["image"]["data_url"] == image_data_url


def test_submit_method_suggestion_rejects_invalid_source(db_session):
    with pytest.raises(PendingEditError, match="HTTP"):
        PendingEditService(db_session).submit(
            paper_id=None,
            hf_username="alice",
            edit_type="new_method",
            proposed_payload={
                "name": "New Attention",
                "source_url": "javascript:alert(1)",
            },
        )
    _no_rows_created(db_session)


def test_submit_directory_conference_suggestion_without_paper_succeeds(db_session):
    row = PendingEditService(db_session).submit(
        paper_id=None,
        hf_username="alice",
        edit_type="new_conference",
        proposed_payload={
            "name": "Conference on Long-context Research 2027",
            "year": 2027,
            "start_date": "2027-05-03",
            "end_date": "2027-05-07",
            "venue": " Vancouver Convention Centre ",
            "url": "https://example.org/conference",
        },
    )

    assert row.id is not None
    assert row.paper_id is None
    assert row.proposed_payload == {
        "name": "Conference on Long-context Research 2027",
        "year": 2027,
        "start_date": "2027-05-03",
        "end_date": "2027-05-07",
        "venue": "Vancouver Convention Centre",
        "url": "https://example.org/conference",
    }


def test_submit_directory_conference_suggestion_rejects_invalid_url(db_session):
    with pytest.raises(PendingEditError, match="HTTP"):
        PendingEditService(db_session).submit(
            paper_id=None,
            hf_username="alice",
            edit_type="new_conference",
            proposed_payload={
                "name": "Conference on Long-context Research 2027",
                "year": 2027,
                "url": "example.org/conference",
            },
        )
    _no_rows_created(db_session)


def test_submit_non_taxonomy_edit_without_paper_rejects(db_session):
    with pytest.raises(PendingEditError, match="paper_id is required"):
        PendingEditService(db_session).submit(
            paper_id=None,
            hf_username="alice",
            edit_type="tasks",
            proposed_payload={"task_ids": [1]},
        )
    _no_rows_created(db_session)


def test_submit_repositories_noop_rejects(db_session, paper_fixture):
    service = PendingEditService(db_session)
    with pytest.raises(PendingEditError, match="does not contain any changes"):
        service.submit(
            paper_id=1,
            hf_username="alice",
            edit_type="repositories",
            proposed_payload={
                "repositories": [
                    {"url": "https://github.com/owner/repo", "is_official": True},
                ]
            },
        )
    _no_rows_created(db_session)


def test_submit_repositories_is_official_flip_succeeds(db_session, paper_fixture):
    row = PendingEditService(db_session).submit(
        paper_id=1,
        hf_username="alice",
        edit_type="repositories",
        proposed_payload={
            "repositories": [
                {"url": "https://github.com/owner/repo", "is_official": False},
            ]
        },
    )
    assert row.id is not None


def test_submit_project_pages_noop_rejects(db_session, paper_fixture):
    service = PendingEditService(db_session)
    with pytest.raises(PendingEditError, match="does not contain any changes"):
        service.submit(
            paper_id=1,
            hf_username="alice",
            edit_type="project_pages",
            proposed_payload={
                "project_pages": [
                    {"url": "https://example.com/project", "is_official": False},
                ]
            },
        )
    _no_rows_created(db_session)


def test_submit_source_url_noop_rejects(db_session, paper_fixture):
    service = PendingEditService(db_session)
    with pytest.raises(PendingEditError, match="does not contain any changes"):
        service.submit(
            paper_id=1,
            hf_username="alice",
            edit_type="source_url",
            # Same URL with surrounding whitespace — should still be a no-op.
            proposed_payload={"source_url": "  https://example.com/paper  "},
        )
    _no_rows_created(db_session)


def test_submit_source_url_change_succeeds(db_session, paper_fixture):
    row = PendingEditService(db_session).submit(
        paper_id=1,
        hf_username="alice",
        edit_type="source_url",
        proposed_payload={"source_url": "https://example.com/paper/v2"},
    )
    assert row.id is not None
    assert row.proposed_payload == {"source_url": "https://example.com/paper/v2"}


def test_submit_hf_artifacts_noop_rejects(db_session, paper_fixture):
    service = PendingEditService(db_session)
    with pytest.raises(PendingEditError, match="does not contain any changes"):
        service.submit(
            paper_id=1,
            hf_username="alice",
            edit_type="hf_artifacts",
            proposed_payload={
                "hf_models": [],
                "hf_datasets": [],
                "hf_spaces": [],
            },
        )
    _no_rows_created(db_session)


def test_submit_hf_artifacts_change_succeeds(db_session, paper_fixture):
    row = PendingEditService(db_session).submit(
        paper_id=1,
        hf_username="alice",
        edit_type="hf_artifacts",
        proposed_payload={
            "hf_models": ["https://huggingface.co/org/model-a"],
            "hf_datasets": ["https://huggingface.co/datasets/org/data-a"],
            "hf_spaces": ["https://huggingface.co/spaces/org/demo-a"],
        },
    )
    assert row.id is not None
    assert row.proposed_payload["hf_models"] == [
        "https://huggingface.co/org/model-a",
    ]


def test_submit_hf_artifacts_invalid_bucket_rejects(db_session, paper_fixture):
    service = PendingEditService(db_session)
    with pytest.raises(PendingEditError, match="not a Hugging Face model"):
        service.submit(
            paper_id=1,
            hf_username="alice",
            edit_type="hf_artifacts",
            proposed_payload={
                "hf_models": ["https://huggingface.co/datasets/org/data-a"],
                "hf_datasets": [],
                "hf_spaces": [],
            },
        )
    _no_rows_created(db_session)


def test_submit_tasks_empty_against_empty_paper_rejects(db_session):
    db_session.add(
        DBPaper(
            id=2,
            title="P2",
            abstract=None,
            source="external",
            source_url="https://example.com/p2",
            arxiv_id=None,
        )
    )
    db_session.commit()

    service = PendingEditService(db_session)
    with pytest.raises(PendingEditError, match="does not contain any changes"):
        service.submit(
            paper_id=2,
            hf_username="alice",
            edit_type="tasks",
            proposed_payload={"task_ids": []},
        )
    _no_rows_created(db_session)


def test_submit_evaluations_create_succeeds(db_session, paper_fixture):
    row = PendingEditService(db_session).submit(
        paper_id=1,
        hf_username="alice",
        edit_type="evaluations",
        proposed_payload={
            "operations": [
                {
                    "op": "create",
                    "data": {
                        "task_id": 1,
                        "dataset_id": 99,
                        "model_name": "TestModel",
                        "metrics": {"Accuracy": "91.2"},
                        "best_metric": "Accuracy",
                        "is_open": True,
                    },
                }
            ]
        },
    )
    assert row.id is not None
    assert row.status == "pending"
    assert row.proposed_payload["operations"][0]["op"] == "create"


def test_adjusted_task_approval_is_atomic_audited_and_idempotent(db_session):
    service = PendingEditService(db_session)
    submitted = service.submit(
        paper_id=None,
        hf_username="alice",
        hf_subject="hf-alice",
        edit_type="new_task",
        proposed_payload={"name": "Original task"},
    )
    reviewed = service.approve(
        edit_id=submitted.id,
        reviewer_username="admin",
        reviewer_hf_subject="hf-admin",
        resolved_payload={"name": "Reviewed task", "keywords": "reviewed"},
    )
    assert reviewed.status == "approved"
    assert reviewed.proposed_payload == {"name": "Original task"}
    assert reviewed.applied_payload == {"name": "Reviewed task", "keywords": "reviewed"}
    assert reviewed.result_entity_type == "task"
    assert (
        db_session.get(DBTask, int(reviewed.result_entity_id)).slug == "reviewed-task"
    )
    event = db_session.get(CatalogMutationEvent, reviewed.catalog_event_id)
    assert event.entity_type == "submission_created_task"
    with pytest.raises(PendingEditAlreadyReviewedError):
        service.approve(edit_id=submitted.id, reviewer_username="admin")


def test_failed_taxonomy_application_leaves_submission_pending(
    db_session, paper_fixture
):
    row = PendingEditService(db_session).submit(
        paper_id=None,
        hf_username="alice",
        edit_type="new_task",
        proposed_payload={"name": "Task A"},
    )
    with pytest.raises(ValueError, match="already exists"):
        PendingEditService(db_session).approve(
            edit_id=row.id, reviewer_username="admin"
        )
    db_session.expire_all()
    persisted = db_session.get(PendingPaperEdit, row.id)
    assert persisted.status == "pending"
    assert persisted.failure_reason


def test_benchmark_metric_method_and_conference_approvals_use_canonical_tables(
    db_session, paper_fixture
):
    service = PendingEditService(db_session)
    method = service.submit(
        paper_id=None,
        hf_username="method-user",
        edit_type="new_method",
        proposed_payload={
            "name": "Verified Method",
            "source_url": "https://example.org/method",
        },
    )
    method = service.approve(edit_id=method.id, reviewer_username="admin")
    assert db_session.get(DBMethod, int(method.result_entity_id)) is not None

    benchmark = service.submit(
        paper_id=None,
        hf_username="benchmark-user",
        edit_type="new_benchmark",
        proposed_payload={
            "name": "Verified Benchmark",
            "description": "A benchmark.",
            "task_ids": [1],
        },
    )
    benchmark = service.approve(edit_id=benchmark.id, reviewer_username="admin")
    dataset_id = int(benchmark.result_entity_id)
    assert db_session.get(DBDataset, dataset_id) is not None
    assert db_session.get(TaskDataset, (1, dataset_id)) is not None

    metric = service.submit(
        paper_id=None,
        hf_username="metric-user",
        edit_type="new_metric",
        proposed_payload={
            "name": "Verified Score",
            "description": "A score.",
            "direction": "higher_is_better",
            "task_id": 1,
            "dataset_id": dataset_id,
        },
    )
    metric = service.approve(edit_id=metric.id, reviewer_username="admin")
    metric_id = int(metric.result_entity_id)
    assert db_session.get(DBMetric, metric_id) is not None
    assert db_session.get(TaskDatasetMetric, (1, dataset_id, metric_id)) is not None

    conference = service.submit(
        paper_id=None,
        hf_username="conference-user",
        edit_type="new_conference",
        proposed_payload={
            "name": "Verified Conference 2027",
            "year": 2027,
            "url": "https://example.org/conference-2027",
        },
    )
    conference = service.approve(edit_id=conference.id, reviewer_username="admin")
    assert db_session.get(DBConference, int(conference.result_entity_id)) is not None


def test_created_entity_rollback_is_append_only(db_session):
    service = PendingEditService(db_session)
    row = service.submit(
        paper_id=None,
        hf_username="alice",
        edit_type="new_task",
        proposed_payload={"name": "Rollback task"},
    )
    row = service.approve(edit_id=row.id, reviewer_username="admin")
    event = db_session.get(CatalogMutationEvent, row.catalog_event_id)
    task_id = int(row.result_entity_id)
    rollback = SubmissionRollbackService(db_session).rollback(
        event=event,
        actor={"hf_subject": "hf-admin", "username": "admin", "role": "admin"},
        request_id="test-rollback",
    )
    assert db_session.get(DBTask, task_id) is None
    assert rollback.operation == "rollback"
    assert rollback.rollback_of_event_id == event.id
    assert db_session.get(PendingPaperEdit, row.id).status == "approved"


def test_created_entity_rollback_refuses_after_later_dependency(
    db_session, paper_fixture
):
    service = PendingEditService(db_session)
    row = service.submit(
        paper_id=None,
        hf_username="alice",
        edit_type="new_task",
        proposed_payload={"name": "Now referenced"},
    )
    row = service.approve(edit_id=row.id, reviewer_username="admin")
    event = db_session.get(CatalogMutationEvent, row.catalog_event_id)
    task_id = int(row.result_entity_id)
    db_session.add(PaperTask(paper_id=1, task_id=task_id))
    db_session.commit()
    with pytest.raises(HTTPException) as error:
        SubmissionRollbackService(db_session).rollback(
            event=event,
            actor={"hf_subject": "hf-admin", "username": "admin", "role": "admin"},
            request_id="test-conflict",
        )
    assert error.value.status_code == 409
    assert db_session.get(DBTask, task_id) is not None


def test_active_submission_limit_is_database_backed(
    db_session, paper_fixture, monkeypatch
):
    current = Settings(submission_max_active_pending=1)
    monkeypatch.setattr(
        "backend.services.pending_edit_service.get_settings", lambda: current
    )
    service = PendingEditService(db_session)
    service.submit(
        paper_id=1,
        hf_username="alice",
        hf_subject="hf-alice",
        edit_type="tasks",
        proposed_payload={"task_ids": [1]},
    )
    with pytest.raises(SubmissionRateLimitError, match="Active pending"):
        service.submit(
            paper_id=1,
            hf_username="alice",
            hf_subject="hf-alice",
            edit_type="methods",
            proposed_payload={"method_ids": [10, 11]},
        )


def test_idempotent_replay_does_not_create_another_row(db_session, paper_fixture):
    service = PendingEditService(db_session)
    first = service.submit(
        paper_id=1,
        hf_username="alice",
        hf_subject="hf-alice",
        idempotency_key="same-request",
        edit_type="tasks",
        proposed_payload={"task_ids": [1]},
    )
    replay = service.submit(
        paper_id=1,
        hf_username="alice",
        hf_subject="hf-alice",
        idempotency_key="same-request",
        edit_type="tasks",
        proposed_payload={"task_ids": [1]},
    )
    assert replay.id == first.id
    assert db_session.query(PendingPaperEdit).count() == 1
    with pytest.raises(PendingEditError, match="another payload"):
        service.submit(
            paper_id=1,
            hf_username="alice",
            hf_subject="hf-alice",
            idempotency_key="same-request",
            edit_type="tasks",
            proposed_payload={"task_ids": [1, 2, 3]},
        )


def test_suspension_blocks_new_submission_without_deleting_history(
    db_session, paper_fixture
):
    service = PendingEditService(db_session)
    existing = service.submit(
        paper_id=1,
        hf_username="alice",
        hf_subject="hf-alice",
        edit_type="tasks",
        proposed_payload={"task_ids": [1]},
    )
    profile = db_session.get(UserProfile, "hf-alice")
    profile.is_submission_suspended = True
    db_session.commit()
    with pytest.raises(SubmissionSuspendedError):
        service.submit(
            paper_id=1,
            hf_username="alice",
            hf_subject="hf-alice",
            edit_type="methods",
            proposed_payload={"method_ids": [10, 11]},
        )
    assert db_session.get(PendingPaperEdit, existing.id).status == "pending"
