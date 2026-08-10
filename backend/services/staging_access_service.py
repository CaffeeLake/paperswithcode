"""Durable staging contributor access requests."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from backend.models.database import StagingAccessRequest


def submit_staging_access_request(
    db: Session, *, hf_subject: str, hf_username: str
) -> StagingAccessRequest:
    """Create or refresh one pending request for a verified HF identity."""

    access_request = db.get(StagingAccessRequest, hf_subject)
    if access_request is None:
        access_request = StagingAccessRequest(
            hf_subject=hf_subject,
            hf_username=hf_username,
            status="pending",
        )
        db.add(access_request)
    else:
        access_request.hf_username = hf_username
        access_request.status = "pending"
        access_request.updated_at = datetime.now(UTC)

    db.commit()
    db.refresh(access_request)
    return access_request
