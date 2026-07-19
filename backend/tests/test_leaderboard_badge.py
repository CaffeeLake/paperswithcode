from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.routers import papers
from backend.services.badge_service import (
    LeaderboardBadgePlacement,
    leaderboard_rank_message,
    render_leaderboard_badge,
)
from backend.utils.exceptions import PaperNotFoundError


def _rank(value: int, dataset_name: str = "Benchmark", evaluation_id: str = "1"):
    return SimpleNamespace(
        best_rank=value,
        dataset_name=dataset_name,
        evaluation_id=evaluation_id,
    )


def test_rank_message_names_each_top_three_benchmark():
    assert (
        leaderboard_rank_message([_rank(3, "RealSR"), _rank(1, "DIV2K-Val")])
        == "SOTA on DIV2K-Val · #3 on RealSR"
    )
    assert leaderboard_rank_message([]) == "unranked"


def test_rank_message_keeps_showing_a_placement_below_top_three():
    placement = LeaderboardBadgePlacement(dataset_name="RealSR", best_rank=4)

    assert leaderboard_rank_message([placement]) == "#4 on RealSR"


def test_svg_is_accessible_and_uses_ranked_color():
    svg = render_leaderboard_badge([_rank(1, "DIV2K-Val"), _rank(3, "RealSR")])

    assert (
        "Papers with Code leaderboard ranking: SOTA on DIV2K-Val · #3 on RealSR" in svg
    )
    assert 'role="img"' in svg
    assert "#16837a" in svg


def test_badge_endpoint_returns_live_svg_for_requested_evaluation(monkeypatch):
    class FakePaperService:
        def __init__(self, db):
            pass

        def get_paper_by_id_or_arxiv(self, paper_id):
            assert paper_id == "2605.23264"
            return SimpleNamespace(
                id="42",
                leaderboard_ranks=[
                    _rank(1, "DIV2K-Val", "12885"),
                    _rank(3, "RealSR", "12886"),
                ],
            )

    monkeypatch.setattr(papers, "PaperService", FakePaperService)
    query = SimpleNamespace(
        join=lambda *args, **kwargs: query,
        filter=lambda *args, **kwargs: query,
        first=lambda: (1, "DIV2K-Val"),
    )
    db = SimpleNamespace(query=lambda *args, **kwargs: query)
    response = papers.get_paper_leaderboard_badge(
        "2605.23264", evaluation_id=12885, db=db
    )

    assert response.media_type == "image/svg+xml"
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert b"SOTA" in response.body
    assert b"RealSR" not in response.body


def test_badge_endpoint_returns_404_for_unknown_paper(monkeypatch):
    class MissingPaperService:
        def __init__(self, db):
            pass

        def get_paper_by_id_or_arxiv(self, paper_id):
            raise PaperNotFoundError("missing")

    monkeypatch.setattr(papers, "PaperService", MissingPaperService)
    with pytest.raises(HTTPException) as exc:
        papers.get_paper_leaderboard_badge("missing", evaluation_id=None, db=object())

    assert exc.value.status_code == 404
