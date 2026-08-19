"""Same-origin staging proxy for the browser Excalidraw MCP App host.

The official Excalidraw MCP server answers POST, but its OPTIONS preflight
returns 405. A browser on staging.paperswithcode.co therefore cannot talk to
mcp.excalidraw.com directly. This proxy keeps the reviewed endpoint, strips
PwC cookies, and refuses redirects.

The App HTML is fetched once server-side and cached. Historical chats only
need that shell plus persisted `elements`; they should not depend on a live
browser MCP Streamable HTTP session.
"""

from __future__ import annotations

import asyncio
import json
import logging

import httpx
from fastapi import HTTPException, Request, Response

from backend.chat_sandbox_worker.mcp_app_registry import WORKER_MCP_PROVIDERS

logger = logging.getLogger(__name__)

MAX_REQUEST_BYTES = 256 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024
MIN_APP_HTML_BYTES = 1024
APP_HTML_RESOURCE_URI = "ui://excalidraw/mcp-app.html"
APP_HTML_MIME = "text/html;profile=mcp-app"
REQUEST_HEADERS = (
    "accept",
    "content-type",
    "mcp-session-id",
    "mcp-protocol-version",
    "last-event-id",
)
RESPONSE_HEADERS = (
    "content-type",
    "mcp-session-id",
    "mcp-protocol-version",
    "cache-control",
)
_APP_HTML_CACHE: str | None = None
_APP_HTML_LOCK = asyncio.Lock()


def excalidraw_endpoint() -> str:
    for provider in WORKER_MCP_PROVIDERS:
        if provider.id == "excalidraw":
            return provider.endpoint
    raise RuntimeError("Excalidraw MCP provider is not registered")


def _request_headers(request: Request) -> dict[str, str]:
    return {
        name: value for name in REQUEST_HEADERS if (value := request.headers.get(name))
    }


def _response_headers(headers: httpx.Headers) -> dict[str, str]:
    copied: dict[str, str] = {}
    for name in RESPONSE_HEADERS:
        value = headers.get(name)
        if value:
            copied[name] = value
    return copied


def reset_excalidraw_app_html_cache() -> None:
    global _APP_HTML_CACHE
    _APP_HTML_CACHE = None


def mcp_jsonrpc_result(body: bytes) -> dict:
    """Parse a JSON-RPC result from a JSON or SSE MCP HTTP body."""
    text = body.decode("utf-8")
    payload: object | None = None
    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        payload = json.loads(stripped)
    else:
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line.startswith("data:"):
                continue
            payload = json.loads(line[5:].lstrip())
            if isinstance(payload, dict) and (
                "result" in payload or "error" in payload
            ):
                break
    if isinstance(payload, list) and payload:
        payload = payload[0]
    if not isinstance(payload, dict):
        raise ValueError("MCP response was empty")
    if payload.get("error"):
        raise ValueError("MCP error")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise ValueError("MCP result missing")
    return result


def _unavailable() -> HTTPException:
    return HTTPException(status_code=502, detail="Diagram service unavailable")


async def _post_mcp(client: httpx.AsyncClient, payload: dict) -> httpx.Response:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return await client.request(
        "POST",
        excalidraw_endpoint(),
        headers={
            "accept": "application/json, text/event-stream",
            "content-type": "application/json",
            "mcp-protocol-version": "2025-03-26",
        },
        content=body,
    )


def _extract_app_html(result: dict) -> str:
    contents = result.get("contents")
    resource = contents[0] if isinstance(contents, list) and contents else None
    if not isinstance(resource, dict):
        raise ValueError("MCP App resource missing")
    if resource.get("uri") != APP_HTML_RESOURCE_URI:
        raise ValueError("Unapproved App resource")
    text = resource.get("text")
    if resource.get("mimeType") != APP_HTML_MIME or not isinstance(text, str):
        raise ValueError("Incompatible App resource")
    encoded = text.encode("utf-8")
    if not MIN_APP_HTML_BYTES <= len(encoded) <= MAX_RESPONSE_BYTES:
        raise ValueError("App HTML size is invalid")
    lowered = text.lower()
    if "<html" not in lowered and "<!doctype html" not in lowered:
        raise ValueError("App HTML is invalid")
    return text


async def download_excalidraw_app_html() -> str:
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(30.0, connect=10.0),
        follow_redirects=False,
        trust_env=False,
    ) as client:
        initialized = await _post_mcp(
            client,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "pwc-chat-mcp-app-host", "version": "1"},
                },
            },
        )
        if 300 <= initialized.status_code < 400:
            raise httpx.HTTPError("redirect")
        if initialized.status_code >= 400:
            raise httpx.HTTPError("initialize failed")
        mcp_jsonrpc_result(initialized.content)
        await _post_mcp(
            client, {"jsonrpc": "2.0", "method": "notifications/initialized"}
        )
        listed = await _post_mcp(
            client,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "resources/read",
                "params": {"uri": APP_HTML_RESOURCE_URI},
            },
        )
        if 300 <= listed.status_code < 400:
            raise httpx.HTTPError("redirect")
        if listed.status_code >= 400:
            raise httpx.HTTPError("resource read failed")
        if len(listed.content) > MAX_RESPONSE_BYTES:
            raise ValueError("oversize")
        return _extract_app_html(mcp_jsonrpc_result(listed.content))


async def fetch_excalidraw_app_html() -> str:
    global _APP_HTML_CACHE
    if _APP_HTML_CACHE:
        return _APP_HTML_CACHE
    async with _APP_HTML_LOCK:
        if _APP_HTML_CACHE:
            return _APP_HTML_CACHE
        try:
            html = await download_excalidraw_app_html()
        except (
            httpx.HTTPError,
            ValueError,
            json.JSONDecodeError,
            UnicodeDecodeError,
        ) as exc:
            logger.warning(
                "excalidraw mcp html fetch failed class=%s", type(exc).__name__
            )
            raise _unavailable() from None
        _APP_HTML_CACHE = html
        return html


async def forward_excalidraw_mcp(request: Request) -> Response:
    body = await request.body()
    if len(body) > MAX_REQUEST_BYTES:
        raise HTTPException(status_code=413, detail="Payload too large")
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            upstream = await client.request(
                request.method,
                excalidraw_endpoint(),
                headers=_request_headers(request),
                content=body if request.method != "GET" else None,
            )
    except httpx.HTTPError:
        logger.warning("excalidraw mcp host proxy failed class=HTTPError")
        raise HTTPException(
            status_code=502, detail="Diagram service unavailable"
        ) from None
    if 300 <= upstream.status_code < 400:
        logger.warning("excalidraw mcp host proxy failed class=redirect")
        raise HTTPException(status_code=502, detail="Diagram service unavailable")
    if len(upstream.content) > MAX_RESPONSE_BYTES:
        logger.warning("excalidraw mcp host proxy failed class=oversize")
        raise HTTPException(status_code=502, detail="Diagram service unavailable")
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=_response_headers(upstream.headers),
        media_type=upstream.headers.get("content-type"),
    )
