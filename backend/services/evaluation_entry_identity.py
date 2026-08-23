"""Canonical identity for one displayed benchmark leaderboard entry."""

from __future__ import annotations

import json

EvaluationDisplayEntryKey = tuple[int, int, int, str, str]


def evaluation_display_entry_key(
    paper_id: int,
    task_id: int,
    dataset_id: int,
    model_name: str | None,
    harness: str | None,
) -> EvaluationDisplayEntryKey:
    """Match the frontend's paper/task/dataset/model/harness display grouping."""
    return (
        paper_id,
        task_id,
        dataset_id,
        model_name or "",
        harness or "",
    )


def serialize_evaluation_display_entry_key(key: EvaluationDisplayEntryKey) -> str:
    """Encode a display identity injectively for JSON report object keys."""
    return json.dumps(key, ensure_ascii=False, separators=(",", ":"))
