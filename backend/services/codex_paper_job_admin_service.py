"""Shared admin workflow for starting and managing paper-curation jobs."""

from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import Paper, PaperCurationJob
from backend.services.codex_add_evals_service import (
    CodexPaperJob,
    CodexPaperJobService,
    codex_paper_job_service,
)
from backend.utils.urls import get_paper_route_identifier

CodexPaperJobKind = Literal["add-evals", "enrich-paper"]


class CodexPaperJobsDisabledError(LookupError):
    """Paper-curation job routes are disabled."""


class CodexPaperNotFoundError(LookupError):
    """The requested paper does not exist."""


class CodexPaperJobNotFoundError(LookupError):
    """The requested paper-curation job does not exist."""


class CodexPaperJobAdminService:
    """Own shared paper lookup and durable job lifecycle dispatch."""

    def __init__(
        self,
        db: Session,
        *,
        job_service: CodexPaperJobService = codex_paper_job_service,
    ):
        self.db = db
        self.job_service = job_service

    @staticmethod
    def _require_enabled(settings: Settings) -> None:
        if not settings.codex_jobs_enabled:
            raise CodexPaperJobsDisabledError("Not found")

    def start(
        self,
        *,
        kind: CodexPaperJobKind,
        paper_id: int,
        requested_by: str,
        settings: Settings,
    ) -> CodexPaperJob:
        self._require_enabled(settings)
        paper = self.db.query(Paper).filter(Paper.id == paper_id).one_or_none()
        if paper is None:
            raise CodexPaperNotFoundError("Paper not found")
        route = get_paper_route_identifier(paper.source, paper.arxiv_id, paper.id)
        return self.job_service.enqueue(
            self.db,
            kind=kind,
            paper_id=paper.id,
            paper_route=route,
            paper_title=paper.title,
            requested_by=requested_by,
            settings=settings,
        )

    def get(self, job_id: uuid.UUID, settings: Settings) -> CodexPaperJob:
        self._require_enabled(settings)
        job = self.job_service.get(self.db, job_id, settings)
        if job is None:
            raise CodexPaperJobNotFoundError("Job not found")
        return job

    def cancel(self, job_id: uuid.UUID, settings: Settings) -> CodexPaperJob:
        self._require_enabled(settings)
        row = self.db.get(PaperCurationJob, job_id)
        if row is None:
            raise CodexPaperJobNotFoundError("Job not found")
        return self.job_service.cancel(self.db, row, settings)
