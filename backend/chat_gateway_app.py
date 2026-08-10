"""Private, separately started gateway for sandbox model/catalog/store traffic."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from huggingface_hub.errors import HfHubHTTPError
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from backend.config import Settings, get_settings
from backend.chat_execution_policy import MAX_PROVIDER_REQUESTS
from backend.chat_sandbox_worker.contract import PROVIDER_OUTPUT_TOKEN_LIMIT
from backend.database.connection import db_manager, get_database_session
from backend.models.database import ChatSession, ChatTurnCapability
from backend.services.chat_capability_service import (
    CapabilityError,
    ChatCapabilityService,
)
from backend.services.chat_gateway_service import ChatGatewayService
from backend.services.chat_latency_service import ChatLatencyService
from backend.services.chat_session_store_gateway import (
    ChatSessionStoreGateway,
    SessionStoreCommand,
    SessionStoreGatewayError,
)
from backend.services.chat_web_fetch_service import (
    ChatWebFetchError,
    fetch_catalog_url,
)
from backend.services.chat_web_search_service import WebSearchError, search_web
from backend.services.hf_inference_billing_service import HfInferenceCredential
from backend.services.openrouter_budget_service import (
    OpenRouterBudgetExceeded,
    OpenRouterBudgetUnavailable,
    require_openrouter_budget,
)
from backend.services.openrouter_byok_service import (
    OpenRouterBYOKService,
    OpenRouterCredentialUnavailable,
)
from backend.services.openrouter_usage_extractor import OpenRouterUsageExtractor
from backend.services.openrouter_user_budget_service import (
    PUBLIC_SUPPORT_URL,
    OpenRouterMonthlyBudgetExhausted,
    OpenRouterPricingUnavailable,
    OpenRouterUserBudgetService,
    RequestBounds,
    opaque_owner,
)
from backend.utils.exceptions import PaperNotFoundError

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
logger = logging.getLogger(__name__)
MAX_PROVIDER_OUTPUT_TOKENS = PROVIDER_OUTPUT_TOKEN_LIMIT
MAX_PROVIDER_TURN_TOKENS = 512_000


def _opaque_turn(turn_id: uuid.UUID) -> str:
    return hashlib.sha256(str(turn_id).encode()).hexdigest()[:12]


def _record_gateway_timing(
    settings: Settings,
    turn_id: uuid.UUID,
    *,
    phase: str | None = None,
    elapsed_ms: int | None = None,
    received_at: datetime | None = None,
) -> None:
    if settings.environment != "staging":
        return
    try:
        with db_manager.session_local() as timing_db:
            service = ChatLatencyService(timing_db)
            if received_at is not None:
                service.record_gateway_received(turn_id, received_at)
            elif phase is not None and elapsed_ms is not None:
                service.record_phase_for_turn(turn_id, phase, elapsed_ms)
            timing_db.commit()
    except Exception as error:
        logger.warning(
            "chat gateway latency persistence failed turn=%s phase=%s error=%s",
            _opaque_turn(turn_id),
            phase or "received",
            type(error).__name__,
        )


class CatalogRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: str = Field(max_length=64)
    arguments: dict[str, Any]


class StoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str
    key: dict[str, Any] | None = None
    entries: list[dict[str, Any]] | None = None
    project_key: str | None = None


class WebFetchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(max_length=2000)


def _bearer(authorization: Annotated[str, Header()]) -> str:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Invalid capability")
    return token


def _output_tokens_allowed(value: int) -> bool:
    return 1 <= value <= MAX_PROVIDER_OUTPUT_TOKENS


def _user_provider_credential(row, settings: Settings) -> HfInferenceCredential:
    credential = ChatCapabilityService.provider_credential(
        row, row.owner_hash, settings
    )
    if not credential:
        raise HTTPException(status_code=402, detail="Authorize Hugging Face inference")
    return credential


def _user_provider_token(row, settings: Settings) -> str:
    return _user_provider_credential(row, settings).token


def _provider_headers(
    provider_token: str,
    request: Request,
    *,
    bill_to: str | None = None,
) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {provider_token}",
        "Content-Type": "application/json",
        "Accept": request.headers.get("accept", "application/json"),
        "Anthropic-Version": request.headers.get("anthropic-version", "2023-06-01"),
    }
    if request.headers.get("anthropic-beta"):
        headers["Anthropic-Beta"] = request.headers["anthropic-beta"]
    if bill_to:
        headers["X-HF-Bill-To"] = bill_to
    return headers


def _provider_target(
    row, settings: Settings, db: Session | None = None
) -> tuple[str, str, str | None]:
    provider = settings.chat_route_providers.get(row.model)
    if provider == "openrouter":
        mode = getattr(row, "provider_mode", None) or "openrouter_funded"
        if mode == "openrouter_byok":
            if db is None or not row.provider_credential_revision:
                raise HTTPException(status_code=403, detail="Capability rejected")
            session = db.get(ChatSession, row.chat_session_id)
            if (
                session is None
                or row.owner_hash
                != hashlib.sha256(session.hf_user_id.encode()).hexdigest()
            ):
                raise HTTPException(status_code=403, detail="Capability rejected")
            try:
                selected = OpenRouterBYOKService(db, settings).validate_dispatch(
                    session.hf_user_id, row.provider_credential_revision
                )
                copied = _user_provider_token(row, settings)
            except OpenRouterCredentialUnavailable:
                raise HTTPException(
                    status_code=401, detail="OpenRouter credential was revoked"
                ) from None
            if not hmac.compare_digest(selected.token, copied):
                raise HTTPException(status_code=403, detail="Capability rejected")
            return (
                "https://openrouter.ai/api/v1/messages",
                copied,
                None,
            )
        if mode != "openrouter_funded":
            raise HTTPException(status_code=403, detail="Capability rejected")
        if (
            not settings.chat_openrouter_server_funded_enabled
            or not settings.chat_openrouter_api_key
        ):
            raise HTTPException(status_code=503, detail="OpenRouter is not configured")
        return (
            "https://openrouter.ai/api/v1/messages",
            settings.chat_openrouter_api_key,
            None,
        )
    if provider == "huggingface":
        credential = _user_provider_credential(row, settings)
        return (
            "https://router.huggingface.co/v1/messages",
            credential.token,
            credential.bill_to,
        )
    raise HTTPException(status_code=422, detail="Unsupported model provider")


def _pin_openrouter_reasoning_effort(
    payload: dict[str, Any], model: str, settings: Settings
) -> None:
    """Keep the discounted OpenAI variants on their requested medium tier."""

    if model not in {settings.chat_luna_route, settings.chat_terra_route}:
        return
    output_config = payload.get("output_config")
    if not isinstance(output_config, dict):
        output_config = {}
        payload["output_config"] = output_config
    output_config["effort"] = "medium"


def _capability_owner(row: ChatTurnCapability, db: Session) -> str:
    session = db.get(ChatSession, row.chat_session_id)
    if session is None:
        logger.critical("openrouter funded dispatch missing owner session")
        raise HTTPException(status_code=403, detail="Capability rejected")
    if row.owner_hash != hashlib.sha256(session.hf_user_id.encode()).hexdigest():
        logger.critical("openrouter funded dispatch owner binding mismatch")
        raise HTTPException(status_code=403, detail="Capability rejected")
    return session.hf_user_id


def _record_provider_error(capability_id: uuid.UUID, code: str) -> None:
    with db_manager.session_local() as error_db:
        row = error_db.get(ChatTurnCapability, capability_id)
        if row is not None:
            ChatCapabilityService(error_db).record_provider_error(row, code)
            error_db.commit()


def _byok_provider_error_code(status_code: int) -> str | None:
    return {
        402: "openrouter_byok_billing_error",
        429: "openrouter_byok_rate_limit",
    }.get(status_code)


def _huggingface_provider_error_code(status_code: int) -> str | None:
    if status_code == 402:
        return "hf_inference_billing_exhausted"
    return None


def _settle_openrouter_call(
    settings: Settings,
    call_id: uuid.UUID,
    extractor: OpenRouterUsageExtractor,
) -> None:
    result = extractor.result()
    with db_manager.session_local() as accounting_db:
        service = OpenRouterUserBudgetService(accounting_db, settings)
        if result.cost_microusd is None:
            service.mark_cost_unknown(call_id, result.generation_id)
        else:
            service.settle_call(call_id, result.cost_microusd, result.generation_id)
        accounting_db.commit()


def _scope(
    token: str,
    scope: str,
    session_id: str,
    turn_id: str,
    db: Session,
    *,
    model: str | None = None,
):
    try:
        row = ChatCapabilityService(db).validate(
            token,
            scope=scope,
            chat_session_id=uuid.UUID(session_id),
            turn_id=uuid.UUID(turn_id),
            model=model,
        )
        return row
    except (CapabilityError, ValueError):
        db.rollback()
        raise HTTPException(status_code=403, detail="Capability rejected") from None


@app.post("/catalog")
def catalog(
    body: CatalogRequest,
    authorization: Annotated[str, Header()],
    x_pwc_session: Annotated[str, Header()],
    x_pwc_turn: Annotated[str, Header()],
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    token = _bearer(authorization)
    scope = "web_search" if body.operation == "web_search" else "catalog"
    capability = _scope(token, scope, x_pwc_session, x_pwc_turn, db)
    try:
        if body.operation == "web_search":
            ChatCapabilityService(db).meter_web_search(
                capability, maximum_searches=settings.chat_web_search_max_calls
            )
        else:
            ChatCapabilityService(db).meter_catalog(
                capability,
                body.operation,
                maximum_searches=settings.chat_max_direct_search_calls,
            )
        db.commit()
    except CapabilityError:
        db.rollback()
        raise HTTPException(
            status_code=429, detail="Tool execution limit reached"
        ) from None
    if body.operation == "web_search":
        try:
            query = body.arguments["query"]
            if set(body.arguments) != {"query"} or not isinstance(query, str):
                raise ValueError
            result = asyncio.run(
                search_web(query, settings, owner_hash=capability.owner_hash)
            )
            return {"result": result}
        except (KeyError, TypeError, ValueError):
            raise HTTPException(
                status_code=422, detail="Invalid web search request"
            ) from None
        except WebSearchError as error:
            capability = db.get(ChatTurnCapability, capability.id)
            if capability is not None:
                ChatCapabilityService(db).fail_web_search(capability)
                db.commit()
            raise HTTPException(
                status_code=503,
                detail={"code": error.code, "message": str(error)},
            ) from None
    try:
        result = ChatGatewayService(db, settings).catalog(
            body.operation, body.arguments
        )
    except PaperNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from None
    except (HfHubHTTPError, OSError):
        raise HTTPException(
            status_code=502, detail="Paper Markdown could not be read"
        ) from None
    except (KeyError, TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"result": result}


@app.post("/session-store")
def session_store(
    body: StoreRequest,
    authorization: Annotated[str, Header()],
    x_pwc_session: Annotated[str, Header()],
    x_pwc_turn: Annotated[str, Header()],
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    token = _bearer(authorization)
    capability = _scope(token, "session_store", x_pwc_session, x_pwc_turn, db)
    try:
        result = ChatSessionStoreGateway(db, settings).execute(
            capability,
            SessionStoreCommand(
                action=body.action,
                key=body.key,
                entries=body.entries,
                project_key=body.project_key,
            ),
        )
        db.commit()
        return {"result": result}
    except SessionStoreGatewayError as error:
        db.rollback()
        raise HTTPException(status_code=error.status_code, detail=str(error)) from None


@app.post("/web-fetch")
async def web_fetch(
    body: WebFetchRequest,
    authorization: Annotated[str, Header()],
    x_pwc_session: Annotated[str, Header()],
    x_pwc_turn: Annotated[str, Header()],
    db: Session = Depends(get_database_session),
):
    token = _bearer(authorization)
    _scope(token, "web_fetch", x_pwc_session, x_pwc_turn, db)
    db.commit()
    try:
        result = await fetch_catalog_url(db, body.url)
    except ChatWebFetchError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from None
    return Response(
        content=result.body,
        status_code=result.status_code,
        headers={
            "Content-Type": result.content_type,
            "Content-Length": str(len(result.body)),
            "Cache-Control": "no-store",
        },
    )


@app.post("/v1/messages")
async def messages(
    request: Request,
    authorization: Annotated[str, Header()],
    x_pwc_session: Annotated[str, Header()],
    x_pwc_turn: Annotated[str, Header()],
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    gateway_started = time.perf_counter()
    received_at = datetime.now(UTC)
    try:
        turn_id = uuid.UUID(x_pwc_turn)
    except ValueError:
        raise HTTPException(status_code=403, detail="Capability rejected") from None
    token = _bearer(authorization)
    raw = await request.body()
    if len(raw) > 512 * 1024:
        raise HTTPException(status_code=413, detail="Model request is too large")
    try:
        payload = json.loads(raw)
        model = str(payload["model"])
        maximum_tokens = int(payload.get("max_tokens", 0))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=422, detail="Invalid model request") from None
    if not _output_tokens_allowed(maximum_tokens):
        raise HTTPException(status_code=422, detail="max_tokens is out of range")
    row = _scope(token, "model", x_pwc_session, x_pwc_turn, db, model=model)
    provider = settings.chat_route_providers.get(row.model)
    provider_mode = row.provider_mode or (
        "openrouter_funded" if provider == "openrouter" else "huggingface"
    )
    owner_id = _capability_owner(row, db)
    if provider == "openrouter":
        # Supplemental reconciliation metadata is opaque and cannot identify
        # the HF subject at OpenRouter.
        payload["user"] = opaque_owner(owner_id, settings)
        _pin_openrouter_reasoning_effort(payload, model, settings)
        raw = json.dumps(payload, separators=(",", ":")).encode()
        if len(raw) > 512 * 1024:
            raise HTTPException(status_code=413, detail="Model request is too large")
    provider_url, provider_token, provider_bill_to = _provider_target(row, settings, db)
    capability_id = row.id
    funded_call_id: uuid.UUID | None = None
    try:
        ChatCapabilityService(db).meter_provider(
            row,
            request_tokens=max(1, len(raw) // 4) + maximum_tokens,
            maximum_requests=MAX_PROVIDER_REQUESTS,
            maximum_tokens=MAX_PROVIDER_TURN_TOKENS,
        )
        call_sequence = row.provider_requests
        # Capability validation takes a row lock so concurrent SDK model calls
        # receive distinct request counters. Land that bounded mutation before
        # any provider network check; otherwise a slow OpenRouter budget lookup
        # holds the lock for its full timeout and blocks the other model call.
        db.commit()
    except CapabilityError:
        db.rollback()
        raise HTTPException(
            status_code=429, detail="Model execution limit reached"
        ) from None

    if provider_mode == "openrouter_funded":
        try:
            await require_openrouter_budget(settings)
        except (OpenRouterBudgetExceeded, OpenRouterBudgetUnavailable):
            _record_provider_error(capability_id, "openrouter_unavailable")
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "openrouter_unavailable",
                    "message": (
                        "OpenRouter is currently unavailable. However, you can "
                        "still bring your own key in Settings."
                    ),
                    "byok_settings_available": True,
                    "support_url": PUBLIC_SUPPORT_URL,
                },
            ) from None
        try:
            funded_call_id = uuid.uuid5(capability_id, f"provider-call:{call_sequence}")
            OpenRouterUserBudgetService(db, settings).reserve_call(
                owner_id,
                turn_id,
                funded_call_id,
                call_sequence,
                model,
                RequestBounds(
                    request_bytes=len(raw),
                    maximum_output_tokens=maximum_tokens,
                    payload=payload,
                ),
            )
            db.commit()
        except OpenRouterMonthlyBudgetExhausted as error:
            db.rollback()
            _record_provider_error(capability_id, "openrouter_monthly_budget_exhausted")
            usage = OpenRouterUserBudgetService(db, settings).status_percentage(
                owner_id
            )
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "openrouter_monthly_budget_exhausted",
                    "message": (
                        "The remaining shared Papers With Code OpenRouter allowance "
                        "is not enough for another model call."
                    ),
                    "used_percent": usage.used_percent,
                    "remaining_percent": usage.remaining_percent,
                    "resets_at": error.resets_at.isoformat().replace("+00:00", "Z"),
                },
            ) from None
        except OpenRouterPricingUnavailable:
            db.rollback()
            _record_provider_error(capability_id, "openrouter_unavailable")
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "openrouter_unavailable",
                    "message": (
                        "OpenRouter is currently unavailable. However, you can "
                        "still bring your own key in Settings."
                    ),
                    "byok_settings_available": True,
                    "support_url": PUBLIC_SUPPORT_URL,
                },
            ) from None
    _record_gateway_timing(settings, turn_id, received_at=received_at)

    if funded_call_id is not None:
        # Persist the ambiguous-dispatch boundary before any network bytes can
        # reach OpenRouter. A crash after this point retains the full bound.
        OpenRouterUserBudgetService(db, settings).mark_dispatched(funded_call_id)
        db.commit()

    client = httpx.AsyncClient(timeout=180, follow_redirects=False)
    upstream_headers = _provider_headers(
        provider_token,
        request,
        bill_to=provider_bill_to,
    )
    try:
        upstream = await client.send(
            client.build_request(
                "POST",
                provider_url,
                content=raw,
                headers=upstream_headers,
            ),
            stream=True,
        )
    except httpx.HTTPError:
        await client.aclose()
        if funded_call_id is not None:
            with db_manager.session_local() as accounting_db:
                OpenRouterUserBudgetService(accounting_db, settings).mark_cost_unknown(
                    funded_call_id
                )
                accounting_db.commit()
        raise HTTPException(status_code=502, detail="Model provider failed") from None
    _record_gateway_timing(
        settings,
        turn_id,
        phase="upstream_response_headers",
        elapsed_ms=round((time.perf_counter() - gateway_started) * 1000),
    )

    extractor = OpenRouterUsageExtractor()

    if provider_mode == "openrouter_byok" and upstream.status_code == 401:
        with db_manager.session_local() as credential_db:
            OpenRouterBYOKService(credential_db, settings).invalidate_auth_failure(
                owner_id
            )
            capability = credential_db.get(ChatTurnCapability, capability_id)
            if capability is not None:
                ChatCapabilityService(credential_db).record_provider_error(
                    capability, "openrouter_byok_credential_invalid"
                )
            credential_db.commit()
    elif provider_mode == "openrouter_byok":
        provider_error = _byok_provider_error_code(upstream.status_code)
        if provider_error is not None:
            _record_provider_error(capability_id, provider_error)
    elif provider_mode == "openrouter_funded" and upstream.status_code in {402, 403}:
        _record_provider_error(capability_id, "openrouter_unavailable")
    elif provider_mode == "huggingface":
        provider_error = _huggingface_provider_error_code(upstream.status_code)
        if provider_error is not None:
            _record_provider_error(capability_id, provider_error)

    async def chunks():
        first_byte = True
        try:
            async for chunk in upstream.aiter_bytes():
                if funded_call_id is not None:
                    extractor.feed(chunk)
                if first_byte:
                    first_byte = False
                    _record_gateway_timing(
                        settings,
                        turn_id,
                        phase="upstream_first_body_byte",
                        elapsed_ms=round(
                            (time.perf_counter() - gateway_started) * 1000
                        ),
                    )
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()
            if funded_call_id is not None:
                try:
                    _settle_openrouter_call(settings, funded_call_id, extractor)
                except Exception as error:
                    logger.error(
                        "openrouter stream settlement failed call=%s error=%s",
                        funded_call_id,
                        type(error).__name__,
                    )
            logger.info(
                "chat provider stream complete call_class=research turn=%s "
                "duration_ms=%.1f",
                _opaque_turn(turn_id),
                (time.perf_counter() - gateway_started) * 1000,
            )

    headers = {
        key: value
        for key, value in upstream.headers.items()
        if key.lower() in {"content-type", "request-id"}
    }
    if payload.get("stream"):
        return StreamingResponse(
            chunks(), status_code=upstream.status_code, headers=headers
        )
    body = await upstream.aread()
    if funded_call_id is not None:
        extractor.inspect_complete_response(body)
    _record_gateway_timing(
        settings,
        turn_id,
        phase="upstream_first_body_byte",
        elapsed_ms=round((time.perf_counter() - gateway_started) * 1000),
    )
    await upstream.aclose()
    await client.aclose()
    if funded_call_id is not None:
        try:
            _settle_openrouter_call(settings, funded_call_id, extractor)
        except Exception as error:
            logger.error(
                "openrouter response settlement failed call=%s error=%s",
                funded_call_id,
                type(error).__name__,
            )
    return Response(body, status_code=upstream.status_code, headers=headers)
