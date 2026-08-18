"""Validation and aggregation for benchmark gaps discovered during add-evals."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models.database import (
    BenchmarkCurationCandidate,
    BenchmarkCurationEvidence,
    Task,
)
from backend.utils.public_urls import normalize_public_url

GAP_TYPES = {
    "dataset_missing",
    "task_dataset_association_missing",
    "metric_configuration_missing",
    "task_missing",
}


def _bounded_text(value: Any, name: str, limit: int = 2_000) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    value = value.strip()
    if len(value) > limit:
        raise ValueError(f"{name} exceeds {limit} characters")
    return value


class BenchmarkGapService:
    def __init__(self, db: Session):
        self.db = db

    def validate(self, gaps: list[dict]) -> tuple[list[dict], list[dict]]:
        accepted: list[dict] = []
        rejected: list[dict] = []
        for index, gap in enumerate(gaps):
            try:
                accepted.append(self._validate_one(gap))
            except (TypeError, ValueError) as exc:
                rejected.append({"index": index, "error": str(exc)[:500]})
        return accepted, rejected

    def _validate_one(self, gap: dict) -> dict:
        if not isinstance(gap, dict):
            raise TypeError("gap must be an object")
        reasoning = _bounded_text(gap.get("reasoning"), "reasoning")
        gap_type = gap.get("gap_type")
        if gap_type not in GAP_TYPES:
            raise ValueError("invalid gap_type")
        proposed = gap.get("proposed_benchmark")
        if not isinstance(proposed, dict):
            raise ValueError("proposed_benchmark is required")
        name = _bounded_text(proposed.get("name"), "proposed_benchmark.name", 500)
        blocked = gap.get("blocked_evaluations")
        evidence = gap.get("evidence")
        searches = (gap.get("catalog_search") or {}).get("queries")
        if not isinstance(blocked, list) or not blocked:
            raise ValueError("at least one blocked_evaluation is required")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError("primary-paper evidence is required")
        if not isinstance(searches, list) or not searches:
            raise ValueError("catalog search queries are required")
        task_ids = []
        for task in proposed.get("task_candidates") or []:
            task_id = int(task["task_id"])
            if self.db.get(Task, task_id) is None:
                raise ValueError(f"unknown task_id {task_id}")
            task_ids.append(task_id)
        sources = proposed.get("canonical_sources") or []
        canonical_url = None
        if sources:
            canonical_url = normalize_public_url(
                _bounded_text(sources[0].get("url"), "canonical source URL", 2000)
            )
        result = dict(gap)
        result["reasoning"] = reasoning
        result["_normalized"] = {
            "name": name,
            "canonical_url": canonical_url,
            "task_ids": sorted(set(task_ids)),
            "aliases": sorted(set(str(v)[:500] for v in proposed.get("aliases") or []))[
                :30
            ],
        }
        return result

    def persist(
        self, *, paper_id: int, job_id: uuid.UUID, gaps: list[dict]
    ) -> list[dict]:
        results = []
        for gap in gaps:
            normalized = gap.pop("_normalized")
            identity_source = normalized["canonical_url"] or (
                re.sub(r"[^a-z0-9]", "", normalized["name"].lower())
                + ":"
                + ",".join(map(str, normalized["task_ids"]))
            )
            identity_key = hashlib.sha256(identity_source.encode()).hexdigest()
            row = (
                self.db.query(BenchmarkCurationCandidate)
                .filter(BenchmarkCurationCandidate.identity_key == identity_key)
                .with_for_update()
                .one_or_none()
            )
            if row is None:
                row = BenchmarkCurationCandidate(
                    id=uuid.uuid4(),
                    identity_key=identity_key,
                    canonical_name=normalized["name"],
                    gap_type=gap["gap_type"],
                    canonical_url=normalized["canonical_url"],
                    task_ids=normalized["task_ids"],
                    aliases=normalized["aliases"],
                    confidence=(gap.get("assessment") or {}).get("confidence"),
                )
                self.db.add(row)
                self.db.flush()
            evidence = BenchmarkCurationEvidence(
                id=uuid.uuid4(),
                candidate_id=row.id,
                paper_id=paper_id,
                job_id=job_id,
                payload=json.loads(json.dumps(gap)),
            )
            exists = (
                self.db.query(BenchmarkCurationEvidence.id)
                .filter(
                    BenchmarkCurationEvidence.candidate_id == row.id,
                    BenchmarkCurationEvidence.paper_id == paper_id,
                    BenchmarkCurationEvidence.job_id == job_id,
                )
                .first()
            )
            if not exists:
                self.db.add(evidence)
            row.last_seen_at = datetime.now(UTC)
            self.db.flush()
            row.distinct_paper_count = int(
                self.db.query(
                    func.count(func.distinct(BenchmarkCurationEvidence.paper_id))
                )
                .filter(BenchmarkCurationEvidence.candidate_id == row.id)
                .scalar()
                or 0
            )
            results.append({"candidate_id": str(row.id), "identity_key": identity_key})
        return results
