from datetime import date
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.database.connection import get_database_session
from backend.main import create_app
from backend.models.api import Paper, Papers
from backend.models.database import (
    Conference as DBConference,
    Framework as DBFramework,
    Method as DBMethod,
    Organization as DBOrganization,
    Paper as DBPaper,
    Repository as DBRepository,
    Task as DBTask,
)
from backend.utils.exceptions import PaperNotFoundError
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


def test_papers_endpoint_forwards_repository_scope(client, monkeypatch):
    captured = {}

    def fake_get_papers(self, **kwargs):
        captured.update(kwargs)
        return Papers(count=0, next_page=None, previous_page=None, results=[])

    monkeypatch.setattr(PaperService, "get_papers", fake_get_papers)

    response = client.get(
        "/api/v1/papers/",
        params={"repository": "https://github.com/HuggingFace/LeRobot"},
    )

    assert response.status_code == 200
    assert captured["repository"] == "https://github.com/HuggingFace/LeRobot"
    assert captured["framework"] is None


def test_papers_endpoint_forwards_catalog_filters(client, monkeypatch):
    captured = {}

    def fake_get_papers(self, **kwargs):
        captured.update(kwargs)
        return Papers(count=0, next_page=None, previous_page=None, results=[])

    monkeypatch.setattr(PaperService, "get_papers", fake_get_papers)

    response = client.get(
        "/api/v1/papers/",
        params={
            "task": "Image Classification",
            "method": "Vision Transformer",
            "conference": "CVPR 2026",
            "framework": "vLLM",
            "organization": "Qwen",
        },
    )

    assert response.status_code == 200
    assert captured["task"] == "Image Classification"
    assert captured["method"] == "Vision Transformer"
    assert captured["conference"] == "CVPR 2026"
    assert captured["framework"] == "vLLM"
    assert captured["organization"] == "Qwen"


def test_papers_endpoint_rejects_framework_and_repository(client):
    response = client.get(
        "/api/v1/papers/",
        params={"framework": "lerobot", "repository": "huggingface/lerobot"},
    )

    assert response.status_code == 422
    assert "mutually exclusive" in response.json()["detail"]


def test_papers_endpoint_returns_not_found_for_unknown_framework(client, monkeypatch):
    def fake_get_papers(self, **kwargs):
        raise PaperNotFoundError("Framework with slug 'missing' not found")

    monkeypatch.setattr(PaperService, "get_papers", fake_get_papers)

    response = client.get("/api/v1/papers/", params={"framework": "missing"})

    assert response.status_code == 404
    assert "Framework" in response.json()["detail"]


class ScopeQuery:
    def __init__(self, first_result=None, papers=None):
        self.first_result = first_result
        self.papers = papers or []
        self.filters = []
        self.offset_value = None
        self.limit_value = None

    def outerjoin(self, *args):
        return self

    def join(self, *args):
        return self

    def filter(self, *args):
        self.filters.extend(args)
        return self

    def first(self):
        return self.first_result

    def order_by(self, *args):
        return self

    def count(self):
        return len(self.papers)

    def offset(self, value):
        self.offset_value = value
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def all(self):
        start = self.offset_value or 0
        end = start + self.limit_value if self.limit_value is not None else None
        return self.papers[start:end]


class ScopeDatabase:
    def __init__(
        self,
        repository=None,
        framework=None,
        introducing_paper=None,
        papers=None,
        tasks=None,
        task=None,
        method=None,
        organization=None,
        conference=None,
    ):
        self.repository = repository
        self.framework = framework
        self.introducing_paper = introducing_paper
        self.paper_query = ScopeQuery(papers=papers)
        self.tasks = tasks or []
        self.task = task
        self.method = method
        self.organization = organization
        self.conference = conference
        self.repository_query = None

    def query(self, *entities):
        if entities == (DBFramework, DBRepository, DBPaper):
            return ScopeQuery(
                first_result=(
                    (self.framework, self.repository, self.introducing_paper)
                    if self.framework
                    else None
                )
            )
        if entities == (DBRepository,):
            self.repository_query = ScopeQuery(first_result=self.repository)
            return self.repository_query
        if entities == (DBPaper,):
            return self.paper_query
        if entities == (DBTask,):
            return ScopeQuery(first_result=self.task, papers=self.tasks)
        if entities == (DBMethod,):
            return ScopeQuery(first_result=self.method)
        if entities == (DBOrganization,):
            return ScopeQuery(first_result=self.organization)
        if entities == (DBConference,):
            return ScopeQuery(first_result=self.conference)
        raise AssertionError(f"Unexpected query: {entities}")


def test_repository_scope_normalizes_url_and_resolves_case_insensitively():
    repository = SimpleNamespace(
        id=41,
        owner="huggingface",
        name="lerobot",
        url="https://github.com/huggingface/lerobot",
    )
    database = ScopeDatabase(repository=repository)

    repository_id, scope = PaperService(database)._resolve_paper_feed_scope(
        framework=None,
        repository="https://github.com/HuggingFace/LeRobot/tree/main/examples",
    )

    assert repository_id == 41
    assert scope.repository == "huggingface/lerobot"
    filter_sql = " ".join(str(item) for item in database.repository_query.filters)
    assert "lower(repositories.owner)" in filter_sql
    assert "lower(repositories.name)" in filter_sql


