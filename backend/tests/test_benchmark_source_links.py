from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.models.database import (
    Base,
    Dataset as DBDataset,
    Paper as DBPaper,
)
from backend.services.paper_service import PaperService


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_element, _compiler, **_kw):
    return "TEXT"


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_element, _compiler, **_kw):
    return "TEXT"


def test_paper_response_includes_introduced_benchmarks():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    with SessionLocal() as db:
        paper = DBPaper(
            id=1,
            title="Terminal-Bench Paper",
            abstract="Introduces the Terminal Bench benchmark.",
            arxiv_id="2601.11868",
            version="v1",
            is_latest_version=True,
            date_published=date(2026, 1, 24),
        )
        introduced = DBDataset(
            id=10,
            name="Terminal Bench",
            slug="terminal-bench",
            full_name="Terminal-Bench",
            introducing_paper_id=1,
            introducing_paper_title="Terminal-Bench Paper",
            paper_url="https://arxiv.org/abs/2601.11868",
            introduced_year=2026,
        )
        unrelated = DBDataset(
            id=11,
            name="Other Dataset",
            slug="other-dataset",
        )
        db.add_all([paper, introduced, unrelated])
        db.commit()

        response = PaperService(db).get_paper_by_arxiv_id("2601.11868")

    assert response.introduced_benchmarks is not None
    assert [b.slug for b in response.introduced_benchmarks] == ["terminal-bench"]
    assert response.introduced_benchmarks[0].name == "Terminal Bench"
    assert response.introduced_benchmarks[0].introduced_year == 2026


def test_paper_without_introduced_benchmarks_returns_none():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    with SessionLocal() as db:
        paper = DBPaper(
            id=1,
            title="Some Paper",
            abstract="Does not introduce any benchmark.",
            arxiv_id="1234.5678",
            version="v1",
            is_latest_version=True,
            date_published=date(2024, 1, 1),
        )
        db.add(paper)
        db.commit()

        response = PaperService(db).get_paper_by_arxiv_id("1234.5678")

    assert response.introduced_benchmarks is None
