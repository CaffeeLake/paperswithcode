"""Authenticated durable chat sessions and SSE research turns."""

from __future__ import annotations

import logging
import uuid
from contextlib import nullcontext
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from itertools import count

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from backend.config import Settings, get_settings
from backend.database.connection import db_manager, get_database_session
from backend.models.api import ChatAvailabilityResponse, ChatSandboxSpendResponse
from backend.models.chat import (
    ArchiveOldChatsResponse,
    ChatBrowserLatencyRequest,
    ChatMessageResponse,
    ChatRequest,
    ChatSessionDetail,
    ChatSessionList,
    ChatSessionSummary,
    ChatShareDetail,
    ChatShareSummary,
    CreateSessionRequest,
    UpdateSessionRequest,
    sse_event,
)
from backend.models.database import ChatMessageRecord, ChatSession
from backend.routers.inference_billing import inference_credential_for_request
from backend.services.chat_latency_service import ChatLatencyService
from backend.services.chat_sandbox_service import SandboxSessionManager
from backend.services.chat_sandbox_spend_service import (
    ChatComputeDisabled,
    ChatSandboxSpendService,
)
from backend.services.chat_session_service import (
    ChatServiceError,
    ChatSessionService,
    owner_from_user,
)
from backend.services.chat_share_service import ChatShareService
from backend.services.chat_stream_service import ChatStreamOrchestrator
from backend.services.chat_turn_runner import shared_sandbox_manager
from backend.services.deployment_lifecycle import deployment_lifecycle
from backend.services.openrouter_budget_service import (
    OpenRouterBudgetExceeded,
    OpenRouterBudgetUnavailable,
    require_openrouter_budget,
)
from backend.services.openrouter_byok_service import (
    OpenRouterBYOKService,
    OpenRouterCredentialError,
    OpenRouterCredentialUnavailable,
)
from backend.services.openrouter_user_budget_service import (
    PUBLIC_SUPPORT_URL,
    OpenRouterUserBudgetService,
)
from backend.utils.auth import require_admin, require_user

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)


CHAT_CAPACITY_RETRY_SECONDS = 5
SSE_PROXY_FLUSH_PADDING_BYTES = 2048
_capacity_denials = count(1)


async def _release_durable_admission() -> None:
    """The database lease is released by turn finalization, not this callback."""


def _raise(exc: ChatServiceError, headers: dict[str, str] | None = None) -> None:
    response_headers = dict(headers or {})
    if exc.code == "chat_capacity":
        response_headers["Retry-After"] = str(CHAT_CAPACITY_RETRY_SECONDS)
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": str(exc), **exc.details},
        headers=response_headers or None,
    )


@dataclass(frozen=True)
class OpenRouterAdmission:
    mode: str
    token: str | None = None
    credential_revision: uuid.UUID | None = None


class ConnectOpenRouterKey(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_key: str = Field(min_length=1, max_length=512)


class SetOpenRouterFallback(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


OPENROUTER_UNAVAILABLE_MESSAGE = (
    "OpenRouter is currently unavailable. However, you can still bring your own "
    "key in Settings."
)


def _selected_byok(db: Session, settings: Settings, owner_id: str):
    """Isolate credential faults so a healthy funded ledger can still admit."""

    nested = db.begin_nested() if hasattr(db, "begin_nested") else nullcontext()
    try:
        with nested:
            return OpenRouterBYOKService(db, settings).selected(owner_id)
    except Exception as error:
        logger.error(
            "openrouter credential selection unavailable error=%s",
            type(error).__name__,
        )
        return None


def _require_same_origin_csrf(request: Request, settings: Settings) -> None:
    if settings.is_deployed:
        origin = request.headers.get("origin")
        expected = f"https://{request.headers.get('host', '').split(':', 1)[0]}"
        if origin != expected or request.headers.get("sec-fetch-site") not in {
            None,
            "same-origin",
            "same-site",
        }:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "csrf_rejected",
                    "message": "Request origin was rejected.",
                },
            )


def _require_recent_auth(request: Request, user: dict, settings: Settings) -> None:
    from backend.routers.auth import decode_request_session

    issued_at = (decode_request_session(request) or {}).get("iat")
    now = datetime.now(UTC).timestamp()
    if (
        not isinstance(issued_at, (int, float))
        or now - issued_at > settings.chat_openrouter_recent_auth_seconds
    ):
        raise HTTPException(
            status_code=401,
            detail={
                "code": "fresh_auth_required",
                "message": "Sign in with Hugging Face again before changing your OpenRouter key.",
            },
        )
    _require_same_origin_csrf(request, settings)


