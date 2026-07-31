from __future__ import annotations

from contextlib import contextmanager

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
        "generate-research-response",
        "generate-session-title",
        "run-bash-command",
    }
    generation = children["generate-research-response"]
    assert generation.fields["usage_details"] == {"input": 10, "output": 4}
    assert generation.fields["cost_details"] == {"total": 0.02}
    assert generation.fields["model"] == "provider/model"
    assert children["run-bash-command"].fields["as_type"] == "tool"
    assert propagated["session_id"] == "session-1"
    assert propagated["environment"] == "staging"
    assert propagated["user_id"] != "private-user"


def test_redaction_masks_common_pii_and_secrets():
    value = "Email me@example.com, call 415-555-1212, token sk-test_123456789012"
    assert tracing._redact(value) == (
        "Email [REDACTED EMAIL], call [REDACTED PHONE], token [REDACTED SECRET]"
    )


def test_tracing_is_staging_only(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://example.com")
    settings = Settings(environment="production", chat_langfuse_enabled=True)
    assert tracing._configured_client(settings) is None
