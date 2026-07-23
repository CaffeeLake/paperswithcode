"""Tests for database-backed recommended frameworks on task pages."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database.connection import get_database_session
from backend.main import create_app
from backend.models.database import (
    Base,
    Repository as DBRepository,
    Task as DBTask,
    TaskRecommendedFramework as DBTaskRecommendedFramework,
)


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_element, _compiler, **_kw):
    return "TEXT"


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_element, _compiler, **_kw):
    return "TEXT"


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_database_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client():
    Base.metadata.create_all(bind=engine)
    app = create_app()
    app.dependency_overrides[get_database_session] = override_get_database_session

    db = TestingSessionLocal()
    db.add_all(
        [
            DBTask(id=1, name="Image Classification", slug="image-classification"),
            DBTask(id=2, name="Object Detection", slug="object-detection"),
            DBRepository(
                id=10,
                url="https://github.com/huggingface/transformers",
                owner="huggingface",
                name="transformers",
                num_stars=150_000,
            ),
            DBRepository(
                id=11,
                url="https://github.com/huggingface/pytorch-image-models",
                owner="huggingface",
                name="pytorch-image-models",
                num_stars=35_000,
            ),
        ]
    )
    db.add_all(
        [
            DBTaskRecommendedFramework(task_id=1, repository_id=11, display_order=1),
            DBTaskRecommendedFramework(task_id=1, repository_id=10, display_order=0),
        ]
    )
    db.commit()
    db.close()

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def test_task_page_returns_frameworks_in_display_order_with_stars(client):
    response = client.get("/api/v1/tasks/image-classification/page")

    assert response.status_code == 200
    assert response.json()["recommended_frameworks"] == [
        {
            "id": "10",
            "url": "https://github.com/huggingface/transformers",
            "owner": "huggingface",
            "name": "transformers",
            "num_stars": 150_000,
        },
        {
            "id": "11",
            "url": "https://github.com/huggingface/pytorch-image-models",
            "owner": "huggingface",
            "name": "pytorch-image-models",
            "num_stars": 35_000,
        },
    ]


def test_task_without_recommendations_returns_empty_list(client):
    response = client.get("/api/v1/tasks/object-detection/page")

    assert response.status_code == 200
    assert response.json()["recommended_frameworks"] == []