async def _authorize_openrouter(
    settings: Settings,
    db: Session | None = None,
    owner_id: str | None = None,
) -> OpenRouterAdmission:
    if not settings.chat_openrouter_server_funded_enabled:
        if db is not None and owner_id is not None:
            byok = _selected_byok(db, settings, owner_id)
            if byok:
                return OpenRouterAdmission("openrouter_byok", byok.token, byok.revision)
        raise ChatServiceError(
            "openrouter_unavailable",
            503,
            OPENROUTER_UNAVAILABLE_MESSAGE,
            details={
                "byok_settings_available": True,
                "support_url": PUBLIC_SUPPORT_URL,
            },
        )
    if db is not None and owner_id is not None:
        try:
            funded_available = OpenRouterUserBudgetService(db, settings).can_fund_call(
                owner_id
            )
        except Exception as error:
            logger.error(
                "openrouter user budget database failure error=%s",
                type(error).__name__,
            )
            raise ChatServiceError(
                "openrouter_unavailable",
                503,
                OPENROUTER_UNAVAILABLE_MESSAGE,
                details={
                    "byok_settings_available": True,
                    "support_url": PUBLIC_SUPPORT_URL,
                },
            ) from None
        byok = _selected_byok(db, settings, owner_id)
        if not funded_available:
            if byok:
                return OpenRouterAdmission("openrouter_byok", byok.token, byok.revision)
            status = OpenRouterUserBudgetService(db, settings).status_percentage(
                owner_id
            )
            raise ChatServiceError(
                "openrouter_monthly_budget_exhausted",
                429,
                "You have used this month's Papers With Code OpenRouter allowance.",
                details={
                    "used_percent": 100,
                    "resets_at": status.resets_at.isoformat().replace("+00:00", "Z"),
                },
            )
    try:
        await require_openrouter_budget(settings)
    except OpenRouterBudgetExceeded:
        if db is not None and owner_id is not None:
            byok = _selected_byok(db, settings, owner_id)
            if byok:
                return OpenRouterAdmission("openrouter_byok", byok.token, byok.revision)
        raise ChatServiceError(
            "openrouter_unavailable",
            503,
            OPENROUTER_UNAVAILABLE_MESSAGE,
            details={
                "byok_settings_available": True,
                "support_url": PUBLIC_SUPPORT_URL,
            },
        ) from None
    except OpenRouterBudgetUnavailable:
        if db is not None and owner_id is not None:
            byok = _selected_byok(db, settings, owner_id)
            if byok:
                return OpenRouterAdmission("openrouter_byok", byok.token, byok.revision)
        raise ChatServiceError(
            "openrouter_unavailable",
            503,
            OPENROUTER_UNAVAILABLE_MESSAGE,
            details={
                "byok_settings_available": True,
                "support_url": PUBLIC_SUPPORT_URL,
            },
        ) from None
    return OpenRouterAdmission("openrouter_funded")


def _busy(session: ChatSession) -> bool:
    from datetime import UTC, datetime

    return bool(
        session.active_turn_id
        and session.active_turn_expires_at
        and session.active_turn_expires_at > datetime.now(UTC)
    )


def _summary(session: ChatSession) -> ChatSessionSummary:
    return ChatSessionSummary(
        id=session.id,
        title=session.title,
        selected_model=session.selected_model,
        created_at=session.created_at,
        updated_at=session.updated_at,
        message_count=session.message_count,
        is_busy=_busy(session),
    )


def _message(row: ChatMessageRecord) -> ChatMessageResponse:
    return ChatMessageResponse(
        id=row.id,
        turn_id=row.turn_id,
        sequence=row.sequence,
        role=row.role,
        content=row.content,
        revision=row.revision,
        status=row.status,
        citations=row.citations or [],
        followups=row.followups or [],
        display_blocks=row.display_blocks or [],
        model=row.model,
        finish_reason=row.finish_reason,
        error_code=row.error_code,
        created_at=row.created_at,
    )


@router.get("/models")
def list_models(
    user: dict = Depends(require_user), settings: Settings = Depends(get_settings)
):
    del user
    return {
        "items": [
            {
                "id": choice["id"],
                "label": choice["label"],
                "provider": choice["provider"],
            }
            for choice in settings.chat_model_choices
        ],
        "default_model": settings.chat_model_choices[0]["id"],
    }


