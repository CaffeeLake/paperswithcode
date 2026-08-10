"""Public staging entrypoint for verified contributor access requests."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.database.connection import get_database_session
from backend.models.api import StagingAccessRequestResponse
from backend.routers.auth import decode_request_session
from backend.services.staging_access_service import submit_staging_access_request
from backend.utils.auth import can_access_staging

router = APIRouter()


@router.post(
    "/staging-access-request",
    response_model=StagingAccessRequestResponse,
    status_code=status.HTTP_200_OK,
)
def request_staging_access(
    request: Request,
    db: Session = Depends(get_database_session),
) -> StagingAccessRequestResponse:
    """Record a request for the signed-in Hugging Face identity."""

    if get_settings().environment != "staging":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    payload = decode_request_session(request)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in with Hugging Face before requesting access",
        )
    if can_access_staging(payload.get("sub"), username=payload.get("username")):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This account already has staging access",
        )

    hf_subject = payload.get("sub")
    hf_username = payload.get("username")
    if not isinstance(hf_subject, str) or not isinstance(hf_username, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The Hugging Face session is missing account identity",
        )

    row = submit_staging_access_request(
        db,
        hf_subject=hf_subject,
        hf_username=hf_username,
    )
    return StagingAccessRequestResponse.model_validate(row)
