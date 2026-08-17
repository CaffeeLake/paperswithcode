"""Conservative cost accounting for paper-Markdown Hugging Face Jobs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Iterable

PAPER_MARKDOWN_GPU_HOURLY_RATE_USD = 1.80
PAPER_MARKDOWN_JOB_RESERVATION_HOURS = 12.0
PAPER_MARKDOWN_LIVE_WINDOW_DAYS = 30

_ACTIVE_STAGES = {"PENDING", "RUNNING", "STARTING", "QUEUED", "SCHEDULING"}


def _stage(job: object) -> str:
    status = getattr(job, "status", None)
    stage = getattr(job, "stage", None) or getattr(status, "stage", status)
    return str(getattr(stage, "value", stage) or "").upper()


def _labels(job: object) -> dict[str, str]:
    labels = getattr(job, "labels", {}) or {}
    if isinstance(labels, dict):
        return {str(key): str(value) for key, value in labels.items()}
    return {
        item.split("=", 1)[0]: item.split("=", 1)[1]
        for value in labels
        if "=" in (item := str(value))
    }


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def paper_markdown_budget_snapshot(
    jobs: Iterable[object],
    *,
    mode: str,
    ceiling_usd: float,
    planned_jobs: int = 0,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return the same fail-closed accounting used to admit paid GPU work."""
    if mode not in {"live", "backfill"}:
        raise ValueError("paper Markdown budget mode must be live or backfill")
    if planned_jobs < 0:
        raise ValueError("planned_jobs must not be negative")

    observed_at = _utc(now) or datetime.now(UTC)
    cutoff = observed_at - timedelta(days=PAPER_MARKDOWN_LIVE_WINDOW_DAYS)
    reservation_per_job = (
        PAPER_MARKDOWN_JOB_RESERVATION_HOURS * PAPER_MARKDOWN_GPU_HOURLY_RATE_USD
    )
    relevant: list[object] = []
    for job in jobs:
        if _labels(job).get("mode") != mode:
            continue
        created_at = _utc(getattr(job, "created_at", None))
        if mode == "live" and created_at is not None and created_at < cutoff:
            continue
        relevant.append(job)

    spent = 0.0
    active_reserved = 0.0
    releases: list[tuple[datetime, float]] = []
    for job in relevant:
        started_at = _utc(getattr(job, "started_at", None))
        finished_at = _utc(getattr(job, "finished_at", None))
        if started_at is not None and finished_at is not None:
            accounted = (
                max(0.0, (finished_at - started_at).total_seconds())
                / 3600
                * PAPER_MARKDOWN_GPU_HOURLY_RATE_USD
            )
            spent += accounted
        elif _stage(job) in _ACTIVE_STAGES:
            accounted = reservation_per_job
            active_reserved += accounted
        else:
            # Missing terminal timing must fail conservatively.
            accounted = reservation_per_job
            spent += accounted

        created_at = _utc(getattr(job, "created_at", None))
        if mode == "live" and created_at is not None:
            releases.append(
                (
                    created_at + timedelta(days=PAPER_MARKDOWN_LIVE_WINDOW_DAYS),
                    accounted,
                )
            )

    releases.sort(key=lambda item: item[0])
    planned_reserved = planned_jobs * reservation_per_job
    current_exposure = spent + active_reserved
    projected = current_exposure + planned_reserved
    next_release_at, next_release_usd = releases[0] if releases else (None, 0.0)
    return {
        "mode": mode,
        "window": "rolling_30_days" if mode == "live" else "all_history",
        "window_days": PAPER_MARKDOWN_LIVE_WINDOW_DAYS if mode == "live" else None,
        "window_started_at": _iso(cutoff) if mode == "live" else None,
        "next_release_at": _iso(next_release_at),
        "next_release_usd": round(next_release_usd, 2),
        "spent_usd": round(spent, 2),
        "active_reserved_usd": round(active_reserved, 2),
        "planned_jobs": planned_jobs,
        "planned_reserved_usd": round(planned_reserved, 2),
        "current_exposure_usd": round(current_exposure, 2),
        "projected_usd": round(projected, 2),
        "ceiling_usd": round(float(ceiling_usd), 2),
        "headroom_usd": round(max(0.0, float(ceiling_usd) - current_exposure), 2),
        "can_launch_planned": projected <= float(ceiling_usd),
        "hourly_rate_usd": PAPER_MARKDOWN_GPU_HOURLY_RATE_USD,
        "reservation_hours_per_job": PAPER_MARKDOWN_JOB_RESERVATION_HOURS,
        "reservation_per_job_usd": round(reservation_per_job, 2),
        "relevant_jobs": len(relevant),
    }
