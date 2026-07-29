from __future__ import annotations

import asyncio
import importlib
import json
import os
import sys
import uuid
from datetime import UTC, date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from claude_agent_sdk import StreamEvent
from fastapi import HTTPException

from backend.chat_gateway_app import (
    MAX_PROVIDER_OUTPUT_TOKENS,
    MAX_PROVIDER_TURN_TOKENS,
    CatalogRequest,
    _output_tokens_allowed,
    catalog,
)
from backend.chat_sandbox_worker import agent, publish_image, supervisor
from backend.chat_sandbox_worker.contract import (
    BASE_IMAGE,
    IMAGE_PUBLISH_NAME,
    MODAL_APP_NAME,
    MODAL_IMAGE_ID,
)
from backend.chat_sandbox_worker.prompt import render, sha256
from backend.chat_sandbox_worker.protocol import (
    ProtocolError,
    WorkerEventValidator,
    decode_frame,
    encode_frame,
)
from backend.chat_sandbox_worker.render_task_catalog import (
    render as render_task_catalog,
)
from backend.chat_sandbox_worker.sdk_adapter import SDKEventAdapter as WorkerSDKAdapter
from backend.chat_sandbox_worker.tool_policy import ToolBudget, bound_tool_output
from backend.models.chat import DISPLAY_BLOCKS_ADAPTER, sse_event
from backend.models.database import ChatTurnCapability
from backend.scripts.qualify_chat_sandbox import QualificationRunner, Sample, summarize
from backend.services.chat_capability_service import (
    CapabilityError,
    ChatCapabilityService,
    _digest,
)
from backend.services.chat_gateway_service import ChatGatewayService
from backend.services.chat_sandbox_service import (
    RunningWorker,
    SandboxSessionManager,
    WorkerClaim,
    WorkspaceSnapshotProvider,
    create_isolated_sandbox,
    resolve_modal_image,
)
from backend.config import Settings
from backend.services.chat_session_store_gateway import (
    ChatSessionStoreGateway,
    SessionStoreCommand,
    SessionStoreGatewayError,
)
from backend.services.chat_web_fetch_service import (
    ChatWebFetchError,
    _arxiv_identifier,
    _public_addresses,
    _validate_body_size,
    _validate_origin_metadata,
    authorize_catalog_url,
    canonical_fetch_url,
)
from backend.utils.exceptions import PaperNotFoundError
from deploy.release import build_manifest


def _import_broker(monkeypatch):
    read_fd, write_fd = os.pipe()
    try:
        os.write(
            write_fd,
            json.dumps(
                {
                    "capability": "test-capability",
                    "gateway_url": "https://gateway.example.test/api/internal/chat-gateway",
                    "session_id": str(uuid.uuid4()),
                    "turn_id": str(uuid.uuid4()),
                    "proxy_token": "test-proxy-token",
                }
            ).encode(),
        )
    finally:
        os.close(write_fd)
    monkeypatch.setenv("PWC_BROKER_CONFIG_FD", str(read_fd))
    sys.modules.pop("backend.chat_sandbox_worker.broker", None)
    return importlib.import_module("backend.chat_sandbox_worker.broker")


def test_broker_accepts_claude_messages_beta_query(monkeypatch):
    broker = _import_broker(monkeypatch)

    class Request:
        path = "/v1/messages?beta=true"
        headers = {"Content-Length": "2", "Content-Type": "application/json"}
        rfile = BytesIO(b"{}")
        forwarded: list[tuple[str, bytes]] = []
        error: int | None = None

        def _forward(self, path, body, **_kwargs):
            self.forwarded.append((path, body))

        def send_error(self, status):
            self.error = status

    request = Request()
    broker.Handler.do_POST(request)

    assert request.forwarded == [("v1/messages", b"{}")]
    assert request.error is None


def test_broker_capability_rotation_rejects_stale_and_cross_turn_clear(monkeypatch):
    broker = _import_broker(monkeypatch)
    state = broker.BrokerState(
        {"capability": "old", "session_id": "session", "turn_id": "turn-1"}
    )

    assert state.current()["capability"] == "old"
    with pytest.raises(RuntimeError, match="already installed"):
        state.install(
            {"capability": "new", "session_id": "session", "turn_id": "turn-2"}
        )
    with pytest.raises(RuntimeError, match="correlation"):
        state.clear(session_id="session", turn_id="turn-2")

    state.clear(session_id="session", turn_id="turn-1")
    with pytest.raises(PermissionError):
        state.current()
    state.install({"capability": "new", "session_id": "session", "turn_id": "turn-2"})
    assert state.current()["capability"] == "new"


