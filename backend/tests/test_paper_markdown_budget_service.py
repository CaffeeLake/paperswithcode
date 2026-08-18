from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from backend.services.paper_markdown_budget_service import (
    paper_markdown_budget_decision,
    paper_markdown_budget_snapshot,
)


def _job(
    *,
    mode: str,
    created_at: datetime,
    stage: str = "COMPLETED",
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
):
    return SimpleNamespace(
        labels={"mode": mode},
        created_at=created_at,
        status=SimpleNamespace(stage=stage),
        started_at=started_at,
        finished_at=finished_at,
    )


def test_live_budget_separates_spend_reservations_and_next_launch():
    now = datetime(2026, 8, 17, 12, tzinfo=UTC)
    completed = _job(
        mode="live",
        created_at=datetime(2026, 8, 1, tzinfo=UTC),
        started_at=datetime(2026, 8, 1, 1, tzinfo=UTC),
        finished_at=datetime(2026, 8, 1, 3, tzinfo=UTC),
    )
    active = _job(
        mode="live",
        created_at=datetime(2026, 8, 10, tzinfo=UTC),
        stage="RUNNING",
        started_at=datetime(2026, 8, 10, 1, tzinfo=UTC),
    )
    expired = _job(
        mode="live",
        created_at=datetime(2026, 7, 1, tzinfo=UTC),
    )

    budget = paper_markdown_budget_snapshot(
        [completed, active, expired],
        mode="live",
        ceiling_usd=40,
        planned_jobs=1,
        now=now,
    )

    assert budget["spent_usd"] == 3.6
    assert budget["active_reserved_usd"] == 21.6
    assert budget["current_exposure_usd"] == 25.2
    assert budget["desired_jobs"] == 1
    assert budget["affordable_jobs"] == 0
    assert budget["planned_reserved_usd"] == 0
    assert budget["projected_usd"] == 25.2
    assert budget["can_launch_planned"] is False
    assert budget["next_release_at"] == "2026-08-31T00:00:00Z"
    assert budget["next_release_usd"] == 3.6
    assert budget["relevant_jobs"] == 2


def test_budget_decision_admits_largest_affordable_prefix_and_exact_boundary():
    partial = paper_markdown_budget_decision(
        desired_jobs=4,
        current_exposure_usd=678.42,
        ceiling_usd=750,
        reservation_per_job_usd=21.60,
    )
    assert partial.affordable_jobs == 3
    assert partial.planned_reservation_usd == 64.8
    assert partial.projected_exposure_usd == 743.22

    exact = paper_markdown_budget_decision(
        desired_jobs=1,
        current_exposure_usd=728.40,
        ceiling_usd=750,
        reservation_per_job_usd=21.60,
    )
    assert exact.affordable_jobs == 1
    assert exact.projected_exposure_usd == 750

    zero = paper_markdown_budget_decision(
        desired_jobs=1,
        current_exposure_usd=728.41,
        ceiling_usd=750,
        reservation_per_job_usd=21.60,
    )
    assert zero.affordable_jobs == 0
    assert zero.reason == "no shard fits within remaining budget"


def test_budget_mode_isolation_excludes_other_lane_reservations():
    now = datetime(2026, 8, 17, tzinfo=UTC)
    live = _job(mode="live", created_at=now, stage="RUNNING")
    backfill = _job(mode="backfill", created_at=now, stage="RUNNING")
    budget = paper_markdown_budget_snapshot(
        [live, backfill], mode="live", ceiling_usd=100, planned_jobs=1, now=now
    )
    assert budget["relevant_jobs"] == 1
    assert budget["active_reserved_usd"] == 21.6


def test_backfill_budget_is_all_history_and_fails_closed_without_timing():
    old_terminal = _job(
        mode="backfill",
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
        stage="ERROR",
    )

    budget = paper_markdown_budget_snapshot(
        [old_terminal],
        mode="backfill",
        ceiling_usd=750,
        planned_jobs=1,
        now=datetime(2026, 8, 17, tzinfo=UTC),
    )

    assert budget["window"] == "all_history"
    assert budget["next_release_at"] is None
    assert budget["spent_usd"] == 21.6
    assert budget["projected_usd"] == 43.2