@router.get("/availability", response_model=ChatAvailabilityResponse)
def chat_availability():
    """Content-free public state; internal warning and accounting stay private."""
    settings = get_settings()
    if (
        settings.chat_default_backend != "modal_cli"
        or not settings.chat_sandbox_spend_enforcement_enabled
    ):
        return {"status": "available", "reason": None, "expected_recovery_at": None}
    try:
        with db_manager.session_local() as db:
            try:
                ChatSandboxSpendService(db, settings).assert_available()
            except ChatComputeDisabled:
                db.commit()
                raise
            db.commit()
        return {"status": "available", "reason": None, "expected_recovery_at": None}
    except ChatComputeDisabled:
        return {
            "status": "paused",
            "reason": "chat_temporarily_disabled",
            "expected_recovery_at": None,
        }


@router.get(
    "/admin/sandbox-spend",
    dependencies=[Depends(require_admin)],
    response_model=ChatSandboxSpendResponse,
)
def chat_sandbox_spend(environment: str | None = None):
    settings = get_settings()
    if environment is not None:
        if not environment.startswith(f"{settings.environment}-q-"):
            raise HTTPException(status_code=404, detail="Unknown qualification")
        settings = settings.model_copy(update={"environment": environment})
    with db_manager.session_local() as db, db.begin():
        return ChatSandboxSpendService(db, settings).status()


