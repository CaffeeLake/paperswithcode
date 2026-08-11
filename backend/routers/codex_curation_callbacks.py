"""Scoped callback API used by remote Hugging Face Codex Jobs."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from backend.config import Settings, get_settings
from backend.database.connection import get_database_session
from backend.models.api import (
    ApplyMutationRequest,
    CompleteJobRequest,
    CurationLink as CurationLink,
    EnrichPaperMutation as EnrichPaperMutation,
    EvaluationCreateRequest as EvaluationCreateRequest,
)
from backend.services.codex_add_evals_service import (
    CodexPaperJob,
    CodexPaperJobsResponse,
    codex_paper_job_service,
)
from backend.services.codex_curation_callback_service import (
    CodexCurationCallbackService,
    CodexCurationEnrichmentNotAllowedError,
    CodexCurationEnrichmentRequiredError,
    CodexCurationEvaluationPaperMismatchError,
    CodexCurationEvaluationsNotAllowedError,
    CodexCurationMutationClosedError,
    CodexCurationPaperNotFoundError,
)
from backend.services.curation_thumbnail_queue_service import serialize_thumbnail
from backend.services.evaluation_service import EvaluationService
from backend.services.paper_service import PaperService
from backend.utils.auth import require_hf_admin

router = APIRouter(prefix="/admin/codex-curation/jobs", tags=["admin"])


def _require_enabled(settings: Settings) -> None:
    if not settings.codex_jobs_enabled:
        raise HTTPException(status_code=404, detail="Not found")


def _callback_job(
    job_id: uuid.UUID,
    authorization: str | None,
    db: Session,
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing job bearer token")
    row = codex_paper_job_service.authenticate(db, job_id, authorization[7:])
    if row is None:
        raise HTTPException(status_code=401, detail="Invalid job bearer token")
    return row


def _service(db: Session) -> CodexCurationCallbackService:
    """Construct through router imports so existing test patch seams remain valid."""
    return CodexCurationCallbackService(
        db,
        job_service=codex_paper_job_service,
        evaluation_service=EvaluationService(db),
        paper_service=PaperService(db),
    )


def _leaderboard_inventory(db: Session, query: str) -> list[dict]:
    """Compatibility seam for tests patching the legacy router helper."""
    return _service(db).leaderboard_inventory(query)


@router.get("", response_model=CodexPaperJobsResponse)
def list_jobs(
    limit: int = Query(default=100, ge=1, le=500),
    _admin: dict = Depends(require_hf_admin),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    """List the durable paper-curation queue and recent execution history."""
    _require_enabled(settings)
    return codex_paper_job_service.list_jobs(db, settings, limit=limit)


@router.get("/{job_id}/context")
def get_context(
    job_id: uuid.UUID,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    _require_enabled(settings)
    row = _callback_job(job_id, authorization, db)
    try:
        return _service(db).context(row, settings)
    except CodexCurationPaperNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/{job_id}/taxonomy")
def search_taxonomy(
    job_id: uuid.UUID,
    q: str = Query(min_length=1, max_length=120),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    _require_enabled(settings)
    _callback_job(job_id, authorization, db)
    return _service(db).search_taxonomy(q)


@router.get("/{job_id}/leaderboards")
def search_leaderboards(
    job_id: uuid.UUID,
    q: str = Query(min_length=1, max_length=120),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    """Search only existing, fully configured leaderboards for a scoped worker."""
    _require_enabled(settings)
    _callback_job(job_id, authorization, db)
    return {"query": q, "leaderboards": _leaderboard_inventory(db, q)}


@router.post("/{job_id}/apply")
def apply_mutation(
    job_id: uuid.UUID,
    body: ApplyMutationRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    _require_enabled(settings)
    row = _callback_job(job_id, authorization, db)
    try:
        return _service(db).apply(row, body)
    except CodexCurationMutationClosedError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except CodexCurationEnrichmentNotAllowedError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except CodexCurationEvaluationPaperMismatchError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except CodexCurationEvaluationsNotAllowedError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except CodexCurationEnrichmentRequiredError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/{job_id}/thumbnail")
def get_thumbnail_status(
    job_id: uuid.UUID,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    _require_enabled(settings)
    row = _callback_job(job_id, authorization, db)
    return {"thumbnail": serialize_thumbnail(row)}


@router.post("/{job_id}/complete", response_model=CodexPaperJob)
def complete_job(
    job_id: uuid.UUID,
    body: CompleteJobRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    _require_enabled(settings)
    row = _callback_job(job_id, authorization, db)
    return codex_paper_job_service.complete(
        db, row, report=body.report, error=body.error, settings=settings
    )
