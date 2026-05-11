"""
Tests for the Tasks API endpoints.

Focused regression coverage for the homepage "Top Domains" sidebar, which
relies on `/api/v1/tasks/?ordering=-paper_count` returning the tasks with
the most associated papers first.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.main import create_app
from backend.models.database import (
    Base,
    Paper as DBPaper,
    Task as DBTask,
    PaperTask,
    Repository as DBRepository,
    PaperRepository as DBPaperRepository,
)
from backend.database.connection import get_database_session


# The ORM uses Postgres-only types for unrelated columns; teach SQLite to
# render them as TEXT so the schema can be created in-memory for tests.
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

    with TestClient(app) as test_client:
        yield test_client

    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def tasks_with_uneven_paper_counts():
    """Create tasks linked to differing numbers of papers.

    Layout:
        - Language Modeling: 4 papers
        - Robotics: 3 papers
        - Object Detection: 1 paper
        - Speech Recognition: 0 papers
    """
    db = TestingSessionLocal()

    tasks = [
        DBTask(id=1, name="Language Modeling", slug="language-modeling", level=0),
        DBTask(id=2, name="Robotics", slug="robotics", level=0),
        DBTask(id=3, name="Object Detection", slug="object-detection", level=0),
        DBTask(id=4, name="Speech Recognition", slug="speech-recognition", level=0),
    ]
    db.add_all(tasks)

    papers = [
        DBPaper(
            id=i,
            title=f"Paper {i}",
            abstract=f"Abstract {i}",
            arxiv_id=f"2025.0{i:04d}",
            version="v1",
            is_latest_version=True,
        )
        for i in range(1, 9)
    ]
    db.add_all(papers)
    db.commit()

    associations = [
        # Language Modeling: 4 papers
        (1, 1),
        (2, 1),
        (3, 1),
        (4, 1),
        # Robotics: 3 papers
        (1, 2),
        (5, 2),
        (6, 2),
        # Object Detection: 1 paper
        (7, 3),
    ]
    db.add_all(
        PaperTask(paper_id=paper_id, task_id=task_id)
        for paper_id, task_id in associations
    )
    db.commit()
    db.close()


def test_tasks_ordering_by_paper_count_desc(client, tasks_with_uneven_paper_counts):
    """`ordering=-paper_count` returns tasks ranked by paper count desc."""
    response = client.get("/api/v1/tasks/?ordering=-paper_count&page_size=8")

    assert response.status_code == 200
    data = response.json()

    names = [task["name"] for task in data["results"]]
    counts = [task["paper_count"] for task in data["results"]]

    assert names[:3] == ["Language Modeling", "Robotics", "Object Detection"]
    assert counts[:3] == [4, 3, 1]
    assert "Speech Recognition" in names
    assert counts == sorted(counts, reverse=True)


def test_tasks_ordering_by_paper_count_asc(client, tasks_with_uneven_paper_counts):
    """`ordering=paper_count` returns tasks ranked by paper count asc."""
    response = client.get("/api/v1/tasks/?ordering=paper_count&page_size=8")

    assert response.status_code == 200
    data = response.json()

    counts = [task["paper_count"] for task in data["results"]]
    assert counts == sorted(counts)
    assert counts[0] == 0
    assert counts[-1] == 4


def test_tasks_default_ordering_unaffected(client, tasks_with_uneven_paper_counts):
    """Default ordering still sorts by name and reports counts correctly."""
    response = client.get("/api/v1/tasks/?page_size=8")

    assert response.status_code == 200
    data = response.json()

    names = [task["name"] for task in data["results"]]
    assert names == sorted(names)

    counts_by_name = {task["name"]: task["paper_count"] for task in data["results"]}
    assert counts_by_name["Language Modeling"] == 4
    assert counts_by_name["Robotics"] == 3
    assert counts_by_name["Object Detection"] == 1
    assert counts_by_name["Speech Recognition"] == 0


@pytest.fixture
def task_with_trending_papers():
    """Create one task with papers covering each trending edge case.

    Layout (all linked to task `audio-classification`):
      - Paper 1: official repo, trending_score=10.0 (highest score)
      - Paper 2: official repo, trending_score=2.5
      - Paper 3: official repo, trending_score=NULL (no fresh score)
      - Paper 4: non-official repo with trending_score=99.0 (must NOT win;
                 only official repos contribute to trending sort)
      - Paper 5: no repository at all
    """
    db = TestingSessionLocal()

    task = DBTask(
        id=1, name="Audio Classification", slug="audio-classification", level=0
    )
    db.add(task)

    papers = [
        DBPaper(
            id=i,
            title=f"Paper {i}",
            abstract=f"Abstract {i}",
            arxiv_id=f"2025.0{i:04d}",
            version="v1",
            is_latest_version=True,
        )
        for i in range(1, 6)
    ]
    db.add_all(papers)

    repositories = [
        DBRepository(
            id=1,
            url="https://github.com/owner/repo-1",
            owner="owner",
            name="repo-1",
            num_stars=500,
            trending_score=10.0,
        ),
        DBRepository(
            id=2,
            url="https://github.com/owner/repo-2",
            owner="owner",
            name="repo-2",
            num_stars=200,
            trending_score=2.5,
        ),
        DBRepository(
            id=3,
            url="https://github.com/owner/repo-3",
            owner="owner",
            name="repo-3",
            num_stars=50,
            trending_score=None,
        ),
        DBRepository(
            id=4,
            url="https://github.com/owner/repo-4",
            owner="owner",
            name="repo-4",
            num_stars=10000,
            trending_score=99.0,
        ),
    ]
    db.add_all(repositories)
    db.commit()

    db.add_all(
        [PaperTask(paper_id=i, task_id=1) for i in range(1, 6)]
        + [
            DBPaperRepository(paper_id=1, repository_id=1, is_official=True),
            DBPaperRepository(paper_id=2, repository_id=2, is_official=True),
            DBPaperRepository(paper_id=3, repository_id=3, is_official=True),
            DBPaperRepository(paper_id=4, repository_id=4, is_official=False),
        ]
    )
    db.commit()
    db.close()


def test_task_papers_trending_orders_by_official_repo_trending_score(
    client, task_with_trending_papers
):
    """`order_by=trending` ranks task papers by their best official repo score."""
    response = client.get(
        "/api/v1/tasks/audio-classification/papers?order_by=trending&page_size=10"
    )

    assert response.status_code == 200
    data = response.json()

    titles = [paper["title"] for paper in data["results"]]

    # Papers 1 and 2 have official trending scores (10.0 and 2.5) and must
    # come first, in that order. The remaining three papers have no
    # qualifying official trending score and follow.
    assert titles[:2] == ["Paper 1", "Paper 2"]
    assert set(titles[2:]) == {"Paper 3", "Paper 4", "Paper 5"}
    assert data["count"] == 5


def test_task_papers_trending_ignores_non_official_repos(
    client, task_with_trending_papers
):
    """A non-official repository's trending score must not influence ordering.

    Paper 4's only repo has `trending_score=99.0` but is not official, so it
    must not outrank Paper 1 (`trending_score=10.0` via official repo).
    """
    response = client.get(
        "/api/v1/tasks/audio-classification/papers?order_by=trending&page_size=10"
    )

    titles = [paper["title"] for paper in response.json()["results"]]

    assert titles.index("Paper 1") < titles.index("Paper 4")


def test_task_papers_default_ordering_unchanged(client, task_with_trending_papers):
    """Default ordering (date_published desc) is unaffected by trending logic."""
    response = client.get("/api/v1/tasks/audio-classification/papers?page_size=10")

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 5
    assert {paper["title"] for paper in data["results"]} == {
        f"Paper {i}" for i in range(1, 6)
    }


if __name__ == "__main__":
    pytest.main([__file__])
