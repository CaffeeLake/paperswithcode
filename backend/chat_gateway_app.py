"""Private, separately started gateway for sandbox model/catalog/store traffic."""

from __future__ import annotations

import json
import hashlib
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
from backend.database.connection import db_manager, get_database_session
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
from backend.utils.exceptions import PaperNotFoundError

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
logger = logging.getLogger(__name__)
MAX_PROVIDER_OUTPUT_TOKENS = 32_000
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


def _user_provider_token(row, settings: Settings) -> str:
    token = ChatCapabilityService.provider_token(row, row.owner_hash, settings)
    if not token:
        raise HTTPException(status_code=402, detail="Connect Hugging Face billing")
    return token


def _provider_headers(provider_token: str, request: Request) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {provider_token}",
        "Content-Type": "application/json",
        "Accept": request.headers.get("accept", "application/json"),
        "Anthropic-Version": request.headers.get("anthropic-version", "2023-06-01"),
    }
    if request.headers.get("anthropic-beta"):
        headers["Anthropic-Beta"] = request.headers["anthropic-beta"]
    return headers


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
    capability = _scope(token, "catalog", x_pwc_session, x_pwc_turn, db)
    try:
        ChatCapabilityService(db).meter_catalog(
            capability,
            body.operation,
            maximum_searches=settings.chat_max_direct_search_calls,
        )
        db.commit()
    except CapabilityError:
        db.rollback()
        raise HTTPException(
            status_code=429, detail="Catalog execution limit reached"
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
    provider_token = _user_provider_token(row, settings)
    try:
        ChatCapabilityService(db).meter_provider(
            row,
            request_tokens=max(1, len(raw) // 4) + maximum_tokens,
            maximum_requests=16,
            maximum_tokens=MAX_PROVIDER_TURN_TOKENS,
        )
        db.commit()
    except CapabilityError:
        db.rollback()
        raise HTTPException(
            status_code=429, detail="Model execution limit reached"
        ) from None
    _record_gateway_timing(settings, turn_id, received_at=received_at)

    client = httpx.AsyncClient(timeout=180, follow_redirects=False)
    upstream_headers = _provider_headers(provider_token, request)
    upstream = await client.send(
        client.build_request(
            "POST",
            "https://router.huggingface.co/v1/messages",
            content=raw,
            headers=upstream_headers,
        ),
        stream=True,
    )
    _record_gateway_timing(
        settings,
        turn_id,
        phase="upstream_response_headers",
        elapsed_ms=round((time.perf_counter() - gateway_started) * 1000),
    )

    async def chunks():
        first_byte = True
        try:
            async for chunk in upstream.aiter_bytes():
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
    _record_gateway_timing(
        settings,
        turn_id,
        phase="upstream_first_body_byte",
        elapsed_ms=round((time.perf_counter() - gateway_started) * 1000),
    )
    await upstream.aclose()
    await client.aclose()
    return Response(body, status_code=upstream.status_code, headers=headers)
