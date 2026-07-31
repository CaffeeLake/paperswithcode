"""Manage user-funded Hugging Face Inference Providers access."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from backend.config import Settings, get_settings
from backend.services.hf_inference_billing_service import (
    COOKIE_NAME,
    HF_INFERENCE_SETTINGS_URL,
    HF_TOKEN_SETTINGS_URL,
    HfInferenceCredentialError,
    decrypt_token,
    encrypt_token,
    verify_token,
)
from backend.utils.auth import require_user

router = APIRouter(prefix="/me/inference-billing", tags=["inference-billing"])
COOKIE_MAX_AGE_SECONDS = 30 * 24 * 60 * 60


class ConnectInferenceBilling(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=1, max_length=512)


class InferenceBillingStatus(BaseModel):
    connected: bool
    account_type: str | None = None
    monthly_credits_usd: float | None = None
    pay_as_you_go: bool = True
    requests_per_minute: int
    requests_per_day: int
    usage_url: str = HF_INFERENCE_SETTINGS_URL
    token_url: str = HF_TOKEN_SETTINGS_URL


def inference_token_for_request(
    request: Request,
    user: dict,
    settings: Settings,
) -> str | None:
    encrypted = request.cookies.get(COOKIE_NAME)
    if not encrypted:
        return None
    return decrypt_token(encrypted, user["hf_user_id"], settings)


def _status(
    settings: Settings,
    *,
    connected: bool,
    is_pro: bool | None = None,
) -> InferenceBillingStatus:
    return InferenceBillingStatus(
        connected=connected,
        account_type=("PRO" if is_pro else "Free") if connected else None,
        monthly_credits_usd=(2.0 if is_pro else 0.1) if connected else None,
        requests_per_minute=settings.chat_requests_per_minute,
        requests_per_day=settings.chat_requests_per_day,
    )


@router.get("", response_model=InferenceBillingStatus)
async def get_inference_billing(
    request: Request,
    user: dict = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> InferenceBillingStatus:
    token = inference_token_for_request(request, user, settings)
    if not token:
        return _status(settings, connected=False)
    try:
        account = await verify_token(token, user["hf_user_id"])
    except HfInferenceCredentialError:
        return _status(settings, connected=False)
    return _status(settings, connected=True, is_pro=account.is_pro)


@router.put("", response_model=InferenceBillingStatus)
async def connect_inference_billing(
    body: ConnectInferenceBilling,
    response: Response,
    user: dict = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> InferenceBillingStatus:
    token = body.token.strip()
    try:
        account = await verify_token(token, user["hf_user_id"])
    except HfInferenceCredentialError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    response.set_cookie(
        COOKIE_NAME,
        encrypt_token(token, user["hf_user_id"], settings),
        max_age=COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        secure=settings.is_deployed,
        samesite="lax",
        path="/",
    )
    return _status(settings, connected=True, is_pro=account.is_pro)


@router.delete("", status_code=204)
def disconnect_inference_billing(
    response: Response,
    _user: dict = Depends(require_user),
) -> Response:
    response.delete_cookie(COOKIE_NAME, path="/", samesite="lax")
    return response
