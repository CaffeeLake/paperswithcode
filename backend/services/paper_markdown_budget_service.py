"""Conservative cost accounting for paper-Markdown Hugging Face Jobs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from math import floor
from typing import Any, Iterable

PAPER_MARKDOWN_GPU_HOURLY_RATE_USD = 1.80
PAPER_MARKDOWN_JOB_RESERVATION_HOURS = 12.0
PAPER_MARKDOWN_LIVE_WINDOW_DAYS = 30

_ACTIVE_STAGES = {"PENDING", "RUNNING", "STARTING", "QUEUED", "SCHEDULING"}


@dataclass(frozen=True)
class PaperMarkdownBudgetDecision:
    """Fail-closed admission decision shared by schedulers and operators."""

    desired_jobs: int
    affordable_jobs: int
    current_exposure_usd: float
    reservation_per_job_usd: float
    planned_reservation_usd: float
    projected_exposure_usd: float
    ceiling_usd: float
    headroom_usd: float
    reason: str | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def paper_markdown_budget_decision(
    *,
    desired_jobs: int,
    current_exposure_usd: float,
    ceiling_usd: float,
    reservation_per_job_usd: float,
) -> PaperMarkdownBudgetDecision:
    """Admit the largest requested prefix whose worst case fits the ceiling."""
    if desired_jobs < 0:
        raise ValueError("desired_jobs must not be negative")
    if reservation_per_job_usd <= 0:
        raise ValueError("reservation_per_job_usd must be positive")

    headroom = max(0.0, float(ceiling_usd) - float(current_exposure_usd))
    # Monetary inputs are reported to cents. The tiny epsilon makes an exact
    # decimal boundary robust to binary floating-point representation without
    # admitting a cent above the configured ceiling.
    affordable = min(desired_jobs, floor((headroom + 1e-9) / reservation_per_job_usd))
    planned = affordable * reservation_per_job_usd
    projected = float(current_exposure_usd) + planned
    reason = None
    if desired_jobs and not affordable:
        reason = "no shard fits within remaining budget"
    elif affordable < desired_jobs:
        reason = f"only {affordable} of {desired_jobs} desired shards fit"
    return PaperMarkdownBudgetDecision(
        desired_jobs=desired_jobs,
        affordable_jobs=affordable,
        current_exposure_usd=round(float(current_exposure_usd), 2),
        reservation_per_job_usd=round(reservation_per_job_usd, 2),
        planned_reservation_usd=round(planned, 2),
        projected_exposure_usd=round(projected, 2),
        ceiling_usd=round(float(ceiling_usd), 2),
        headroom_usd=round(headroom, 2),
        reason=reason,
    )


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
    current_exposure = spent + active_reserved
    decision = paper_markdown_budget_decision(
        desired_jobs=planned_jobs,
        current_exposure_usd=current_exposure,
        ceiling_usd=ceiling_usd,
        reservation_per_job_usd=reservation_per_job,
    )
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
        "desired_jobs": decision.desired_jobs,
        "affordable_jobs": decision.affordable_jobs,
        # Legacy keys now describe the actual admitted plan, which is the plan
        # the scheduler will reserve and launch.
        "planned_jobs": decision.affordable_jobs,
        "planned_reserved_usd": decision.planned_reservation_usd,
        "current_exposure_usd": round(current_exposure, 2),
        "projected_usd": decision.projected_exposure_usd,
        "ceiling_usd": round(float(ceiling_usd), 2),
        "headroom_usd": round(max(0.0, float(ceiling_usd) - current_exposure), 2),
        "can_launch_planned": decision.affordable_jobs > 0 or planned_jobs == 0,
        "reason": decision.reason,
        "hourly_rate_usd": PAPER_MARKDOWN_GPU_HOURLY_RATE_USD,
        "reservation_hours_per_job": PAPER_MARKDOWN_JOB_RESERVATION_HOURS,
        "reservation_per_job_usd": round(reservation_per_job, 2),
        "relevant_jobs": len(relevant),
    }
