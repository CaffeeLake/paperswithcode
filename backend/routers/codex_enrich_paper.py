"""Admin endpoints for Codex paper-enrichment jobs."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from backend.config import Settings, get_settings
from backend.database.connection import get_database_session
from backend.services.codex_add_evals_service import (
    CodexPaperJob,
    codex_paper_job_service,
)
from backend.services.codex_paper_job_admin_service import (
    CodexPaperJobAdminService,
    CodexPaperJobNotFoundError,
    CodexPaperJobsDisabledError,
    CodexPaperNotFoundError,
)
from backend.utils.auth import require_hf_admin

router = APIRouter(prefix="/admin/codex-enrich-paper", tags=["admin"])


class StartCodexEnrichPaperRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paper_id: int


def _service(db: Session) -> CodexPaperJobAdminService:
    return CodexPaperJobAdminService(db, job_service=codex_paper_job_service)


def _not_found(error: LookupError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))


@router.post("/jobs", response_model=CodexPaperJob, status_code=202)
async def start_job(
    body: StartCodexEnrichPaperRequest,
    admin: dict = Depends(require_hf_admin),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    try:
        return await run_in_threadpool(
            _service(db).start,
            kind="enrich-paper",
            paper_id=body.paper_id,
            requested_by=admin["username"],
            settings=settings,
        )
    except (CodexPaperJobsDisabledError, CodexPaperNotFoundError) as error:
        raise _not_found(error) from error


@router.get("/jobs/{job_id}", response_model=CodexPaperJob)
async def get_job(
    job_id: uuid.UUID,
    _admin: dict = Depends(require_hf_admin),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    try:
        return await run_in_threadpool(_service(db).get, job_id, settings)
    except (CodexPaperJobsDisabledError, CodexPaperJobNotFoundError) as error:
        raise _not_found(error) from error


@router.delete("/jobs/{job_id}", response_model=CodexPaperJob)
async def cancel_job(
    job_id: uuid.UUID,
    _admin: dict = Depends(require_hf_admin),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    try:
        return await run_in_threadpool(_service(db).cancel, job_id, settings)
    except (CodexPaperJobsDisabledError, CodexPaperJobNotFoundError) as error:
        raise _not_found(error) from error
