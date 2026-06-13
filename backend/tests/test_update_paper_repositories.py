"""Tests for PaperService.update_paper_repositories deduplication."""

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.models.database import (
    Base,
    Paper as DBPaper,
    PaperRepository,
    Repository as DBRepository,
)
from backend.services.paper_service import PaperService


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
def paper_with_duplicate_repo_urls(db_session):
    db_session.add(
        DBPaper(
            id=1,
            title="Paper",
            abstract="Abstract",
            arxiv_id="2104.01778",
        )
    )
    db_session.add_all(
        [
            DBRepository(
                id=10,
                url="https://github.com/pwc-1/Paper-8",
                owner="pwc-1",
                name="Paper-8",
            ),
            DBRepository(
                id=11,
                url="https://github.com/pwc-1/Paper-8/tree/main/audio_spectrogram",
                owner="pwc-1",
                name="Paper-8",
            ),
            DBRepository(
                id=12,
                url="https://github.com/huggingface/transformers",
                owner="huggingface",
                name="transformers",
            ),
        ]
    )
    db_session.add_all(
        [
            PaperRepository(paper_id=1, repository_id=10, is_official=True),
            PaperRepository(paper_id=1, repository_id=11, is_official=False),
        ]
    )
    db_session.commit()


def test_update_paper_repositories_dedupes_same_github_repo(
    db_session, paper_with_duplicate_repo_urls
):
    service = PaperService(db_session)
    service.update_paper_repositories(
        1,
        [
            {"url": "https://github.com/pwc-1/Paper-8", "is_official": True},
            {
                "url": "https://github.com/pwc-1/Paper-8/tree/main/audio_spectrogram",
                "is_official": False,
            },
            {
                "url": "https://github.com/huggingface/transformers",
                "is_official": False,
            },
        ],
    )

    links = (
        db_session.query(PaperRepository)
        .filter(PaperRepository.paper_id == 1)
        .order_by(PaperRepository.repository_id)
        .all()
    )
    assert len(links) == 2
    assert links[0].repository_id == 10
    assert links[0].is_official is True
    assert links[1].repository_id == 12
    assert links[1].is_official is False
