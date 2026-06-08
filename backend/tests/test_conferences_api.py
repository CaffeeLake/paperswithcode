"""Conference API tests."""

from collections import Counter
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database.conferences_setup.cvpr2026_best_paper_finalist_order import (
    CVPR_2026_BEST_PAPER_FINALIST_ARXIV_ORDER,
)
from backend.database.connection import get_database_session
from backend.main import create_app
from backend.models.database import (
    Base,
    Conference,
    Paper,
    PaperConference,
    PaperRepository,
    Repository,
)


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
    db = TestingSessionLocal()

    conference = Conference(
        id=1,
        name="CVPR 2099",
        slug="cvpr-2099",
        short_name="CVPR",
        year=2099,
        url="https://example.com/",
        start_date=date(2099, 6, 1),
        end_date=date(2099, 6, 5),
    )
    db.add(conference)

    repo = Repository(
        id=1,
        url="https://github.com/example/repo",
        owner="example",
        name="repo",
        num_stars=0,
        trending_score=1.0,
        source="test",
    )
    db.add(repo)

    for idx in range(15):
        paper = Paper(
            id=idx + 1,
            arxiv_id=f"2099.{idx:05d}",
            title=f"Oral Paper {idx}",
            version="v1",
            is_latest_version=True,
            source="arxiv",
            proceeding="CVPR 2099 Oral",
        )
        db.add(paper)
        db.add(
            PaperConference(
                paper_id=paper.id, conference_id=conference.id, source="test"
            )
        )
        db.add(
            PaperRepository(
                paper_id=paper.id,
                repository_id=repo.id,
                is_official=True,
            )
        )

    db.commit()
    db.close()

    app = create_app()
    app.dependency_overrides[get_database_session] = override_get_database_session

    with TestClient(app) as test_client:
        yield test_client

    Base.metadata.drop_all(bind=engine)


def _fetch_all_pages(client, url: str) -> list[str]:
    page = 1
    ids: list[str] = []
    while True:
        response = client.get(f"{url}&page={page}&page_size=5")
        assert response.status_code == 200
        data = response.json()
        ids.extend(paper["id"] for paper in data["results"])
        if data.get("next_page") is None:
            break
        page = data["next_page"]
    return ids


def test_conference_oral_papers_pagination_has_no_duplicate_ids(client):
    """Offset pagination must use a stable sort so papers never repeat across pages."""
    for order_by in ("trending", "date_published", "citation_count"):
        ids = _fetch_all_pages(
            client,
            f"/api/v1/conferences/cvpr-2099/papers?presentation=oral&order_by={order_by}&order_dir=desc",
        )
        counts = Counter(ids)
        duplicates = [paper_id for paper_id, n in counts.items() if n > 1]
        assert duplicates == [], (
            f"order_by={order_by} returned duplicate paper ids: {duplicates}"
        )
        assert len(ids) == 15


@pytest.fixture
def award_client():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    conference = Conference(
        id=2,
        name="CVPR 2098",
        slug="cvpr-2098",
        short_name="CVPR",
        year=2098,
        url="https://example.com/",
        start_date=date(2098, 6, 1),
        end_date=date(2098, 6, 5),
    )
    db.add(conference)

    award_specs = [
        ("outstanding", "Outstanding Paper A"),
        ("honorable_mention", "Honorable Mention Paper"),
        ("best_paper_finalist", "Best Paper Finalist A"),
        ("best_paper_finalist", "Best Paper Finalist B"),
        (None, "Regular Paper"),
    ]
    for idx, (award, title) in enumerate(award_specs, start=1):
        paper = Paper(
            id=100 + idx,
            arxiv_id=f"2098.{idx:05d}",
            title=title,
            version="v1",
            is_latest_version=True,
            source="arxiv",
            proceeding="CVPR 2098",
        )
        db.add(paper)
        db.add(
            PaperConference(
                paper_id=paper.id,
                conference_id=conference.id,
                source="test",
                award=award,
            )
        )

    db.commit()
    db.close()

    app = create_app()
    app.dependency_overrides[get_database_session] = override_get_database_session

    with TestClient(app) as test_client:
        yield test_client

    Base.metadata.drop_all(bind=engine)


def test_conference_award_counts_exclude_best_paper_finalists_from_outstanding(
    award_client,
):
    response = award_client.get("/api/v1/conferences/cvpr-2098/areas-with-tasks")
    assert response.status_code == 200
    data = response.json()
    assert data["outstanding_paper_count"] == 2
    assert data["best_paper_finalist_paper_count"] == 2


def test_conference_best_paper_finalist_papers_filter(award_client):
    response = award_client.get(
        "/api/v1/conferences/cvpr-2098/papers?presentation=best_paper_finalist"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    titles = {paper["title"] for paper in data["results"]}
    assert titles == {"Best Paper Finalist A", "Best Paper Finalist B"}
    assert all(
        paper["conference_award"] == "best_paper_finalist" for paper in data["results"]
    )


def test_conference_outstanding_papers_filter_excludes_best_paper_finalists(
    award_client,
):
    response = award_client.get(
        "/api/v1/conferences/cvpr-2098/papers?presentation=outstanding"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    awards = {paper["conference_award"] for paper in data["results"]}
    assert awards == {"outstanding", "honorable_mention"}


@pytest.fixture
def cvpr_2026_finalist_client():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    conference = Conference(
        id=3,
        name="CVPR 2026",
        slug="cvpr-2026",
        short_name="CVPR",
        year=2026,
        url="https://example.com/",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 5),
    )
    db.add(conference)

    for idx, arxiv_id in enumerate(reversed(CVPR_2026_BEST_PAPER_FINALIST_ARXIV_ORDER)):
        paper = Paper(
            id=200 + idx,
            arxiv_id=arxiv_id,
            title=f"Finalist {arxiv_id}",
            version="v1",
            is_latest_version=True,
            source="arxiv",
            proceeding="CVPR 2026 Best Paper Finalist",
        )
        db.add(paper)
        db.add(
            PaperConference(
                paper_id=paper.id,
                conference_id=conference.id,
                source="test",
                award="best_paper_finalist",
            )
        )

    db.commit()
    db.close()

    app = create_app()
    app.dependency_overrides[get_database_session] = override_get_database_session

    with TestClient(app) as test_client:
        yield test_client

    Base.metadata.drop_all(bind=engine)


def test_cvpr_2026_best_paper_finalists_follow_announcement_order(
    cvpr_2026_finalist_client,
):
    response = cvpr_2026_finalist_client.get(
        "/api/v1/conferences/cvpr-2026/papers?presentation=best_paper_finalist"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == len(CVPR_2026_BEST_PAPER_FINALIST_ARXIV_ORDER)
    assert [
        paper["arxiv_id"] for paper in data["results"]
    ] == CVPR_2026_BEST_PAPER_FINALIST_ARXIV_ORDER
