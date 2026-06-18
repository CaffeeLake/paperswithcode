"""Tests for the Organizations API papers endpoint.

Focused coverage for `order_by=trending` on `/api/v1/organizations/{slug}/papers`,
ensuring organization feeds rank by the same active trending metric as the home
feed (composite paper-level score or official-repo velocity).
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.config import get_settings
from backend.database.connection import get_database_session
from backend.main import create_app
from backend.models.database import (
    Base,
    Organization,
    Paper as DBPaper,
    PaperOrganization,
    PaperRepository as DBPaperRepository,
    Repository as DBRepository,
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


# Trending scores older than 24h are treated as missing, so test rows stamp a
# fresh timestamp to be eligible for the trending sort.
_FRESH = datetime.now(timezone.utc)
_STALE = datetime.now(timezone.utc) - timedelta(hours=48)


def override_get_database_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def _pin_trending_mode(monkeypatch, mode: str) -> None:
    """Force the active trending ranking mode for a test, regardless of env."""
    monkeypatch.setattr(get_settings(), "trending_ranking_mode", mode)


@pytest.fixture
def org_client():
    """Organization `acme` whose papers carry both repo velocity and composite
    paper-level trending scores.

      - Paper 1: papers.trending_score=80 (fresh), official repo velocity 1.0
      - Paper 2: papers.trending_score=40 (fresh), official repo velocity 50.0
      - Paper 3: papers.trending_score=99 but STALE (must be ignored)
      - Paper 4: no paper-level trending_score, no repo
    """
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    org = Organization(id=1, name="Acme", slug="acme")
    db.add(org)

    specs = {
        1: (80.0, _FRESH),
        2: (40.0, _FRESH),
        3: (99.0, _STALE),
        4: (None, None),
    }
    for paper_id, (score, stamp) in specs.items():
        db.add(
            DBPaper(
                id=paper_id,
                title=f"Paper {paper_id}",
                abstract=f"Abstract {paper_id}",
                arxiv_id=f"2025.2{paper_id:04d}",
                version="v1",
                is_latest_version=True,
                source="arxiv",
                trending_score=score,
                trending_score_updated_at=stamp,
            )
        )
        db.add(PaperOrganization(paper_id=paper_id, organization_id=1, source="test"))

    repos = [
        DBRepository(
            id=1,
            url="https://github.com/owner/repo-1",
            owner="owner",
            name="repo-1",
            num_stars=100,
            trending_score=1.0,
            trending_score_updated_at=_FRESH,
            source="test",
        ),
        DBRepository(
            id=2,
            url="https://github.com/owner/repo-2",
            owner="owner",
            name="repo-2",
            num_stars=100,
            trending_score=50.0,
            trending_score_updated_at=_FRESH,
            source="test",
        ),
    ]
    db.add_all(repos)
    db.commit()
    db.add_all(
        [
            DBPaperRepository(paper_id=1, repository_id=1, is_official=True),
            DBPaperRepository(paper_id=2, repository_id=2, is_official=True),
        ]
    )
    db.commit()
    db.close()

    app = create_app()
    app.dependency_overrides[get_database_session] = override_get_database_session

    with TestClient(app) as test_client:
        yield test_client

    Base.metadata.drop_all(bind=engine)


def test_organization_papers_trending_composite_ranks_by_paper_score(
    org_client, monkeypatch
):
    """In composite mode, organization papers rank by `papers.trending_score`.

    Paper 1 (score 80) beats Paper 2 (score 40) despite Paper 2's much higher
    repo velocity, proving the paper-level score drives the order.
    """
    _pin_trending_mode(monkeypatch, "composite")
    response = org_client.get(
        "/api/v1/organizations/acme/papers?order_by=trending&page_size=10"
    )

    assert response.status_code == 200
    data = response.json()
    titles = [paper["title"] for paper in data["results"]]

    assert titles[:2] == ["Paper 1", "Paper 2"]
    assert set(titles[2:]) == {"Paper 3", "Paper 4"}
    assert data["count"] == 4


def test_organization_papers_trending_github_ranks_by_repo_velocity(
    org_client, monkeypatch
):
    """In github mode, organization papers rank by official-repo velocity.

    Paper 2's repo velocity (50.0) now outranks Paper 1's (1.0), the inverse of
    composite mode.
    """
    _pin_trending_mode(monkeypatch, "github")
    response = org_client.get(
        "/api/v1/organizations/acme/papers?order_by=trending&page_size=10"
    )

    assert response.status_code == 200
    data = response.json()
    titles = [paper["title"] for paper in data["results"]]

    assert titles[:2] == ["Paper 2", "Paper 1"]
    assert set(titles[2:]) == {"Paper 3", "Paper 4"}
    assert data["count"] == 4


if __name__ == "__main__":
    pytest.main([__file__])