@router.get("/usage")
def get_openrouter_usage(
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    try:
        status = OpenRouterUserBudgetService(db, settings).status_percentage(
            user["hf_user_id"]
        )
    except Exception as error:
        logger.error("openrouter usage status failed error=%s", type(error).__name__)
        raise HTTPException(
            status_code=503,
            detail={
                "code": "openrouter_usage_unavailable",
                "message": "OpenRouter usage is temporarily unavailable.",
            },
        ) from None
    return status.public_dict()


@router.get("/openrouter-key")
def get_openrouter_key_status(
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    try:
        return (
            OpenRouterBYOKService(db, settings).status(user["hf_user_id"]).public_dict()
        )
    except Exception as error:
        logger.error(
            "openrouter credential status failed error=%s", type(error).__name__
        )
        raise HTTPException(
            status_code=503,
            detail={
                "code": "openrouter_credential_unavailable",
                "message": "Your OpenRouter key status is temporarily unavailable.",
            },
        ) from None


@router.put("/openrouter-key")
async def connect_openrouter_key(
    body: ConnectOpenRouterKey,
    request: Request,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    _require_recent_auth(request, user, settings)
    try:
        status = await OpenRouterBYOKService(db, settings).connect(
            user["hf_user_id"], body.api_key
        )
        db.commit()
        return status.public_dict()
    except OpenRouterCredentialError as error:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from None
    except OpenRouterCredentialUnavailable:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="OpenRouter key verification is temporarily unavailable.",
        ) from None


@router.patch("/openrouter-key")
def set_openrouter_fallback(
    body: SetOpenRouterFallback,
    request: Request,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    if body.enabled:
        _require_recent_auth(request, user, settings)
    else:
        _require_same_origin_csrf(request, settings)
    try:
        status = OpenRouterBYOKService(db, settings).set_fallback_enabled(
            user["hf_user_id"], body.enabled
        )
        db.commit()
        return status.public_dict()
    except OpenRouterCredentialError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from None


@router.delete("/openrouter-key", status_code=204)
def disconnect_openrouter_key(
    request: Request,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    _require_recent_auth(request, user, settings)
    OpenRouterBYOKService(db, settings).disconnect(user["hf_user_id"])
    db.commit()
    return Response(status_code=204)


@router.post("/sessions", response_model=ChatSessionSummary, status_code=201)
def create_session(
    body: CreateSessionRequest,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    try:
        session = ChatSessionService(db, settings).create_session(
            owner_from_user(user), body.selected_model
        )
        db.commit()
        db.refresh(session)
        return _summary(session)
    except ChatServiceError as exc:
        db.rollback()
        _raise(exc)


@router.get("/sessions", response_model=ChatSessionList)
def list_sessions(
    limit: int = Query(50, ge=1, le=50),
    cursor: str | None = None,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    try:
        rows, next_cursor = ChatSessionService(db, settings).list_sessions(
            owner_from_user(user), cursor, limit
        )
        return ChatSessionList(
            items=[_summary(row) for row in rows], next_cursor=next_cursor
        )
    except ChatServiceError as exc:
        _raise(exc)


@router.post("/sessions/archive-old", response_model=ArchiveOldChatsResponse)
def archive_old_sessions(
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    try:
        archived_count = ChatSessionService(db, settings).archive_old_sessions(
            owner_from_user(user), days=30
        )
        db.commit()
        return ArchiveOldChatsResponse(archived_count=archived_count)
    except ChatServiceError as exc:
        db.rollback()
        _raise(exc)


@router.post("/sessions/archive-oldest", response_model=ArchiveOldChatsResponse)
def archive_oldest_sessions(
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    try:
        archived_count = ChatSessionService(db, settings).archive_oldest_sessions(
            owner_from_user(user), limit=50
        )
        db.commit()
        return ArchiveOldChatsResponse(archived_count=archived_count)
    except ChatServiceError as exc:
        db.rollback()
        _raise(exc)


@router.get("/sessions/{session_id}", response_model=ChatSessionDetail)
def get_session(
    session_id: uuid.UUID,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    try:
        session, messages = ChatSessionService(db, settings).get_session(
            owner_from_user(user), session_id
        )
        return ChatSessionDetail(
            **_summary(session).model_dump(),
            messages=[_message(row) for row in messages],
            transcript_status=session.transcript_status,
        )
    except ChatServiceError as exc:
        _raise(exc)


@router.post(
    "/sessions/{session_id}/share",
    response_model=ChatShareSummary,
)
def create_or_refresh_share(
    session_id: uuid.UUID,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    try:
        share = ChatShareService(db, settings).create_or_refresh(
            owner_from_user(user), session_id
        )
        db.commit()
        db.refresh(share)
        return ChatShareSummary(
            share_id=share.id,
            public_path=f"/share/{share.id}",
            created_at=share.created_at,
            updated_at=share.updated_at,
        )
    except ChatServiceError as exc:
        db.rollback()
        _raise(exc)


@router.get("/shares/{share_id}", response_model=ChatShareDetail)
def get_shared_chat(
    share_id: str,
    response: Response,
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    response.headers["Cache-Control"] = "no-store"
    try:
        return ChatShareService(db, settings).get_public(share_id)
    except ChatServiceError as exc:
        _raise(exc, {"Cache-Control": "no-store"})


@router.patch("/sessions/{session_id}", response_model=ChatSessionSummary)
def update_session(
    session_id: uuid.UUID,
    body: UpdateSessionRequest,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    service = ChatSessionService(db, settings)
    owner = owner_from_user(user)
    try:
        session = None
        if body.title is not None:
            session = service.rename_session(owner, session_id, body.title)
        if body.selected_model is not None:
            session = service.select_model(owner, session_id, body.selected_model)
        assert session is not None
        db.commit()
        db.refresh(session)
        return _summary(session)
    except ChatServiceError as exc:
        db.rollback()
        _raise(exc)


@router.post("/sessions/{session_id}/cancel", status_code=204)
async def cancel_active_turn(
    session_id: uuid.UUID,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    owner = owner_from_user(user)
    try:
        session, _messages = ChatSessionService(db, settings).get_session(
            owner, session_id
        )
    except ChatServiceError as exc:
        _raise(exc)
    if session.active_turn_id is None:
        return Response(status_code=204)
    manager = shared_sandbox_manager(settings)
    cancelled = await manager.cancel(session_id, session.active_turn_id)
    if not cancelled:
        await manager.terminate(session_id, failure_code="cancel_control_missing")
    return Response(status_code=204)


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: uuid.UUID,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    try:
        sandbox_id, snapshot_id = ChatSessionService(db, settings).delete_session(
            owner_from_user(user), session_id
        )
        db.commit()
        if sandbox_id or snapshot_id:
            await SandboxSessionManager(settings).cleanup_deleted(
                sandbox_id, snapshot_id
            )
        return Response(status_code=204)
    except ChatServiceError as exc:
        db.rollback()
        _raise(exc)


@router.post("/stream", summary="Stream a durable research-assistant response")
async def stream_chat(
    body: ChatRequest, request: Request, user: dict = Depends(require_user)
):
    settings = get_settings()
    if not settings.chat_enabled:
        raise HTTPException(status_code=503, detail="Chat is not configured")
    if (
        settings.chat_default_backend == "modal_cli"
        and settings.chat_sandbox_spend_enforcement_enabled
    ):
        try:
            with db_manager.session_local() as budget_db:
                try:
                    ChatSandboxSpendService(budget_db, settings).assert_available()
                except ChatComputeDisabled:
                    budget_db.commit()
                    raise
                budget_db.commit()
        except ChatComputeDisabled as error:
            raise HTTPException(
                status_code=503,
                detail={"code": error.code, "message": str(error)},
            ) from error
    inference_credential = inference_credential_for_request(request, user, settings)
    if not deployment_lifecycle.status().accepting_chat_turns:
        raise HTTPException(
            status_code=503,
            detail="A deployment is activating; retry this turn shortly",
            headers={"Retry-After": "3"},
        )
    owner = owner_from_user(
        user,
        inference_token=inference_credential.token if inference_credential else None,
        inference_bill_to=(
            inference_credential.bill_to if inference_credential else None
        ),
    )
    request_id = str(uuid.uuid4())
    try:
        with db_manager.session_local() as db:
            try:
                service = ChatSessionService(db, settings)
                admission = service.begin_turn(
                    owner,
                    session_id=body.session_id,
                    client_message_id=body.client_message_id,
                    text=body.message,
                    initial_model=body.initial_model,
                    replace_message_id=body.replace_message_id,
                    prior_revision=body.prior_revision,
                )
                provider = settings.chat_model_providers[admission.selected_model]
                if provider == "huggingface" and not inference_credential:
                    raise ChatServiceError(
                        "hf_inference_billing_required",
                        402,
                        "Authorize Hugging Face inference in Settings to use this model.",
                    )
                if provider == "openrouter" and not admission.replay_assistant:
                    try:
                        openrouter = await _authorize_openrouter(
                            settings, db, owner.hf_user_id
                        )
                    except ChatServiceError as exc:
                        service.fail_turn(owner, admission, exc.code)
                        exc.commit_changes = True
                        raise
                    owner = replace(
                        owner,
                        openrouter_mode=openrouter.mode,
                        openrouter_token=openrouter.token,
                        openrouter_credential_revision=openrouter.credential_revision,
                    )
                title_token = (
                    service.begin_title(
                        owner,
                        admission.session_id,
                        revision=admission.prompt_revision,
                    )
                    if admission.title_should_generate
                    and not admission.replay_assistant
                    else None
                )
                if settings.environment == "staging" and not admission.replay_assistant:
                    ChatLatencyService(db).admit(
                        turn_id=admission.turn_id,
                        session_id=admission.session_id,
                        request_id=request_id,
                        settings=settings,
                        model_route=admission.model_route,
                        execution_backend=admission.execution_backend,
                        is_new_chat=body.session_id is None,
                    )
                db.commit()
            except ChatServiceError as exc:
                if exc.commit_changes:
                    db.commit()
                else:
                    db.rollback()
                raise
    except ChatServiceError as exc:
        if exc.code == "chat_capacity":
            logger.warning(
                "chat capacity denied environment=%s release=%s active=%s ceiling=%s denial_count=%s retry_seconds=%s",
                settings.environment,
                settings.release_id,
                exc.active_count,
                settings.chat_max_concurrency,
                next(_capacity_denials),
                CHAT_CAPACITY_RETRY_SECONDS,
            )
        _raise(exc)

    orchestrator = ChatStreamOrchestrator(
        settings=settings,
        owner=owner,
        admission=admission,
        prompt=body.message,
        request_id=request_id,
        title_token=title_token,
        is_disconnected=request.is_disconnected,
        release_admission=_release_durable_admission,
    )

    async def event_stream():
        # Some edge POPs buffer small initial HTTP/2 DATA frames even when the
        # origin and nginx both disable response buffering. An ignored SSE
        # comment above the common 2 KiB threshold forces those intermediaries
        # to flush the response before the first model delta arrives.
        yield b": " + (b" " * SSE_PROXY_FLUSH_PADDING_BYTES) + b"\n\n"
        async for frame in orchestrator.events():
            if frame.event is None:
                yield b": ping\n\n"
            else:
                yield sse_event(frame.event, **frame.payload)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/latency/{request_id}", status_code=204)
def report_browser_latency(
    request_id: uuid.UUID,
    body: ChatBrowserLatencyRequest,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
):
    owner = owner_from_user(user)
    try:
        found = ChatLatencyService(db).update_browser(
            owner.hf_user_id, str(request_id), body
        )
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from None
    if not found:
        db.rollback()
        raise HTTPException(status_code=404, detail="Chat request not found")
    db.commit()
    return Response(status_code=204)
