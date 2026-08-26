import hashlib
import asyncio
import uuid

import httpx
import pytest

from backend.services.chat_external_pi_shadow import (
    ExternalPiShadowClient,
    ExternalPiShadowRequest,
    ExternalPiWorkerControlClient,
    ExternalPiWorkerStatus,
)


def _request():
    agent_session_id = uuid.UUID("20000000-0000-4000-8000-000000000001")
    return ExternalPiShadowRequest(
        request_id="shadow-1",
        chat_session_id=uuid.UUID("10000000-0000-4000-8000-000000000001"),
        agent_session_id=agent_session_id,
        current_leaf_id="entry-1",
        prompt="trusted system prompt",
        tool_names=("read", "bash", "pwc__search"),
        transcript_entries=(
            {"type": "session", "id": str(agent_session_id), "version": 3},
            {"type": "message", "id": "entry-1", "parentId": None},
        ),
    )


def test_external_pi_shadow_uses_authenticated_content_free_projection():
    request = _request()

    async def handler(http_request):
        assert http_request.url == httpx.URL("http://worker.internal/v1/shadow")
        assert http_request.headers["Authorization"] == "Bearer secret"
        payload = __import__("json").loads(http_request.content)
        assert "prompt" not in payload
        assert "tool_names" not in payload
        assert payload["expected_prompt_sha256"] == request.prompt_sha256
        return httpx.Response(
            200,
            json={
                "type": "shadow_projection",
                "protocol_version": 1,
                "request_id": "shadow-1",
                "chat_session_id": str(request.chat_session_id),
                "agent_session_id": str(request.agent_session_id),
                "current_leaf_id": "entry-1",
                "entry_count": 2,
                "prompt_sha256": hashlib.sha256(request.prompt.encode()).hexdigest(),
                "tool_names_sha256": request.tool_names_sha256,
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await ExternalPiShadowClient(
                base_url="http://worker.internal",
                token="secret",
                http=http,
            ).compare(request)

    projection = asyncio.run(run())

    assert projection.compatible_with(request)
    assert "trusted system prompt" not in projection.model_dump_json()


def test_external_pi_shadow_rejects_unexpected_worker_response_fields():
    async def handler(_request):
        return httpx.Response(200, json={"type": "shadow_projection", "prompt": "leak"})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await ExternalPiShadowClient(
                base_url="http://worker.internal",
                token="secret",
                http=http,
            ).compare(_request())

    with pytest.raises(RuntimeError, match="invalid response"):
        asyncio.run(run())


def test_external_pi_shadow_bounds_utf8_prompt_bytes_and_hides_client_token():
    with pytest.raises(ValueError, match="prompt is too large"):
        ExternalPiShadowRequest(
            **{
                **_request().model_dump(),
                "prompt": "🙂" * (512 * 1024 + 1),
            }
        )

    client = ExternalPiShadowClient(
        base_url="http://worker.internal",
        token="secret-token",
        http=httpx.AsyncClient(),
    )
    try:
        assert "secret-token" not in repr(client)
    finally:
        asyncio.run(client.http.aclose())


def test_external_pi_worker_status_and_drain_are_authenticated_and_typed():
    requests = []

    async def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "protocol": "external-pi-v1",
                "worker_id": "worker-1",
                "instance_id": "10000000-0000-4000-8000-000000000001",
                "release_id": "release-a",
                "state": "draining" if request.method == "POST" else "ready",
                "active_sessions": 2,
                "maximum_sessions": 8,
                "worker_generation": None if request.url.path == "/v1/status" else 3,
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = ExternalPiWorkerControlClient(
                base_url="http://worker.internal",
                token="secret",
                http=http,
            )
            return (
                await client.status(),
                await client.bind_claim(3),
                await client.begin_drain(3),
            )

    ready, claimed, draining = asyncio.run(run())

    assert isinstance(ready, ExternalPiWorkerStatus)
    assert ready.state == "ready"
    assert ready.worker_generation is None
    assert claimed.worker_generation == 3
    assert draining.state == "draining"
    assert [request.url.path for request in requests] == [
        "/v1/status",
        "/v1/claim",
        "/v1/drain",
    ]
    assert all(
        request.headers["Authorization"] == "Bearer secret" for request in requests
    )
    assert requests[-1].headers["X-PWC-Worker-Generation"] == "3"


def test_external_pi_worker_status_rejects_unexpected_or_oversized_capacity():
    async def handler(_request):
        return httpx.Response(
            200,
            json={
                "protocol": "external-pi-v1",
                "worker_id": "worker-1",
                "instance_id": "10000000-0000-4000-8000-000000000001",
                "release_id": "release-a",
                "state": "ready",
                "active_sessions": 0,
                "maximum_sessions": 33,
                "worker_generation": None,
                "host_path": "/workspace",
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await ExternalPiWorkerControlClient(
                base_url="http://worker.internal",
                token="secret",
                http=http,
            ).status()

    with pytest.raises(RuntimeError, match="invalid response"):
        asyncio.run(run())
