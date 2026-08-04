"""
Service for non-admin paper edit submissions.

Backs the `/api/v1/me/paper-edits` (user submit) and `/api/v1/admin/paper-edits`
(admin list / approve / reject) endpoints. Edit application is delegated to the
existing mutation services (``PaperService`` and ``EvaluationService``) so admin
direct edits and approved submissions go through the same code path.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, UnidentifiedImageError
from sqlalchemy import desc, text
from sqlalchemy.orm import Session

from backend.models.database import (
    Author as DBAuthor,
    CatalogMutationEvent,
    Conference as DBConference,
    Dataset as DBDataset,
    Evaluation as DBEvaluation,
    Method as DBMethod,
    Metric as DBMetric,
    Paper as DBPaper,
    PaperAuthor,
    PaperConference,
    PaperMethod,
    PaperOrganization,
    PaperProjectPage,
    PaperRepository,
    PaperTask,
    PendingPaperEdit,
    ProjectPage as DBProjectPage,
    Repository as DBRepository,
    Organization as DBOrganization,
    Task as DBTask,
    TaskDataset,
    TaskDatasetMetric,
    UserProfile,
    UserProfileAlias,
)
from backend.config import get_settings
from backend.services.evaluation_service import EvaluationService
from backend.services.external_resource_service import (
    ExternalResourceInput,
    ExternalResourceService,
)
from backend.services.evaluation_curation_service import EvaluationCurationService
from backend.services.paper_curation_service import PaperCurationService
from backend.services.catalog_mutation_service import json_safe
from backend.services.paper_service import PaperService
from backend.services.task_service import TaskService
from backend.services.dataset_service import DatasetService
from backend.services.method_service import MethodService
from backend.services.metric_service import MetricService
from backend.services.conference_service import ConferenceService
from backend.models.api import TaskCreateRequest, DatasetCreateRequest
from backend.utils.exceptions import DatabaseError, PaperNotFoundError
from backend.utils.public_urls import PublicUrlValidationError, normalize_public_url


EDIT_TYPES = frozenset(
    {
        "tasks",
        "methods",
        "evaluations",
        "repositories",
        "project_pages",
        "source_url",
        "hf_artifacts",
        "organizations",
        "new_task",
        "new_method",
        "new_benchmark",
        "new_metric",
        "new_conference",
        "new_external_paper",
    }
)
STATUSES = frozenset({"pending", "approved", "rejected"})
SUGGESTION_IMAGE_MAX_BYTES = 2 * 1024 * 1024
SUGGESTION_IMAGE_FORMATS = {
    "GIF": "image/gif",
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}
logger = logging.getLogger(__name__)


class PendingEditError(Exception):
    """Raised for validation problems with pending edit submissions or reviews."""


class PendingEditNotFoundError(PendingEditError):
    """Raised when a pending edit row cannot be found."""


class PendingEditAlreadyReviewedError(PendingEditError):
    """Raised when an admin tries to approve or reject a non-pending row."""


class PendingEditConflictError(PendingEditError):
    pass


class SubmissionRateLimitError(PendingEditError):
    def __init__(self, message: str, *, retry_after: int = 3600):
        super().__init__(message)
        self.retry_after = retry_after


class SubmissionSuspendedError(PendingEditError):
    pass


class PendingEditService:
    """Submission and review of non-admin paper edits."""

    def __init__(self, db: Session):
        self.db = db

    # ----------------------------------------------------------------
    # Author resolution
    # ----------------------------------------------------------------

    def is_linked_author(self, paper_id: int, hf_username: str) -> bool:
        """
        Return True if ``hf_username`` matches a linked author of the paper.

        Uses the canonical ``papers`` -> ``paper_authors`` -> ``authors`` chain
        and a case-insensitive comparison on ``authors.hf_username``. Returns
        False for empty usernames or papers with no linked authors.
        """

        if not hf_username:
            return False

        normalized = hf_username.strip().lower()
        if not normalized:
            return False

        match = (
            self.db.query(PaperAuthor.paper_id)
            .join(DBAuthor, PaperAuthor.author_id == DBAuthor.id)
            .filter(
                PaperAuthor.paper_id == paper_id,
                DBAuthor.hf_username.isnot(None),
                # `LOWER(authors.hf_username) = :normalized` is portable; the
                # column is `String(255)` so this remains cheap even without
                # a functional index.
                DBAuthor.hf_username.ilike(normalized),
            )
            .first()
        )
        return match is not None

    # ----------------------------------------------------------------
    # Snapshot helpers (current_payload at submit time)
    # ----------------------------------------------------------------

    def _snapshot_tasks(self, paper_id: int) -> Dict[str, Any]:
        from backend.models.database import Task as DBTask

        rows = (
            self.db.query(DBTask.id, DBTask.name, DBTask.slug)
            .join(PaperTask, PaperTask.task_id == DBTask.id)
            .filter(PaperTask.paper_id == paper_id)
            .order_by(DBTask.name)
            .all()
        )
        return {
            "tasks": [{"id": row[0], "name": row[1], "slug": row[2]} for row in rows]
        }

    def _snapshot_methods(self, paper_id: int) -> Dict[str, Any]:
        from backend.models.database import Method as DBMethod

        rows = (
            self.db.query(DBMethod.id, DBMethod.name, DBMethod.slug)
            .join(PaperMethod, PaperMethod.method_id == DBMethod.id)
            .filter(PaperMethod.paper_id == paper_id)
            .order_by(DBMethod.name)
            .all()
        )
        return {
            "methods": [{"id": row[0], "name": row[1], "slug": row[2]} for row in rows]
        }

    def _snapshot_repositories(self, paper_id: int) -> Dict[str, Any]:
        rows = (
            self.db.query(DBRepository.url, PaperRepository.is_official)
            .join(PaperRepository, PaperRepository.repository_id == DBRepository.id)
            .filter(PaperRepository.paper_id == paper_id)
            .order_by(desc(PaperRepository.is_official), DBRepository.url)
            .all()
        )
        return {
            "repositories": [
                {"url": row[0], "is_official": bool(row[1])} for row in rows
            ]
        }

    def _snapshot_project_pages(self, paper_id: int) -> Dict[str, Any]:
        rows = (
            self.db.query(DBProjectPage.url, DBProjectPage.is_official)
            .join(
                PaperProjectPage,
                PaperProjectPage.project_page_id == DBProjectPage.id,
            )
            .filter(PaperProjectPage.paper_id == paper_id)
            .order_by(DBProjectPage.url)
            .all()
        )
        return {
            "project_pages": [
                {"url": row[0], "is_official": bool(row[1])} for row in rows
            ]
        }

    def _snapshot_organizations(self, paper_id: int) -> Dict[str, Any]:
        rows = (
            self.db.query(DBOrganization.id, DBOrganization.name, DBOrganization.slug)
            .join(
                PaperOrganization,
                PaperOrganization.organization_id == DBOrganization.id,
            )
            .filter(PaperOrganization.paper_id == paper_id)
            .order_by(DBOrganization.name)
            .all()
        )
        return {
            "organizations": [
                {"id": row[0], "name": row[1], "slug": row[2]} for row in rows
            ]
        }

    def _snapshot_source_url(self, paper_id: int) -> Dict[str, Any]:
        row = (
            self.db.query(DBPaper.source, DBPaper.source_url)
            .filter(DBPaper.id == paper_id)
            .first()
        )
        if row is None:
            raise PaperNotFoundError(f"Paper with ID {paper_id} not found")
        return {"source_url": row[1], "source": row[0]}

    def _snapshot_evaluations(self, paper_id: int) -> Dict[str, Any]:
        rows = (
            self.db.query(DBEvaluation)
            .filter(DBEvaluation.paper_id == paper_id)
            .order_by(DBEvaluation.id)
            .all()
        )
        return {
            "evaluations": [
                {
                    "id": row.id,
                    "task_id": row.task_id,
                    "dataset_id": row.dataset_id,
                    "model_name": row.model_name,
                    "harness": row.harness,
                    "methodology": row.methodology,
                    "metrics": row.metrics,
                    "uses_additional_data": row.uses_additional_data,
                    "is_open": row.is_open,
                    "best_rank": row.best_rank,
                    "best_metric": row.best_metric,
                    "evaluated_on": row.evaluated_on.isoformat()
                    if row.evaluated_on
                    else None,
                    "external_source_url": row.external_source_url,
                    "num_parameters": row.num_parameters,
                    "hf_model_url": row.hf_model_url,
                }
                for row in rows
            ]
        }

    def _snapshot_hf_artifacts(self, paper_id: int) -> Dict[str, Any]:
        row = (
            self.db.query(
                DBPaper.hf_models,
                DBPaper.hf_datasets,
                DBPaper.hf_spaces,
            )
            .filter(DBPaper.id == paper_id)
            .first()
        )
        if row is None:
            raise PaperNotFoundError(f"Paper with ID {paper_id} not found")
        return {
            "hf_models": list(row[0] or []),
            "hf_datasets": list(row[1] or []),
            "hf_spaces": list(row[2] or []),
        }

    def _build_snapshot(self, paper_id: int, edit_type: str) -> Dict[str, Any]:
        if edit_type == "tasks":
            return self._snapshot_tasks(paper_id)
        if edit_type == "methods":
            return self._snapshot_methods(paper_id)
        if edit_type == "repositories":
            return self._snapshot_repositories(paper_id)
        if edit_type == "project_pages":
            return self._snapshot_project_pages(paper_id)
        if edit_type == "organizations":
            return self._snapshot_organizations(paper_id)
        if edit_type == "evaluations":
            return self._snapshot_evaluations(paper_id)
        if edit_type == "source_url":
            return self._snapshot_source_url(paper_id)
        if edit_type == "hf_artifacts":
            return self._snapshot_hf_artifacts(paper_id)
        if edit_type in (
            "new_task",
            "new_method",
            "new_benchmark",
            "new_metric",
            "new_conference",
            "new_external_paper",
        ):
            # Suggestions for brand-new taxonomy entries have no existing live
            # state to diff against.
            return {}
        raise PendingEditError(f"Unsupported edit_type: {edit_type}")

    # ----------------------------------------------------------------
    # Payload validation
    # ----------------------------------------------------------------

    @staticmethod
    def _normalize_suggestion_image(image: Any) -> Dict[str, str]:
        if not isinstance(image, dict):
            raise PendingEditError("Suggestion 'image' must be an object")

        file_name = image.get("file_name")
        mime_type = image.get("mime_type")
        data_url = image.get("data_url")
        if not isinstance(file_name, str) or not file_name.strip():
            raise PendingEditError(
                "Suggestion image file name must be a non-empty string"
            )
        normalized_file_name = file_name.strip()
        if len(normalized_file_name) > 255:
            raise PendingEditError(
                "Suggestion image file name must be at most 255 characters"
            )
        if mime_type not in SUGGESTION_IMAGE_FORMATS.values():
            raise PendingEditError("Suggestion image must be a JPEG, PNG, WebP, or GIF")
        if not isinstance(data_url, str):
            raise PendingEditError("Suggestion image data must be a string")

        prefix = f"data:{mime_type};base64,"
        if not data_url.startswith(prefix):
            raise PendingEditError("Suggestion image data does not match its MIME type")
        try:
            content = base64.b64decode(data_url[len(prefix) :], validate=True)
        except (binascii.Error, ValueError) as exc:
            raise PendingEditError("Suggestion image data is not valid base64") from exc
        if not content:
            raise PendingEditError("Suggestion image must not be empty")
        if len(content) > SUGGESTION_IMAGE_MAX_BYTES:
            raise PendingEditError("Suggestion image must be 2 MB or smaller")

        try:
            with Image.open(BytesIO(content)) as opened_image:
                detected_mime = SUGGESTION_IMAGE_FORMATS.get(opened_image.format or "")
                opened_image.verify()
        except (UnidentifiedImageError, OSError, SyntaxError) as exc:
            raise PendingEditError(
                "Suggestion image is not a valid supported image"
            ) from exc
        if detected_mime != mime_type:
            raise PendingEditError("Suggestion image data does not match its MIME type")

        return {
            "file_name": normalized_file_name,
            "mime_type": mime_type,
            "data_url": data_url,
        }

    @staticmethod
    def _is_valid_evaluation_create_data(data: Dict[str, Any]) -> bool:
        task_id = data.get("task_id")
        dataset_id = data.get("dataset_id")
        if not isinstance(task_id, int) or task_id <= 0:
            return False
        if not isinstance(dataset_id, int) or dataset_id <= 0:
            return False

        best_metric = data.get("best_metric")
        if not isinstance(best_metric, str) or not best_metric.strip():
            return False

        metrics = data.get("metrics")
        if not isinstance(metrics, dict) or not metrics:
            return False
        for name, value in metrics.items():
            if not isinstance(name, str) or not name.strip():
                return False
            if value is None:
                return False
            if isinstance(value, str) and not value.strip():
                return False
        return True

    @staticmethod
    def _validate_payload(edit_type: str, payload: Any) -> Dict[str, Any]:
        """Shape-check ``proposed_payload`` for the given ``edit_type``.

        Raises ``PendingEditError`` with a user-readable message if the shape
        is wrong. Approval will re-validate against the underlying mutation
        services (which already do their own validation), so this method only
        rejects payloads that the approval step would not understand at all.
        """

        if not isinstance(payload, dict):
            raise PendingEditError("proposed_payload must be a JSON object")

        if edit_type == "tasks":
            task_ids = payload.get("task_ids")
            if not isinstance(task_ids, list) or not all(
                isinstance(t, int) for t in task_ids
            ):
                raise PendingEditError('Tasks payload must be {"task_ids": [int, ...]}')
            return {"task_ids": list(task_ids)}

        if edit_type == "methods":
            method_ids = payload.get("method_ids")
            if not isinstance(method_ids, list) or not all(
                isinstance(m, int) for m in method_ids
            ):
                raise PendingEditError(
                    'Methods payload must be {"method_ids": [int, ...]}'
                )
            return {"method_ids": list(method_ids)}

        if edit_type == "repositories":
            repos = payload.get("repositories")
            if not isinstance(repos, list):
                raise PendingEditError(
                    "Repositories payload must be "
                    '{"repositories": [{"url": str, "is_official": bool}, ...]}'
                )
            out: List[Dict[str, Any]] = []
            for repo in repos:
                if (
                    not isinstance(repo, dict)
                    or not isinstance(repo.get("url"), str)
                    or not isinstance(repo.get("is_official"), bool)
                ):
                    raise PendingEditError(
                        "Each repository must have a string 'url' and bool 'is_official'"
                    )
                try:
                    url = normalize_public_url(repo["url"])
                except PublicUrlValidationError as exc:
                    raise PendingEditError(str(exc)) from exc
                out.append({"url": url, "is_official": repo["is_official"]})
            return {"repositories": out}

        if edit_type == "project_pages":
            pages = payload.get("project_pages")
            if not isinstance(pages, list):
                raise PendingEditError(
                    "Project pages payload must be "
                    '{"project_pages": [{"url": str, "is_official": bool}, ...]}'
                )
            out = []
            for page in pages:
                if (
                    not isinstance(page, dict)
                    or not isinstance(page.get("url"), str)
                    or not isinstance(page.get("is_official"), bool)
                ):
                    raise PendingEditError(
                        "Each project page must have a string 'url' and bool 'is_official'"
                    )
                try:
                    url = normalize_public_url(page["url"])
                except PublicUrlValidationError as exc:
                    raise PendingEditError(str(exc)) from exc
                out.append({"url": url, "is_official": page["is_official"]})
            return {"project_pages": out}

        if edit_type == "organizations":
            organization_ids = payload.get("organization_ids")
            if not isinstance(organization_ids, list) or not all(
                isinstance(item, int) for item in organization_ids
            ):
                raise PendingEditError(
                    "Organizations payload must be {'organization_ids': [int, ...]}"
                )
            return {"organization_ids": sorted(set(organization_ids))}

        if edit_type == "source_url":
            source_url = payload.get("source_url")
            if not isinstance(source_url, str):
                raise PendingEditError('Source URL payload must be {"source_url": str}')
            try:
                normalized = normalize_public_url(source_url)
            except PublicUrlValidationError as exc:
                raise PendingEditError(str(exc)) from exc
            return {"source_url": normalized}

        if edit_type == "hf_artifacts":
            from backend.utils.hf_utils import normalize_hf_artifact_payload

            for key in ("hf_models", "hf_datasets", "hf_spaces"):
                values = payload.get(key)
                if not isinstance(values, list) or not all(
                    isinstance(item, str) for item in values
                ):
                    raise PendingEditError(
                        "HF artifacts payload must be "
                        '{"hf_models": [str, ...], "hf_datasets": [str, ...], '
                        '"hf_spaces": [str, ...]}'
                    )
            try:
                models, datasets, spaces = normalize_hf_artifact_payload(
                    list(payload.get("hf_models", [])),
                    list(payload.get("hf_datasets", [])),
                    list(payload.get("hf_spaces", [])),
                )
            except ValueError as exc:
                raise PendingEditError(str(exc)) from exc
            return {
                "hf_models": models,
                "hf_datasets": datasets,
                "hf_spaces": spaces,
            }

        if edit_type == "new_external_paper":
            source_url = payload.get("source_url")
            if not isinstance(source_url, str):
                raise PendingEditError("External paper source_url must be a string")
            try:
                normalized_url = normalize_public_url(source_url)
            except PublicUrlValidationError as exc:
                raise PendingEditError(str(exc)) from exc
            normalized_external: Dict[str, Any] = {"source_url": normalized_url}
            for field, limit in (("title", 500), ("abstract", 20_000)):
                value = payload.get(field)
                if value is not None:
                    if not isinstance(value, str) or len(value.strip()) > limit:
                        raise PendingEditError(f"External paper {field} is invalid")
                    if value.strip():
                        normalized_external[field] = value.strip()
            authors = payload.get("authors") or []
            if not isinstance(authors, list) or not all(
                isinstance(author, str) and author.strip() for author in authors
            ):
                raise PendingEditError("External paper authors must be a list of names")
            normalized_external["authors"] = [author.strip() for author in authors]
            published = payload.get("date_published")
            if published is not None:
                if not isinstance(published, str):
                    raise PendingEditError(
                        "External paper date_published must be ISO text"
                    )
                try:
                    datetime.fromisoformat(published)
                except ValueError as exc:
                    raise PendingEditError(
                        "External paper date_published is invalid"
                    ) from exc
                normalized_external["date_published"] = published
            return normalized_external

        if edit_type in (
            "new_task",
            "new_method",
            "new_benchmark",
            "new_metric",
            "new_conference",
        ):
            name = payload.get("name")
            description = payload.get("description")
            if not isinstance(name, str):
                raise PendingEditError("Suggestion 'name' must be a string")
            normalized_name = name.strip()
            if not normalized_name:
                raise PendingEditError("Suggestion 'name' must be a non-empty string")
            if len(normalized_name) > 200:
                raise PendingEditError(
                    "Suggestion 'name' must be at most 200 characters"
                )

            normalized_payload = {"name": normalized_name}
            if description is not None:
                if not isinstance(description, str):
                    raise PendingEditError("Suggestion 'description' must be a string")
                normalized_description = description.strip()
                if normalized_description:
                    if len(normalized_description) > 2000:
                        raise PendingEditError(
                            "Suggestion 'description' must be at most 2000 characters"
                        )
                    normalized_payload["description"] = normalized_description

            def optional_text(field: str, limit: int) -> None:
                value = payload.get(field)
                if value is None:
                    return
                if not isinstance(value, str) or len(value.strip()) > limit:
                    raise PendingEditError(f"Suggestion '{field}' is invalid")
                if value.strip():
                    normalized_payload[field] = value.strip()

            def optional_id(field: str) -> None:
                value = payload.get(field)
                if value is not None:
                    if not isinstance(value, int) or value <= 0:
                        raise PendingEditError(
                            f"Suggestion '{field}' must be a positive integer"
                        )
                    normalized_payload[field] = value

            if edit_type == "new_conference":
                for field, limit in (
                    ("short_name", 50),
                    ("venue", 300),
                    ("location", 300),
                    ("description", 2000),
                    ("url", 500),
                ):
                    optional_text(field, limit)
                year = payload.get("year")
                if not isinstance(year, int) or not 1900 <= year <= 2200:
                    raise PendingEditError("Conference 'year' is required")
                normalized_payload["year"] = year
                for field in ("start_date", "end_date"):
                    value = payload.get(field)
                    if value is not None:
                        if not isinstance(value, str):
                            raise PendingEditError(
                                f"Conference '{field}' must be an ISO date"
                            )
                        try:
                            date.fromisoformat(value)
                        except ValueError as exc:
                            raise PendingEditError(
                                f"Conference '{field}' must be an ISO date"
                            ) from exc
                        normalized_payload[field] = value
                if normalized_payload.get("url"):
                    try:
                        normalized_payload["url"] = normalize_public_url(
                            normalized_payload["url"]
                        )
                    except PublicUrlValidationError as exc:
                        raise PendingEditError(str(exc)) from exc
                else:
                    raise PendingEditError("Conference source URL is required")
                return normalized_payload

            if edit_type == "new_benchmark":
                if "description" not in normalized_payload:
                    raise PendingEditError("Benchmark 'description' is required")
                task_ids = payload.get("task_ids")
                if (
                    not isinstance(task_ids, list)
                    or not task_ids
                    or not all(isinstance(item, int) and item > 0 for item in task_ids)
                ):
                    raise PendingEditError(
                        "Benchmark 'task_ids' must contain positive integers"
                    )
                normalized_payload["task_ids"] = sorted(set(task_ids))
                for field, limit in (
                    ("full_name", 500),
                    ("url", 500),
                    ("hf_url", 500),
                    ("paper_url", 500),
                    ("license_name", 255),
                    ("license_url", 500),
                ):
                    optional_text(field, limit)
                for field in ("url", "hf_url", "paper_url", "license_url"):
                    if normalized_payload.get(field):
                        try:
                            normalized_payload[field] = normalize_public_url(
                                normalized_payload[field]
                            )
                        except PublicUrlValidationError as exc:
                            raise PendingEditError(str(exc)) from exc
                return normalized_payload

            if edit_type == "new_metric":
                if "description" not in normalized_payload:
                    raise PendingEditError("Metric 'description' is required")
                direction = payload.get("direction")
                if direction not in ("higher_is_better", "lower_is_better"):
                    raise PendingEditError("Metric 'direction' is required")
                normalized_payload["direction"] = direction
                optional_text("full_name", 255)
                optional_text("scale", 50)
                optional_id("task_id")
                optional_id("dataset_id")
                if (
                    "task_id" not in normalized_payload
                    or "dataset_id" not in normalized_payload
                ):
                    raise PendingEditError(
                        "Metric leaderboard needs both task_id and dataset_id"
                    )
                return normalized_payload

            image = payload.get("image")
            if image is not None:
                normalized_payload["image"] = (
                    PendingEditService._normalize_suggestion_image(image)
                )

            image_credit = payload.get("image_credit")
            if image_credit is not None:
                if not isinstance(image_credit, str):
                    raise PendingEditError("Suggestion 'image_credit' must be a string")
                normalized_image_credit = image_credit.strip()
                if normalized_image_credit:
                    if len(normalized_image_credit) > 1000:
                        raise PendingEditError(
                            "Suggestion 'image_credit' must be at most 1000 characters"
                        )
                    normalized_payload["image_credit"] = normalized_image_credit

            if edit_type == "new_method":
                optional_id("source_paper_id")
                optional_text("source_url", 500)
                optional_text("source_title", 500)
                if normalized_payload.get("source_url"):
                    try:
                        normalized_payload["source_url"] = normalize_public_url(
                            normalized_payload["source_url"]
                        )
                    except PublicUrlValidationError as exc:
                        raise PendingEditError(str(exc)) from exc
                if (
                    "source_paper_id" not in normalized_payload
                    and "source_url" not in normalized_payload
                ):
                    raise PendingEditError(
                        "Method source_paper_id or source_url is required"
                    )

            if edit_type == "new_task":
                optional_id("parent_id")
                optional_id("area_id")
                optional_text("keywords", 2000)

            return normalized_payload

        if edit_type == "evaluations":
            operations = payload.get("operations")
            if not isinstance(operations, list) or not operations:
                raise PendingEditError(
                    "Evaluations payload must be "
                    '{"operations": [{"op": ..., ...}, ...]} with at least one operation'
                )
            out_ops: List[Dict[str, Any]] = []
            for op in operations:
                if not isinstance(op, dict):
                    raise PendingEditError(
                        "Each evaluation operation must be an object"
                    )
                kind = op.get("op")
                if kind not in {"create", "update", "delete"}:
                    raise PendingEditError(
                        "Evaluation op must be one of: 'create', 'update', 'delete'"
                    )
                if kind == "create":
                    data = op.get("data")
                    if not isinstance(data, dict):
                        raise PendingEditError(
                            "Evaluation create op needs a 'data' object"
                        )
                    if not PendingEditService._is_valid_evaluation_create_data(data):
                        continue
                    normalized_data = dict(data)
                    for field in ("external_source_url", "source_url", "hf_model_url"):
                        if normalized_data.get(field) is not None:
                            try:
                                normalized_data[field] = normalize_public_url(
                                    normalized_data[field]
                                )
                            except (PublicUrlValidationError, TypeError) as exc:
                                raise PendingEditError(str(exc)) from exc
                    out_ops.append({"op": "create", "data": normalized_data})
                elif kind == "update":
                    evaluation_id = op.get("evaluation_id")
                    data = op.get("data")
                    if not isinstance(evaluation_id, int) or not isinstance(data, dict):
                        raise PendingEditError(
                            "Evaluation update op needs int 'evaluation_id' and 'data' object"
                        )
                    normalized_data = dict(data)
                    for field in ("external_source_url", "source_url", "hf_model_url"):
                        if normalized_data.get(field) is not None:
                            try:
                                normalized_data[field] = normalize_public_url(
                                    normalized_data[field]
                                )
                            except (PublicUrlValidationError, TypeError) as exc:
                                raise PendingEditError(str(exc)) from exc
                    out_ops.append(
                        {
                            "op": "update",
                            "evaluation_id": evaluation_id,
                            "data": normalized_data,
                        }
                    )
                else:  # delete
                    evaluation_id = op.get("evaluation_id")
                    if not isinstance(evaluation_id, int):
                        raise PendingEditError(
                            "Evaluation delete op needs int 'evaluation_id'"
                        )
                    out_ops.append({"op": "delete", "evaluation_id": evaluation_id})
            if not out_ops:
                raise PendingEditError(
                    "Evaluations payload must include at least one valid operation"
                )
            return {"operations": out_ops}

        raise PendingEditError(f"Unsupported edit_type: {edit_type}")

    # ----------------------------------------------------------------
    # No-op detection
    # ----------------------------------------------------------------

    @staticmethod
    def _is_noop(
        edit_type: str,
        normalized_payload: Dict[str, Any],
        current_payload: Dict[str, Any],
    ) -> bool:
        """Return True when the normalized payload matches the current state.

        Prevents submissions that would not change anything from creating
        review rows on the submissions dashboard. Evaluation operations are
        already required to be non-empty by ``_validate_payload``; we don't
        replay them here because that would duplicate the approval logic.
        """

        if edit_type == "tasks":
            current_ids = {int(item["id"]) for item in current_payload.get("tasks", [])}
            proposed_ids = set(normalized_payload.get("task_ids", []))
            return current_ids == proposed_ids

        if edit_type == "methods":
            current_ids = {
                int(item["id"]) for item in current_payload.get("methods", [])
            }
            proposed_ids = set(normalized_payload.get("method_ids", []))
            return current_ids == proposed_ids

        if edit_type == "repositories":
            current = {
                (item["url"].strip(), bool(item["is_official"]))
                for item in current_payload.get("repositories", [])
            }
            proposed = {
                (item["url"].strip(), bool(item["is_official"]))
                for item in normalized_payload.get("repositories", [])
            }
            return current == proposed

        if edit_type == "project_pages":
            current = {
                (item["url"].strip(), bool(item["is_official"]))
                for item in current_payload.get("project_pages", [])
            }
            proposed = {
                (item["url"].strip(), bool(item["is_official"]))
                for item in normalized_payload.get("project_pages", [])
            }
            return current == proposed

        if edit_type == "organizations":
            current = {
                int(item["id"]) for item in current_payload.get("organizations", [])
            }
            return current == set(normalized_payload.get("organization_ids", []))

        if edit_type == "source_url":
            current = (current_payload.get("source_url") or "").strip()
            proposed = (normalized_payload.get("source_url") or "").strip()
            return current == proposed

        if edit_type == "hf_artifacts":
            for key in ("hf_models", "hf_datasets", "hf_spaces"):
                current = sorted(current_payload.get(key) or [])
                proposed = sorted(normalized_payload.get(key) or [])
                if current != proposed:
                    return False
            return True

        if edit_type in (
            "new_task",
            "new_method",
            "new_benchmark",
            "new_metric",
            "new_conference",
        ):
            # Suggestions for new taxonomy entries are never a no-op; there is
            # no existing entry to compare against.
            return False

        # `evaluations` already requires at least one operation; treat any
        # well-formed operation list as a real change for now.
        return False

    # ----------------------------------------------------------------
    # Submission
    # ----------------------------------------------------------------

    def submit(
        self,
        *,
        paper_id: Optional[int],
        hf_username: str,
        hf_subject: Optional[str] = None,
        source_ip: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        exempt_from_limits: bool = False,
        edit_type: str,
        proposed_payload: Any,
    ) -> PendingPaperEdit:
        if edit_type not in EDIT_TYPES:
            raise PendingEditError(
                f"Unsupported edit_type: {edit_type}. Allowed: {sorted(EDIT_TYPES)}"
            )

        is_taxonomy_suggestion = edit_type in (
            "new_task",
            "new_method",
            "new_benchmark",
            "new_metric",
            "new_conference",
            "new_external_paper",
        )
        if paper_id is None and not is_taxonomy_suggestion:
            raise PendingEditError(
                "paper_id is required unless submitting a taxonomy suggestion"
            )
        if paper_id is not None:
            paper_exists = (
                self.db.query(DBPaper.id).filter(DBPaper.id == paper_id).first()
            )
            if not paper_exists:
                raise PaperNotFoundError(f"Paper with ID {paper_id} not found")

        normalized_payload = self._validate_payload(edit_type, proposed_payload)
        settings = get_settings()
        encoded_payload = json.dumps(
            normalized_payload, sort_keys=True, separators=(",", ":")
        ).encode()
        if len(encoded_payload) > settings.submission_max_payload_bytes:
            raise PendingEditError("Submission payload is too large")
        payload_hash = hashlib.sha256(encoded_payload).hexdigest()
        stable_subject = hf_subject or f"legacy-username:{hf_username.lower()}"
        if idempotency_key and len(idempotency_key) > 255:
            raise PendingEditError("Idempotency key is too long")
        if self.db.bind is not None and self.db.bind.dialect.name == "postgresql":
            self.db.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:subject, 0))"),
                {"subject": stable_subject},
            )

        profile = (
            self.db.query(UserProfile)
            .filter(UserProfile.hf_subject == stable_subject)
            .with_for_update()
            .first()
        )
        normalized_username = hf_username.strip().lower()
        if profile is None:
            profile = UserProfile(
                hf_subject=stable_subject,
                current_username=normalized_username,
            )
            self.db.add(profile)
            self.db.flush()
            self.db.add(
                UserProfileAlias(
                    alias=normalized_username,
                    hf_subject=stable_subject,
                )
            )
        elif profile.current_username != normalized_username:
            existing_alias = self.db.get(UserProfileAlias, normalized_username)
            if (
                existing_alias is not None
                and existing_alias.hf_subject != stable_subject
            ):
                raise PendingEditError("Hugging Face username is already claimed")
            profile.current_username = normalized_username
            if existing_alias is None:
                self.db.add(
                    UserProfileAlias(
                        alias=normalized_username,
                        hf_subject=stable_subject,
                    )
                )
        if profile.is_submission_suspended:
            raise SubmissionSuspendedError("This account cannot create new submissions")

        if idempotency_key:
            replay = (
                self.db.query(PendingPaperEdit)
                .filter(
                    PendingPaperEdit.hf_subject == stable_subject,
                    PendingPaperEdit.idempotency_key == idempotency_key,
                )
                .first()
            )
            if replay is not None:
                if replay.payload_hash != payload_hash:
                    raise PendingEditError(
                        "Idempotency key was already used for another payload"
                    )
                return replay
        current_payload = (
            {} if paper_id is None else self._build_snapshot(paper_id, edit_type)
        )

        if self._is_noop(edit_type, normalized_payload, current_payload):
            raise PendingEditError("Submission does not contain any changes.")

        duplicate = (
            self.db.query(PendingPaperEdit)
            .filter(
                PendingPaperEdit.hf_subject == stable_subject,
                PendingPaperEdit.edit_type == edit_type,
                PendingPaperEdit.paper_id == paper_id,
                PendingPaperEdit.payload_hash == payload_hash,
                PendingPaperEdit.status == "pending",
            )
            .first()
        )
        if duplicate is not None:
            return duplicate

        if not exempt_from_limits:
            active = (
                self.db.query(PendingPaperEdit.id)
                .filter(
                    PendingPaperEdit.hf_subject == stable_subject,
                    PendingPaperEdit.status == "pending",
                )
                .count()
            )
            if active >= settings.submission_max_active_pending:
                raise SubmissionRateLimitError(
                    "Active pending submission limit reached"
                )
            window_start = datetime.now(timezone.utc) - timedelta(hours=1)
            subject_created = (
                self.db.query(PendingPaperEdit.id)
                .filter(
                    PendingPaperEdit.hf_subject == stable_subject,
                    PendingPaperEdit.created_at >= window_start,
                )
                .count()
            )
            if subject_created >= settings.submission_hourly_subject_limit:
                raise SubmissionRateLimitError(
                    "Hourly account submission limit reached"
                )
            if source_ip:
                ip_created = (
                    self.db.query(PendingPaperEdit.id)
                    .filter(
                        PendingPaperEdit.source_ip == source_ip,
                        PendingPaperEdit.created_at >= window_start,
                    )
                    .count()
                )
                if ip_created >= settings.submission_hourly_ip_limit:
                    raise SubmissionRateLimitError(
                        "Hourly network submission limit reached"
                    )

        is_author = (
            self.is_linked_author(paper_id, hf_username)
            if paper_id is not None
            else False
        )

        row = PendingPaperEdit(
            paper_id=paper_id,
            hf_username=hf_username,
            hf_subject=stable_subject,
            source_ip=source_ip,
            idempotency_key=idempotency_key,
            payload_hash=payload_hash,
            is_author=is_author,
            edit_type=edit_type,
            proposed_payload=normalized_payload,
            current_payload=current_payload,
            status="pending",
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        logger.info(
            "submission_created id=%s subject=%s edit_type=%s paper_id=%s",
            row.id,
            stable_subject,
            edit_type,
            paper_id,
        )
        return row

    # ----------------------------------------------------------------
    # Listing
    # ----------------------------------------------------------------

    def list_edits(
        self,
        *,
        status: Optional[str] = None,
        edit_type: Optional[str] = None,
        paper_id: Optional[int] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[PendingPaperEdit], int]:
        if status is not None and status not in STATUSES:
            raise PendingEditError(
                f"Unsupported status: {status}. Allowed: {sorted(STATUSES)}"
            )
        if edit_type is not None and edit_type not in EDIT_TYPES:
            raise PendingEditError(
                f"Unsupported edit_type: {edit_type}. Allowed: {sorted(EDIT_TYPES)}"
            )

        query = self.db.query(PendingPaperEdit)
        if status:
            query = query.filter(PendingPaperEdit.status == status)
        if edit_type:
            query = query.filter(PendingPaperEdit.edit_type == edit_type)
        if paper_id is not None:
            query = query.filter(PendingPaperEdit.paper_id == paper_id)

        total = query.count()

        rows = (
            query.order_by(desc(PendingPaperEdit.created_at))
            .offset(offset)
            .limit(limit)
            .all()
        )
        return rows, total

    def get(self, edit_id: int) -> PendingPaperEdit:
        row = (
            self.db.query(PendingPaperEdit)
            .filter(PendingPaperEdit.id == edit_id)
            .first()
        )
        if not row:
            raise PendingEditNotFoundError(f"Pending edit with ID {edit_id} not found")
        return row

    # ----------------------------------------------------------------
    # Approval / rejection
    # ----------------------------------------------------------------

    def approve(
        self,
        *,
        edit_id: int,
        reviewer_username: Optional[str],
        reviewer_hf_subject: Optional[str] = None,
        resolved_payload: Optional[Dict[str, Any]] = None,
        admin_note: Optional[str] = None,
        user_review_reason: Optional[str] = None,
    ) -> PendingPaperEdit:
        row = (
            self.db.query(PendingPaperEdit)
            .filter(PendingPaperEdit.id == edit_id)
            .with_for_update()
            .first()
        )
        if row is None:
            raise PendingEditNotFoundError(f"Pending edit with ID {edit_id} not found")
        if row.status != "pending":
            raise PendingEditAlreadyReviewedError(
                f"Pending edit {edit_id} is already {row.status}"
            )

        if row.paper_id is None and row.edit_type not in (
            "new_task",
            "new_method",
            "new_benchmark",
            "new_metric",
            "new_conference",
            "new_external_paper",
        ):
            raise PendingEditError("This edit is missing its paper_id")
        if row.paper_id is not None:
            current = self._build_snapshot(row.paper_id, row.edit_type)
            if current != (row.current_payload or {}):
                row.conflict_payload = {
                    "submitted_snapshot": row.current_payload or {},
                    "current_snapshot": current,
                }
                self.db.commit()
                raise PendingEditConflictError(
                    "Canonical state changed after submission"
                )
        applied_payload = self._validate_payload(
            row.edit_type,
            resolved_payload if resolved_payload is not None else row.proposed_payload,
        )
        event_before = self._approval_event_snapshot(row.edit_type, row.paper_id)
        try:
            result_type, result_id = self._apply_payload(
                row.edit_type, row.paper_id, applied_payload
            )
        except Exception as exc:
            self.db.rollback()
            failed_row = self.db.get(PendingPaperEdit, edit_id)
            if failed_row is not None and failed_row.status == "pending":
                failed_row.failure_reason = str(exc)[:2000]
                self.db.commit()
            logger.warning(
                "submission_apply_failed id=%s edit_type=%s error_type=%s",
                edit_id,
                row.edit_type,
                type(exc).__name__,
            )
            raise

        row.status = "approved"
        row.reviewed_by = reviewer_username
        row.reviewed_by_kind = "human"
        row.reviewed_by_hf_subject = reviewer_hf_subject
        row.applied_payload = applied_payload
        row.result_entity_type = result_type
        row.result_entity_id = result_id
        after_snapshot = self._approval_event_snapshot(
            row.edit_type, row.paper_id, result_type=result_type, result_id=result_id
        )
        if row.paper_id is not None:
            event_entity_type = (
                "evaluation"
                if row.edit_type == "evaluations"
                else f"paper_{row.edit_type}"
            )
            event_entity_id = (
                f"paper:{row.paper_id}"
                if row.edit_type == "evaluations"
                else str(row.paper_id)
            )
        else:
            event_entity_type = f"submission_created_{result_type}"
            event_entity_id = result_id
        event = CatalogMutationEvent(
            actor_hf_subject=reviewer_hf_subject or "legacy-human-reviewer",
            actor_username=reviewer_username,
            actor_role="admin",
            operation="approve_submission",
            entity_type=event_entity_type,
            entity_id=event_entity_id,
            before_snapshot=json_safe(event_before),
            after_snapshot=json_safe(after_snapshot),
            request_id=f"submission-review:{row.id}",
            source_environment=get_settings().environment,
            release_id=get_settings().release_id,
        )
        self.db.add(event)
        self.db.flush()
        row.catalog_event_id = event.id
        row.admin_note = admin_note
        row.user_review_reason = user_review_reason
        row.reviewed_at = datetime.now(timezone.utc)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        logger.info(
            "submission_approved id=%s reviewer_subject=%s result=%s:%s",
            row.id,
            reviewer_hf_subject,
            result_type,
            result_id,
        )
        return row

    def _approval_event_snapshot(
        self,
        edit_type: str,
        paper_id: Optional[int],
        *,
        result_type: Optional[str] = None,
        result_id: Optional[str] = None,
    ) -> Any:
        if paper_id is not None:
            if edit_type == "evaluations":
                return EvaluationCurationService(self.db)._paper_evaluations(paper_id)
            return PaperCurationService(self.db).snapshot(paper_id, edit_type)
        if result_type is None or result_id is None:
            return {}
        return self._created_entity_snapshot(result_type, int(result_id))

    def _created_entity_snapshot(
        self, entity_type: str, entity_id: int
    ) -> Dict[str, Any]:
        model_by_type = {
            "paper": DBPaper,
            "task": DBTask,
            "method": DBMethod,
            "dataset": DBDataset,
            "metric": DBMetric,
            "conference": DBConference,
        }
        model = model_by_type[entity_type]
        row = self.db.get(model, entity_id)
        if row is None:
            return {}
        values: Dict[str, Any] = {}
        for column in model.__table__.columns:
            value = getattr(row, column.name)
            if isinstance(value, bytes):
                value = {"base64": base64.b64encode(value).decode()}
            elif isinstance(value, (datetime, date)):
                value = value.isoformat()
            values[column.name] = value
        snapshot: Dict[str, Any] = {"entity": values}
        if entity_type == "paper":
            snapshot["associations"] = {
                "author_ids": sorted(
                    row[0]
                    for row in self.db.query(PaperAuthor.author_id)
                    .filter(PaperAuthor.paper_id == entity_id)
                    .all()
                ),
                "task_ids": sorted(
                    row[0]
                    for row in self.db.query(PaperTask.task_id)
                    .filter(PaperTask.paper_id == entity_id)
                    .all()
                ),
                "method_ids": sorted(
                    row[0]
                    for row in self.db.query(PaperMethod.method_id)
                    .filter(PaperMethod.paper_id == entity_id)
                    .all()
                ),
                "organization_ids": sorted(
                    row[0]
                    for row in self.db.query(PaperOrganization.organization_id)
                    .filter(PaperOrganization.paper_id == entity_id)
                    .all()
                ),
                "repository_ids": sorted(
                    row[0]
                    for row in self.db.query(PaperRepository.repository_id)
                    .filter(PaperRepository.paper_id == entity_id)
                    .all()
                ),
                "project_page_ids": sorted(
                    row[0]
                    for row in self.db.query(PaperProjectPage.project_page_id)
                    .filter(PaperProjectPage.paper_id == entity_id)
                    .all()
                ),
                "conference_ids": sorted(
                    row[0]
                    for row in self.db.query(PaperConference.conference_id)
                    .filter(PaperConference.paper_id == entity_id)
                    .all()
                ),
                "evaluation_ids": sorted(
                    row[0]
                    for row in self.db.query(DBEvaluation.id)
                    .filter(DBEvaluation.paper_id == entity_id)
                    .all()
                ),
            }
        if entity_type == "task":
            snapshot["associations"] = {
                "child_ids": sorted(
                    row[0]
                    for row in self.db.query(DBTask.id)
                    .filter(DBTask.parent_id == entity_id)
                    .all()
                ),
                "paper_ids": sorted(
                    row[0]
                    for row in self.db.query(PaperTask.paper_id)
                    .filter(PaperTask.task_id == entity_id)
                    .all()
                ),
                "dataset_ids": sorted(
                    row[0]
                    for row in self.db.query(TaskDataset.dataset_id)
                    .filter(TaskDataset.task_id == entity_id)
                    .all()
                ),
                "evaluation_ids": sorted(
                    row[0]
                    for row in self.db.query(DBEvaluation.id)
                    .filter(DBEvaluation.task_id == entity_id)
                    .all()
                ),
            }
        if entity_type == "method":
            snapshot["paper_ids"] = sorted(
                row[0]
                for row in self.db.query(PaperMethod.paper_id)
                .filter(PaperMethod.method_id == entity_id)
                .all()
            )
        if entity_type == "dataset":
            snapshot["task_ids"] = sorted(
                task_id
                for (task_id,) in self.db.query(TaskDataset.task_id)
                .filter(TaskDataset.dataset_id == entity_id)
                .all()
            )
            snapshot["evaluation_ids"] = sorted(
                row[0]
                for row in self.db.query(DBEvaluation.id)
                .filter(DBEvaluation.dataset_id == entity_id)
                .all()
            )
            snapshot["leaderboards"] = [
                {"task_id": row.task_id, "metric_id": row.metric_id}
                for row in self.db.query(TaskDatasetMetric)
                .filter(TaskDatasetMetric.dataset_id == entity_id)
                .all()
            ]
        if entity_type == "metric":
            snapshot["leaderboards"] = [
                {"task_id": row.task_id, "dataset_id": row.dataset_id}
                for row in self.db.query(TaskDatasetMetric)
                .filter(TaskDatasetMetric.metric_id == entity_id)
                .all()
            ]
        if entity_type == "conference":
            snapshot["paper_ids"] = sorted(
                row[0]
                for row in self.db.query(PaperConference.paper_id)
                .filter(PaperConference.conference_id == entity_id)
                .all()
            )
        return snapshot

    def reject(
        self,
        *,
        edit_id: int,
        reviewer_username: Optional[str],
        reviewer_hf_subject: Optional[str] = None,
        admin_note: Optional[str] = None,
        user_review_reason: Optional[str] = None,
    ) -> PendingPaperEdit:
        row = (
            self.db.query(PendingPaperEdit)
            .filter(PendingPaperEdit.id == edit_id)
            .with_for_update()
            .first()
        )
        if row is None:
            raise PendingEditNotFoundError(f"Pending edit with ID {edit_id} not found")
        if row.status != "pending":
            raise PendingEditAlreadyReviewedError(
                f"Pending edit {edit_id} is already {row.status}"
            )

        row.status = "rejected"
        row.reviewed_by = reviewer_username
        row.reviewed_by_kind = "human"
        row.reviewed_by_hf_subject = reviewer_hf_subject
        row.admin_note = admin_note
        row.user_review_reason = user_review_reason
        row.reviewed_at = datetime.now(timezone.utc)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        logger.info(
            "submission_rejected id=%s reviewer_subject=%s",
            row.id,
            reviewer_hf_subject,
        )
        return row

    # ----------------------------------------------------------------
    # Apply proposed payload through existing mutation services
    # ----------------------------------------------------------------

    def _apply_payload(
        self, edit_type: str, paper_id: Optional[int], payload: Dict[str, Any]
    ) -> tuple[str, str]:
        if edit_type == "new_external_paper":
            title = payload.get("title")
            published = payload.get("date_published")
            if not title or not published:
                raise PendingEditError(
                    "External-paper approval requires source_url, title, and date_published"
                )
            try:
                published_date = date.fromisoformat(str(published))
            except ValueError as exc:
                raise PendingEditError(
                    "External-paper publication date is invalid"
                ) from exc
            result = ExternalResourceService(self.db).add_external_resource(
                ExternalResourceInput(
                    source_url=payload["source_url"],
                    title=title,
                    abstract=payload.get("abstract"),
                    authors=list(payload.get("authors") or []),
                    date_published=published_date,
                ),
                commit=False,
            )
            return "paper", str(result.paper.id)
        if edit_type == "new_task":
            parent_id = payload.get("parent_id")
            area_id = payload.get("area_id")
            created = TaskService(self.db).create_task(
                TaskCreateRequest(
                    name=payload["name"],
                    description=payload.get("description"),
                    keywords=payload.get("keywords"),
                    parent_id=parent_id,
                    area_id=area_id,
                    image_credit=payload.get("image_credit"),
                ),
                commit=False,
            )
            entity = self.db.get(DBTask, int(created.id))
            assert entity is not None
            image_data, image_mime = self._decode_suggestion_image(payload.get("image"))
            entity.image_data = image_data
            entity.image_mime_type = image_mime
            self.db.flush()
            return "task", str(entity.id)
        if edit_type == "new_method":
            source_paper_id = payload.get("source_paper_id")
            if source_paper_id and self.db.get(DBPaper, source_paper_id) is None:
                raise PendingEditError(f"Source paper {source_paper_id} does not exist")
            image_data, image_mime = self._decode_suggestion_image(payload.get("image"))
            entity = MethodService(self.db).create_method(
                commit=False,
                name=payload["name"],
                description=payload.get("description"),
                source_paper_id=source_paper_id,
                source_url=payload.get("source_url"),
                source_title=payload.get("source_title"),
                image_data=image_data,
                image_mime_type=image_mime,
                image_credit=payload.get("image_credit"),
            )
            return "method", str(entity.id)
        if edit_type == "new_benchmark":
            task_ids = payload["task_ids"]
            created = DatasetService(self.db).create_dataset(
                DatasetCreateRequest(
                    name=payload["name"],
                    full_name=payload.get("full_name"),
                    description=payload["description"],
                    url=payload.get("url"),
                    hf_url=payload.get("hf_url"),
                    paper_url=payload.get("paper_url"),
                    license_name=payload.get("license_name"),
                    license_url=payload.get("license_url"),
                    task_ids=task_ids,
                ),
                commit=False,
            )
            entity = self.db.get(DBDataset, int(created.id))
            assert entity is not None
            for task_id in task_ids:
                self.db.add(TaskDataset(task_id=task_id, dataset_id=entity.id))
            self.db.flush()
            return "dataset", str(entity.id)
        if edit_type == "new_metric":
            entity = MetricService(self.db).create_metric(
                commit=False,
                name=payload["name"],
                full_name=payload.get("full_name"),
                direction=payload["direction"],
                scale=payload.get("scale"),
                description=payload["description"],
            )
            task_id = payload.get("task_id")
            dataset_id = payload.get("dataset_id")
            if task_id is not None:
                membership = self.db.get(TaskDataset, (task_id, dataset_id))
                if membership is None:
                    raise PendingEditError(
                        "The requested task/benchmark association does not exist"
                    )
                self.db.add(
                    TaskDatasetMetric(
                        task_id=task_id,
                        dataset_id=dataset_id,
                        metric_id=entity.id,
                    )
                )
                self.db.flush()
            return "metric", str(entity.id)
        if edit_type == "new_conference":
            entity = ConferenceService(self.db).create_conference(
                commit=False,
                name=payload["name"],
                short_name=payload.get("short_name"),
                year=payload["year"],
                url=payload.get("url"),
                start_date=date.fromisoformat(payload["start_date"])
                if payload.get("start_date")
                else None,
                end_date=date.fromisoformat(payload["end_date"])
                if payload.get("end_date")
                else None,
                venue=payload.get("venue"),
                location=payload.get("location"),
                description=payload.get("description"),
            )
            return "conference", str(entity.id)
        if paper_id is None:
            raise PendingEditError("This edit is missing its paper_id")
        if edit_type == "tasks":
            PaperService(self.db).update_paper_tasks(
                paper_id, list(payload.get("task_ids", [])), commit=False
            )
            return "paper", str(paper_id)
        if edit_type == "methods":
            PaperService(self.db).update_paper_methods(
                paper_id, list(payload.get("method_ids", [])), commit=False
            )
            return "paper", str(paper_id)
        if edit_type == "repositories":
            PaperService(self.db).update_paper_repositories(
                paper_id, list(payload.get("repositories", [])), commit=False
            )
            return "paper", str(paper_id)
        if edit_type == "project_pages":
            PaperService(self.db).update_paper_project_pages(
                paper_id, list(payload.get("project_pages", [])), commit=False
            )
            return "paper", str(paper_id)
        if edit_type == "organizations":
            PaperService(self.db).update_paper_organizations(
                paper_id, list(payload.get("organization_ids", [])), commit=False
            )
            return "paper", str(paper_id)
        if edit_type == "source_url":
            PaperService(self.db).update_paper_source_url(
                paper_id, str(payload.get("source_url", "")), commit=False
            )
            return "paper", str(paper_id)
        if edit_type == "hf_artifacts":
            PaperService(self.db).update_paper_hf_artifacts(
                paper_id,
                list(payload.get("hf_models", [])),
                list(payload.get("hf_datasets", [])),
                list(payload.get("hf_spaces", [])),
                commit=False,
            )
            return "paper", str(paper_id)
        if edit_type == "evaluations":
            self._apply_evaluations(paper_id, payload)
            return "paper", str(paper_id)
        raise PendingEditError(f"Unsupported edit_type: {edit_type}")

    @staticmethod
    def _decode_suggestion_image(image: Any) -> tuple[Optional[bytes], Optional[str]]:
        if not image:
            return None, None
        prefix = f"data:{image['mime_type']};base64,"
        return base64.b64decode(image["data_url"][len(prefix) :]), image["mime_type"]

    def _apply_evaluations(self, paper_id: int, payload: Dict[str, Any]) -> None:
        operations: List[Dict[str, Any]] = payload.get("operations", [])
        service = EvaluationService(self.db)

        for op in operations:
            kind = op.get("op")
            if kind == "delete":
                evaluation_id = int(op["evaluation_id"])
                self._ensure_evaluation_paper_match(evaluation_id, paper_id)
                service.delete_evaluation(evaluation_id, commit=False)
                continue

            if kind == "update":
                evaluation_id = int(op["evaluation_id"])
                self._ensure_evaluation_paper_match(evaluation_id, paper_id)
                data = dict(op["data"])
                # Honor "field was explicitly set in the source dialog" semantics
                # the same way the EvaluationUpdateRequest handler does, so
                # clearing harness/num_parameters still works after approval.
                harness_set = "harness" in data
                source_url_set = "source_url" in data
                num_parameters_set = "num_parameters" in data
                hf_model_url_set = "hf_model_url" in data
                service.update_evaluation(
                    evaluation_id=evaluation_id,
                    task_id=data.get("task_id"),
                    dataset_id=data.get("dataset_id"),
                    model_name=data.get("model_name"),
                    harness=data.get("harness"),
                    methodology=data.get("methodology"),
                    metrics=data.get("metrics"),
                    uses_additional_data=data.get("uses_additional_data"),
                    is_open=data.get("is_open"),
                    best_rank=data.get("best_rank"),
                    best_metric=data.get("best_metric"),
                    evaluated_on=data.get("evaluated_on"),
                    external_source_url=data.get("external_source_url"),
                    source_url=data.get("source_url"),
                    num_parameters=data.get("num_parameters"),
                    hf_model_url=data.get("hf_model_url"),
                    harness_set=harness_set,
                    source_url_set=source_url_set,
                    num_parameters_set=num_parameters_set,
                    hf_model_url_set=hf_model_url_set,
                    commit=False,
                )
                continue

            if kind == "create":
                data = dict(op["data"])
                if not PendingEditService._is_valid_evaluation_create_data(data):
                    continue
                # Force the create to target the paper this edit was submitted
                # against; submitters cannot reroute the row to another paper
                # at approval time.
                data["paper_id"] = paper_id
                service.create_evaluation(
                    paper_id=paper_id,
                    task_id=data["task_id"],
                    dataset_id=data["dataset_id"],
                    metrics=data.get("metrics") or {},
                    model_name=data.get("model_name"),
                    harness=data.get("harness"),
                    methodology=data.get("methodology"),
                    uses_additional_data=bool(data.get("uses_additional_data", False)),
                    is_open=bool(data.get("is_open", True)),
                    best_rank=data.get("best_rank"),
                    best_metric=data.get("best_metric"),
                    evaluated_on=data.get("evaluated_on"),
                    external_source_url=data.get("external_source_url"),
                    source_url=data.get("source_url"),
                    num_parameters=data.get("num_parameters"),
                    hf_model_url=data.get("hf_model_url"),
                    commit=False,
                )
                continue

            raise PendingEditError(f"Unsupported evaluation op: {kind}")

    def _ensure_evaluation_paper_match(
        self, evaluation_id: int, expected_paper_id: int
    ) -> None:
        row = (
            self.db.query(DBEvaluation.paper_id)
            .filter(DBEvaluation.id == evaluation_id)
            .first()
        )
        if row is None:
            raise DatabaseError(f"Evaluation {evaluation_id} not found")
        if int(row[0]) != int(expected_paper_id):
            raise PendingEditError(
                f"Evaluation {evaluation_id} does not belong to paper {expected_paper_id}"
            )
