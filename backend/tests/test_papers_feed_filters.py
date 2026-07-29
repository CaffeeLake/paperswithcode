from datetime import date

import pytest
from fastapi.testclient import TestClient

from backend.database.connection import get_database_session
from backend.main import create_app
from backend.models.api import Papers
from backend.services.conference_service import ConferenceService
from backend.services.method_service import MethodService
from backend.services.organization_service import OrganizationService
from backend.services.paper_service import PaperService
from backend.services.task_service import TaskService


@pytest.fixture
def client():
    app = create_app()

    def override_get_database_session():
        yield object()

    app.dependency_overrides[get_database_session] = override_get_database_session

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("time_window", "expected"),
    [
        ("today", date(2026, 5, 6)),
        ("week", date(2026, 5, 4)),
        ("month", date(2026, 5, 1)),
        ("all_time", None),
    ],
)
def test_time_window_to_published_after(time_window, expected):
    assert (
        PaperService._get_published_after_for_time_window(
            time_window,
            today=date(2026, 5, 6),
        )
        == expected
    )


@pytest.mark.parametrize(
    ("order_by", "time_window"),
    [
        ("trending", "week"),
        ("date_published", "today"),
        ("citation_count", "all_time"),
        ("citation_count", "month"),
    ],
)
def test_papers_endpoint_accepts_feed_order_and_time(
    client,
    monkeypatch,
    order_by,
    time_window,
):
    captured = {}

    def fake_get_papers(self, **kwargs):
        captured.update(kwargs)
        return Papers(count=0, next_page=None, previous_page=None, results=[])

    monkeypatch.setattr(PaperService, "get_papers", fake_get_papers)

    response = client.get(f"/api/v1/papers/?order_by={order_by}&time={time_window}")

    assert response.status_code == 200
    assert captured["order_by"] == order_by
    assert captured["order_dir"] == "desc"
    assert captured["time_window"] == time_window


@pytest.mark.parametrize(
    ("path", "service_class", "method_name"),
    [
        ("/api/v1/papers/", PaperService, "get_papers"),
        ("/api/v1/tasks/object-detection/papers", TaskService, "get_task_papers"),
        ("/api/v1/methods/transformer/papers", MethodService, "get_method_papers"),
        (
            "/api/v1/conferences/cvpr-2026/papers",
            ConferenceService,
            "get_conference_papers",
        ),
        (
            "/api/v1/organizations/nvidia/papers",
            OrganizationService,
            "get_organization_papers",
        ),
    ],
)
def test_paper_feed_endpoints_accept_has_code(
    client,
    monkeypatch,
    path,
    service_class,
    method_name,
):
    captured = {}

    def fake_feed(self, **kwargs):
        captured.update(kwargs)
        return Papers(count=0, next_page=None, previous_page=None, results=[])

    monkeypatch.setattr(service_class, method_name, fake_feed)

    response = client.get(path, params={"has_code": "true"})

    assert response.status_code == 200
    assert captured["has_code"] is True


def test_papers_endpoint_rejects_unknown_order_by(client, monkeypatch):
    def fake_get_papers(self, **kwargs):
        return Papers(count=0, next_page=None, previous_page=None, results=[])

    monkeypatch.setattr(PaperService, "get_papers", fake_get_papers)

    response = client.get("/api/v1/papers/?order_by=title&time=week")

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("order_dir", "expected_order"),
    [
        ("desc", "papers.date_published DESC NULLS LAST"),
        ("asc", "papers.date_published ASC NULLS LAST"),
    ],
)
def test_date_published_feed_places_undated_papers_last(order_dir, expected_order):
    class FakeQuery:
        def __init__(self):
            self.order_clause = None

        def filter(self, *args):
            return self

        def order_by(self, clause):
            self.order_clause = clause
            return self

        def count(self):
            return 0

        def offset(self, value):
            return self

        def limit(self, value):
            return self

        def all(self):
            return []

    class FakeDatabase:
        def __init__(self):
            self.query_result = FakeQuery()

        def query(self, *args):
            return self.query_result

    database = FakeDatabase()

    response = PaperService(database).get_papers(
        order_by="date_published",
        order_dir=order_dir,
    )

    assert response.results == []
    assert str(database.query_result.order_clause) == expected_order


def test_trending_endpoint_deduplicates_view_rows_by_paper():
    app = create_app()
    captured = {}

    class EmptyResult:
        def fetchall(self):
            return []

    class FakeDatabase:
        def execute(self, statement, params):
            captured["sql"] = str(statement)
            captured["params"] = params
            return EmptyResult()

    def override_get_database_session():
        yield FakeDatabase()

    app.dependency_overrides[get_database_session] = override_get_database_session

    with TestClient(app) as test_client:
        response = test_client.get("/api/v1/papers/trending?limit=30&max_age_days=365")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == []
    assert "PARTITION BY tp.paper_id" in captured["sql"]
    assert "paper_repo_rank = 1" in captured["sql"]
    # Each GitHub repository should contribute at most one paper to the
    # trending list; when several latest papers share a repo we keep the
    # most recently published one.
    assert "PARTITION BY repository_id" in captured["sql"]
    assert "repo_paper_rank = 1" in captured["sql"]
    assert captured["params"]["limit"] == 30


def test_trending_feed_uses_official_repository_ema_scores():
    captured = {}

    class EmptyResult:
        def fetchall(self):
            return []

    class FakeDatabase:
        def execute(self, statement, params):
            captured["sql"] = str(statement)
            captured["params"] = params
            return EmptyResult()

    service = PaperService(FakeDatabase())

    response = service._get_trending_papers(page=1, page_size=20)

    assert response.count == 0
    assert "pr.is_official = TRUE" in captured["sql"]
    assert "r.trending_score" in captured["sql"]
    assert "repository_star_history" not in captured["sql"]
    assert "MAX(rsh.num_stars)" not in captured["sql"]
    # Repository-level dedup: prevents two trending papers from sharing the
    # same GitHub URL (e.g. older + newer paper pointing at the same repo).
    assert "PARTITION BY repository_id" in captured["sql"]
    assert "repo_paper_rank = 1" in captured["sql"]


def test_trending_feed_filters_to_linked_repositories_when_requested():
    captured = {}

    class EmptyResult:
        def fetchall(self):
            return []

    class FakeDatabase:
        def execute(self, statement, params):
            captured["sql"] = str(statement)
            captured["params"] = params
            return EmptyResult()

    response = PaperService(FakeDatabase())._get_trending_papers(
        page=1,
        page_size=20,
        has_code=True,
    )

    assert response.count == 0
    assert "EXISTS" in captured["sql"]
    assert "code_pr.paper_id = p.id" in captured["sql"]
    assert captured["params"]["has_code"] is True
