from datetime import date

import pytest
from fastapi.testclient import TestClient

from backend.database.connection import get_database_session
from backend.main import create_app
from backend.models.api import Papers
from backend.services.paper_service import PaperService


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


def test_papers_endpoint_rejects_unknown_order_by(client, monkeypatch):
    def fake_get_papers(self, **kwargs):
        return Papers(count=0, next_page=None, previous_page=None, results=[])

    monkeypatch.setattr(PaperService, "get_papers", fake_get_papers)

    response = client.get("/api/v1/papers/?order_by=title&time=week")

    assert response.status_code == 422


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
