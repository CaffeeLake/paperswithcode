from __future__ import annotations

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.config import Settings, get_settings
from backend.routers import chat as chat_router
from backend.services import chat_mcp_app_proxy
from backend.utils.auth import require_user

PROXY_PATH = "/api/v1/chat/mcp-apps/excalidraw"


def _settings(**overrides) -> Settings:
    values = {
        "environment": "staging",
        "release_id": "test-release",
        "chat_enabled": True,
        "chat_mcp_apps_host_enabled": True,
        "chat_gateway_url": "https://gateway.example.test/api/internal/chat-gateway",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _app(settings: Settings) -> FastAPI:
    app = FastAPI()
    app.include_router(chat_router.router, prefix="/api/v1")
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[require_user] = lambda: {
        "source": "cookie",
        "username": "tester",
        "hf_user_id": "hf-test-sub",
    }
    return app


def _headers() -> dict[str, str]:
    return {
        "Origin": "https://testserver",
        "sec-fetch-site": "same-origin",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "Cookie": "pwc_session=secret",
        "Authorization": "Bearer leaked",
        "Mcp-Session-Id": "sess-1",
    }


def test_proxy_hidden_when_host_flag_is_off():
    with TestClient(_app(_settings(chat_mcp_apps_host_enabled=False))) as client:
        response = client.post(PROXY_PATH, headers=_headers(), content=b"{}")
    assert response.status_code == 404


def test_proxy_hidden_outside_staging():
    with TestClient(_app(_settings(environment="production"))) as client:
        response = client.post(PROXY_PATH, headers=_headers(), content=b"{}")
    assert response.status_code == 404


def test_proxy_rejects_cross_origin(monkeypatch):
    async def fail_forward(_request):
        raise AssertionError("must not reach upstream")

    monkeypatch.setattr(chat_router, "forward_excalidraw_mcp", fail_forward)
    with TestClient(_app(_settings())) as client:
        response = client.post(
            PROXY_PATH,
            headers={"Origin": "https://evil.example", "sec-fetch-site": "cross-site"},
            content=b"{}",
        )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "csrf_rejected"


def test_proxy_allows_same_origin_get_without_origin(monkeypatch):
    async def ok(_request):
        from starlette.responses import Response

        return Response(content=b"ok", status_code=200)

    monkeypatch.setattr(chat_router, "forward_excalidraw_mcp", ok)
    with TestClient(_app(_settings())) as client:
        response = client.get(
            PROXY_PATH,
            headers={
                "sec-fetch-site": "same-origin",
                "Referer": "https://testserver/chat",
                "Accept": "text/event-stream",
            },
        )
    assert response.status_code == 200


def test_proxy_strips_cookies_and_forwards_mcp_headers(monkeypatch):
    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200
        content = b'event: message\ndata: {"ok":true}\n\n'
        headers = httpx.Headers(
            {
                "Content-Type": "text/event-stream",
                "Mcp-Session-Id": "upstream-session",
            }
        )

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def request(self, method, url, headers=None, content=None):
            captured["method"] = method
            captured["url"] = url
            captured["headers"] = headers
            captured["content"] = content
            return FakeResponse()

    monkeypatch.setattr(chat_mcp_app_proxy.httpx, "AsyncClient", FakeClient)
    with TestClient(_app(_settings())) as client:
        response = client.post(
            PROXY_PATH,
            headers=_headers(),
            content=b'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}',
        )
    assert response.status_code == 200
    assert response.content.startswith(b"event: message")
    assert response.headers["mcp-session-id"] == "upstream-session"
    assert captured["url"] == "https://mcp.excalidraw.com/mcp"
    assert captured["headers"]["mcp-session-id"] == "sess-1"
    forwarded = {key.lower() for key in captured["headers"]}
    assert "cookie" not in forwarded
    assert "authorization" not in forwarded
    assert captured["content"].startswith(b'{"jsonrpc"')


def test_proxy_rejects_oversize_bodies(monkeypatch):
    async def fail_exchange(*_args, **_kwargs):
        raise AssertionError("must not reach upstream")

    monkeypatch.setattr(chat_mcp_app_proxy.httpx.AsyncClient, "request", fail_exchange)
    with TestClient(_app(_settings())) as client:
        response = client.post(
            PROXY_PATH,
            headers=_headers(),
            content=b"x" * (256 * 1024 + 1),
        )
    assert response.status_code == 413


def test_proxy_refuses_upstream_redirects(monkeypatch):
    class RedirectResponse:
        status_code = 302
        content = b""
        headers = httpx.Headers({"Location": "https://evil.example/mcp"})

    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs.get("follow_redirects") is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def request(self, *_args, **_kwargs):
            return RedirectResponse()

    monkeypatch.setattr(chat_mcp_app_proxy.httpx, "AsyncClient", FakeClient)
    with TestClient(_app(_settings())) as client:
        response = client.post(PROXY_PATH, headers=_headers(), content=b"{}")
    assert response.status_code == 502
    assert "evil.example" not in response.text


def test_frontend_host_uses_same_origin_proxy_path():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2]
        / "frontend/src/components/chat/mcpAppRegistry.ts"
    ).read_text(encoding="utf-8")
    assert 'EXCALIDRAW_HOST_PATH = "/api/v1/chat/mcp-apps/excalidraw"' in source
    assert "hostMcpUrl()" in source
    assert 'credentials: "include"' in source
    assert "new URL(EXCALIDRAW_ENDPOINT)" not in source
