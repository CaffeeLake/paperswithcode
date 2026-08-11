"""Durable staging contributor access requests."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from backend.models.database import StagingAccessRequest


def submit_staging_access_request(
    db: Session,
    *,
    hf_subject: str,
    hf_username: str,
    email: str,
    already_authorized: bool = False,
) -> StagingAccessRequest:
    """Create or refresh one pending request for a verified HF identity."""

    access_request = db.get(StagingAccessRequest, hf_subject)
    if access_request is None:
        access_request = StagingAccessRequest(
            hf_subject=hf_subject,
            hf_username=hf_username,
            email=email,
            email_verified=True,
            status="approved" if already_authorized else "pending",
        )
        db.add(access_request)
    else:
        access_request.hf_username = hf_username
        access_request.email = email
        access_request.email_verified = True
        access_request.status = "approved" if already_authorized else "pending"
        access_request.updated_at = datetime.now(UTC)

    db.commit()
    db.refresh(access_request)
    return access_request
