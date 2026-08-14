"""Authenticated durable chat sessions and SSE research turns."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import deque
from contextlib import nullcontext
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from itertools import count
from typing import Literal

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
from backend.models.api import (
    ChatAvailabilityResponse,
    ChatSandboxSpendResponse,
    ChatWebSearchBudgetResponse,
)
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
from backend.services.chat_live_stream_service import live_chat_stream_registry
from backend.services.chat_paper_context_service import (
    ChatPaperContextService,
    PreparedPaperTurn,
)
from backend.services.chat_pi_release_window import (
    PiReleaseWindowUnavailable,
    require_pi_release_window,
)
from backend.services.chat_sandbox_service import (
    SandboxCleanupUnverified,
    SandboxSessionManager,
)
from backend.services.chat_sandbox_spend_access import (
    assert_chat_sandbox_spend_available,
    chat_sandbox_spend_status,
)
from backend.services.chat_sandbox_spend_service import (
    ChatComputeDisabled,
)
from backend.services.chat_session_service import (
    ChatOwner,
    ChatServiceError,
    ChatSessionService,
    owner_from_user,
)
from backend.services.chat_share_service import ChatShareService
from backend.services.chat_stream_service import ChatStreamOrchestrator
from backend.services.chat_turn_runner import shared_sandbox_manager
from backend.services.chat_web_search_service import (
    ChatWebSearchBudgetService,
    web_search_available,
)
from backend.services.deployment_lifecycle import deployment_lifecycle
from backend.services.openrouter_budget_service import (
    OpenRouterBudgetExceeded,
    OpenRouterBudgetUnavailable,
    openrouter_budget_status,
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
from backend.utils.client_ip import get_client_ip

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)


CHAT_CAPACITY_RETRY_SECONDS = 5
SSE_PROXY_FLUSH_PADDING_BYTES = 2048
_capacity_denials = count(1)
_prewarm_requests: dict[str, deque[float]] = {}
_PREWARM_CLIENT_BUCKETS = 4096
_prewarm_lock = asyncio.Lock()
_prewarm_tasks: dict[str, asyncio.Task[None]] = {}


class PaperContextPrewarmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    route_id: str = Field(min_length=1, max_length=200)


def _prepare_paper_turn(
    settings: Settings,
    owner_id: str,
    body: ChatRequest,
) -> PreparedPaperTurn:
    with db_manager.session_local() as db:
        return ChatPaperContextService(db, settings).prepare_turn(
            owner_id=owner_id,
            display_message=body.message,
            mentions=body.paper_mentions,
            session_id=body.session_id,
            replace_message_id=body.replace_message_id,
        )


def _prewarm_paper(settings: Settings, route_id: str) -> None:
    with db_manager.session_local() as db:
        ChatPaperContextService(db, settings).prewarm(route_id)


async def _run_prewarm(settings: Settings, route_id: str) -> None:
    try:
        await asyncio.to_thread(_prewarm_paper, settings, route_id)
    finally:
        async with _prewarm_lock:
            _prewarm_tasks.pop(route_id, None)


async def _release_durable_admission() -> None:
    """The database lease is released by turn finalization, not this callback."""


async def _never_disconnected() -> bool:
    """A durable turn outlives any one browser transport."""

    return False


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


class AdminCreateHarnessSession(BaseModel):
    """Protected qualification-only session creation contract."""

    model_config = ConfigDict(extra="forbid")
    agent_harness: Literal["claude", "pi"]
    selected_model: str | None = None
    reasoning_effort: Literal["low", "high", "max"] = "low"


OPENROUTER_UNAVAILABLE_MESSAGE = (
    "OpenRouter is currently unavailable. However, you can still bring your own "
    "key in Settings."
)


def _require_staging_openrouter(settings: Settings) -> None:
    if settings.environment != "staging":
        raise HTTPException(status_code=404, detail="Not found")


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
                "message": (
                    "For security, refresh your Hugging Face sign-in before "
                    "changing your OpenRouter key."
                ),
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
                "The remaining shared Papers With Code OpenRouter allowance is not enough for another model call.",
                details={
                    "used_percent": status.used_percent,
                    "remaining_percent": status.remaining_percent,
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
        web_search_enabled=session.web_search_enabled,
        reasoning_effort=getattr(session, "reasoning_effort", None) or "high",
    )


def _message(row: ChatMessageRecord) -> ChatMessageResponse:
    return ChatMessageResponse(
        id=row.id,
        turn_id=row.turn_id,
        sequence=row.sequence,
        role=row.role,
        content=row.content,
        paper_mentions=row.paper_mentions or [],
        revision=row.revision,
        status=row.status,
        citations=row.citations or [],
        followups=row.followups or [],
        display_blocks=row.display_blocks or [],
        model=row.model,
        reasoning_effort=getattr(row, "reasoning_effort", None) or "high",
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
                "reasoning_efforts": ["low", "high", "max"],
            }
            for choice in settings.chat_model_choices
        ],
        "default_model": settings.chat_model_choices[0]["id"],
    }


@router.get("/availability", response_model=ChatAvailabilityResponse)
def chat_availability(user: dict = Depends(require_user)):
    """Content-free public state; internal warning and accounting stay private."""
    del user
    settings = get_settings()
    search_available = web_search_available(settings)
    if (
        not settings.chat_public_admission_enabled
        or not settings.chat_sandbox_admission_enabled
    ):
        return {
            "status": "paused",
            "reason": "chat_temporarily_disabled",
            "expected_recovery_at": None,
            "paper_mentions_enabled": settings.chat_paper_mentions_enabled,
            "web_search_available": False,
        }
    if (
        settings.chat_default_backend != "modal_cli"
        or not settings.chat_sandbox_spend_enforcement_enabled
    ):
        return {
            "status": "available",
            "reason": None,
            "expected_recovery_at": None,
            "paper_mentions_enabled": settings.chat_paper_mentions_enabled,
            "web_search_available": search_available,
        }
    try:
        assert_chat_sandbox_spend_available(
            settings,
            session_factory=db_manager.session_local,
        )
        return {
            "status": "available",
            "reason": None,
            "expected_recovery_at": None,
            "paper_mentions_enabled": settings.chat_paper_mentions_enabled,
            "web_search_available": search_available,
        }
    except ChatComputeDisabled:
        return {
            "status": "paused",
            "reason": "chat_temporarily_disabled",
            "expected_recovery_at": None,
            "paper_mentions_enabled": settings.chat_paper_mentions_enabled,
            "web_search_available": False,
        }


@router.get(
    "/admin/web-search-budget",
    dependencies=[Depends(require_admin)],
    response_model=ChatWebSearchBudgetResponse,
)
def chat_web_search_budget():
    settings = get_settings()
    if not settings.chat_web_search_enabled:
        raise HTTPException(status_code=404, detail="Web search is not enabled")
    with db_manager.session_local() as db, db.begin():
        return ChatWebSearchBudgetService(db, settings).status()


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
    return chat_sandbox_spend_status(
        settings,
        session_factory=db_manager.session_local,
    )


@router.get("/usage")
async def get_openrouter_usage(
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    _require_staging_openrouter(settings)
    try:
        user_status = OpenRouterUserBudgetService(db, settings).status_percentage(
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
    result = user_status.public_dict()
    try:
        shared_status = await openrouter_budget_status(settings)
    except OpenRouterBudgetUnavailable:
        result.update(
            available=False,
            unavailable_reason="provider_status_unavailable",
        )
        return result
    if not user_status.available:
        unavailable_reason = "personal_allowance_exhausted"
    else:
        unavailable_reason = shared_status.unavailable_reason
    result.update(
        available=user_status.available and shared_status.within_budget,
        unavailable_reason=unavailable_reason,
    )
    return result


@router.get("/openrouter-key")
def get_openrouter_key_status(
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    _require_staging_openrouter(settings)
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
    _require_staging_openrouter(settings)
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
    _require_staging_openrouter(settings)
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
    _require_staging_openrouter(settings)
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
    if not settings.chat_public_admission_enabled:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "chat_temporarily_disabled",
                "message": "Chat is temporarily disabled. No chat was created.",
            },
        )
    try:
        session = ChatSessionService(db, settings).create_session(
            owner_from_user(user), body.selected_model, body.reasoning_effort
        )
        db.commit()
        db.refresh(session)
        return _summary(session)
    except ChatServiceError as exc:
        db.rollback()
        _raise(exc)


@router.post(
    "/admin/sessions",
    response_model=ChatSessionSummary,
    status_code=201,
    dependencies=[],
)
def create_admin_harness_session(
    body: AdminCreateHarnessSession,
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    """Create a fresh pinned qualification chat without exposing a public picker."""

    if settings.environment != "staging":
        raise HTTPException(status_code=404, detail="Not found")
    if body.agent_harness == "pi":
        try:
            require_pi_release_window()
        except PiReleaseWindowUnavailable as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "pi_qualification_unavailable",
                    "message": str(exc),
                },
            ) from exc
    subject = str(admin.get("hf_subject") or "admin-api-token")
    owner_id = (
        str(admin.get("chat_qualification_owner") or subject)
        if admin.get("source") == "cookie"
        else f"operator:{subject}"
    )
    owner = ChatOwner(
        hf_user_id=owner_id,
        hf_username=str(admin.get("username") or "operator"),
    )
    try:
        session = ChatSessionService(db, settings).create_session(
            owner,
            body.selected_model,
            body.reasoning_effort,
            agent_harness_override=body.agent_harness,
            operator_subject=subject,
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


@router.get(
    "/sessions/{session_id}/stream",
    summary="Reconnect to an active research-assistant response",
)
def reconnect_active_stream(
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
        raise HTTPException(
            status_code=409,
            detail={
                "code": "chat_not_busy",
                "message": "This chat is not generating.",
            },
        )
    stream = live_chat_stream_registry().get(
        session_id, session.active_turn_id, owner.hf_user_id
    )
    if stream is None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "chat_stream_unavailable",
                "message": "The active response cannot be reconnected.",
            },
        )

    async def event_stream():
        yield b": " + (b" " * SSE_PROXY_FLUSH_PADDING_BYTES) + b"\n\n"
        async for frame in stream.subscribe():
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
        if body.reasoning_effort is not None:
            session = service.select_reasoning_effort(
                owner, session_id, body.reasoning_effort
            )
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
        service = ChatSessionService(db, settings)
        receipt = service.delete_session(owner_from_user(user), session_id)
        if receipt.sandbox_id or receipt.snapshot_id:
            try:
                await SandboxSessionManager(settings).cleanup_deleted(
                    receipt.sandbox_id, receipt.snapshot_id
                )
            except SandboxCleanupUnverified as exc:
                raise ChatServiceError(
                    "chat_deletion_unverified",
                    503,
                    "Chat workspace deletion could not be verified. Retry before relying on removal.",
                ) from exc
        db.commit()
        if not service.deletion_complete(receipt):
            raise ChatServiceError(
                "chat_deletion_unverified",
                503,
                "Chat deletion could not be verified. Retry before relying on removal.",
            )
        return Response(status_code=204)
    except ChatServiceError as exc:
        db.rollback()
        _raise(exc)


@router.post("/paper-context/prewarm")
async def prewarm_paper_context(body: PaperContextPrewarmRequest, request: Request):
    """Best-effort public warming; paper content never leaves the server."""
    settings = get_settings()
    if not settings.chat_paper_mentions_enabled:
        return {"status": "disabled"}
    started = time.perf_counter()
    client_ip = get_client_ip(request) or "unknown"
    now = time.monotonic()
    async with _prewarm_lock:
        if (
            client_ip not in _prewarm_requests
            and len(_prewarm_requests) >= _PREWARM_CLIENT_BUCKETS
        ):
            _prewarm_requests.pop(next(iter(_prewarm_requests)))
        recent = _prewarm_requests.setdefault(client_ip, deque())
        while recent and recent[0] <= now - 60:
            recent.popleft()
        if len(recent) >= 30:
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "paper_context_rate_limited",
                    "message": "Try again shortly.",
                },
                headers={"Retry-After": "5"},
            )
        recent.append(now)
        existing = _prewarm_tasks.get(body.route_id)
        coalesced = existing is not None
        if existing is None:
            if len(_prewarm_tasks) >= 4:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "code": "paper_context_busy",
                        "message": "Try again shortly.",
                    },
                    headers={"Retry-After": "2"},
                )
            existing = asyncio.create_task(_run_prewarm(settings, body.route_id))
            _prewarm_tasks[body.route_id] = existing
    try:
        await asyncio.wait_for(
            asyncio.shield(existing),
            timeout=settings.chat_paper_context_timeout_seconds,
        )
    except TimeoutError as exc:
        logger.info(
            "chat paper prewarm outcome=timeout coalesced=%s elapsed_ms=%s",
            coalesced,
            round((time.perf_counter() - started) * 1000),
        )
        raise HTTPException(
            status_code=503,
            detail={
                "code": "paper_context_unavailable",
                "message": "Paper context preparation timed out.",
            },
            headers={"Retry-After": "2"},
        ) from exc
    except ChatServiceError as exc:
        logger.info(
            "chat paper prewarm outcome=%s coalesced=%s elapsed_ms=%s",
            exc.code,
            coalesced,
            round((time.perf_counter() - started) * 1000),
        )
        _raise(exc)
    logger.info(
        "chat paper prewarm outcome=ready coalesced=%s elapsed_ms=%s",
        coalesced,
        round((time.perf_counter() - started) * 1000),
    )
    return {"status": "ready"}


@router.post("/stream", summary="Stream a durable research-assistant response")
async def stream_chat(
    body: ChatRequest, request: Request, user: dict = Depends(require_user)
):
    settings = get_settings()
    if not settings.chat_enabled:
        raise HTTPException(status_code=503, detail="Chat is not configured")
    if (
        not settings.chat_public_admission_enabled
        or not settings.chat_sandbox_admission_enabled
    ):
        raise HTTPException(
            status_code=503,
            detail={
                "code": "chat_temporarily_disabled",
                "message": "Chat is temporarily disabled. Your message was not sent.",
            },
        )
    if (
        settings.chat_default_backend == "modal_cli"
        and settings.chat_sandbox_spend_enforcement_enabled
    ):
        try:
            assert_chat_sandbox_spend_available(
                settings,
                session_factory=db_manager.session_local,
            )
        except ChatComputeDisabled as error:
            raise HTTPException(
                status_code=503,
                detail={"code": error.code, "message": str(error)},
            ) from error
    search_is_available = web_search_available(settings)
    if body.web_search_enabled and not search_is_available:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "web_search_unavailable",
                "message": "Web search is temporarily unavailable. Turn Search off and retry.",
            },
        )
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
    prepared = PreparedPaperTurn(body.message, body.message, [], 0, 0, 0)
    existing_prompt: str | None = None
    if body.session_id is not None:
        with db_manager.session_local() as replay_db:
            existing_prompt = ChatSessionService(
                replay_db, settings
            ).existing_effective_prompt(owner, body.session_id, body.client_message_id)
    if existing_prompt is not None:
        prepared = PreparedPaperTurn(body.message, existing_prompt, [], 0, 0, 0)
    elif body.paper_mentions:
        started = time.perf_counter()
        try:
            prepared = await asyncio.wait_for(
                asyncio.to_thread(
                    _prepare_paper_turn, settings, owner.hf_user_id, body
                ),
                timeout=settings.chat_paper_context_timeout_seconds,
            )
        except TimeoutError as exc:
            logger.info(
                "chat paper context outcome=timeout elapsed_ms=%s",
                round((time.perf_counter() - started) * 1000),
            )
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "paper_context_unavailable",
                    "message": "Attached paper context could not be prepared. Please retry.",
                },
                headers={"Retry-After": "2"},
            ) from exc
        except ChatServiceError as exc:
            logger.info(
                "chat paper context outcome=%s elapsed_ms=%s",
                exc.code,
                round((time.perf_counter() - started) * 1000),
            )
            _raise(exc, {"Retry-After": "2"} if exc.status_code == 503 else None)
        logger.info(
            "chat paper context prepared request_id=%s papers=%s occurrences=%s bytes=%s truncated=%s elapsed_ms=%s",
            request_id,
            prepared.distinct_papers,
            len(prepared.mentions),
            prepared.included_bytes,
            prepared.truncated_papers,
            round((time.perf_counter() - started) * 1000),
        )
    try:
        with db_manager.session_local() as db:
            try:
                service = ChatSessionService(db, settings)
                admission = service.begin_turn(
                    owner,
                    session_id=body.session_id,
                    client_message_id=body.client_message_id,
                    text=prepared.display_message,
                    effective_prompt=prepared.effective_prompt,
                    paper_mentions=prepared.mentions,
                    initial_model=body.initial_model,
                    replace_message_id=body.replace_message_id,
                    prior_revision=body.prior_revision,
                    web_search_enabled=body.web_search_enabled,
                    reasoning_effort=body.reasoning_effort,
                    update_web_search_preference=search_is_available,
                )
                provider = settings.chat_model_providers[admission.selected_model]
                if provider == "huggingface" and not inference_credential:
                    raise ChatServiceError(
                        "hf_inference_billing_required",
                        402,
                        "Your Hugging Face Inference Providers authorization is "
                        "missing or expired. Re-sign in with Hugging Face to continue.",
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
                if not admission.replay_assistant:
                    ChatLatencyService(db).admit(
                        turn_id=admission.turn_id,
                        session_id=admission.session_id,
                        request_id=request_id,
                        settings=settings,
                        model_route=admission.model_route,
                        execution_backend=admission.execution_backend,
                        is_new_chat=body.session_id is None,
                        agent_harness=admission.agent_harness,
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
        prompt=prepared.effective_prompt,
        display_message=prepared.display_message,
        request_id=request_id,
        title_token=title_token,
        is_disconnected=_never_disconnected,
        release_admission=_release_durable_admission,
    )
    live_stream = live_chat_stream_registry().start(
        session_id=admission.session_id,
        turn_id=admission.turn_id,
        owner_id=owner.hf_user_id,
        source=orchestrator.events(),
    )

    async def event_stream():
        # Some edge POPs buffer small initial HTTP/2 DATA frames even when the
        # origin and nginx both disable response buffering. An ignored SSE
        # comment above the common 2 KiB threshold forces those intermediaries
        # to flush the response before the first model delta arrives.
        yield b": " + (b" " * SSE_PROXY_FLUSH_PADDING_BYTES) + b"\n\n"
        async for frame in live_stream.subscribe():
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
