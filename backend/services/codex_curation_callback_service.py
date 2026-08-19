"""Job-scoped reads and transactional mutations for Codex curation callbacks."""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

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
    PaperMethod,
    PaperMethodEvidence,
    PaperMethodExclusion,
    PaperRepository,
    PaperTask,
    Repository,
    Task,
    TaskDataset,
    TaskDatasetMetric,
)
from backend.services.benchmark_gap_service import BenchmarkGapService
from backend.services.codex_add_evals_service import (
    CodexPaperJobService,
    codex_paper_job_service,
)
from backend.services.curation_thumbnail_queue_service import serialize_thumbnail
from backend.services.evaluation_service import EvaluationService
from backend.services.paper_method_link_service import upsert_evidence_links
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


def _requires_scheduled_dispatch_pause(exc: Exception) -> bool:
    """Separate expected proposal rejection from an unexpected safety fault."""
    return not isinstance(
        exc,
        (
            ValueError,
            CodexCurationMutationClosedError,
            CodexCurationPaperNotFoundError,
        ),
    )


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
        repository_rows = (
            self.db.query(Repository, PaperRepository.is_official, Repository.source)
            .join(PaperRepository, PaperRepository.repository_id == Repository.id)
            .filter(PaperRepository.paper_id == paper.id)
            .all()
        )
        repositories = [
            (
                values[0],
                values[1],
                values[2] if len(values) > 2 else getattr(values[0], "source", None),
            )
            for values in repository_rows
        ]
        task_rows = (
            self.db.query(Task, PaperTask.source)
            .join(PaperTask, PaperTask.task_id == Task.id)
            .filter(PaperTask.paper_id == paper.id)
            .all()
        )
        if task_rows and not all(
            isinstance(values, (tuple, list))
            and len(values) == 2
            and hasattr(values[0], "id")
            for values in task_rows
        ):
            task_rows = [(task, "unknown") for task in getattr(paper, "tasks", [])]

        def method_evidence(method_id: int) -> list:
            values = (
                self.db.query(PaperMethodEvidence)
                .filter(
                    PaperMethodEvidence.paper_id == paper.id,
                    PaperMethodEvidence.method_id == method_id,
                )
                .all()
            )
            return [value for value in values if hasattr(value, "evidence_type")]

        exclusions = [
            value
            for value in self.db.query(PaperMethodExclusion)
            .filter(PaperMethodExclusion.paper_id == paper.id)
            .all()
            if hasattr(value, "method_id")
        ]
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
                    {
                        "id": task.id,
                        "name": task.name,
                        "slug": task.slug,
                        "source": source,
                    }
                    for task, source in task_rows
                ],
                "methods": [
                    {
                        "id": method.id,
                        "name": method.name,
                        "slug": method.slug,
                        "evidence": [
                            {
                                "type": evidence.evidence_type,
                                "details": evidence.details,
                            }
                            for evidence in method_evidence(method.id)
                        ],
                    }
                    for method in paper.methods
                ],
                "repositories": [
                    {
                        "url": repository.url,
                        "is_official": is_official,
                        "source": source,
                    }
                    for repository, is_official, source in repositories
                ],
                "project_pages": [
                    {
                        "url": page.url,
                        "is_official": page.is_official,
                        "source": getattr(page, "source", None),
                    }
                    for page in paper.project_pages
                ],
                "hf_models": getattr(paper, "hf_models", None) or [],
                "hf_datasets": getattr(paper, "hf_datasets", None) or [],
                "hf_spaces": getattr(paper, "hf_spaces", None) or [],
                "method_exclusions": [
                    {"method_id": item.method_id, "reason": item.reason}
                    for item in exclusions
                ],
                "evaluations": [
                    {
                        "id": item.id,
                        "task_id": item.task_id,
                        "dataset_id": item.dataset_id,
                        "model_name": item.model_name,
                        "harness": item.harness,
                        "best_metric": item.best_metric,
                        "metrics": item.metrics,
                        "methodology": item.methodology,
                        "source_url": item.source_url,
                        "external_source_url": item.external_source_url,
                        "uses_additional_data": item.uses_additional_data,
                        "is_open": item.is_open,
                        "best_rank": item.best_rank,
                        "evaluated_on": item.evaluated_on.isoformat()
                        if item.evaluated_on
                        else None,
                        "num_parameters": item.num_parameters,
                        "hf_model_url": item.hf_model_url,
                    }
                    for item in getattr(paper, "evaluations", [])
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
        gap_service = BenchmarkGapService(self.db)
        gap_paper = self.db.get(Paper, row.paper_id) if body.benchmark_gaps else None
        accepted_gaps, rejected_gaps = gap_service.validate(
            body.benchmark_gaps, paper=gap_paper
        )
        before_state: dict[str, Any] = {"paper_id": row.paper_id}
        try:
            if hasattr(self.db, "refresh"):
                self.db.refresh(row, with_for_update=True)
            self._validate_mutation(row, body)
            before_state = self._mutation_projection(row, body)
            validation = self._validate_scheduled_policy(row, body)
            created = 0
            updated = 0
            removed = 0
            if row.kind == "add-evals":
                created, updated = self._apply_evaluations(body)
                removed = self._apply_evaluation_removals(row, body)
            else:
                self._apply_enrichment(row, body)

            if hasattr(self.db, "flush"):
                self.db.flush()
            after_state = self._mutation_projection(row, body)
            self._verify_after_state(row, body, after_state)

            before_evaluations = {
                int(item["id"]): item for item in before_state.get("evaluations", [])
            }
            after_evaluations = {
                int(item["id"]): item for item in after_state.get("evaluations", [])
            }
            changed_existing_evaluations = sorted(
                evaluation_id
                for evaluation_id, before in before_evaluations.items()
                if after_evaluations.get(evaluation_id) != before
            )
            flagged_existing_evaluations = (
                changed_existing_evaluations
                if getattr(row, "trigger", "admin") != "admin"
                else []
            )

            gap_results = (
                gap_service.persist(
                    paper_id=row.paper_id, job_id=row.id, gaps=accepted_gaps
                )
                if accepted_gaps
                else []
            )

            changed = before_state != after_state or created + updated + removed > 0
            row.submitted_at = datetime.now(UTC)
            # Enrichment can enqueue thumbnail work or use adapters whose fake
            # test/session projection cannot observe the relation write. Keep
            # its accepted-apply lifecycle, while a true add-evals no-op remains
            # distinguishable from a catalog mutation.
            if changed or row.kind == "enrich-paper":
                row.applied_at = row.submitted_at
            row.proposal = body.model_dump(mode="json")
            row.validation_summary = {
                **validation,
                "post_write_verification": "passed",
                "existing_evaluation_rows_affected": sorted(
                    {int(item["id"]) for item in before_state.get("evaluations", [])}
                ),
                # Historical evaluation rows have no trustworthy author/source
                # provenance column. Conservatively flag every changed existing
                # row as manual-or-legacy so automatic corrections are prominent
                # in the dashboard and trace instead of assuming automation.
                "manual_or_legacy_evaluation_rows_affected": (
                    flagged_existing_evaluations
                ),
                "requires_prominent_review": bool(flagged_existing_evaluations),
                "benchmark_gaps_accepted": len(accepted_gaps),
                "benchmark_gaps_rejected": rejected_gaps,
            }
            row.mutation_result = {
                "status": "applied" if changed else "no_changes",
                "evaluations_created": created,
                "evaluations_updated": updated,
            }
            if getattr(row, "trigger", "admin") != "admin":
                row.mutation_result.update(
                    before_state=before_state,
                    after_state=after_state,
                )
            if body.benchmark_gaps or getattr(row, "trigger", "admin") != "admin":
                row.mutation_result.update(
                    benchmark_gap_candidates=gap_results,
                    benchmark_gaps_rejected=rejected_gaps,
                )
            if removed:
                row.mutation_result["evaluations_removed"] = removed
            self.db.commit()
        except Exception as exc:
            from backend.models.database import PaperCurationSchedulerState

            if hasattr(self.db, "rollback"):
                self.db.rollback()
            mutation_closed = isinstance(exc, CodexCurationMutationClosedError)
            rejected_row = (
                self.db.get(type(row), row.id)
                if not mutation_closed
                and hasattr(self.db, "get")
                and hasattr(row, "id")
                else None
            )
            should_commit = False
            if rejected_row is not None:
                rejected_row.proposal = body.model_dump(mode="json")
                rejected_row.validation_summary = {
                    "status": "rejected",
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:2_000],
                    "before_state": before_state,
                    "benchmark_gaps_rejected": rejected_gaps,
                }
                rejected_row.submitted_at = datetime.now(UTC)
                should_commit = True
            if (
                not mutation_closed
                and getattr(row, "trigger", "admin") != "admin"
                and _requires_scheduled_dispatch_pause(exc)
            ):
                state = self.db.get(PaperCurationSchedulerState, 1)
                if state is not None:
                    state.paused_at = datetime.now(UTC)
                    state.pause_condition = "server_invariant"
                    state.pause_reason = (
                        "Scheduled callback proposal breached a server-side invariant"
                    )
                    should_commit = True
            if should_commit:
                self.db.commit()
            raise

        response: dict[str, Any] = dict(row.mutation_result)
        if body.benchmark_gaps or getattr(row, "trigger", "admin") != "admin":
            response["benchmark_gap_candidates"] = gap_results
            response["benchmark_gaps_rejected"] = rejected_gaps
        if getattr(row, "thumbnail_requested_at", None) is not None:
            response["thumbnail"] = serialize_thumbnail(row)
        return response

    def _mutation_projection(self, row, body: ApplyMutationRequest) -> dict[str, Any]:
        """Bound the durable before/after trace to relations touched by this stage."""
        if not hasattr(self.db, "flush"):
            return {"paper_id": row.paper_id, "evaluations": []}
        if row.kind == "enrich-paper":
            paper = self.db.get(Paper, row.paper_id)
            task_links = (
                self.db.query(PaperTask)
                .filter(PaperTask.paper_id == row.paper_id)
                .all()
            )
            method_links = (
                self.db.query(PaperMethod)
                .filter(PaperMethod.paper_id == row.paper_id)
                .all()
            )
            evidence = (
                self.db.query(PaperMethodEvidence)
                .filter(PaperMethodEvidence.paper_id == row.paper_id)
                .all()
            )
            evidence_by_method: dict[int, list[str]] = {}
            for item in evidence:
                evidence_by_method.setdefault(int(item.method_id), []).append(
                    item.evidence_type
                )
            repository_rows = (
                self.db.query(Repository, PaperRepository.is_official)
                .join(PaperRepository, PaperRepository.repository_id == Repository.id)
                .filter(PaperRepository.paper_id == row.paper_id)
                .all()
            )
            return {
                "paper_id": row.paper_id,
                "urls_extracted": bool(paper.urls_extracted),
                "tasks": [
                    {"id": int(item.task_id), "source": item.source}
                    for item in sorted(task_links, key=lambda value: value.task_id)
                ],
                "methods": [
                    {
                        "id": int(item.method_id),
                        "evidence_types": sorted(
                            evidence_by_method.get(int(item.method_id), [])
                        ),
                    }
                    for item in sorted(method_links, key=lambda value: value.method_id)
                ],
                "repositories": [
                    {
                        "url": repository.url,
                        "is_official": bool(is_official),
                        "source": repository.source,
                    }
                    for repository, is_official in sorted(
                        repository_rows, key=lambda value: value[0].url
                    )
                ],
                "project_pages": [
                    {
                        "url": page.url,
                        "is_official": bool(page.is_official),
                        "source": getattr(page, "source", None),
                    }
                    for page in sorted(paper.project_pages, key=lambda value: value.url)
                ],
                "hf_models": sorted(paper.hf_models or []),
                "hf_datasets": sorted(paper.hf_datasets or []),
                "hf_spaces": sorted(paper.hf_spaces or []),
            }

        identities = {
            (
                item.task_id,
                item.dataset_id,
                item.model_name,
                item.harness,
                item.best_metric,
            )
            for item in body.evaluations
        }
        removal_ids = {item.evaluation_id for item in body.evaluation_removals}
        evaluations = (
            self.db.query(Evaluation).filter(Evaluation.paper_id == row.paper_id).all()
        )
        selected = [
            item
            for item in evaluations
            if item.id in removal_ids
            or (
                item.task_id,
                item.dataset_id,
                item.model_name,
                item.harness,
                item.best_metric,
            )
            in identities
        ]
        return {
            "paper_id": row.paper_id,
            "evaluations": [
                self._evaluation_state(item)
                for item in sorted(selected, key=lambda value: value.id)
            ][:200],
        }

    def _verify_after_state(
        self, row, body: ApplyMutationRequest, after_state: dict[str, Any]
    ) -> None:
        if not hasattr(self.db, "flush"):
            return
        if row.kind == "enrich-paper":
            mutation = body.enrich
            assert mutation is not None
            if mutation.task_ids is not None and {
                item["id"] for item in after_state["tasks"]
            } != set(mutation.task_ids):
                raise ValueError("Post-write task verification failed")
            if mutation.method_ids is not None and {
                item["id"] for item in after_state["methods"]
            } != set(mutation.method_ids):
                raise ValueError("Post-write method verification failed")
            if (
                mutation.urls_extracted is not None
                and after_state["urls_extracted"] != mutation.urls_extracted
            ):
                raise ValueError("Post-write URL extraction verification failed")
            return

        states = {item["id"]: item for item in after_state["evaluations"]}
        for removal in body.evaluation_removals:
            if removal.evaluation_id in states:
                raise ValueError("Post-write evaluation removal verification failed")
        all_rows = (
            self.db.query(Evaluation).filter(Evaluation.paper_id == row.paper_id).all()
        )
        for proposal in body.evaluations:
            matches = [
                item
                for item in all_rows
                if (
                    item.task_id,
                    item.dataset_id,
                    item.model_name,
                    item.harness,
                    item.best_metric,
                )
                == (
                    proposal.task_id,
                    proposal.dataset_id,
                    proposal.model_name,
                    proposal.harness,
                    proposal.best_metric,
                )
            ]
            changes = self._evaluation_changes(matches[0], proposal) if matches else {}
            if len(matches) != 1 or changes:
                raise ValueError(
                    "Post-write evaluation verification failed"
                    + (
                        f": {len(matches)} matching rows"
                        if len(matches) != 1
                        else f": {sorted(changes)}"
                    )
                )

        for task_id, dataset_id, best_metric in {
            (item.task_id, item.dataset_id, item.best_metric)
            for item in body.evaluations
        }:
            leaderboard_rows = [
                item
                for item in all_rows
                if item.task_id == task_id
                and item.dataset_id == dataset_id
                and item.best_metric == best_metric
            ]
            if len(leaderboard_rows) > 1:
                raise ValueError(
                    "Scheduled curation must keep one paper-native result per leaderboard"
                )

    def _validate_mutation(self, row, body: ApplyMutationRequest) -> None:
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
            for removal in body.evaluation_removals:
                existing = self.db.get(Evaluation, removal.evaluation_id)
                if existing is None or existing.paper_id != row.paper_id:
                    raise CodexCurationEvaluationPaperMismatchError(
                        "Evaluation removal does not match job paper"
                    )
            return
        if body.benchmark_gaps:
            raise CodexCurationEvaluationsNotAllowedError(
                "Benchmark gaps are allowed only for add-evals jobs"
            )
        if body.evaluations:
            raise CodexCurationEvaluationsNotAllowedError(
                "Evaluations are not allowed for this job"
            )
        if body.enrich is None:
            raise CodexCurationEnrichmentRequiredError("Enrichment payload is required")

    def _validate_scheduled_policy(
        self, row, body: ApplyMutationRequest
    ) -> dict[str, Any]:
        if getattr(row, "trigger", "admin") == "admin":
            return {"policy": "admin"}
        if row.trace_status not in {"preapply_stored", "disabled"}:
            raise CodexCurationMutationClosedError(
                "Scheduled mutation requires a durable pre-apply trace"
            )
        if row.kind == "enrich-paper":
            mutation = body.enrich
            if mutation is None:
                raise CodexCurationEnrichmentRequiredError(
                    "Enrichment payload is required"
                )
            if mutation.regenerate_thumbnail:
                raise ValueError("Scheduled enrichment must not request thumbnail work")
            if (
                mutation.urls_extracted is True
                and row.url_candidates
                and not row.url_candidates.get("complete", False)
            ):
                raise ValueError(
                    "urls_extracted cannot be set after an incomplete evidence search"
                )
            task_ids = set(mutation.task_ids or [])
            method_ids = set(mutation.method_ids or [])
            if task_ids and self.db.query(Task).filter(
                Task.id.in_(task_ids)
            ).count() != len(task_ids):
                raise ValueError("Unknown task ID in enrichment proposal")
            if method_ids and self.db.query(Method).filter(
                Method.id.in_(method_ids)
            ).count() != len(method_ids):
                raise ValueError("Unknown method ID in enrichment proposal")
            current_tasks = (
                self.db.query(PaperTask)
                .filter(PaperTask.paper_id == row.paper_id)
                .all()
            )
            protected_tasks = {
                item.task_id for item in current_tasks if item.source != "auto"
            }
            if not protected_tasks <= task_ids:
                raise ValueError("Scheduled enrichment cannot remove manual task links")
            removed_auto_tasks = {
                item.task_id for item in current_tasks if item.source == "auto"
            } - task_ids
            if removed_auto_tasks - set(mutation.task_removal_reasons):
                raise ValueError("Every automated task removal requires a reason")
            evidence = (
                self.db.query(PaperMethodEvidence)
                .filter(PaperMethodEvidence.paper_id == row.paper_id)
                .all()
            )
            protected_methods = {
                item.method_id
                for item in evidence
                if item.evidence_type in {"manual", "source", "legacy_unknown"}
            }
            if not protected_methods <= method_ids:
                raise ValueError(
                    "Scheduled enrichment cannot remove protected method links"
                )
            current_methods = {
                item.method_id
                for item in self.db.query(PaperMethod).filter(
                    PaperMethod.paper_id == row.paper_id
                )
            }
            removed_methods = current_methods - method_ids
            if removed_methods - set(mutation.method_removal_reasons):
                raise ValueError("Every automated method removal requires a reason")
            for link in mutation.repositories or []:
                parsed = urlsplit(link.url)
                if (
                    parsed.scheme != "https"
                    or parsed.hostname != "github.com"
                    or len(parsed.path.strip("/").split("/")) < 2
                ):
                    raise ValueError(
                        "Repository links must be public GitHub repository URLs"
                    )
            for link in mutation.project_pages or []:
                if urlsplit(link.url).scheme != "https":
                    raise ValueError("Project page links must use HTTPS")
            if mutation.repositories is not None:
                current_urls = {
                    repository.url
                    for repository, _is_official in self.db.query(
                        Repository, PaperRepository.is_official
                    )
                    .join(
                        PaperRepository,
                        PaperRepository.repository_id == Repository.id,
                    )
                    .filter(PaperRepository.paper_id == row.paper_id)
                }
                if not current_urls <= {link.url for link in mutation.repositories}:
                    raise ValueError(
                        "Scheduled enrichment cannot remove an existing repository"
                    )
            if mutation.project_pages is not None:
                current_pages = {
                    page.url: getattr(page, "source", "unknown")
                    for page in self.db.get(Paper, row.paper_id).project_pages
                }
                removed_pages = set(current_pages) - {
                    link.url for link in mutation.project_pages
                }
                protected_pages = {
                    url for url in removed_pages if current_pages[url] != "hf_api"
                }
                if protected_pages:
                    raise ValueError(
                        "Scheduled enrichment cannot remove a non-HF-imported project page"
                    )
                if removed_pages and mutation.urls_extracted is not True:
                    raise ValueError(
                        "Scheduled project-page removal requires a complete URL search"
                    )
                missing_reasons = {
                    url
                    for url in removed_pages
                    if not mutation.project_page_removal_reasons.get(url, "").strip()
                }
                if missing_reasons:
                    raise ValueError(
                        "Every HF-imported project-page removal requires a reason"
                    )
                if any(
                    len(reason) > 2_000
                    for url, reason in mutation.project_page_removal_reasons.items()
                    if url in removed_pages
                ):
                    raise ValueError("Project-page removal reason is too long")
            return {
                "policy": "scheduled-enrich-v1",
                "removed_auto_tasks": sorted(removed_auto_tasks),
                "removed_methods": sorted(removed_methods),
                "removed_hf_api_project_pages": sorted(removed_pages),
            }

        paper = self.db.get(Paper, row.paper_id)
        paper_route = paper.arxiv_id if paper.source != "external" else paper.id
        expected_source = f"https://paperswithcode.co/paper/{paper_route}"
        leaderboard_keys = [
            (item.task_id, item.dataset_id, item.best_metric)
            for item in body.evaluations
        ]
        if len(leaderboard_keys) != len(set(leaderboard_keys)):
            raise ValueError(
                "Scheduled curation accepts only the best eligible target result "
                "per leaderboard"
            )
        evidence_by_id = {
            int(item["evaluation_id"]): item
            for item in body.validation_evidence
            if isinstance(item, dict) and str(item.get("evaluation_id", "")).isdigit()
        }
        for item in body.evaluations:
            leaderboard = (
                self.db.query(TaskDataset)
                .filter(
                    TaskDataset.task_id == item.task_id,
                    TaskDataset.dataset_id == item.dataset_id,
                )
                .one_or_none()
            )
            if leaderboard is None:
                raise ValueError(
                    "Evaluation targets an unconfigured task/dataset leaderboard"
                )
            configured_rows = (
                self.db.query(Metric)
                .join(TaskDatasetMetric, TaskDatasetMetric.metric_id == Metric.id)
                .filter(
                    TaskDatasetMetric.task_id == item.task_id,
                    TaskDatasetMetric.dataset_id == item.dataset_id,
                )
                .all()
            )
            configured = {metric.name: metric for metric in configured_rows}
            if item.best_metric not in configured or set(item.metrics) - set(
                configured
            ):
                raise ValueError("Evaluation contains an unconfigured metric")
            if item.harness and not leaderboard.supports_harness:
                raise ValueError("Harness is not supported by this leaderboard")
            # Scheduled jobs do not get to choose the catalog source URL.  The
            # paper route is already known and is the only accepted value, so
            # canonicalize it deterministically instead of turning a harmless
            # agent formatting mistake into a circuit-breaker event.  Primary
            # arXiv/HF URLs remain available in validation evidence and traces.
            item.source_url = expected_source
            # EvaluationService keeps both legacy source columns synchronized.
            item.external_source_url = expected_source
            for metric_name, value in item.metrics.items():
                try:
                    numeric = float(str(value).rstrip("%"))
                except ValueError as exc:
                    raise ValueError("Evaluation metric must be numeric") from exc
                if not math.isfinite(numeric):
                    raise ValueError("Evaluation metric must be finite")
                self._validate_metric_scale(configured[metric_name].scale, numeric)
            matches = self._matching_evaluations(item)
            if matches:
                canonical = self._canonical_evaluation(matches)
                changes = self._evaluation_changes(canonical, item)
                if not changes and len(matches) == 1:
                    continue
                audit = evidence_by_id.get(canonical.id)
                if not audit:
                    raise ValueError(
                        "Existing evaluation updates require matched-row evidence"
                    )
                before = audit.get("before_state")
                if before != self._evaluation_state(canonical):
                    raise ValueError(
                        "Existing evaluation changed after proposal context was read"
                    )
                supplied_diff = dict(audit.get("field_diff") or {})
                for field in ("source_url", "external_source_url"):
                    if field in changes:
                        supplied_diff[field] = changes[field]
                audit["field_diff"] = supplied_diff
                if audit.get("field_diff") != changes or not audit.get("evidence"):
                    raise ValueError(
                        "Evaluation update requires the exact field diff and primary evidence"
                    )
                if len(matches) > 1:
                    duplicate_ids = sorted(
                        int(value)
                        for value in audit.get("duplicate_evaluation_ids", [])
                    )
                    if duplicate_ids != sorted(value.id for value in matches):
                        raise ValueError(
                            "Duplicate consolidation requires every matched row ID"
                        )
                    if not audit.get("canonical_selection_reason"):
                        raise ValueError(
                            "Duplicate consolidation requires a selection reason"
                        )
                    duplicate_states = audit.get("duplicate_before_states")
                    if not isinstance(duplicate_states, list):
                        raise ValueError(
                            "Duplicate consolidation requires every before-state"
                        )
                    states_by_id = {
                        value.get("id"): value
                        for value in duplicate_states
                        if isinstance(value, dict)
                    }
                    if states_by_id != {
                        value.id: self._evaluation_state(value) for value in matches
                    }:
                        raise ValueError(
                            "Duplicate consolidation before-states are incomplete or stale"
                        )
        for removal in body.evaluation_removals:
            existing = self.db.get(Evaluation, removal.evaluation_id)
            if removal.before_state != self._evaluation_state(existing):
                raise ValueError(
                    "Evaluation removal target changed after context was read"
                )
            if not removal.evidence:
                raise ValueError("Evaluation removal requires primary-source evidence")
        return {
            "policy": "scheduled-add-evals-v1",
            "evaluations": len(body.evaluations),
        }

    @staticmethod
    def _validate_metric_scale(scale: str | None, value: float) -> None:
        """Enforce explicit finite numeric ranges without guessing missing metadata."""
        if not scale:
            return
        normalized = scale.strip().lower().replace(" ", "")
        ranges = {
            "0-1": (0.0, 1.0),
            "[0,1]": (0.0, 1.0),
            "fraction": (0.0, 1.0),
            "0-100": (0.0, 100.0),
            "[0,100]": (0.0, 100.0),
            "percent": (0.0, 100.0),
            "percentage": (0.0, 100.0),
            "0-1000": (0.0, 1000.0),
            "[0,1000]": (0.0, 1000.0),
        }
        bounds = ranges.get(normalized)
        if bounds is not None and not bounds[0] <= value <= bounds[1]:
            raise ValueError(
                f"Evaluation metric value {value:g} is outside configured scale {scale}"
            )

    def _matching_evaluations(self, item) -> list[Evaluation]:
        return (
            self.db.query(Evaluation)
            .filter(
                Evaluation.paper_id == item.paper_id,
                Evaluation.task_id == item.task_id,
                Evaluation.dataset_id == item.dataset_id,
                Evaluation.model_name == item.model_name,
                Evaluation.harness.is_(item.harness),
                Evaluation.best_metric == item.best_metric,
            )
            .all()
        )

    @staticmethod
    def _canonical_evaluation(matches: list[Evaluation]) -> Evaluation:
        return max(
            matches,
            key=lambda value: (
                sum(
                    field is not None
                    for field in (
                        getattr(value, "methodology", None),
                        getattr(value, "source_url", None),
                        getattr(value, "external_source_url", None),
                        getattr(value, "num_parameters", None),
                        getattr(value, "hf_model_url", None),
                    )
                ),
                -value.id,
            ),
        )

    @staticmethod
    def _evaluation_state(value: Evaluation) -> dict[str, Any]:
        return {
            "id": value.id,
            "paper_id": value.paper_id,
            "task_id": value.task_id,
            "dataset_id": value.dataset_id,
            "model_name": value.model_name,
            "harness": value.harness,
            "methodology": value.methodology,
            "metrics": value.metrics,
            "uses_additional_data": value.uses_additional_data,
            "is_open": value.is_open,
            "best_metric": value.best_metric,
            "source_url": value.source_url,
            "external_source_url": value.external_source_url,
            "best_rank": value.best_rank,
            "evaluated_on": value.evaluated_on.isoformat()
            if value.evaluated_on
            else None,
            "num_parameters": value.num_parameters,
            "hf_model_url": value.hf_model_url,
        }

    @classmethod
    def _evaluation_changes(cls, existing: Evaluation, item) -> dict[str, dict]:
        before = cls._evaluation_state(existing)
        proposed = item.model_dump()
        if proposed.get("evaluated_on") is not None:
            proposed["evaluated_on"] = proposed["evaluated_on"].isoformat()
        # These legacy update fields have no explicit "set" sentinel in
        # EvaluationService: None means omitted, not clear.  best_rank is also
        # recalculated after writes, so an omitted rank must accept the derived
        # catalog value during post-write verification. create_evaluation also
        # copies a paper-native source_url onto external_source_url.
        for field in (
            "methodology",
            "best_rank",
            "evaluated_on",
            "source_url",
            "external_source_url",
        ):
            if proposed.get(field) is None:
                proposed[field] = before[field]
        fields = (
            "methodology",
            "metrics",
            "uses_additional_data",
            "is_open",
            "best_rank",
            "evaluated_on",
            "source_url",
            "external_source_url",
            "num_parameters",
            "hf_model_url",
        )
        return {
            field: {"before": before[field], "after": proposed[field]}
            for field in fields
            if before[field] != proposed[field]
        }

    def _apply_evaluations(self, body: ApplyMutationRequest) -> tuple[int, int]:
        created = 0
        updated = 0
        for item in body.evaluations:
            query = self.db.query(Evaluation).filter(
                Evaluation.paper_id == item.paper_id,
                Evaluation.task_id == item.task_id,
                Evaluation.dataset_id == item.dataset_id,
                Evaluation.model_name == item.model_name,
                Evaluation.harness.is_(item.harness),
                Evaluation.best_metric == item.best_metric,
            )
            if hasattr(query, "with_for_update"):
                query = query.with_for_update()
            if hasattr(query, "all"):
                matches = query.all()
            else:
                value = query.one_or_none()
                matches = [value] if value is not None else []
            existing = self._canonical_evaluation(matches) if matches else None
            values = item.model_dump()
            if existing is None:
                self.evaluation_service.create_evaluation(**values, commit=False)
                created += 1
            else:
                changes = self._evaluation_changes(existing, item)
                if not changes and len(matches) == 1:
                    continue
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
                for duplicate in matches:
                    if duplicate.id != existing.id:
                        self.db.delete(duplicate)
        return created, updated

    def _apply_evaluation_removals(self, row, body: ApplyMutationRequest) -> int:
        removed = 0
        for removal in body.evaluation_removals:
            existing = (
                self.db.query(Evaluation)
                .filter(
                    Evaluation.id == removal.evaluation_id,
                    Evaluation.paper_id == row.paper_id,
                )
                .with_for_update()
                .one()
            )
            self.db.delete(existing)
            removed += 1
        return removed

    def _apply_enrichment(self, row, body: ApplyMutationRequest) -> None:
        mutation = body.enrich
        if mutation is None:
            raise AssertionError("validated enrichment payload is missing")
        scheduled = getattr(row, "trigger", "admin") != "admin"
        if mutation.task_ids is not None and scheduled:
            desired_tasks = set(mutation.task_ids)
            current_tasks = (
                self.db.query(PaperTask)
                .filter(PaperTask.paper_id == row.paper_id)
                .all()
            )
            for link in current_tasks:
                if link.task_id not in desired_tasks:
                    self.db.delete(link)
                else:
                    desired_tasks.discard(link.task_id)
            for task_id in desired_tasks:
                self.db.add(
                    PaperTask(paper_id=row.paper_id, task_id=task_id, source="auto")
                )
        elif mutation.task_ids is not None:
            self.paper_service.update_paper_tasks(
                row.paper_id, mutation.task_ids, commit=False
            )
        if mutation.method_ids is not None and scheduled:
            desired_methods = set(mutation.method_ids)
            current_methods = {
                item.method_id
                for item in self.db.query(PaperMethod).filter(
                    PaperMethod.paper_id == row.paper_id
                )
            }
            for method_id in current_methods - desired_methods:
                self.db.query(PaperMethodEvidence).filter(
                    PaperMethodEvidence.paper_id == row.paper_id,
                    PaperMethodEvidence.method_id == method_id,
                ).delete(synchronize_session=False)
                link = self.db.get(PaperMethod, (row.paper_id, method_id))
                if link is not None:
                    self.db.delete(link)
            for method_id in desired_methods:
                exclusion = self.db.get(PaperMethodExclusion, (row.paper_id, method_id))
                if exclusion is not None:
                    self.db.delete(exclusion)
            self.db.flush()
            upsert_evidence_links(
                self.db,
                (
                    {"paper_id": row.paper_id, "method_id": method_id}
                    for method_id in desired_methods
                ),
                evidence_type="curation",
                details={"job_id": str(row.id), "policy_version": row.policy_version},
            )
        elif mutation.method_ids is not None:
            self.paper_service.update_paper_methods(
                row.paper_id, mutation.method_ids, commit=False
            )
        if mutation.method_ids is not None:
            for method_id, reason in mutation.method_removal_reasons.items():
                exclusion = self.db.get(PaperMethodExclusion, (row.paper_id, method_id))
                if exclusion is None:
                    self.db.add(
                        PaperMethodExclusion(
                            paper_id=row.paper_id,
                            method_id=method_id,
                            reason=reason[:2_000],
                        )
                    )
                else:
                    exclusion.reason = reason[:2_000]
                    exclusion.updated_at = datetime.now(UTC)
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
        if any(
            value is not None
            for value in (mutation.hf_models, mutation.hf_datasets, mutation.hf_spaces)
        ):
            self.paper_service.update_paper_hf_artifacts(
                row.paper_id,
                mutation.hf_models
                if mutation.hf_models is not None
                else (paper.hf_models or []),
                mutation.hf_datasets
                if mutation.hf_datasets is not None
                else (paper.hf_datasets or []),
                mutation.hf_spaces
                if mutation.hf_spaces is not None
                else (paper.hf_spaces or []),
                commit=False,
            )
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
