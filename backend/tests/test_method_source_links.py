from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.models.database import (
    Base,
    Method as DBMethod,
    Paper as DBPaper,
    PaperMethod,
)
from backend.services.paper_service import PaperService


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_element, _compiler, **_kw):
    return "TEXT"


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_element, _compiler, **_kw):
    return "TEXT"


def test_paper_response_keeps_source_paper_id_on_methods_without_url_fallback():
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
            title="Source Paper",
            abstract="Introduces one method and uses another.",
            arxiv_id="2212.04356",
            version="v1",
            is_latest_version=True,
            date_published=date(2022, 12, 8),
        )
        introduced_method = DBMethod(
            id=1,
            name="Whisper",
            slug="whisper",
            source_paper_id=1,
            source_url="/paper/2212.04356",
        )
        used_method = DBMethod(
            id=2,
            name="Transformer",
            slug="transformer",
        )
        source_url_only_method = DBMethod(
            id=3,
            name="Legacy URL Match",
            slug="legacy-url-match",
            source_url="/paper/2212.04356",
        )
        db.add_all([paper, introduced_method, used_method, source_url_only_method])
        db.add_all(
            [
                PaperMethod(paper_id=1, method_id=1),
                PaperMethod(paper_id=1, method_id=2),
            ]
        )
        db.commit()

        response = PaperService(db).get_paper_by_arxiv_id("2212.04356")

    assert [method.name for method in response.methods or []] == [
        "Transformer",
        "Whisper",
    ]
    introduced_methods = [
        method
        for method in response.methods or []
        if method.source_paper_id == response.id
    ]
    assert [method.name for method in introduced_methods] == ["Whisper"]
