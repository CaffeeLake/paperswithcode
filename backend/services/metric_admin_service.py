"""Idempotent metric definition management for the maintenance CLI."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.database import Metric


@dataclass(frozen=True)
class MetricAddResult:
    status: str
    id: int
    name: str
    full_name: str | None
    direction: str
    scale: str | None
    description: str | None

    def to_dict(self) -> dict:
        return asdict(self)


def add_or_update_metric(
    db: Session,
    *,
    name: str,
    direction: str,
    full_name: str | None = None,
    scale: str | None = None,
    description: str | None = None,
) -> MetricAddResult:
    """Create a metric or normalize the metadata of an existing metric."""
    normalized_name = name.strip()
    if not normalized_name:
        raise ValueError("Metric name must not be empty")
    if direction not in {"higher_is_better", "lower_is_better"}:
        raise ValueError(f"Invalid metric direction: {direction}")

    metric = db.execute(
        select(Metric).where(Metric.name == normalized_name)
    ).scalar_one_or_none()
    status = "updated" if metric else "created"
    if metric is None:
        metric = Metric(name=normalized_name, direction=direction)
        db.add(metric)

    metric.full_name = full_name.strip() if full_name else None
    metric.direction = direction
    metric.scale = scale.strip() if scale else None
    metric.description = description.strip() if description else None
    db.commit()

    return MetricAddResult(
        status=status,
        id=metric.id,
        name=metric.name,
        full_name=metric.full_name,
        direction=metric.direction,
        scale=metric.scale,
        description=metric.description,
    )