def test_persistent_agent_reuses_client_and_applies_model_changes(monkeypatch):
    calls: list[tuple] = []
    monkeypatch.setattr(
        agent,
        "GUIDE",
        Path(agent.__file__).with_name("PWC_CLI_SKILL.md"),
    )

    class Client:
        def __init__(self, options):
            calls.append(("init", options.model, options.resume))

        async def connect(self, prompt):
            calls.append(("connect", prompt))

        async def query(self, prompt):
            calls.append(("query", prompt))

        def receive_response(self):
            return object()

        async def set_model(self, model):
            calls.append(("model", model))

        async def disconnect(self):
            calls.append(("disconnect",))

        async def interrupt(self):
            calls.append(("interrupt",))

    async def adapted(_messages, *, request_id, **_kwargs):
        yield {"v": 1, "type": "done", "request_id": request_id}

    monkeypatch.setattr(agent, "ClaudeSDKClient", Client)
    monkeypatch.setattr(agent, "_adapt_messages", adapted)
    settings = agent.WorkerSettings.from_environment()
    worker = agent.PersistentAgent(settings)

    async def run():
        first = [
            event
            async for event in worker.stream(
                {
                    "type": "run_turn",
                    "request_id": "request-1",
                    "prompt": "first",
                    "model": "model-a",
                    "resume": "session-a",
                }
            )
        ]
        second = [
            event
            async for event in worker.stream(
                {
                    "type": "run_turn",
                    "request_id": "request-2",
                    "prompt": "second",
                    "model": "model-b",
                    "resume": "session-a",
                }
            )
        ]
        await worker.close()
        return first, second

    first, second = asyncio.run(run())
    assert [event["type"] for event in first] == ["workspace_ready", "done"]
    assert [event["type"] for event in second] == ["workspace_ready", "done"]
    assert [call[0] for call in calls].count("init") == 1
    assert ("model", "model-b") in calls
    assert calls.count(("connect", None)) == 1
    assert calls[-1] == ("disconnect",)


def test_persistent_agent_accepts_resume_hint_before_sdk_session(monkeypatch):
    monkeypatch.setattr(
        agent,
        "GUIDE",
        Path(agent.__file__).with_name("PWC_CLI_SKILL.md"),
    )

    class Client:
        def __init__(self, _options):
            pass

        async def connect(self, prompt):
            pass

        async def disconnect(self):
            pass

    monkeypatch.setattr(agent, "ClaudeSDKClient", Client)
    worker = agent.PersistentAgent(agent.WorkerSettings.from_environment())

    async def run():
        await worker.connect(model="model-a", resume="session-a")
        await worker.connect(model="model-a", resume="session-b")
        await worker.close()

    asyncio.run(run())


def test_persistent_agent_keeps_sdk_session_authoritative():
    worker = agent.PersistentAgent(agent.WorkerSettings.from_environment())
    worker.client = SimpleNamespace()
    worker.model = "model-a"
    worker._record_session_id("session-a")

    asyncio.run(worker.connect(model="model-a", resume="session-a"))
    with pytest.raises(RuntimeError, match="Resume changed"):
        asyncio.run(worker.connect(model="model-a", resume="session-b"))
    assert worker.sdk_session_id == "session-a"


@pytest.mark.parametrize(
    ("path", "operation"),
    [
        ("/api/v1/areas/?page_size=500", "area_list"),
        ("/api/v1/areas/with-tasks/", "area_tasks"),
        ("/api/v1/tasks/?page_size=10", "task_list"),
        ("/api/v1/methods/?page_size=10", "method_list"),
        ("/api/v1/conferences/", "conference_list"),
    ],
)
def test_broker_routes_taxonomy_cli_reads_to_catalog(monkeypatch, path, operation):
    broker = _import_broker(monkeypatch)

    class Response:
        status = 200

        def read(self, _size):
            return b'{"result":{"count":0,"results":[]}}'

    class Connection:
        requests: list[tuple[str, str, bytes]] = []

        def request(self, method, request_path, body, headers):
            del headers
            self.requests.append((method, request_path, body))

        def getresponse(self):
            return Response()

        def close(self):
            return

    monkeypatch.setattr(broker, "_connection", Connection)

    class Request:
        wfile = BytesIO()
        status = None

        def __init__(self):
            self.path = path

        def _connection(self):
            return Connection()

        def send_response(self, status):
            self.status = status

        def send_header(self, _name, _value):
            return

        def end_headers(self):
            return

        def send_error(self, status):
            self.status = status

    request = Request()
    broker.Handler.do_GET(request)

    assert request.status == 200
    payload = json.loads(Connection.requests[-1][2])
    assert payload["operation"] == operation


def test_proxy_routes_only_claude_model_posts_to_gateway(monkeypatch):
    broker = _import_broker(monkeypatch)

    class Response:
        status = 200

        def getheader(self, name):
            return "application/json" if name == "Content-Type" else None

        def read(self, _size):
            return b""

    class Connection:
        requests: list[tuple[str, str, bytes]] = []

        def request(self, method, path, body, headers):
            del headers
            self.requests.append((method, path, body))

        def getresponse(self):
            return Response()

        def close(self):
            return

    monkeypatch.setattr(broker, "_connection", Connection)

    class Request:
        path = "/v1/messages?beta=true"
        headers = {
            "Host": "api.anthropic.com",
            "Content-Length": "2",
            "Content-Type": "application/json",
        }
        rfile = BytesIO(b"{}")
        wfile = BytesIO()
        server = type("Server", (), {"target_host": "api.anthropic.com"})()
        error: int | None = None

        def send_response(self, status):
            assert status == 200

        def send_header(self, _name, _value):
            return

        def end_headers(self):
            return

        def send_error(self, status):
            self.error = status

    request = Request()
    broker.OriginHandler.do_POST(request)

    assert Connection.requests == [
        (
            "POST",
            "/api/internal/chat-gateway/v1/messages",
            b"{}",
        )
    ]
    assert request.error is None

    request.path = "/v1/complete"
    broker.OriginHandler.do_POST(request)
    assert request.error == 403


