"""Manage user-funded Hugging Face Inference Providers access."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from backend.config import Settings, get_settings
from backend.services.hf_inference_billing_service import (
    COOKIE_NAME,
    HF_INFERENCE_SETTINGS_URL,
    HF_TOKEN_SETTINGS_URL,
    OAUTH_COOKIE_NAME,
    HfInferenceCredential,
    HfInferenceCredentialError,
    HfInferenceOrganization,
    decrypt_credential,
    decrypt_oauth_credential,
    encrypt_credential,
    encrypt_oauth_credential,
    encrypt_token,
    validate_bill_to,
    verify_oauth_token,
    verify_token,
)
from backend.utils.auth import require_user

router = APIRouter(prefix="/me/inference-billing", tags=["inference-billing"])
COOKIE_MAX_AGE_SECONDS = 30 * 24 * 60 * 60


class ConnectInferenceBilling(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=1, max_length=512)


class SelectInferenceBillingAccount(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bill_to: str | None = Field(default=None, min_length=1, max_length=256)


class InferenceBillingOrganization(BaseModel):
    name: str
    display_name: str


class InferenceBillingStatus(BaseModel):
    connected: bool
    account_type: str | None = None
    monthly_credits_usd: float | None = None
    pay_as_you_go: bool = True
    requests_per_minute: int
    requests_per_day: int
    usage_url: str = HF_INFERENCE_SETTINGS_URL
    token_url: str = HF_TOKEN_SETTINGS_URL
    bill_to: str | None = None
    organizations: list[InferenceBillingOrganization] = Field(default_factory=list)


def inference_token_for_request(
    request: Request,
    user: dict,
    settings: Settings,
) -> str | None:
    credential = inference_credential_for_request(request, user, settings)
    return credential.token if credential else None


def inference_credential_for_request(
    request: Request,
    user: dict,
    settings: Settings,
) -> HfInferenceCredential | None:
    oauth_encrypted = request.cookies.get(OAUTH_COOKIE_NAME)
    if oauth_encrypted:
        credential = decrypt_oauth_credential(
            oauth_encrypted, user["hf_user_id"], settings
        )
        if credential:
            return credential
    encrypted = request.cookies.get(COOKIE_NAME)
    if not encrypted:
        return None
    return decrypt_credential(encrypted, user["hf_user_id"], settings)


def _uses_oauth_credential(request: Request, user: dict, settings: Settings) -> bool:
    encrypted = request.cookies.get(OAUTH_COOKIE_NAME)
    return bool(
        encrypted and decrypt_oauth_credential(encrypted, user["hf_user_id"], settings)
    )


async def _verify_request_credential(
    request: Request,
    credential: HfInferenceCredential,
    user: dict,
    settings: Settings,
):
    verifier = (
        verify_oauth_token
        if _uses_oauth_credential(request, user, settings)
        else verify_token
    )
    return await verifier(credential.token, user["hf_user_id"])


def _oauth_cookie_domain(settings: Settings) -> str | None:
    return settings.shared_session_cookie_domain.strip() or None


def _status(
    settings: Settings,
    *,
    connected: bool,
    is_pro: bool | None = None,
    bill_to: str | None = None,
    organizations: tuple[HfInferenceOrganization, ...] = (),
) -> InferenceBillingStatus:
    organization_billing = connected and bill_to is not None
    return InferenceBillingStatus(
        connected=connected,
        account_type=(
            "Organization"
            if organization_billing
            else ("PRO" if is_pro else "Free")
            if connected
            else None
        ),
        monthly_credits_usd=(
            None if organization_billing or not connected else 2.0 if is_pro else 0.1
        ),
        requests_per_minute=settings.chat_requests_per_minute,
        requests_per_day=settings.chat_requests_per_day,
        usage_url=(
            f"https://huggingface.co/organizations/{bill_to}/settings/inference-providers"
            if bill_to
            else HF_INFERENCE_SETTINGS_URL
        ),
        bill_to=bill_to,
        organizations=[
            InferenceBillingOrganization(
                name=organization.name,
                display_name=organization.display_name,
            )
            for organization in organizations
        ],
    )


@router.get("", response_model=InferenceBillingStatus)
async def get_inference_billing(
    request: Request,
    user: dict = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> InferenceBillingStatus:
    credential = inference_credential_for_request(request, user, settings)
    if not credential:
        return _status(settings, connected=False)
    try:
        account = await _verify_request_credential(request, credential, user, settings)
        validate_bill_to(account, credential.bill_to)
    except HfInferenceCredentialError:
        return _status(settings, connected=False)
    return _status(
        settings,
        connected=True,
        is_pro=account.is_pro,
        bill_to=credential.bill_to,
        organizations=account.organizations,
    )


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
    return _status(
        settings,
        connected=True,
        is_pro=account.is_pro,
        organizations=account.organizations,
    )


@router.patch("", response_model=InferenceBillingStatus)
async def select_inference_billing_account(
    body: SelectInferenceBillingAccount,
    request: Request,
    response: Response,
    user: dict = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> InferenceBillingStatus:
    credential = inference_credential_for_request(request, user, settings)
    if not credential:
        raise HTTPException(
            status_code=409,
            detail="Sign in with Hugging Face again to authorize Inference Providers.",
        )
    try:
        account = await _verify_request_credential(request, credential, user, settings)
        validate_bill_to(account, body.bill_to)
    except HfInferenceCredentialError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    updated = HfInferenceCredential(token=credential.token, bill_to=body.bill_to)
    if _uses_oauth_credential(request, user, settings):
        response.set_cookie(
            OAUTH_COOKIE_NAME,
            encrypt_oauth_credential(updated, user["hf_user_id"], settings),
            max_age=COOKIE_MAX_AGE_SECONDS,
            httponly=True,
            secure=settings.is_deployed,
            samesite="lax",
            path="/",
            domain=_oauth_cookie_domain(settings),
        )
    else:
        response.set_cookie(
            COOKIE_NAME,
            encrypt_credential(updated, user["hf_user_id"], settings),
            max_age=COOKIE_MAX_AGE_SECONDS,
            httponly=True,
            secure=settings.is_deployed,
            samesite="lax",
            path="/",
        )
    return _status(
        settings,
        connected=True,
        is_pro=account.is_pro,
        bill_to=body.bill_to,
        organizations=account.organizations,
    )


@router.delete("", status_code=204)
def disconnect_inference_billing(
    response: Response,
    _user: dict = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> Response:
    response.delete_cookie(COOKIE_NAME, path="/", samesite="lax")
    response.delete_cookie(
        OAUTH_COOKIE_NAME,
        path="/",
        samesite="lax",
        domain=_oauth_cookie_domain(settings),
    )
    return response
