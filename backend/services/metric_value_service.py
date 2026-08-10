"""Canonical parsing for stored leaderboard metric values."""

from typing import Any


def parse_metric_value(raw_value: Any) -> float | None:
    """Parse a numeric metric value, ignoring an optional uncertainty suffix."""
    if raw_value is None:
        return None

    if isinstance(raw_value, str):
        for separator in ("±", "+/-"):
            if separator in raw_value:
                raw_value = raw_value.split(separator, 1)[0].strip()
        if raw_value.count(",") == 1 and "." not in raw_value:
            raw_value = raw_value.replace(",", ".")

    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return None
