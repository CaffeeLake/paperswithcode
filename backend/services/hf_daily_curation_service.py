"""Idempotent rolling-cohort reconciliation for autonomous paper curation."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import (
    Paper,
    PaperCurationJob,
    PaperCurationSchedulerState,
    PaperCurationWorkflow,
)
from backend.services.codex_add_evals_service import (
    CodexPaperJobService,
    codex_paper_job_service,
    deferred_workflows_for_release,
)
from backend.utils.hf_daily_papers import fetch_hf_daily_papers
from backend.utils.urls import get_paper_route_identifier

FetchCohort = Callable[[date], list[str]]
logger = logging.getLogger(__name__)


def fetch_hf_daily_cohort(cohort_date: date) -> list[str]:
    """Fetch a complete HF daily list, preserving upstream order."""
    payloads = asyncio.run(fetch_hf_daily_papers(cohort_date.isoformat()))
    return [
        arxiv_id
        for item in payloads
        if (arxiv_id := (item.get("paper") or {}).get("id"))
    ]


class HFDailyCurationService:
    def __init__(
        self,
        db: Session,
        settings: Settings,
        *,
        fetch_cohort: FetchCohort = fetch_hf_daily_cohort,
        job_service: CodexPaperJobService = codex_paper_job_service,
    ) -> None:
        self.db = db
        self.settings = settings
        self.fetch_cohort = fetch_cohort
        self.job_service = job_service

    def _state(self) -> PaperCurationSchedulerState:
        state = self.db.get(PaperCurationSchedulerState, 1)
        if state is None:
            state = PaperCurationSchedulerState(id=1)
            self.db.add(state)
            self.db.flush()
        return state

    def set_dispatch(self, enabled: bool, *, reason: str | None = None) -> dict:
        state = self._state()
        state.dispatch_enabled = enabled
        if enabled:
            state.paused_at = None
            state.pause_reason = None
            state.pause_condition = None
            state.acknowledged_at = datetime.now(UTC)
            state.first_enabled_at = state.first_enabled_at or datetime.now(UTC)
            logger.warning("paper curation dispatch resumed")
        else:
            state.paused_at = datetime.now(UTC)
            state.pause_reason = reason or "disabled by operator"
            state.pause_condition = "operator"
            logger.error("paper curation dispatch paused condition=operator")
        self.db.commit()
        if enabled:
            self.job_service.dispatch_next(self.db, self.settings)
        return self.status()

    def status(self) -> dict:
        state = self._state()
        oldest = (
            self.db.query(func.min(PaperCurationJob.created_at))
            .filter(
                PaperCurationJob.trigger != "admin", PaperCurationJob.status == "queued"
            )
            .scalar()
        )
        return {
            "dispatch_enabled": state.dispatch_enabled,
            "paused_at": state.paused_at,
            "pause_reason": state.pause_reason,
            "pause_condition": state.pause_condition,
            "canary_released": state.canary_released,
            "oldest_scheduled_queued_at": oldest,
        }

    def reconcile(
        self,
        *,
        today: date | None = None,
        lookback_days: int = 7,
        paper_limit: int | None = None,
        dry_run: bool = False,
    ) -> dict:
        today = today or datetime.now(UTC).date()
        discovered: list[tuple[date, int, str]] = []
        seen: set[str] = set()
        for offset in range(lookback_days):
            cohort_date = today - timedelta(days=offset)
            for order, arxiv_id in enumerate(self.fetch_cohort(cohort_date)):
                if arxiv_id not in seen:
                    seen.add(arxiv_id)
                    discovered.append((cohort_date, order, arxiv_id))

        state = self._state()
        existing_canary = (
            self.db.query(PaperCurationWorkflow)
            .filter(
                PaperCurationWorkflow.policy_version
                == self.settings.codex_curation_policy_version
            )
            .all()
        )
        if existing_canary and not state.canary_released:
            terminal = [
                item
                for item in existing_canary
                if item.status in {"completed", "satisfied", "failed", "partial"}
            ]
            if len(terminal) == len(existing_canary) and all(
                item.status in {"completed", "satisfied"} for item in terminal
            ):
                state.canary_released = True

        queue_count = (
            self.db.query(PaperCurationWorkflow)
            .filter(PaperCurationWorkflow.status.in_({"queued", "running"}))
            .count()
        )
        capacity = max(0, self.settings.codex_curation_queue_depth - queue_count)
        if state.canary_released:
            canary_capacity = capacity
        elif existing_canary:
            # Never grow the first canary cohort on a later reconciliation.
            canary_capacity = 0
        else:
            canary_capacity = self.settings.codex_curation_canary_limit
        create_capacity = min(
            capacity,
            canary_capacity,
            paper_limit or self.settings.codex_curation_reconcile_limit,
        )
        summary = {
            "discovered": len(discovered),
            "created": 0,
            "released_deferred": 0,
            "deferred": 0,
            "missing_imports": [],
            "already_satisfied": 0,
        }

        deferred = deferred_workflows_for_release(self.db, create_capacity)
        for workflow in deferred:
            paper = self.db.get(Paper, workflow.paper_id)
            if paper is None:
                workflow.status = "failed"
                workflow.error = (
                    "Paper was deleted before deferred curation could start"
                )
                continue
            route = get_paper_route_identifier(paper.source, paper.arxiv_id, paper.id)
            kind = (
                "add-evals" if workflow.enrich_satisfied_by_job_id else "enrich-paper"
            )
            self.job_service.enqueue(
                self.db,
                kind=kind,
                paper_id=paper.id,
                paper_route=route,
                paper_title=paper.title,
                requested_by="hf-daily-cron",
                settings=self.settings,
                trigger="hf-daily-cron",
                parent_workflow_id=workflow.id,
                cohort_date=workflow.cohort_date,
                policy_version=workflow.policy_version,
                priority=100,
                dispatch=False,
                commit=False,
            )
            workflow.status = "queued"
            workflow.deferred_reason = None
            create_capacity -= 1
            summary["released_deferred"] += 1

        for cohort_date, order, arxiv_id in discovered:
            paper = (
                self.db.query(Paper)
                .filter(Paper.arxiv_id == arxiv_id, Paper.is_latest_version)
                .one_or_none()
            )
            if paper is None:
                summary["missing_imports"].append(
                    {"arxiv_id": arxiv_id, "cohort_date": cohort_date.isoformat()}
                )
                continue
            existing = (
                self.db.query(PaperCurationWorkflow)
                .filter(PaperCurationWorkflow.paper_id == paper.id)
                .first()
            )
            if existing:
                continue
            admin_success = {
                kind: self.db.query(PaperCurationJob)
                .filter(
                    PaperCurationJob.paper_id == paper.id,
                    PaperCurationJob.kind == kind,
                    PaperCurationJob.trigger == "admin",
                    PaperCurationJob.status == "completed",
                )
                .order_by(PaperCurationJob.finished_at.desc())
                .first()
                for kind in ("enrich-paper", "add-evals")
            }
            status = "queued" if create_capacity > 0 else "deferred"
            workflow = PaperCurationWorkflow(
                id=uuid.uuid4(),
                paper_id=paper.id,
                cohort_date=cohort_date,
                cohort_order=order,
                policy_version=self.settings.codex_curation_policy_version,
                status=status,
                enrich_satisfied_by_job_id=admin_success["enrich-paper"].id
                if admin_success["enrich-paper"]
                else None,
                evals_satisfied_by_job_id=admin_success["add-evals"].id
                if admin_success["add-evals"]
                else None,
                deferred_reason=None if status == "queued" else "queue_or_canary_cap",
            )
            if all(admin_success.values()):
                workflow.status = "satisfied"
                workflow.finished_at = datetime.now(UTC)
                summary["already_satisfied"] += 1
            elif status == "deferred":
                summary["deferred"] += 1
            else:
                create_capacity -= 1
                summary["created"] += 1
            self.db.add(workflow)
            self.db.flush()
            if workflow.status == "queued":
                kind = "add-evals" if admin_success["enrich-paper"] else "enrich-paper"
                route = get_paper_route_identifier(
                    paper.source, paper.arxiv_id, paper.id
                )
                self.job_service.enqueue(
                    self.db,
                    kind=kind,
                    paper_id=paper.id,
                    paper_route=route,
                    paper_title=paper.title,
                    requested_by="hf-daily-cron",
                    settings=self.settings,
                    trigger="hf-daily-cron",
                    parent_workflow_id=workflow.id,
                    cohort_date=cohort_date,
                    policy_version=workflow.policy_version,
                    priority=100,
                    dispatch=False,
                    commit=False,
                )
        if dry_run:
            self.db.rollback()
            summary["dry_run"] = True
            return summary
        if (
            self.settings.codex_curation_scheduler_enabled
            and self.settings.codex_curation_direct_apply_enabled
            and state.first_enabled_at is None
        ):
            state.dispatch_enabled = True
            state.first_enabled_at = datetime.now(UTC)
        self.db.commit()
        self.job_service.dispatch_next(self.db, self.settings)
        summary["scheduler"] = self.status()
        return summary
