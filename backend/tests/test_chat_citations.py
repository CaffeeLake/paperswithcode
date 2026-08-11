from datetime import date
from types import SimpleNamespace

from backend.models.chat import CitationSnapshot
from backend.services import chat_citation_service
from backend.services.paper_service import PaperNotFoundError


def test_citation_snapshot_remains_compatible_with_legacy_rows():
    snapshot = CitationSnapshot.model_validate(
        {
            "position": 0,
            "route_id": "2501.00001",
            "title": "Legacy citation",
            "source_url": "https://arxiv.org/abs/2501.00001",
        }
    )

    assert snapshot.thumbnail_url is None
    assert snapshot.arxiv_id is None
    assert snapshot.citation_count is None


def test_resolve_citations_includes_hover_preview_metadata(monkeypatch):
    paper = SimpleNamespace(
        id="9",
        arxiv_id="2501.00001",
        title="Previewable paper",
        source_url=None,
        url_abs="https://arxiv.org/abs/2501.00001",
        thumbnail_url="/api/thumbnails/2501_00001_v1.jpg",
        authors=["Ada Lovelace"],
        published=date(2025, 1, 2),
        conference_name="ICLR 2025",
        conference=None,
        citation_count=42,
    )

    class FakePaperService:
        def __init__(self, _db):
            pass

        def get_paper_by_id_or_arxiv(self, route_id):
            assert route_id == "2501.00001"
            return paper

    monkeypatch.setattr(chat_citation_service, "PaperService", FakePaperService)

    citations = chat_citation_service.resolve_citations(
        object(), "[paper](paper:2501.00001)"
    )

    assert citations == [
        {
            "position": 0,
            "route_id": "2501.00001",
            "title": "Previewable paper",
            "source_url": "https://arxiv.org/abs/2501.00001",
            "thumbnail_url": "/api/thumbnails/2501_00001_v1.jpg",
            "arxiv_id": "2501.00001",
            "authors": ["Ada Lovelace"],
            "published": "2025-01-02",
            "conference": "ICLR 2025",
            "citation_count": 42,
        }
    ]


def test_resolution_tracks_requested_aliases_and_strips_unresolved_links(monkeypatch):
    paper = SimpleNamespace(
        id="9",
        arxiv_id="2501.00001",
        title="Previewable paper",
        source_url=None,
        url_abs="https://arxiv.org/abs/2501.00001",
        thumbnail_url=None,
        authors=[],
        published=None,
        conference_name=None,
        conference=None,
        citation_count=0,
    )

    class FakePaperService:
        def __init__(self, _db):
            pass

        def get_paper_by_id_or_arxiv(self, route_id):
            if route_id == "9":
                return paper
            raise PaperNotFoundError(route_id)

    monkeypatch.setattr(chat_citation_service, "PaperService", FakePaperService)
    text = "[valid alias](paper:9) and [placeholder](paper:<cfg>)"

    citations, targets = chat_citation_service.resolve_citation_targets(object(), text)

    assert [item["route_id"] for item in citations] == ["2501.00001"]
    assert targets == {"9": "2501.00001"}
    assert chat_citation_service.normalize_paper_links(text, targets) == (
        "[valid alias](paper:2501.00001) and placeholder"
    )
