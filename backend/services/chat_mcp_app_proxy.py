"""Same-origin staging proxy for the browser Excalidraw MCP App host.

The official Excalidraw MCP server answers POST, but its OPTIONS preflight
returns 405. A browser on staging.paperswithcode.co therefore cannot talk to
mcp.excalidraw.com directly. This proxy keeps the reviewed endpoint, strips
PwC cookies, and refuses redirects.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import HTTPException, Request, Response

from backend.chat_sandbox_worker.mcp_app_registry import WORKER_MCP_PROVIDERS

logger = logging.getLogger(__name__)

MAX_REQUEST_BYTES = 256 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024
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
