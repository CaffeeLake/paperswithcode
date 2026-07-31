"""Render small, dependency-free SVG badges for paper leaderboard rankings."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Iterable

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from backend.models.database import (
    Dataset,
    Evaluation,
    EvaluationBadgeTombstone,
    Task,
)


@dataclass(frozen=True)
class LeaderboardBadgePlacement:
    dataset_name: str
    best_rank: int | None
    retired: bool = False


@dataclass(frozen=True)
class LeaderboardBadgeTarget:
    placement: LeaderboardBadgePlacement
    evaluation_id: int | None
    task_slug: str | None
    dataset_slug: str | None

    @property
    def retired(self) -> bool:
        return self.placement.retired


def _evaluation_target_query(db: Session, paper_id: int):
    return (
        db.query(
            Evaluation.id,
            Evaluation.best_rank,
            Dataset.name,
            Dataset.slug,
            Task.slug,
        )
        .join(Dataset, Evaluation.dataset_id == Dataset.id)
        .join(Task, Evaluation.task_id == Task.id)
        .filter(Evaluation.paper_id == paper_id)
    )


def _target_from_row(row) -> LeaderboardBadgeTarget:
    evaluation_id, best_rank, dataset_name, dataset_slug, task_slug = row
    return LeaderboardBadgeTarget(
        placement=LeaderboardBadgePlacement(
            dataset_name=dataset_name,
            best_rank=best_rank,
        ),
        evaluation_id=int(evaluation_id),
        task_slug=task_slug,
        dataset_slug=dataset_slug,
    )


def resolve_leaderboard_badge_target(
    db: Session,
    *,
    paper_id: int,
    evaluation_id: int,
) -> LeaderboardBadgeTarget | None:
    """Resolve a live, replacement, or retired target for a public badge URL."""
    live_row = (
        _evaluation_target_query(db, paper_id)
        .filter(Evaluation.id == evaluation_id)
        .first()
    )
    if live_row:
        return _target_from_row(live_row)

    tombstone = (
        db.query(EvaluationBadgeTombstone)
        .filter(
            EvaluationBadgeTombstone.evaluation_id == evaluation_id,
            EvaluationBadgeTombstone.paper_id == paper_id,
        )
        .first()
    )
    if tombstone is None:
        return None

    identity_filters = []
    if tombstone.task_id is not None and tombstone.dataset_id is not None:
        identity_filters.append(
            and_(
                Evaluation.task_id == tombstone.task_id,
                Evaluation.dataset_id == tombstone.dataset_id,
            )
        )
    if tombstone.task_slug and tombstone.dataset_slug:
        identity_filters.append(
            and_(
                Task.slug == tombstone.task_slug,
                Dataset.slug == tombstone.dataset_slug,
            )
        )

    if identity_filters:
        replacement = (
            _evaluation_target_query(db, paper_id)
            .filter(or_(*identity_filters))
            .order_by(Evaluation.best_rank.asc().nulls_last(), Evaluation.id.asc())
            .first()
        )
        if replacement:
            return _target_from_row(replacement)

    return LeaderboardBadgeTarget(
        placement=LeaderboardBadgePlacement(
            dataset_name=tombstone.dataset_name,
            best_rank=None,
            retired=True,
        ),
        evaluation_id=None,
        task_slug=tombstone.task_slug,
        dataset_slug=tombstone.dataset_slug,
    )


def leaderboard_rank_message(ranks: Iterable[object]) -> str:
    """Pair each current placement with its benchmark name."""
    placements: list[tuple[int, str]] = []
    retired_benchmarks: list[str] = []
    for rank in ranks:
        value = getattr(rank, "best_rank", None)
        benchmark = str(getattr(rank, "dataset_name", "") or "").strip()
        if getattr(rank, "retired", False) and benchmark:
            retired_benchmarks.append(benchmark)
            continue
        if isinstance(value, int) and value >= 1 and benchmark:
            placements.append((value, benchmark))

    if retired_benchmarks:
        return f"result retired on {sorted(retired_benchmarks, key=str.casefold)[0]}"
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
    ranks = list(ranks)
    label = "Papers with Code"
    message = leaderboard_rank_message(ranks)
    label_width = 102
    message_width = max(58, round(len(message) * 6.7 + 16))
    width = label_width + message_width
    color = (
        "#16837a"
        if any(isinstance(getattr(rank, "best_rank", None), int) for rank in ranks)
        else "#8a8f98"
    )
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
