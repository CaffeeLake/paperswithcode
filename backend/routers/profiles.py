from __future__ import annotations


from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.database.connection import get_database_session
from backend.models.database import PendingPaperEdit
from backend.routers.auth import decode_request_session
from backend.services.user_profile_service import UserProfileError, UserProfileService
from backend.services.catalog_mutation_service import CatalogMutationService
from backend.utils.auth import require_hf_admin

router = APIRouter()


class SuspendRequest(BaseModel):
    suspended: bool = True
    reason: str = Field(min_length=1, max_length=2000)


class SpamRejectRequest(BaseModel):
    confirm: str


@router.get("/profiles/{username}")
def get_profile(
    username: str,
    request: Request,
    db: Session = Depends(get_database_session),
):
    try:
        profile, redirected = UserProfileService(db).resolve(username)
    except UserProfileError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    if redirected:
        return RedirectResponse(
            url=f"/api/v1/profiles/{profile.current_username}", status_code=308
        )
    session = decode_request_session(request) or {}
    is_owner = session.get("sub") == profile.hf_subject
    private_submissions = []
    if is_owner:
        rows = (
            db.query(PendingPaperEdit)
            .filter(PendingPaperEdit.hf_subject == profile.hf_subject)
            .order_by(PendingPaperEdit.created_at.desc())
            .limit(200)
            .all()
        )
        private_submissions = [
            {
                "id": row.id,
                "edit_type": row.edit_type,
                "status": row.status,
                "proposed_payload": row.proposed_payload,
                "applied_payload": row.applied_payload,
                "result_entity_type": row.result_entity_type,
                "result_entity_id": row.result_entity_id,
                "review_reason": row.user_review_reason,
                "created_at": row.created_at,
                "reviewed_at": row.reviewed_at,
            }
            for row in rows
        ]
    service = UserProfileService(db)
    return {
        "username": profile.current_username,
        "redirected_from_alias": redirected,
        "calendar": service.contribution_calendar(profile.hf_subject),
        "is_owner": is_owner,
        "submissions": private_submissions,
    }


@router.get("/rate-limits")
def get_submission_rate_limits():
    settings = get_settings()
    return {
        "active_pending": settings.submission_max_active_pending,
        "subject_per_hour": settings.submission_hourly_subject_limit,
        "ip_per_hour": settings.submission_hourly_ip_limit,
        "policy_url": "/rate-limits",
    }


@router.post("/admin/submitters/{hf_subject}/suspension")
def set_submission_suspension(
    hf_subject: str,
    body: SuspendRequest,
    request: Request,
    actor: dict = Depends(require_hf_admin),
    db: Session = Depends(get_database_session),
):
    service = UserProfileService(db)
    try:
        after, _, _ = CatalogMutationService(db).mutate(
            actor=actor,
            operation="moderate",
            entity_type="submitter_moderation",
            entity_id=hf_subject,
            request_payload=body.model_dump(),
            idempotency_key=None,
            expected_version=None,
            snapshot=lambda: service.moderation_snapshot(hf_subject, lock=True),
            apply=lambda: service.suspend(
                hf_subject=hf_subject,
                suspended=body.suspended,
                reason=body.reason,
                actor=actor,
            ),
            request_id=request.headers.get("X-Request-ID") or str(id(request)),
        )
    except UserProfileError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"hf_subject": hf_subject, "suspended": after["is_submission_suspended"]}


@router.post("/admin/submitters/{hf_subject}/reject-spam")
def reject_submitter_spam(
    hf_subject: str,
    body: SpamRejectRequest,
    request: Request,
    actor: dict = Depends(require_hf_admin),
    db: Session = Depends(get_database_session),
):
    if body.confirm != "REJECT_ACTIVE_SUBMISSIONS_AS_SPAM":
        raise HTTPException(status_code=400, detail="Confirmation value is required")
    service = UserProfileService(db)
    before = service.moderation_snapshot(hf_subject)
    CatalogMutationService(db).mutate(
        actor=actor,
        operation="moderate",
        entity_type="submitter_moderation",
        entity_id=hf_subject,
        request_payload={"reject_active_as_spam": True},
        idempotency_key=None,
        expected_version=None,
        snapshot=lambda: service.moderation_snapshot(hf_subject, lock=True),
        apply=lambda: service.reject_active_as_spam(hf_subject=hf_subject, actor=actor),
        request_id=request.headers.get("X-Request-ID") or str(id(request)),
    )
    count = sum(1 for row in before["submissions"] if row["status"] == "pending")
    return {"rejected": count}
