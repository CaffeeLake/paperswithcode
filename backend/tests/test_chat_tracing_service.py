from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC

from backend.config import Settings
from backend.services import chat_tracing_service as tracing


class Observation:
    def __init__(self, name: str, **fields):
        self.name = name
        self.fields = fields
        self.children: list[Observation] = []
        self.ended = False
        self.trace_id = "a" * 32

    def start_observation(self, *, name: str, **fields):
        child = Observation(name, **fields)
        self.children.append(child)
        return child

    def update(self, **fields):
        self.fields.update(fields)
        return self

    def end(self):
        self.ended = True
        return self


class Client:
    def __init__(self):
        self.root: Observation | None = None

    def create_trace_id(self, *, seed: str):
        assert seed == "request-1"
        return "b" * 32

    def start_observation(self, *, name: str, **fields):
        self.root = Observation(name, **fields)
        return self.root


def test_chat_trace_captures_hierarchy_usage_and_context(monkeypatch):
    client = Client()
    propagated = {}

    @contextmanager
    def attributes(**values):
        propagated.update(values)
        yield

    monkeypatch.setattr(tracing, "_configured_client", lambda _settings: client)
    monkeypatch.setattr(tracing, "propagate_attributes", attributes)
    settings = Settings(
        environment="staging",
        release_id="release-1",
        chat_langfuse_enabled=True,
    )

    with tracing.trace_chat_turn(
        settings=settings,
        request_id="request-1",
        session_id="session-1",
        user_id="private-user",
        prompt="Find papers",
        model="provider/model",
        execution_backend="modal_cli",
        is_replacement=False,
    ) as trace:
        trace.record_event("sandbox_start", {"session_id": "session-1"})
        trace.record_event(
            "_latency",
            {
                "phase": "sandbox_acquisition_ms",
                "elapsed_ms": 40,
                "acquisition_outcome": "pool_hit",
            },
        )
        trace.record_event("sandbox_ready", {"cold_start_ms": 0})
        trace.record_event(
            "_latency", {"phase": "capability_install_ms", "elapsed_ms": 55}
        )
        trace.record_event("_latency", {"phase": "sdk_dispatch_ms", "elapsed_ms": 60})
        trace.record_event(
            "_latency", {"phase": "first_worker_delta", "elapsed_ms": 100}
        )
        trace.start_title("title-model")
        trace.finish_title("Paper search", fallback=False)
        trace.start_tool(
            {"id": "tool-1", "name": "Bash", "args": {"command": "pwc search"}}
        )
        trace.finish_tool(
            {
                "id": "tool-1",
                "status": "success",
                "took_ms": 12,
                "content": [{"type": "text", "text": "result"}],
            }
        )
        trace.start_tool(
            {
                "id": "tool-2",
                "name": "WebFetch",
                "args": {"url": "https://example.com"},
            }
        )
        trace.finish_tool(
            {
                "id": "tool-2",
                "status": "success",
                "took_ms": 20,
                "content": [{"type": "text", "text": "page"}],
            }
        )
        trace.record_usage(
            {
                "usage": {"input_tokens": 10, "output_tokens": 4},
                "total_cost_usd": 0.02,
            }
        )
        trace.finish("Here are the papers", "success")

    assert client.root is not None and client.root.ended
    children = {child.name: child for child in client.root.children}
    assert set(children) == {
        "acquire-sandbox",
        "install-sandbox-capability",
        "dispatch-model-request",
        "generate-research-response",
        "generate-session-title",
        "run-bash-command",
        "fetch-web-page",
    }
    generation = children["generate-research-response"]
    assert generation.fields["usage_details"] == {"input": 10, "output": 4}
    assert generation.fields["cost_details"] == {"total": 0.02}
    assert generation.fields["model"] == "provider/model"
    assert generation.fields["completion_start_time"].tzinfo is UTC
    assert children["acquire-sandbox"].fields["output"] == {
        "acquisition_outcome": "pool_hit",
        "elapsed_ms": 40,
    }
    assert children["install-sandbox-capability"].ended
    assert children["dispatch-model-request"].ended
    assert children["run-bash-command"].fields["as_type"] == "tool"
    assert children["fetch-web-page"].fields["as_type"] == "tool"
    assert propagated["session_id"] == "session-1"
    assert propagated["environment"] == "staging"
    assert propagated["user_id"] != "private-user"


def test_langfuse_client_exports_trace_content_without_a_mask(monkeypatch):
    captured = {}

    def client(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(tracing, "Langfuse", client)
    tracing._client.cache_clear()
    try:
        tracing._client(
            "staging",
            "release-1",
            "pk-test",
            "sk-test",
            "https://example.com",
        )
    finally:
        tracing._client.cache_clear()

    assert "mask_otel_spans" not in captured


def test_tracing_is_staging_only(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://example.com")
    settings = Settings(environment="production", chat_langfuse_enabled=True)
    assert tracing._configured_client(settings) is None


def test_unfinished_operational_spans_close_as_warnings():
    root = Observation("root")
    trace = tracing.ChatTurnTrace(
        root,
        prompt="Find papers",
        model="provider/model",
        execution_backend="modal_cli",
    )

    trace.record_event("sandbox_start", {})
    acquisition = trace.sandbox_acquisition
    trace.close()

    assert acquisition is not None and acquisition.ended
    assert acquisition.fields["level"] == "WARNING"
