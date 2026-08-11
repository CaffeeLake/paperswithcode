"""Focused contracts for the dataset task-list projection."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database.connection import get_database_session
from backend.main import create_app
from backend.models.database import (
    Area,
    Base,
    Dataset,
    Paper,
    PaperTask,
    Task,
    TaskDataset,
)
from backend.services.dataset_service import DatasetService


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_element, _compiler, **_kwargs):
    return "TEXT"


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_element, _compiler, **_kwargs):
    return "TEXT"


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(engine, "connect")
def _register_jsonb_typeof(dbapi_connection, _connection_record):
    dbapi_connection.create_function("jsonb_typeof", 1, lambda _value: "array")


TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _database_override():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    db.add(Area(id=7, name="Vision"))
    db.add_all(
        [
            Dataset(id=10, name="Mixed Dataset", slug="Mixed-Slug"),
            Dataset(id=11, name="Empty Dataset", slug="empty-dataset"),
        ]
    )
    db.add_all(
        [
            Task(id=90, name="Parent Task", slug="parent-task", level=0),
            Task(
                id=1,
                name="Alpha Task",
                slug="alpha-task",
                description="Alpha description",
                keywords="alpha,task",
                level=0,
                image_url="https://example.test/alpha.png",
                image_credit="Example",
            ),
            Task(
                id=2,
                name="Zulu Task",
                slug="zulu-task",
                parent_id=90,
                area_id=7,
                level=1,
                research_trends=["This field used to default in this response."],
            ),
            Task(id=3, name="Paper Only Task", slug="paper-only", level=0),
        ]
    )
    db.add_all(
        Paper(
            id=paper_id,
            title=f"Paper {paper_id}",
            arxiv_id=f"2608.{paper_id:05d}",
            version="v1",
            is_latest_version=True,
        )
        for paper_id in range(1, 4)
    )
    db.add_all(
        [
            TaskDataset(task_id=1, dataset_id=10),
            TaskDataset(task_id=2, dataset_id=10),
            PaperTask(paper_id=1, task_id=1),
            PaperTask(paper_id=2, task_id=1),
            PaperTask(paper_id=3, task_id=3),
        ]
    )
    db.commit()
    db.close()

    app = create_app()
    app.dependency_overrides[get_database_session] = _database_override
    with TestClient(app) as test_client:
        yield test_client

    Base.metadata.drop_all(bind=engine)


def _selects_during(request):
    statements: list[str] = []

    def record(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        response = request()
    finally:
        event.remove(engine, "before_cursor_execute", record)
    return response, statements


def test_numeric_dataset_task_list_is_one_grouped_query(client):
    response, statements = _selects_during(
        lambda: client.get("/api/v1/datasets/10/tasks/")
    )

    assert response.status_code == 200
    assert len(statements) == 1
    assert response.json()["count"] == 2
    assert [task["name"] for task in response.json()["results"]] == [
        "Alpha Task",
        "Zulu Task",
    ]
    assert [task["paper_count"] for task in response.json()["results"]] == [2, 0]


def test_dataset_task_list_preserves_fields_defaults_and_membership(client):
    response = client.get("/api/v1/datasets/10/tasks/")

    assert response.status_code == 200
    alpha, zulu = response.json()["results"]
    assert set(zulu) == {
        "id",
        "name",
        "description",
        "research_trends",
        "slug",
        "keywords",
        "parent_id",
        "area_id",
        "level",
        "paper_count",
        "benchmark_count",
        "evaluation_count",
        "image_url",
        "image_credit",
        "created_at",
        "updated_at",
    }
    assert alpha | {"created_at": None, "updated_at": None} == {
        "id": "1",
        "name": "Alpha Task",
        "description": "Alpha description",
        "research_trends": [],
        "slug": "alpha-task",
        "keywords": "alpha,task",
        "parent_id": None,
        "area_id": None,
        "level": 0,
        "paper_count": 2,
        "benchmark_count": None,
        "evaluation_count": None,
        "image_url": "https://example.test/alpha.png",
        "image_credit": "Example",
        "created_at": None,
        "updated_at": None,
    }
    assert zulu["id"] == "2"
    assert zulu["parent_id"] == "90"
    assert zulu["area_id"] == "7"
    assert zulu["paper_count"] == 0
    assert zulu["research_trends"] == []
    assert all(task["name"] != "Paper Only Task" for task in (alpha, zulu))
    assert isinstance(alpha["paper_count"], int)
    assert isinstance(alpha["created_at"], str)
    assert isinstance(alpha["updated_at"], str)


def test_dataset_slug_resolution_is_case_insensitive_and_bounded(client):
    response, statements = _selects_during(
        lambda: client.get("/api/v1/datasets/mIxEd-sLuG/tasks/")
    )

    assert response.status_code == 200
    assert response.json()["count"] == 2
    assert len(statements) == 2


def test_missing_slug_and_numeric_id_preserve_distinct_behavior(client):
    missing_slug = client.get("/api/v1/datasets/not-a-dataset/tasks/")
    missing_numeric = client.get("/api/v1/datasets/999/tasks/")

    assert missing_slug.status_code == 404
    assert missing_slug.json() == {
        "detail": "Dataset with slug 'not-a-dataset' not found"
    }
    assert missing_numeric.status_code == 200
    assert missing_numeric.json() == {"count": 0, "results": []}


def test_existing_dataset_without_task_membership_returns_empty_list(client):
    response = client.get("/api/v1/datasets/empty-dataset/tasks/")

    assert response.status_code == 200
    assert response.json() == {"count": 0, "results": []}


def test_legacy_dataset_task_id_contract_remains_a_list_of_ints(client):
    with TestingSessionLocal() as db:
        task_ids = DatasetService(db).get_dataset_tasks(10)

    assert set(task_ids) == {1, 2}
    assert all(isinstance(task_id, int) for task_id in task_ids)