def test_unknown_repository_is_an_empty_scoped_feed():
    response = PaperService(ScopeDatabase()).get_papers(
        repository="unknown/project",
        order_by="trending",
    )

    assert response.count == 0
    assert response.applied_filters == {
        "task": "Image Classification",
        "method": "Vision Transformer",
        "conference": "CVPR 2026",
        "organization": "Qwen",
    }
    assert response.scope.repository == "unknown/project"


def test_unknown_framework_is_not_found():
    with pytest.raises(PaperNotFoundError):
        PaperService(ScopeDatabase()).get_papers(framework="missing")


def test_framework_scope_includes_resource_links():
    repository = SimpleNamespace(
        id=41,
        owner="huggingface",
        name="lerobot",
        url="https://github.com/huggingface/lerobot",
        num_stars=26_414,
    )
    framework = SimpleNamespace(
        id=7,
        repository_id=41,
        slug="lerobot",
        name="LeRobot",
    )
    introducing_paper = SimpleNamespace(arxiv_id="2602.22818")
    tasks = [SimpleNamespace(id=9, slug="robotics", name="Robotics")]

    repository_id, scope = PaperService(
        ScopeDatabase(
            repository=repository,
            framework=framework,
            introducing_paper=introducing_paper,
            tasks=tasks,
        )
    )._resolve_paper_feed_scope(framework="lerobot", repository=None)

    assert repository_id == 41
    assert scope.github_url == repository.url
    assert scope.num_stars == repository.num_stars
    assert scope.introducing_paper_arxiv_id == introducing_paper.arxiv_id
    assert [task.slug for task in scope.recommended_tasks] == ["robotics"]


def test_paper_list_combines_exact_taxonomy_filters(monkeypatch):
    database = ScopeDatabase(
        task=SimpleNamespace(id=1),
        method=SimpleNamespace(id=2),
        organization=SimpleNamespace(id=3),
        conference=SimpleNamespace(id=4),
    )
    service = PaperService(database)
    monkeypatch.setattr(service, "_get_paper_relation_data", lambda *args, **kwargs: {})

    response = service.get_papers(
        task="Image Classification",
        method="Vision Transformer",
        organization="Qwen",
        conference="CVPR 2026",
        order_by="date_published",
    )

    assert response.count == 0
    filter_sql = " ".join(str(item) for item in database.paper_query.filters)
    assert "paper_tasks" in filter_sql
    assert "paper_methods" in filter_sql
    assert "paper_organizations" in filter_sql
    assert "paper_conferences" in filter_sql


def test_paper_list_rejects_unknown_exact_taxonomy_filter():
    with pytest.raises(PaperNotFoundError, match="Organization 'Missing' not found"):
        PaperService(ScopeDatabase()).get_papers(organization="Missing")


def test_repository_trending_uses_scoped_order_and_keeps_all_papers(monkeypatch):
    repository = SimpleNamespace(
        id=41,
        owner="huggingface",
        name="lerobot",
        url="https://github.com/huggingface/lerobot",
    )
    papers = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
    database = ScopeDatabase(repository=repository, papers=papers)
    service = PaperService(database)
    scoped_order_calls = []
    monkeypatch.setattr(
        service,
        "apply_scoped_trending_order",
        lambda query: scoped_order_calls.append(query) or query,
    )
    monkeypatch.setattr(service, "_get_paper_relation_data", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        service,
        "_convert_db_paper_to_api",
        lambda paper, **kwargs: Paper.model_construct(id=str(paper.id)),
    )

    response = service.get_papers(
        repository="HuggingFace/LeRobot",
        order_by="trending",
        latest_only=False,
        page=2,
        page_size=1,
        search="robot",
        time_window="month",
        has_hf_artifacts=True,
    )

    assert [paper.id for paper in response.results] == ["2"]
    assert response.count == 2
    assert response.next_page is None
    assert response.previous_page == 1
    assert scoped_order_calls == [database.paper_query]
    filter_sql = " ".join(str(item) for item in database.paper_query.filters)
    assert "is_latest_version" in filter_sql
    assert "paper_hf_artifacts" in filter_sql
    assert "lower(papers.title)" in filter_sql
    assert "papers.date_published" in filter_sql


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
@pytest.mark.parametrize("filter_name", ["has_code", "has_hf_artifacts"])
def test_paper_feed_endpoints_accept_resource_filters(
    client,
    monkeypatch,
    path,
    service_class,
    method_name,
    filter_name,
):
    captured = {}

    def fake_feed(self, **kwargs):
        captured.update(kwargs)
        return Papers(count=0, next_page=None, previous_page=None, results=[])

    monkeypatch.setattr(service_class, method_name, fake_feed)

    response = client.get(path, params={filter_name: "true"})

    assert response.status_code == 200
    assert captured[filter_name] is True


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


def test_trending_feed_filters_to_linked_hf_artifacts_when_requested():
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
        has_hf_artifacts=True,
    )

    assert response.count == 0
    assert "paper_hf_artifacts" in captured["sql"]
    assert "artifact_link.paper_id = p.id" in captured["sql"]
    assert captured["params"]["has_hf_artifacts"] is True
