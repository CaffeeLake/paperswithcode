"""Contract, paper-indexing, and idempotency tests for Artificial Analysis."""

import asyncio
from datetime import UTC, date, datetime
from types import SimpleNamespace

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from backend.models.database import (
    Base,
    Dataset,
    Evaluation,
    Metric,
    Paper,
    PaperTask,
    Task,
    TaskDatasetMetric,
)
from backend.services import artificial_analysis_sync_service as aa


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
@compiles(TSVECTOR, "sqlite")
def _compile_postgres_types_sqlite(_element, _compiler, **_kw):
    return "JSON"


def _api_row(slug: str, score: float = 42.5):
    return {
        "slug": slug,
        "name": slug.replace("-", " ").title(),
        "release_date": "2026-08-01",
        "evaluations": {"artificial_analysis_intelligence_index": score},
    }


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_fetches_every_api_page_and_validates_reviewed_models(monkeypatch):
    identity = aa.PaperIdentity(arxiv_id="2608.00001", is_open=True)
    monkeypatch.setattr(aa, "MODEL_PAPER_IDENTITIES", {"reviewed-model": identity})
    monkeypatch.setattr(aa, "MIN_EXPECTED_MODELS", 2)
    pages = [
        {
            "intelligence_index_version": "4.1",
            "pagination": {"has_more": True, "total_pages": 2},
            "data": [_api_row("reviewed-model")],
        },
        {
            "intelligence_index_version": "4.1",
            "pagination": {"has_more": False, "total_pages": 2},
            "data": [_api_row("other-model", 12.3)],
        },
    ]

    class Client:
        def get(self, url, *, headers, params):
            assert url == aa.API_ENDPOINT
            assert headers == {"x-api-key": "secret"}
            assert params["page_size"] == 200
            return _Response(pages[params["page"] - 1])

    leaderboard = aa.fetch_artificial_analysis_leaderboard(
        api_key="secret", client=Client()
    )

    assert leaderboard.index_version == "4.1"
    assert [entry.slug for entry in leaderboard.entries] == [
        "reviewed-model",
        "other-model",
    ]


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Paper.__table__,
            Task.__table__,
            Dataset.__table__,
            Metric.__table__,
            TaskDatasetMetric.__table__,
            Evaluation.__table__,
            PaperTask.__table__,
        ],
    )
    session = Session(engine)
    task = Task(id=14, name="Agents", slug=aa.TASK_SLUG)
    dataset = Dataset(id=581, name="Artificial Analysis", slug=aa.DATASET_SLUG)
    metric = Metric(id=1, name=aa.METRIC_NAME, direction="higher_is_better")
    session.add_all([task, dataset, metric])
    session.add(
        TaskDatasetMetric(task_id=task.id, dataset_id=dataset.id, metric_id=metric.id)
    )
    session.commit()
    return session


def test_discovery_indexes_missing_arxiv_and_external_papers(monkeypatch):
    session = _session()
    identities = {
        "arxiv-model": aa.PaperIdentity(arxiv_id="2608.00001", is_open=True),
        "external-model": aa.external(
            "https://example.com/release", "External Model", "2026-08-01"
        ),
    }
    monkeypatch.setattr(aa, "MODEL_PAPER_IDENTITIES", identities)

    class Ingestion:
        async def get_or_import_arxiv_paper(self, arxiv_id):
            paper = Paper(
                title="Arxiv Model",
                arxiv_id=arxiv_id,
                source="arxiv",
                version="v1",
                is_latest_version=True,
            )
            session.add(paper)
            session.flush()
            return paper, True

    class External:
        def add_external_resource(self, payload):
            paper = Paper(
                title=payload.title,
                source="external",
                source_url=payload.source_url,
                date_published=payload.date_published,
                version="v1",
                is_latest_version=True,
            )
            session.add(paper)
            session.flush()
            return SimpleNamespace(paper=SimpleNamespace(id=paper.id))

    result = asyncio.run(
        aa.ArtificialAnalysisPaperDiscoveryService(
            session,
            ingestion_service=Ingestion(),
            external_service=External(),
        ).discover()
    )

    assert set(result.papers) == set(identities)
    assert result.indexed_papers == ["2608.00001", "https://example.com/release"]


def test_sync_adopts_existing_row_and_is_idempotent(monkeypatch):
    session = _session()
    paper = Paper(
        id=7,
        title="Reviewed Model",
        arxiv_id="2608.00001",
        source="arxiv",
        version="v1",
        is_latest_version=True,
    )
    session.add(paper)
    session.flush()
    source_url = f"{aa.SOURCE_URL_PREFIX}reviewed-model"
    session.add(
        Evaluation(
            paper_id=paper.id,
            task_id=14,
            dataset_id=581,
            model_name="Old label",
            metrics={aa.METRIC_NAME: 1.0},
            best_metric=aa.METRIC_NAME,
            external_source_url=source_url,
        )
    )
    session.commit()
    monkeypatch.setattr(
        aa,
        "MODEL_PAPER_IDENTITIES",
        {"reviewed-model": aa.PaperIdentity(arxiv_id="2608.00001", is_open=True)},
    )
    leaderboard = aa.ArtificialAnalysisLeaderboard(
        "4.1",
        [
            aa.ArtificialAnalysisEntry(
                "reviewed-model", "Reviewed Model (high)", 42.5, date(2026, 8, 1)
            )
        ],
    )
    discovery = aa.ArtificialAnalysisDiscovery(papers={"reviewed-model": paper.id})
    now = datetime(2026, 8, 14, tzinfo=UTC)

    first = aa.ArtificialAnalysisSyncService(session).sync(
        leaderboard, discovery=discovery, fetched_at=now
    )
    second = aa.ArtificialAnalysisSyncService(session).sync(
        leaderboard, discovery=discovery, fetched_at=now
    )

    row = session.query(Evaluation).one()
    assert first.updated == second.updated == 1
    assert first.created == second.created == 0
    assert row.model_name == "Reviewed Model (high)"
    assert row.metrics == {aa.METRIC_NAME: 42.5}
    assert row.is_open is True
    assert row.source_url == source_url
    assert session.query(PaperTask).count() == 1
