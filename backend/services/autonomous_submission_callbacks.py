"""Construction and HTTP-facing validation for scoped review callbacks."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from backend.config import Settings
from backend.services.autonomous_submission_service import (
    AutonomousSubmissionDecision,
    AutonomousSubmissionService,
)


def submission_callback_service(
    db: Session, settings: Settings
) -> AutonomousSubmissionService:
    return AutonomousSubmissionService(
        db,
        signing_secret=settings.autonomous_submission_callback_secret.encode(),
        callback_base_url=settings.autonomous_submission_callback_base_url,
    )


def apply_submission_callback(
    db: Session,
    settings: Settings,
    *,
    claim_id: uuid.UUID,
    bearer_token: str,
    decision: AutonomousSubmissionDecision,
) -> None:
    if decision.claim_id != claim_id:
        raise ValueError("Callback path does not match decision scope")
    submission_callback_service(db, settings).apply_submission_decision(
        bearer_token, decision
    )
