"""Render small, dependency-free SVG badges for paper leaderboard rankings."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Iterable


@dataclass(frozen=True)
class LeaderboardBadgePlacement:
    dataset_name: str
    best_rank: int | None


def leaderboard_rank_message(ranks: Iterable[object]) -> str:
    """Pair each current placement with its benchmark name."""
    placements: list[tuple[int, str]] = []
    for rank in ranks:
        value = getattr(rank, "best_rank", None)
        benchmark = str(getattr(rank, "dataset_name", "") or "").strip()
        if isinstance(value, int) and value >= 1 and benchmark:
            placements.append((value, benchmark))

    placements.sort(key=lambda placement: (placement[0], placement[1].casefold()))
    return (
        " · ".join(
            f"{'SOTA' if value == 1 else f'#{value}'} on {benchmark}"
            for value, benchmark in placements
        )
        or "unranked"
    )


def render_leaderboard_badge(ranks: Iterable[object]) -> str:
    """Return a Shields-style SVG badge with the paper's current placements."""
    label = "Papers with Code"
    message = leaderboard_rank_message(ranks)
    label_width = 102
    message_width = max(58, round(len(message) * 6.7 + 16))
    width = label_width + message_width
    color = "#16837a" if message != "unranked" else "#8a8f98"
    title = escape(f"Papers with Code leaderboard ranking: {message}")
    message_text = escape(message)

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="20" role="img" aria-label="{title}">
  <title>{title}</title>
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#fff" stop-opacity=".12"/>
    <stop offset="1" stop-opacity=".12"/>
  </linearGradient>
  <clipPath id="r"><rect width="{width}" height="20" rx="3"/></clipPath>
  <g clip-path="url(#r)">
    <rect width="{label_width}" height="20" fill="#3a3b45"/>
    <rect x="{label_width}" width="{message_width}" height="20" fill="{color}"/>
    <rect width="{width}" height="20" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">
    <text x="{label_width / 2:g}" y="15" fill="#010101" fill-opacity=".3">{label}</text>
    <text x="{label_width / 2:g}" y="14">{label}</text>
    <text x="{label_width + message_width / 2:g}" y="15" fill="#010101" fill-opacity=".3">{message_text}</text>
    <text x="{label_width + message_width / 2:g}" y="14">{message_text}</text>
  </g>
</svg>"""
