"""Job-scoped reads and transactional mutations for Codex curation callbacks."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.api import ApplyMutationRequest
from backend.models.database import (
    Dataset,
    Evaluation,
    Method,
    Metric,
    Paper,
    PaperRepository,
    Repository,
    Task,
    TaskDataset,
    TaskDatasetMetric,
)
from backend.services.codex_add_evals_service import (
    CodexPaperJobService,
    codex_paper_job_service,
)
from backend.services.curation_thumbnail_queue_service import serialize_thumbnail
from backend.services.evaluation_service import EvaluationService
from backend.services.paper_service import PaperService


class CodexCurationPaperNotFoundError(LookupError):
    """The paper attached to a curation job no longer exists."""


class CodexCurationMutationClosedError(RuntimeError):
    """The durable job state no longer permits a callback mutation."""


class CodexCurationEnrichmentNotAllowedError(ValueError):
    """An evaluation job received an enrichment payload."""


class CodexCurationEvaluationPaperMismatchError(ValueError):
    """An evaluation payload targets a paper outside the scoped job."""


class CodexCurationEvaluationsNotAllowedError(ValueError):
    """An enrichment job received evaluation rows."""


class CodexCurationEnrichmentRequiredError(ValueError):
    """An enrichment job did not receive its mutation payload."""


class CodexCurationCallbackService:
    """Own callback projections and the single-apply mutation transaction."""

    def __init__(
        self,
        db: Session,
        *,
        job_service: CodexPaperJobService = codex_paper_job_service,
        evaluation_service: EvaluationService | None = None,
        paper_service: PaperService | None = None,
    ) -> None:
        self.db = db
        self.job_service = job_service
        self.evaluation_service = evaluation_service or EvaluationService(db)
        self.paper_service = paper_service or PaperService(db)

    def context(self, row, settings: Settings) -> dict[str, Any]:
        paper = self.db.get(Paper, row.paper_id)
        if paper is None:
            raise CodexCurationPaperNotFoundError("Paper not found")
        repositories = (
            self.db.query(Repository, PaperRepository.is_official)
            .join(PaperRepository, PaperRepository.repository_id == Repository.id)
            .filter(PaperRepository.paper_id == paper.id)
            .all()
        )
        return {
            "job": self.job_service.serialize(row, settings).model_dump(mode="json"),
            "paper": {
                "id": paper.id,
                "title": paper.title,
                "abstract": paper.abstract,
                "arxiv_id": paper.arxiv_id,
                "source": paper.source,
                "source_url": paper.source_url,
                "date_published": paper.date_published,
                "urls_extracted": paper.urls_extracted,
                "thumbnail_url": paper.thumbnail_url,
                "tasks": [
                    {"id": task.id, "name": task.name, "slug": task.slug}
                    for task in paper.tasks
                ],
                "methods": [
                    {"id": method.id, "name": method.name, "slug": method.slug}
                    for method in paper.methods
                ],
                "repositories": [
                    {"url": repository.url, "is_official": is_official}
                    for repository, is_official in repositories
                ],
                "project_pages": [
                    {"url": page.url, "is_official": page.is_official}
                    for page in paper.project_pages
                ],
            },
        }

    def search_taxonomy(self, query: str) -> dict[str, list[dict[str, Any]]]:
        pattern = f"%{query}%"
        return {
            "tasks": [
                {"id": task.id, "name": task.name, "slug": task.slug}
                for task in self.db.query(Task)
                .filter(or_(Task.name.ilike(pattern), Task.slug.ilike(pattern)))
                .limit(30)
            ],
            "methods": [
                {"id": method.id, "name": method.name, "slug": method.slug}
                for method in self.db.query(Method)
                .filter(or_(Method.name.ilike(pattern), Method.slug.ilike(pattern)))
                .limit(30)
            ],
        }

    def leaderboard_inventory(self, query: str) -> list[dict[str, Any]]:
        """Return configured leaderboard IDs and score-scale evidence."""
        normalized_query = re.sub(r"[^a-z0-9]", "", query.lower())

        def match_quality(dataset: Dataset) -> str:
            names = [dataset.name, dataset.slug or "", dataset.full_name or ""]
            normalized_names = [
                re.sub(r"[^a-z0-9]", "", name.lower()) for name in names
            ]
            if normalized_query in normalized_names:
                return "exact"
            if any(
                name.startswith(normalized_query) or normalized_query.startswith(name)
                for name in normalized_names
            ):
                return "close"
            return "fuzzy"

        flexible = (
            "%" + "%".join(query.replace("_", "-").replace("-", " ").split()) + "%"
        )
        matches = (
            self.db.query(Dataset, Task, TaskDataset, Metric)
            .join(TaskDataset, TaskDataset.dataset_id == Dataset.id)
            .join(Task, Task.id == TaskDataset.task_id)
            .join(
                TaskDatasetMetric,
                (TaskDatasetMetric.task_id == Task.id)
                & (TaskDatasetMetric.dataset_id == Dataset.id),
            )
            .join(Metric, Metric.id == TaskDatasetMetric.metric_id)
            .filter(
                or_(
                    Dataset.name.ilike(f"%{query}%"),
                    Dataset.full_name.ilike(f"%{query}%"),
                    Dataset.slug.ilike(flexible),
                    Dataset.name.ilike(flexible),
                )
            )
            .order_by(Dataset.name, Task.name, Metric.name)
            .limit(200)
            .all()
        )
        matches.sort(
            key=lambda row: (
                {"exact": 0, "close": 1, "fuzzy": 2}[match_quality(row[0])],
                row[0].name,
                row[1].name,
                row[3].name,
            )
        )

        grouped: dict[tuple[int, int], dict[str, Any]] = {}
        for dataset, task, task_dataset, metric in matches:
            key = (int(task.id), int(dataset.id))
            if key not in grouped:
                if len(grouped) == 30:
                    continue
                grouped[key] = {
                    "dataset": {
                        "id": int(dataset.id),
                        "name": dataset.name,
                        "slug": dataset.slug,
                        "full_name": dataset.full_name,
                        "split_name": dataset.split_name,
                        "variant_type": dataset.variant_type,
                        "description": (
                            dataset.short_description or dataset.description or ""
                        )[:1_000]
                        or None,
                        "warning": dataset.warning,
                    },
                    "task": {
                        "id": int(task.id),
                        "name": task.name,
                        "slug": task.slug,
                    },
                    "match_quality": match_quality(dataset),
                    "supports_harness": bool(task_dataset.supports_harness),
                    "metrics": [],
                }
            if key not in grouped:
                continue

            examples = (
                self.db.query(Evaluation)
                .filter(
                    Evaluation.task_id == task.id,
                    Evaluation.dataset_id == dataset.id,
                    Evaluation.best_metric == metric.name,
                )
                .order_by(Evaluation.created_at.desc(), Evaluation.id.desc())
                .limit(5)
                .all()
            )
            grouped[key]["metrics"].append(
                {
                    "id": int(metric.id),
                    "name": metric.name,
                    "direction": metric.direction,
                    "scale": metric.scale,
                    "recent_values": [
                        {
                            "model_name": example.model_name,
                            "value": example.metrics.get(metric.name),
                        }
                        for example in examples
                        if metric.name in example.metrics
                    ],
                }
            )
        return list(grouped.values())

    def apply(self, row, body: ApplyMutationRequest) -> dict[str, Any]:
        try:
            if hasattr(self.db, "refresh"):
                self.db.refresh(row, with_for_update=True)
            self._validate_mutation(row, body)
            created = 0
            updated = 0
            if row.kind == "add-evals":
                created, updated = self._apply_evaluations(body)
            else:
                self._apply_enrichment(row, body)

            changed = row.kind == "enrich-paper" or created + updated > 0
            row.submitted_at = datetime.now(UTC)
            if changed:
                row.applied_at = row.submitted_at
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        response: dict[str, Any] = {
            "status": "applied" if changed else "no_changes",
            "evaluations_created": created,
            "evaluations_updated": updated,
        }
        if getattr(row, "thumbnail_requested_at", None) is not None:
            response["thumbnail"] = serialize_thumbnail(row)
        return response

    @staticmethod
    def _validate_mutation(row, body: ApplyMutationRequest) -> None:
        if (
            row.status in {"completed", "failed", "canceled"}
            or getattr(row, "submitted_at", None) is not None
            or row.applied_at is not None
        ):
            raise CodexCurationMutationClosedError(
                "This job may no longer apply mutations"
            )
        if row.kind == "add-evals":
            if body.enrich is not None:
                raise CodexCurationEnrichmentNotAllowedError(
                    "Enrichment is not allowed for this job"
                )
            if any(item.paper_id != row.paper_id for item in body.evaluations):
                raise CodexCurationEvaluationPaperMismatchError(
                    "Evaluation paper does not match job"
                )
            return
        if body.evaluations:
            raise CodexCurationEvaluationsNotAllowedError(
                "Evaluations are not allowed for this job"
            )
        if body.enrich is None:
            raise CodexCurationEnrichmentRequiredError("Enrichment payload is required")

    def _apply_evaluations(self, body: ApplyMutationRequest) -> tuple[int, int]:
        created = 0
        updated = 0
        for item in body.evaluations:
            existing = (
                self.db.query(Evaluation)
                .filter(
                    Evaluation.paper_id == item.paper_id,
                    Evaluation.task_id == item.task_id,
                    Evaluation.dataset_id == item.dataset_id,
                    Evaluation.model_name == item.model_name,
                    Evaluation.harness.is_(item.harness),
                    Evaluation.best_metric == item.best_metric,
                )
                .one_or_none()
            )
            values = item.model_dump()
            if existing is None:
                self.evaluation_service.create_evaluation(**values, commit=False)
                created += 1
            else:
                values.pop("paper_id")
                self.evaluation_service.update_evaluation(
                    existing.id,
                    **values,
                    harness_set=True,
                    source_url_set=True,
                    num_parameters_set=True,
                    hf_model_url_set=True,
                    commit=False,
                )
                updated += 1
        return created, updated

    def _apply_enrichment(self, row, body: ApplyMutationRequest) -> None:
        mutation = body.enrich
        if mutation is None:
            raise AssertionError("validated enrichment payload is missing")
        if mutation.task_ids is not None:
            self.paper_service.update_paper_tasks(
                row.paper_id, mutation.task_ids, commit=False
            )
        if mutation.method_ids is not None:
            self.paper_service.update_paper_methods(
                row.paper_id, mutation.method_ids, commit=False
            )
        if mutation.repositories is not None:
            self.paper_service.update_paper_repositories(
                row.paper_id,
                [item.model_dump() for item in mutation.repositories],
                commit=False,
            )
        if mutation.project_pages is not None:
            self.paper_service.update_paper_project_pages(
                row.paper_id,
                [item.model_dump() for item in mutation.project_pages],
                commit=False,
            )
        paper = self.db.get(Paper, row.paper_id)
        if mutation.thumbnail_url is not None:
            paper.thumbnail_url = mutation.thumbnail_url
        if mutation.urls_extracted is not None:
            paper.urls_extracted = mutation.urls_extracted
        if mutation.regenerate_thumbnail:
            row.thumbnail_status = "queued"
            row.thumbnail_requested_at = datetime.now(UTC)
            row.thumbnail_claimed_at = None
            row.thumbnail_finished_at = None
            row.thumbnail_attempt_count = 0
            row.thumbnail_url = None
            row.thumbnail_previous_width = None
            row.thumbnail_previous_height = None
            row.thumbnail_generated_width = None
            row.thumbnail_generated_height = None
            row.thumbnail_warnings = None
            row.thumbnail_error = None
