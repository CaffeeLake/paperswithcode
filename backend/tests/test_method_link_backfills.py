"""Focused contracts for method-link provenance and historical backfills."""

from datetime import date
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.models.database import (
    Base,
    Method,
    MethodKeywordBackfillRun,
    MethodReferenceBackfillMonth,
    Paper,
    PaperMethod,
    PaperMethodEvidence,
    PaperMethodExclusion,
)
from backend.services.method_backfill_service import (
    run_keyword_backfill,
    run_reference_backfill,
)
from backend.services.paper_method_link_service import (
    replace_manual_links,
    upsert_evidence_links,
)


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_element, _compiler, **_kw):
    return "JSON"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_element, _compiler, **_kw):
    return "JSON"


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Paper.__table__,
            Method.__table__,
            PaperMethod.__table__,
            PaperMethodEvidence.__table__,
            PaperMethodExclusion.__table__,
            MethodReferenceBackfillMonth.__table__,
            MethodKeywordBackfillRun.__table__,
        ],
    )
    return sessionmaker(bind=engine)()


def _paper(paper_id: int, title: str, published: date | None = None) -> Paper:
    return Paper(
        id=paper_id,
        source="arxiv",
        arxiv_id=f"2601.{paper_id:05d}",
        version="v1",
        is_latest_version=True,
        title=title,
        abstract="",
        date_published=published,
    )


def test_evidence_is_idempotent_and_manual_removal_is_a_durable_veto():
    db = _session()
    db.add_all([_paper(1, "CLIP"), Method(id=10, name="CLIP", slug="clip")])
    db.commit()

    link = [{"paper_id": 1, "method_id": 10}]
    upsert_evidence_links(db, link, evidence_type="keyword")
    upsert_evidence_links(db, link, evidence_type="keyword")
    db.commit()
    assert db.query(PaperMethodEvidence).count() == 1

    replace_manual_links(db, paper_id=1, method_ids=[])
    db.commit()
    assert db.query(PaperMethod).count() == 0
    assert db.query(PaperMethodEvidence).count() == 0
    assert db.get(PaperMethodExclusion, (1, 10)) is not None

    upsert_evidence_links(db, link, evidence_type="reference")
    db.commit()
    assert db.query(PaperMethod).count() == 0

    replace_manual_links(db, paper_id=1, method_ids=[10])
    db.commit()
    assert db.get(PaperMethodExclusion, (1, 10)) is None
    assert db.get(PaperMethodEvidence, (1, 10, "manual")) is not None


def test_keyword_backfill_covers_sourced_and_sourceless_methods_and_resumes():
    db = _session()
    db.add_all(
        [
            _paper(1, "CLIP improves vision", date(2021, 3, 1)),
            _paper(2, "A transformer study", None),
            Method(
                id=10,
                name="CLIP",
                slug="clip",
                keywords="CLIP",
                source_paper_id=1,
            ),
            Method(
                id=11,
                name="Transformer",
                slug="transformer",
                keywords="transformer",
            ),
        ]
    )
    db.commit()

    first = run_keyword_backfill(db, limit=1, dry_run=False)
    second = run_keyword_backfill(db, limit=10, dry_run=False, resume=True)
    rerun = run_keyword_backfill(db, limit=10, dry_run=False, resume=True)

    assert first.papers_processed == 1
    assert second.papers_processed == 1
    assert rerun.links_written == 0
    assert db.get(PaperMethodEvidence, (1, 10, "keyword")) is not None
    assert db.get(PaperMethodEvidence, (2, 11, "keyword")) is not None
    run = db.query(MethodKeywordBackfillRun).one()
    assert run.status == "complete"
    assert run.cursor_paper_id == 2


class _ReferenceClient:
    def __init__(self):
        self.api_calls = 0
        self.api_errors = 0
        self.rate_limit_hits = 0

    def iter_references(self, identifier):
        self.api_calls += 1
        if identifier == "arXiv:2601.00003":
            return iter(
                [
                    SimpleNamespace(semantic_scholar_id="source-a", arxiv_id=None),
                    SimpleNamespace(semantic_scholar_id="source-b", arxiv_id=None),
                ]
            )
        return iter([])


class _FailingReferenceClient:
    api_calls = 0
    api_errors = 0
    rate_limit_hits = 0

    def iter_references(self, _identifier):
        self.api_calls += 1
        self.api_errors += 1
        return iter([])


def test_reference_backfill_fetches_each_paper_once_for_multiple_methods():
    db = _session()
    db.add_all(
        [
            _paper(1, "Source A", date(2026, 1, 1)),
            _paper(2, "Source B", date(2026, 1, 2)),
            _paper(3, "Citing paper", date(2026, 1, 3)),
        ]
    )
    db.flush()
    db.get(Paper, 1).semantic_scholar_id = "source-a"
    db.get(Paper, 2).semantic_scholar_id = "source-b"
    db.add_all(
        [
            Method(id=10, name="A", slug="a", source_paper_id=1),
            Method(id=11, name="B", slug="b", source_paper_id=2),
        ]
    )
    db.commit()
    client = _ReferenceClient()

    stats = run_reference_backfill(
        db,
        client,
        method_ids=[10, 11],
        month_from=date(2026, 1, 1),
        month_to=date(2026, 1, 1),
        limit=10,
        dry_run=False,
    )

    assert client.api_calls == 3
    assert stats.matches == 2
    assert db.get(PaperMethodEvidence, (3, 10, "reference")) is not None
    assert db.get(PaperMethodEvidence, (3, 11, "reference")) is not None
    assert all(
        row.status == "complete" for row in db.query(MethodReferenceBackfillMonth).all()
    )


def test_failed_reference_lookup_does_not_advance_the_month_cursor():
    db = _session()
    paper = _paper(1, "Source", date(2026, 1, 1))
    paper.semantic_scholar_id = "source"
    db.add_all([paper, Method(id=10, name="A", slug="a", source_paper_id=1)])
    db.commit()

    stats = run_reference_backfill(
        db,
        _FailingReferenceClient(),
        method_ids=[10],
        month_from=date(2026, 1, 1),
        month_to=date(2026, 1, 1),
        limit=10,
        dry_run=False,
    )

    progress = db.get(MethodReferenceBackfillMonth, (10, date(2026, 1, 1)))
    assert stats.papers_failed == 1
    assert progress.processed_papers == 0
    assert progress.cursor_published_at is None
    assert progress.cursor_paper_id is None
    assert progress.retryable_failures == 1
