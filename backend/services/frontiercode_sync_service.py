"""Synchronize Cognition's living FrontierCode 1.1 leaderboard."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from math import isfinite
from typing import Any

import httpx
from sqlalchemy.orm import Session

from backend.models.database import (
    Dataset,
    Evaluation,
    Metric,
    Paper,
    Task,
    TaskDatasetMetric,
)
from backend.services.evaluation_service import EvaluationService

FRONTIERCODE_ENDPOINT = "https://cognition.com/data/frontiercode-leaderboard/data.json"
FRONTIERCODE_SOURCE_URL = "https://cognition.com/frontiercode"
SOURCE_PAPER_ID = 98109
TASK_SLUG = "coding-agents"
DATASET_SLUGS = {"main": "frontiercode-main", "extended": "frontiercode-extended"}
METRIC_NAMES = ("Score", "Pass Rate")
MANAGED_METHODOLOGY_PREFIX = "Managed by the Papers with Code FrontierCode live sync."
MIN_EXPECTED_MODELS = 20
MAX_EXPECTED_MODELS = 60
EXPECTED_SUBSET_SIZES = {"main": 100, "extended": 150}

HARNESS_NAMES = {
    "claude-code": "Claude Code",
    "codex": "Codex",
    "grok-build": "Grok Build",
    "chisel": "Chisel",
    "mini-swe-agent": "MiniSWE-Agent",
    "cursor-cli": "Cursor CLI",
}


@dataclass(frozen=True)
class FrontierCodeEntry:
    model: str
    effort: str
    harness: str
    subset: str
    score: float
    pass_rate: float


@dataclass(frozen=True)
class FrontierCodeLeaderboard:
    entries: list[FrontierCodeEntry]


@dataclass
class FrontierCodeSyncStats:
    fetched_models: int = 0
    selected: int = 0
    created: int = 0
    updated: int = 0
    deleted: int = 0
    datasets: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _finite_rate(value: Any, *, field_name: str, model: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"FrontierCode {field_name} is invalid for {model}")
    parsed = float(value)
    if not isfinite(parsed):
        raise ValueError(f"FrontierCode {field_name} is not finite for {model}")
    if not 0 <= parsed <= 1:
        raise ValueError(f"FrontierCode {field_name} is outside 0-1 for {model}")
    return parsed


def parse_frontiercode_leaderboard(payload: Any) -> FrontierCodeLeaderboard:
    if not isinstance(payload, dict) or not isinstance(payload.get("v1_1"), dict):
        raise TypeError("FrontierCode response must contain a v1_1 object")
    revision = payload["v1_1"]
    models = revision.get("models")
    efforts = revision.get("efforts")
    subsets = revision.get("subsets")
    harnesses = revision.get("harness")
    data = revision.get("data")
    if not all(
        isinstance(value, dict) for value in (efforts, subsets, harnesses, data)
    ):
        raise TypeError("FrontierCode v1_1 metadata is malformed")
    if (
        not isinstance(models, list)
        or not MIN_EXPECTED_MODELS <= len(models) <= MAX_EXPECTED_MODELS
    ):
        count = len(models) if isinstance(models, list) else "invalid"
        raise ValueError(f"FrontierCode returned {count} models")
    if subsets != EXPECTED_SUBSET_SIZES:
        raise ValueError(f"FrontierCode subset sizes changed: {subsets!r}")
    if len(set(models)) != len(models):
        raise ValueError("FrontierCode response contains duplicate models")

    entries: list[FrontierCodeEntry] = []
    for model in models:
        if not isinstance(model, str) or not model.strip() or len(model) > 255:
            raise ValueError("FrontierCode response contains an invalid model name")
        model_efforts = efforts.get(model)
        harness = harnesses.get(model)
        model_data = data.get(model)
        if not isinstance(model_efforts, list) or not model_efforts:
            raise ValueError(f"FrontierCode has no efforts for {model}")
        if not isinstance(harness, str) or not harness.strip() or len(harness) > 255:
            raise ValueError(f"FrontierCode has an invalid harness for {model}")
        if not isinstance(model_data, dict):
            raise TypeError(f"FrontierCode has no data for {model}")
        for effort in model_efforts:
            if not isinstance(effort, str) or not effort.strip() or len(effort) > 32:
                raise ValueError(f"FrontierCode has an invalid effort for {model}")
            effort_data = model_data.get(effort)
            if not isinstance(effort_data, dict):
                raise TypeError(f"FrontierCode has no {effort} data for {model}")
            for subset in DATASET_SLUGS:
                result = effort_data.get(subset)
                if not isinstance(result, dict):
                    raise TypeError(
                        f"FrontierCode has no {subset} data for {model}/{effort}"
                    )
                entries.append(
                    FrontierCodeEntry(
                        model=model,
                        effort=effort,
                        harness=HARNESS_NAMES.get(harness, harness),
                        subset=subset,
                        score=_finite_rate(
                            result.get("new_score"), field_name="score", model=model
                        ),
                        pass_rate=_finite_rate(
                            result.get("correct"), field_name="pass rate", model=model
                        ),
                    )
                )
    return FrontierCodeLeaderboard(entries=entries)


def fetch_frontiercode_leaderboard(
    client: httpx.Client | None = None,
) -> FrontierCodeLeaderboard:
    owned_client = client is None
    active_client = client or httpx.Client(
        timeout=httpx.Timeout(20, connect=5),
        follow_redirects=False,
        headers={"User-Agent": "paperswithcode-frontiercode-sync/1.0"},
    )
    try:
        response = active_client.get(FRONTIERCODE_ENDPOINT)
        response.raise_for_status()
        return parse_frontiercode_leaderboard(response.json())
    finally:
        if owned_client:
            active_client.close()


def select_best_entries(entries: list[FrontierCodeEntry]) -> list[FrontierCodeEntry]:
    best: dict[tuple[str, str], FrontierCodeEntry] = {}
    for entry in entries:
        key = (entry.model, entry.subset)
        current = best.get(key)
        if current is None or entry.score > current.score:
            best[key] = entry
    return sorted(
        best.values(), key=lambda entry: (entry.subset, -entry.score, entry.model)
    )


def _managed_key(row: Evaluation) -> tuple[str, str] | None:
    methodology = row.methodology or ""
    if not methodology.startswith(MANAGED_METHODOLOGY_PREFIX):
        return None
    marker = " subset="
    start = methodology.find(marker)
    if start == -1:
        return None
    subset = methodology[start + len(marker) :].split(";", 1)[0]
    return row.model_name or "", subset


class FrontierCodeSyncService:
    """Replace only evaluation rows owned by the FrontierCode live sync."""

    def __init__(self, db: Session):
        self.db = db

    def _leaderboard_identity(self) -> tuple[Task, dict[str, Dataset]]:
        task = self.db.query(Task).filter(Task.slug == TASK_SLUG).one_or_none()
        datasets = {
            subset: self.db.query(Dataset).filter(Dataset.slug == slug).one_or_none()
            for subset, slug in DATASET_SLUGS.items()
        }
        metric_ids = {
            metric.name: metric.id
            for metric in self.db.query(Metric)
            .filter(Metric.name.in_(METRIC_NAMES))
            .all()
        }
        if task is None or any(dataset is None for dataset in datasets.values()):
            raise RuntimeError("FrontierCode task or benchmarks are not configured")
        if set(metric_ids) != set(METRIC_NAMES):
            raise RuntimeError("FrontierCode metrics are not configured")
        for dataset in datasets.values():
            for metric_id in metric_ids.values():
                configured = (
                    self.db.query(TaskDatasetMetric)
                    .filter(
                        TaskDatasetMetric.task_id == task.id,
                        TaskDatasetMetric.dataset_id == dataset.id,
                        TaskDatasetMetric.metric_id == metric_id,
                    )
                    .one_or_none()
                )
                if configured is None:
                    raise RuntimeError(
                        "FrontierCode leaderboard metrics are not linked"
                    )
        return task, datasets  # type: ignore[return-value]

    def sync(
        self, leaderboard: FrontierCodeLeaderboard, *, commit: bool = True
    ) -> FrontierCodeSyncStats:
        selected = select_best_entries(leaderboard.entries)
        if not selected:
            raise ValueError(
                "Refusing to synchronize an empty FrontierCode leaderboard"
            )
        stats = FrontierCodeSyncStats(
            fetched_models=len({entry.model for entry in leaderboard.entries}),
            selected=len(selected),
        )
        try:
            task, datasets = self._leaderboard_identity()
            paper = (
                self.db.query(Paper)
                .filter(Paper.id == SOURCE_PAPER_ID, Paper.is_latest_version)
                .one_or_none()
            )
            if paper is None:
                raise RuntimeError(
                    f"FrontierCode source paper {SOURCE_PAPER_ID} is missing"
                )
            stats.datasets = {
                subset: dataset.id for subset, dataset in datasets.items()
            }
            managed_rows = (
                self.db.query(Evaluation)
                .filter(
                    Evaluation.task_id == task.id,
                    Evaluation.dataset_id.in_(
                        [dataset.id for dataset in datasets.values()]
                    ),
                    Evaluation.external_source_url == FRONTIERCODE_SOURCE_URL,
                    Evaluation.methodology.like(f"{MANAGED_METHODOLOGY_PREFIX}%"),
                )
                .all()
            )
            managed = {
                key: row
                for row in managed_rows
                if (key := _managed_key(row)) is not None
            }
            upstream_keys = {(entry.model, entry.subset) for entry in selected}
            for entry in selected:
                key = (entry.model, entry.subset)
                row = managed.get(key)
                methodology = (
                    f"{MANAGED_METHODOLOGY_PREFIX} subset={entry.subset}; "
                    f"FrontierCode 1.1 best reasoning effort={entry.effort}; "
                    f"{EXPECTED_SUBSET_SIZES[entry.subset]} tasks; unfair internet-use runs are zeroed."
                )
                metrics = {
                    "Score": round(entry.score * 100, 4),
                    "Pass Rate": round(entry.pass_rate * 100, 4),
                }
                if row is None:
                    row = Evaluation(
                        paper_id=paper.id,
                        task_id=task.id,
                        dataset_id=datasets[entry.subset].id,
                    )
                    self.db.add(row)
                    stats.created += 1
                else:
                    stats.updated += 1
                row.paper_id = paper.id
                row.model_name = entry.model
                row.harness = entry.harness
                row.methodology = methodology
                row.metrics = metrics
                row.uses_additional_data = False
                row.is_open = False
                row.best_metric = "Score"
                row.evaluated_on = datetime.now(UTC).date()
                row.external_source_url = FRONTIERCODE_SOURCE_URL
                row.source_url = FRONTIERCODE_SOURCE_URL
                row.external = True
                row.updated_at = datetime.now(UTC)
            for key, row in managed.items():
                if key not in upstream_keys:
                    self.db.delete(row)
                    stats.deleted += 1
            self.db.flush()
            service = EvaluationService(self.db)
            for dataset in datasets.values():
                for metric_name in METRIC_NAMES:
                    service.recalculate_ranks(
                        task.id,
                        dataset.id,
                        metric_name=metric_name,
                        commit=False,
                    )
            if commit:
                self.db.commit()
            else:
                self.db.rollback()
            return stats
        except Exception:
            self.db.rollback()
            raise