def test_supervisor_launch_read_does_not_consume_worker_frame():
    read_fd, write_fd = os.pipe()
    try:
        os.write(write_fd, b"private-launch\nworker-frame\n")
        assert supervisor._readline_unbuffered(read_fd, 64) == b"private-launch\n"
        assert os.read(read_fd, 64) == b"worker-frame\n"
    finally:
        os.close(read_fd)
        os.close(write_fd)


def test_gateway_accepts_claude_output_token_limit_and_rejects_larger():
    assert MAX_PROVIDER_OUTPUT_TOKENS == 32_000
    assert MAX_PROVIDER_TURN_TOKENS >= 8 * MAX_PROVIDER_OUTPUT_TOKENS
    assert _output_tokens_allowed(32_000)
    assert not _output_tokens_allowed(32_001)


def test_gateway_catalog_returns_not_found_for_unknown_task(monkeypatch):
    class DB:
        def commit(self):
            pass

    monkeypatch.setattr(
        "backend.chat_gateway_app._scope", lambda *_args, **_kwargs: object()
    )
    monkeypatch.setattr(
        ChatCapabilityService, "meter_catalog", lambda *_args, **_kwargs: None
    )

    def missing_task(*_args, **_kwargs):
        raise PaperNotFoundError(
            "Task with ID, slug, or name 'speech recognition' not found"
        )

    monkeypatch.setattr(ChatGatewayService, "catalog", missing_task)

    with pytest.raises(HTTPException) as exc_info:
        catalog(
            CatalogRequest(
                operation="benchmark_trending",
                arguments={"task": "speech recognition"},
            ),
            authorization="Bearer test",
            x_pwc_session=str(uuid.uuid4()),
            x_pwc_turn=str(uuid.uuid4()),
            db=DB(),
            settings=SimpleNamespace(chat_max_direct_search_calls=4),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == (
        "Task with ID, slug, or name 'speech recognition' not found"
    )


def test_gateway_paper_read_uses_bounded_diskless_reader(monkeypatch):
    calls = []

    def read(paper, **options):
        calls.append((paper, options))
        return "# EoMT", True

    monkeypatch.setattr(
        "backend.services.chat_gateway_service.read_paper_markdown_bounded", read
    )
    settings = SimpleNamespace(
        paper_markdown_hf_bucket_id="papers",
        hf_token="token",
    )

    result = ChatGatewayService(object(), settings).catalog(
        "paper_read", {"paper": "2503.19108"}
    )

    assert result == {"markdown": "# EoMT", "truncated": True}
    assert calls == [
        (
            "2503.19108",
            {"bucket_id": "papers", "token": "token", "max_bytes": 256 * 1024},
        )
    ]


def test_gateway_method_list_uses_bounded_service_arguments(monkeypatch):
    calls = []

    class Service:
        def __init__(self, db):
            assert db == "db"

        def get_methods(self, **options):
            calls.append(options)
            return {"count": 0, "results": []}

    monkeypatch.setattr("backend.services.chat_gateway_service.MethodService", Service)

    result = ChatGatewayService("db", SimpleNamespace()).catalog(
        "method_list",
        {
            "page": "2",
            "page_size": "500",
            "area_id": "3",
            "introduced_year": "2020",
            "ordering": "-paper_count",
        },
    )

    assert result == {"count": 0, "results": []}
    assert calls == [
        {
            "page": 2,
            "page_size": 500,
            "area_id": 3,
            "introduced_year": 2020,
            "order_by": "paper_count",
            "order_dir": "desc",
        }
    ]


def test_gateway_paper_read_returns_controlled_upstream_error(monkeypatch):
    class DB:
        def commit(self):
            pass

    monkeypatch.setattr(
        "backend.chat_gateway_app._scope", lambda *_args, **_kwargs: object()
    )
    monkeypatch.setattr(
        ChatCapabilityService, "meter_catalog", lambda *_args, **_kwargs: None
    )

    def failed(*_args, **_kwargs):
        raise OSError("read-only cache failure")

    monkeypatch.setattr(ChatGatewayService, "catalog", failed)
    with pytest.raises(HTTPException) as exc_info:
        catalog(
            CatalogRequest(operation="paper_read", arguments={"paper": "2503.19108"}),
            authorization="Bearer test",
            x_pwc_session=str(uuid.uuid4()),
            x_pwc_turn=str(uuid.uuid4()),
            db=DB(),
            settings=SimpleNamespace(chat_max_direct_search_calls=4),
        )
    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "Paper Markdown could not be read"


def test_worker_adapter_assembles_streamed_tool_arguments():
    adapter = WorkerSDKAdapter(show_reasoning=True)
    messages = [
        StreamEvent(
            uuid="1",
            session_id="session",
            event={
                "type": "content_block_start",
                "index": 0,
                "content_block": {
                    "type": "tool_use",
                    "id": "tool-1",
                    "name": "Bash",
                    "input": {},
                },
            },
        ),
        StreamEvent(
            uuid="2",
            session_id="session",
            event={
                "type": "content_block_delta",
                "index": 0,
                "delta": {
                    "type": "input_json_delta",
                    "partial_json": '{"command":"pwc search on-device"}',
                },
            },
        ),
        StreamEvent(
            uuid="3",
            session_id="session",
            event={"type": "content_block_stop", "index": 0},
        ),
    ]

    events = [event for message in messages for event in adapter.feed(message)]

    assert events == [
        {
            "type": "tool_call",
            "id": "tool-1",
            "name": "Bash",
            "args": {"command": "pwc search on-device"},
        }
    ]


@pytest.mark.parametrize("name", ["Bash", "Read", "Grep", "WebFetch"])
def test_generic_tool_projection_and_event_are_v2_raw_text(name):
    block = DISPLAY_BLOCKS_ADAPTER.validate_python(
        [
            {
                "kind": "tool",
                "schema_version": 2,
                "id": "tool-1",
                "name": name,
                "args": {"command": "pwc search vision"},
                "status": "success",
                "took_ms": 25,
                "content": [
                    {"type": "text", "text": "id\ttitle\n1\tPaper", "truncated": False}
                ],
                "metadata": {"exit_code": 0, "output_truncated": False},
            }
        ]
    )[0]
    assert block.name == name
    assert b'"status":"success"' in sse_event(
        "tool_result",
        id="tool-1",
        status="success",
        took_ms=25,
        content=[{"type": "text", "text": "ok", "truncated": False}],
        metadata={"exit_code": 0, "output_truncated": False},
    )


def test_tool_budget_counts_parallel_calls_and_fifth_search_is_denied():
    budget = ToolBudget(
        maximum_calls=12,
        maximum_direct_searches=4,
        maximum_result_bytes=1024,
        maximum_turn_output_bytes=4096,
    )
    for index in range(4):
        assert budget.authorize(
            f"tool-{index}", "Bash", {"command": f"pwc search query-{index}"}
        ).allowed
    denied = budget.authorize("tool-5", "Bash", {"command": "pwc search fifth"})
    assert not denied.allowed
    assert budget.calls == 4


def test_web_fetch_is_limited_to_observed_public_urls():
    budget = ToolBudget(
        maximum_calls=12,
        maximum_direct_searches=4,
        maximum_result_bytes=1024,
        maximum_turn_output_bytes=4096,
    )
    budget.observe_urls(
        "Read https://arxiv.org/abs/2607.12345 and http://127.0.0.1/private"
    )

    assert budget.authorize(
        "fetch", "WebFetch", {"url": "https://arxiv.org/abs/2607.12345"}
    ).allowed
    assert not budget.authorize(
        "unknown", "WebFetch", {"url": "https://example.com/unseen"}
    ).allowed
    assert not budget.authorize(
        "private", "WebFetch", {"url": "http://127.0.0.1/private"}
    ).allowed
    assert not budget.authorize(
        "http", "WebFetch", {"url": "http://arxiv.org/abs/2607.12345"}
    ).allowed


def test_tool_results_make_returned_urls_fetchable():
    budget = ToolBudget(
        maximum_calls=12,
        maximum_direct_searches=4,
        maximum_result_bytes=1024,
        maximum_turn_output_bytes=4096,
    )
    assert budget.authorize("info", "Bash", {"command": "pwc paper info 1"}).allowed
    budget.result(
        "info",
        "Project page: https://example.com/project",
        status="success",
        exit_code=0,
    )

    assert budget.authorize(
        "fetch", "WebFetch", {"url": "https://example.com/project"}
    ).allowed


def test_web_fetch_results_do_not_authorize_discovered_links():
    budget = ToolBudget(
        maximum_calls=12,
        maximum_direct_searches=4,
        maximum_result_bytes=1024,
        maximum_turn_output_bytes=4096,
    )
    source = "https://arxiv.org/abs/2607.12345"
    budget.observe_urls(source)
    assert budget.authorize("fetch", "WebFetch", {"url": source}).allowed
    budget.result(
        "fetch",
        "Discovered https://example.com/not-catalog-authorized",
        status="success",
    )
    assert not budget.authorize(
        "follow",
        "WebFetch",
        {"url": "https://example.com/not-catalog-authorized"},
    ).allowed


def test_catalog_web_fetch_url_normalization_and_arxiv_matching():
    assert (
        canonical_fetch_url("https://ARXIV.org:443/abs/2503.19108/#section")
        == "https://arxiv.org/abs/2503.19108"
    )
    assert _arxiv_identifier("https://arxiv.org/pdf/2503.19108v2.pdf") == "2503.19108"
    assert _arxiv_identifier("https://arxiv.org/abs/2503.19108?download=1") is None
    for value in (
        "http://arxiv.org/abs/2503.19108",
        "https://user@arxiv.org/abs/2503.19108",
        "https://arxiv.org:444/abs/2503.19108",
    ):
        with pytest.raises(ChatWebFetchError):
            canonical_fetch_url(value)


def test_catalog_web_fetch_requires_existing_arxiv_or_exact_attached_url():
    class Result:
        def __init__(self, found):
            self.found = found

        def scalar_one(self):
            return self.found

    class DB:
        def __init__(self, *results):
            self.results = iter(results)

        def execute(self, _statement):
            return Result(next(self.results))

    assert (
        authorize_catalog_url(DB(True), "https://arxiv.org/abs/2503.19108")
        == "https://arxiv.org/abs/2503.19108"
    )
    assert (
        authorize_catalog_url(DB(True), "https://github.com/org/repo")
        == "https://github.com/org/repo"
    )
    with pytest.raises(ChatWebFetchError, match="not attached"):
        authorize_catalog_url(DB(False, False), "https://github.com/org/repo/issues")


def test_catalog_web_fetch_rejects_private_dns_redirects_and_unsupported_content(
    monkeypatch,
):
    class Loop:
        async def getaddrinfo(self, *_args, **_kwargs):
            return [(2, 1, 6, "", ("127.0.0.1", 443))]

    monkeypatch.setattr(asyncio, "get_running_loop", lambda: Loop())
    with pytest.raises(ChatWebFetchError, match="private network"):
        asyncio.run(_public_addresses("example.com"))
    with pytest.raises(ChatWebFetchError, match="redirect"):
        _validate_origin_metadata(302, "text/html")
    with pytest.raises(ChatWebFetchError, match="Unsupported"):
        _validate_origin_metadata(200, "application/octet-stream")
    with pytest.raises(ChatWebFetchError, match="too large"):
        _validate_body_size(b"x" * (10 * 1024 * 1024 + 1))
    assert _validate_origin_metadata(200, "text/html; charset=utf-8") == "text/html"


def test_worker_keeps_native_web_fetch_and_uses_supported_proxy_settings():
    source = Path(agent.__file__).read_text()
    assert 'tools=["Bash", "Read", "Grep", "WebFetch"]' in source
    assert '"skipWebFetchPreflight": True' in source
    assert '"HTTPS_PROXY": "http://127.0.0.1:8766"' in source
    assert '"NO_PROXY": "127.0.0.1,localhost"' in source


def test_system_prompt_prevents_unsupported_method_search_flags():
    prompt = render()

    assert "use `--page-size`, never `--limit`" in prompt
    assert "This subcommand has no `--search` or `--limit` flag" in prompt
    assert "pwc method list --page-size 500 | rg -i -- 'QUERY'" in prompt


def test_tool_output_is_utf8_bounded_and_terminal_controls_are_inert():
    text, truncated = bound_tool_output(b"\x1b[31m" + "é".encode() * 100, 64)
    assert truncated
    assert "\x1b" not in text
    assert len(text.encode()) <= 64


def test_tool_policy_rejects_traversal_and_enforces_aggregate_bytes(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    guide = tmp_path / "PWC_CLI_SKILL.md"
    guide.write_text("guide")
    budget = ToolBudget(
        maximum_calls=12,
        maximum_direct_searches=4,
        maximum_result_bytes=24,
        maximum_turn_output_bytes=48,
    )
    denied = budget.authorize(
        "outside",
        "Read",
        {"file_path": str(tmp_path / "secret")},
        workspace=workspace,
        guide=guide,
    )
    assert not denied.allowed
    for index in range(3):
        tool_id = f"tool-{index}"
        assert budget.authorize(
            tool_id,
            "Bash",
            {"command": "printf data"},
            workspace=workspace,
            guide=guide,
        ).allowed
        result = budget.result(tool_id, "x" * 100, status="success")
        assert len(result["content"][0]["text"].encode()) <= 24
    assert budget.output_bytes == 48


def test_worker_protocol_accepts_complete_turn_after_one_terminal():
    frame = {"v": 1, "type": "run_turn", "request_id": "r"}
    assert decode_frame(encode_frame(frame)) == frame
    validator = WorkerEventValidator()
    validator.accept({"type": "workspace_ready"})
    validator.accept({"type": "tool_call", "id": "t"})
    validator.accept({"type": "tool_result", "id": "t"})
    validator.accept({"type": "done"})
    with pytest.raises(ProtocolError, match="followed a terminal"):
        validator.accept({"type": "workspace_ready"})
    validator.accept({"type": "worker_done", "status": "complete"})


def test_worker_protocol_rejects_invalid_result_and_terminal_sequences():
    validator = WorkerEventValidator()
    with pytest.raises(ProtocolError, match="Uncorrelated"):
        validator.accept({"type": "tool_result", "id": "missing"})
    validator.accept({"type": "tool_call", "id": "t"})
    validator.accept({"type": "tool_result", "id": "t"})
    with pytest.raises(ProtocolError):
        validator.accept({"type": "tool_result", "id": "t"})
    validator.accept({"type": "done"})
    with pytest.raises(ProtocolError, match="followed a terminal"):
        validator.accept({"type": "answer_delta", "text": "late"})
    with pytest.raises(ProtocolError, match="Duplicate terminal"):
        validator.accept({"type": "error"})


def test_worker_protocol_requires_terminal_before_successful_completion():
    validator = WorkerEventValidator()

    with pytest.raises(ProtocolError, match="without a semantic terminal"):
        validator.accept({"type": "worker_done", "status": "complete"})
    with pytest.raises(ProtocolError, match="Invalid worker completion status"):
        validator.accept({"type": "worker_done", "status": "unknown"})


def test_worker_protocol_allows_terminal_less_correlated_cancellation():
    validator = WorkerEventValidator()
    with pytest.raises(ProtocolError, match="without a correlated cancellation"):
        validator.accept({"type": "worker_done", "status": "stopped"})

    validator.accept(
        {"type": "worker_done", "status": "stopped"},
        allow_terminal_less_stop=True,
    )

    with pytest.raises(ProtocolError, match="followed worker completion"):
        validator.accept({"type": "worker_done", "status": "stopped"})
    with pytest.raises(ProtocolError, match="followed worker completion"):
        validator.accept({"type": "done"})


def test_prompt_and_manifest_share_eight_round_contract():
    prompt = render(current_date=date(2026, 7, 28))
    assert "The current UTC date is 2026-07-28." in prompt
    assert "Judge publication recency relative to this date." in prompt
    assert "at most 8 tool-use round trips" in prompt
    assert "secure, disposable sandbox" in prompt
    assert "anonymous, read-only `pwc` CLI" in prompt
    assert "already installed" in prompt
    assert "## Available research areas and representative tasks" in prompt
    assert "### Audio" in prompt
    assert "### Vision" in prompt
    assert prompt.index("## Available research areas") < prompt.index("# pwc CLI skill")
    assert "# pwc CLI skill" in prompt
    assert "name: pwc-cli" in prompt
    manifest = build_manifest("a" * 40, "staging")
    assert manifest["chat_runtime"]["system_prompt_sha256"] == sha256()
    assert manifest["chat_runtime"]["new_chat_modal_percentage"] == 100
    production = build_manifest("b" * 40, "production")
    assert production["chat_runtime"]["enabled"] is False
    assert json.dumps(production["chat_runtime"]).count("pwc-chat") == 0
    assert IMAGE_PUBLISH_NAME == "pwc-chat-v1"
    assert MODAL_APP_NAME == "pwc-chat-sandbox-v1"
    assert BASE_IMAGE.startswith("python:3.12-slim-bookworm@sha256:")
    assert MODAL_IMAGE_ID == "im-E7Yx2TClEwkobCxyyUKmsN"


def test_task_catalog_is_bounded_and_ranked():
    payload = {
        "results": [
            {
                "name": "Vision",
                "tasks": [
                    {
                        "name": "Popular",
                        "slug": "popular",
                        "paper_count": 999,
                    },
                    {"name": "Detection", "slug": "detection", "paper_count": 20},
                    {
                        "name": "Classification",
                        "slug": "classification",
                        "paper_count": 30,
                    },
                    {"name": "Segmentation", "slug": "segmentation", "paper_count": 10},
                ],
            },
            {
                "name": "Audio",
                "tasks": [
                    {"name": "Speech", "slug": "speech", "paper_count": 5},
                ],
            },
        ]
    }

    catalog = render_task_catalog(payload, maximum_tasks_per_area=2)

    assert catalog.index("### Audio") < catalog.index("### Vision")
    assert catalog.index("`popular`") < catalog.index("`classification`")
    assert "`detection`" not in catalog
    assert "`segmentation`" not in catalog


def test_image_makes_copied_worker_readable_and_installs_skill():
    source = (
        Path(__file__).resolve().parents[1] / "chat_sandbox_worker" / "image.py"
    ).read_text()

    assert 'WORKER / "PWC_CLI_SKILL.md", "/opt/pwc/PWC_CLI_SKILL.md"' in source
    assert '"chmod -R a+rX /opt/pwc/backend"' in source
    assert '"chmod 0644 /opt/pwc/PWC_CLI_SKILL.md /opt/pwc/install-pwc.py"' in source
    assert '"chown pwc-broker:pwc-broker /var/empty/pwc-broker"' in source


def test_image_publication_initializes_modal_app(monkeypatch, capsys):
    events: list[str] = []

    class Lookup:
        async def aio(self, name, *, create_if_missing):
            assert name == MODAL_APP_NAME
            assert create_if_missing is True
            events.append("lookup")

    class Run:
        def __enter__(self):
            events.append("enter")

        def __exit__(self, *_args):
            events.append("exit")

    class App:
        def run(self):
            return Run()

    class Built:
        object_id = "im-test"

        def publish(self, name):
            assert events == ["lookup", "enter", "build"]
            events.append(f"publish:{name}")

    class Image:
        def build(self, _app):
            assert events == ["lookup", "enter"]
            events.append("build")
            return Built()

    monkeypatch.setattr(publish_image, "app", App())
    monkeypatch.setattr(publish_image, "image", Image())
    monkeypatch.setattr(publish_image.modal.App, "lookup", Lookup())

    assert publish_image.main() == 0
    assert events == [
        "lookup",
        "enter",
        "build",
        f"publish:{IMAGE_PUBLISH_NAME}",
        "exit",
    ]
    assert capsys.readouterr().out == "im-test\n"


def test_immutable_modal_image_uses_supported_constructor(monkeypatch):
    sentinel = object()

    monkeypatch.setattr(
        "backend.services.chat_sandbox_service.modal.Image.from_id",
        lambda image_id: sentinel if image_id == "im-test" else None,
    )

    assert asyncio.run(resolve_modal_image("im-test")) is sentinel


def test_persistent_sandbox_uses_daemon_probe_and_request_limit_pairs(monkeypatch):
    captured: dict = {}

    async def lookup(*_args, **_kwargs):
        return object()

    async def image(_reference):
        return object()

    class Created:
        def __init__(self):
            self.exec = SimpleNamespace(aio=self._exec)
            self.poll = SimpleNamespace(aio=self._poll)

        async def _exec(self, *_args, **_kwargs):
            async def wait():
                return None

            return SimpleNamespace(
                returncode=0,
                wait=SimpleNamespace(aio=wait),
            )

        async def _poll(self):
            return None

    async def create(*command, **options):
        captured["command"] = command
        captured["options"] = options
        return Created()

    monkeypatch.setattr(
        "backend.services.chat_sandbox_service.modal.App.lookup",
        SimpleNamespace(aio=lookup),
    )
    monkeypatch.setattr(
        "backend.services.chat_sandbox_service.resolve_modal_image",
        image,
    )
    monkeypatch.setattr(
        "backend.services.chat_sandbox_service.modal.Sandbox.create",
        SimpleNamespace(aio=create),
    )
    settings = Settings(
        _env_file=None,
        chat_gateway_url="https://gateway.example.test/api/internal/chat-gateway",
        chat_modal_image_version="im-test",
        chat_persistent_worker_enabled=True,
        chat_sandbox_cpu=0.125,
        chat_sandbox_cpu_limit=1,
        chat_sandbox_memory_mib=512,
        chat_sandbox_memory_limit_mib=2048,
    )

    asyncio.run(
        create_isolated_sandbox(settings, name="test", tags={"purpose": "test"})
    )

    assert captured["command"] == (
        "python",
        "-m",
        "backend.chat_sandbox_worker.control_daemon",
    )
    assert captured["options"]["cpu"] == (0.125, 1)
    assert captured["options"]["memory"] == (512, 2048)
    assert captured["options"]["timeout"] == 86400
    assert captured["options"]["idle_timeout"] == 86400


def test_supervisor_tolerates_unsupported_proc_remount(monkeypatch):
    monkeypatch.setattr(
        supervisor.Path,
        "read_text",
        lambda *_args, **_kwargs: "none /proc proc rw 0 0\n",
    )

    class Result:
        returncode = 32

    calls: list[list[str]] = []

    def run(command, **options):
        calls.append(command)
        assert options["check"] is False
        return Result()

    monkeypatch.setattr(supervisor.subprocess, "run", run)

    supervisor._harden_proc()
    assert calls == [["mount", "-o", "remount,hidepid=2,nosuid,nodev", "/proc"]]


def test_supervisor_child_environment_preserves_packaged_worker_path(monkeypatch):
    monkeypatch.setenv("PWC_CHAT_MAX_TURNS", "8")
    monkeypatch.setenv("PYTHONPATH", "/untrusted")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-pass")

    environment = supervisor._safe_environment("/var/empty/pwc-broker")

    assert environment["PYTHONPATH"] == "/opt/pwc"
    assert environment["PWC_CHAT_MAX_TURNS"] == "8"
    assert "ANTHROPIC_API_KEY" not in environment
    agent_environment = supervisor._agent_environment()
    assert agent_environment["HTTPS_PROXY"] == "http://127.0.0.1:8766"
    assert agent_environment["NO_PROXY"] == "127.0.0.1,localhost"
    assert agent_environment["NODE_EXTRA_CA_CERTS"] == "/tmp/pwc-webfetch-ca.pem"
    assert "PWC_WEBFETCH_TOKEN_FD" not in agent_environment


def test_resource_probe_treats_ephemeral_disk_as_provider_managed(monkeypatch):
    settings = type(
        "Settings",
        (),
        {"chat_sandbox_pids_max": 64, "chat_sandbox_memory_mib": 2048},
    )()
    runner = QualificationRunner(settings, starts=1, parallel=1, snapshot_samples=0)
    probes: list[str] = []

    async def record(name, *_command, **_options):
        probes.append(name)

    monkeypatch.setattr(runner, "_resource_probe", record)

    assert asyncio.run(runner.run_resource_probes()) == {
        "pids": "enforced",
        "disk": "provider_managed_ephemeral",
        "memory": "enforced",
    }
    assert probes == ["pids", "memory"]


def test_capability_is_exactly_scoped_and_metered():
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    token = "opaque-test-token"
    row = ChatTurnCapability(
        id=uuid.uuid4(),
        token_hash=_digest(token),
        chat_session_id=session_id,
        turn_id=turn_id,
        owner_hash="a" * 64,
        model="model-a",
        scopes=["catalog"],
        nonce="b" * 32,
        expires_at=datetime.now(UTC) + timedelta(minutes=1),
        gateway_calls=0,
        provider_requests=0,
        provider_tokens=0,
        catalog_search_calls=0,
    )

    class Result:
        def scalar_one_or_none(self):
            return row

    class DB:
        def execute(self, _query):
            return Result()

        def flush(self):
            pass

    service = ChatCapabilityService(DB())
    assert (
        service.validate(
            token,
            scope="catalog",
            chat_session_id=session_id,
            turn_id=turn_id,
        )
        is row
    )
    assert row.gateway_calls == 1
    with pytest.raises(CapabilityError):
        service.validate(
            token,
            scope="model",
            chat_session_id=session_id,
            turn_id=turn_id,
        )
    with pytest.raises(CapabilityError):
        service.validate(
            token,
            scope="catalog",
            chat_session_id=session_id,
            turn_id=uuid.uuid4(),
        )


def test_workspace_snapshot_provider_only_snapshots_workspace():
    calls: list[tuple[str, int, int]] = []

    class AsyncCall:
        def __init__(self, function):
            self.aio = function

    class Image:
        object_id = "im-snapshot"

        def __init__(self):
            self.hydrate = AsyncCall(self._hydrate)

        async def _hydrate(self):
            return self

    async def snapshot(path, *, timeout, ttl):
        calls.append((path, timeout, ttl))
        return Image()

    class Sandbox:
        snapshot_directory = AsyncCall(snapshot)

    provider = WorkspaceSnapshotProvider(ttl_days=30)
    assert asyncio.run(provider.save(Sandbox(), uuid.uuid4())) == "im-snapshot"
    assert calls == [("/workspace", 55, 30 * 24 * 60 * 60)]


def test_workspace_snapshot_restore_uses_supported_image_constructor(monkeypatch):
    image = object()
    mounted: list[tuple[str, object]] = []

    monkeypatch.setattr(
        "backend.services.chat_sandbox_service.modal.Image.from_id",
        lambda image_id: image if image_id == "im-snapshot" else None,
    )

    class AsyncCall:
        def __init__(self, function):
            self.aio = function

    async def mount(path, mounted_image):
        mounted.append((path, mounted_image))

    class Sandbox:
        mount_image = AsyncCall(mount)

    provider = WorkspaceSnapshotProvider()
    asyncio.run(provider.restore(Sandbox(), "im-snapshot"))
    assert mounted == [("/workspace", image)]


def test_sandbox_cancel_correlates_to_original_run_request():
    writes: list[bytes] = []

    class AsyncCall:
        def __init__(self, function):
            self.aio = function

    class Stdin:
        def __init__(self):
            self.drain = AsyncCall(self._drain)

        def write(self, value):
            writes.append(value)

        async def _drain(self):
            return None

    class Process:
        stdin = Stdin()

        def __init__(self):
            self.wait = AsyncCall(self._wait)

        async def _wait(self):
            return None

    manager = SandboxSessionManager.__new__(SandboxSessionManager)
    manager.settings = type("Settings", (), {"chat_cancel_grace_seconds": 1})()
    turn_id = uuid.uuid4()
    running = RunningWorker(
        Process(),
        "original-request",
        WorkerClaim("sandbox-id", "worker-token"),
    )
    manager._processes = {turn_id: running}

    assert asyncio.run(manager.cancel(uuid.uuid4(), turn_id))
    assert running.cancel_requested
    assert decode_frame(writes[0].rstrip(b"\n"))["request_id"] == ("original-request")


def test_session_store_rejects_bad_shape_before_touching_database():
    class DB:
        def execute(self, _statement):
            raise AssertionError("database must not be touched")

    gateway = ChatSessionStoreGateway(
        DB(),
        type(
            "Settings",
            (),
            {
                "chat_session_byte_limit": 1024,
                "chat_user_byte_limit": 4096,
            },
        )(),
    )
    with pytest.raises(SessionStoreGatewayError, match="Unsupported"):
        gateway.execute(
            ChatTurnCapability(),
            SessionStoreCommand(
                action="delete",
                key=None,
                entries=None,
                project_key=None,
            ),
        )


def test_qualification_summary_uses_nearest_rank_p95():
    samples = [
        Sample(
            cold_start_ms=value,
            exec_ms=value * 2,
            termination_ms=value * 3,
            snapshot_ms=value if value <= 3 else None,
            restore_ms=value + 1 if value <= 3 else None,
        )
        for value in range(1, 21)
    ]
    result = summarize(samples)
    assert result["cold_start_ms"] == {
        "count": 20,
        "min": 1,
        "p50": 10,
        "p95": 19,
        "max": 20,
    }
    assert result["snapshot_ms"]["count"] == 3


def test_sandbox_migration_is_staging_scoped():
    migration = (
        Path(__file__).parents[1]
        / "database"
        / "migrations"
        / "add_chat_sandbox_runtime.sql"
    ).read_text()
    assert "current_schema() <> 'staging'" in migration
    assert "OWNER TO pwc_staging_owner" in migration
    assert "TO pwc_staging;" in migration
    assert "FROM paperswithcode_user;" in migration
