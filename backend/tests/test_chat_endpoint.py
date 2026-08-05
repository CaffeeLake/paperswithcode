from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    StreamEvent,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)
from fastapi.testclient import TestClient
from starlette.requests import Request

from backend.config import Settings, get_settings
from backend.main import create_app
from backend.models.chat import (
    DISPLAY_BLOCKS_ADAPTER,
    ChatBrowserLatencyRequest,
    ChatRequest,
    sse_event,
)
from backend.routers import chat as chat_router
from backend.routers.inference_billing import _status as inference_billing_status
from backend.services import chat_mcp
from backend.services.chat_agent_service import (
    SEARCH_TOOL_NAME,
    SDKEventAdapter,
    SearchCallLimiter,
    build_agent_options,
    stream_agent_events,
)
from backend.services.chat_sandbox_service import SandboxCleanupUnverified
from backend.services.chat_session_service import (
    ChatDeletionReceipt,
    ChatOwner,
    ChatServiceError,
    ChatSessionService,
    TurnAdmission,
)
from backend.services.chat_stream_service import (
    ChatStreamOrchestrator,
    ChatTurnProjection,
    sequential_reasoning_events,
)
from backend.services.chat_title_service import fallback_title, normalize_title
from backend.services.chat_transcript_recovery import reconcile_spooled_session
from backend.utils.auth import require_user


def _cookie_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"cookie", b"pwc_session=test")],
        }
    )


def test_chat_quota_configuration_and_billing_api_fields_are_removed():
    settings = get_settings()

    fields = type(settings).model_fields
    assert "chat_requests_per_minute" not in fields
    assert "chat_requests_per_day" not in fields
    assert "chat_openrouter_requests_per_minute" not in fields
    assert "chat_openrouter_requests_per_day" not in fields
    payload = inference_billing_status(
        settings, connected=True, is_pro=True
    ).model_dump()
    assert "requests_per_minute" not in payload
    assert "requests_per_day" not in payload


def test_require_user_returns_immutable_oauth_subject(monkeypatch):
    from backend.routers import auth

    monkeypatch.setattr(
        auth,
        "decode_session_cookie",
        lambda _token: {"sub": "hf-immutable-123", "username": "Alice"},
    )
    user = require_user(_cookie_request())
    assert user["source"] == "cookie"
    assert user["username"] == "alice"
    assert user["hf_user_id"] == "hf-immutable-123"
    assert user["hf_subject"] == "hf-immutable-123"


def test_require_user_rejects_legacy_cookie_without_subject(monkeypatch):
    from backend.routers import auth

    monkeypatch.setattr(
        auth, "decode_session_cookie", lambda _token: {"username": "alice"}
    )
    with pytest.raises(Exception) as exc_info:
        require_user(_cookie_request())
    assert exc_info.value.status_code == 401


def test_chat_request_is_strict_and_requires_message_and_client_id():
    with pytest.raises(ValueError):
        ChatRequest(message="hello")
    with pytest.raises(ValueError):
        ChatRequest(message=" ", client_message_id="id")
    with pytest.raises(ValueError):
        ChatRequest(message="hello", client_message_id="id", unknown=True)
    request = ChatRequest(message="hello", client_message_id="id")
    assert request.session_id is None


def test_browser_latency_request_is_strict_bounded_and_nonempty():
    with pytest.raises(ValueError):
        ChatBrowserLatencyRequest()
    with pytest.raises(ValueError):
        ChatBrowserLatencyRequest(submission_to_stream_start_ms=-1)
    with pytest.raises(ValueError):
        ChatBrowserLatencyRequest(submission_to_stream_start_ms=1, unexpected="content")
    payload = ChatBrowserLatencyRequest(
        submission_to_stream_start_ms=12.5,
        terminal_classification="complete",
    )
    assert payload.submission_to_stream_start_ms == 12.5


def test_cancel_endpoint_uses_owner_checked_active_turn(monkeypatch):
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    calls: list[tuple[uuid.UUID, uuid.UUID]] = []

    class Service:
        def __init__(self, _db, _settings):
            pass

        def get_session(self, owner, requested_session_id):
            assert owner.hf_user_id == "owner-1"
            assert requested_session_id == session_id
            return SimpleNamespace(active_turn_id=turn_id), []

    class Manager:
        async def cancel(self, requested_session_id, requested_turn_id):
            calls.append((requested_session_id, requested_turn_id))
            return True

    monkeypatch.setattr(chat_router, "ChatSessionService", Service)
    monkeypatch.setattr(
        chat_router, "shared_sandbox_manager", lambda _settings: Manager()
    )
    response = asyncio.run(
        chat_router.cancel_active_turn(
            session_id,
            user={"hf_user_id": "owner-1", "username": "owner"},
            db=object(),
            settings=object(),
        )
    )

    assert response.status_code == 204
    assert calls == [(session_id, turn_id)]


def test_create_session_fails_closed_when_public_admission_is_disabled():
    settings = Settings(chat_public_admission_enabled=False)

    with pytest.raises(Exception) as exc_info:
        chat_router.create_session(
            SimpleNamespace(selected_model=None),
            user={"hf_user_id": "owner-1", "username": "owner"},
            db=SimpleNamespace(),
            settings=settings,
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["code"] == "chat_temporarily_disabled"


def test_production_openrouter_api_is_absent():
    with pytest.raises(Exception) as exc_info:
        chat_router.get_openrouter_key_status(
            user={"hf_user_id": "owner-1"},
            db=SimpleNamespace(),
            settings=Settings(environment="production"),
        )

    assert exc_info.value.status_code == 404


def test_delete_session_reports_success_only_after_durable_and_workspace_verification(
    monkeypatch,
):
    session_id = uuid.uuid4()
    receipt = ChatDeletionReceipt(session_id, "sb-1", None, None, None)
    events: list[str] = []

    class DB:
        def commit(self):
            events.append("commit")

        def rollback(self):
            events.append("rollback")

    class Service:
        def __init__(self, *_args):
            pass

        def delete_session(self, *_args):
            events.append("delete")
            return receipt

        def deletion_complete(self, requested):
            assert requested == receipt
            events.append("verify-db")
            return True

    class Manager:
        def __init__(self, _settings):
            pass

        async def cleanup_deleted(self, sandbox_id, snapshot_id):
            assert (sandbox_id, snapshot_id) == ("sb-1", None)
            events.append("verify-workspace")

    monkeypatch.setattr(chat_router, "ChatSessionService", Service)
    monkeypatch.setattr(chat_router, "SandboxSessionManager", Manager)

    response = asyncio.run(
        chat_router.delete_session(
            session_id,
            user={"hf_user_id": "owner-1", "username": "owner"},
            db=DB(),
            settings=Settings(),
        )
    )

    assert response.status_code == 204
    assert events == ["delete", "verify-workspace", "commit", "verify-db"]


@pytest.mark.parametrize("failure", ["database", "workspace"])
def test_delete_session_never_reports_success_when_removal_is_unverified(
    monkeypatch, failure: str
):
    session_id = uuid.uuid4()
    receipt = ChatDeletionReceipt(session_id, "sb-1", None, None, None)

    class DB:
        def commit(self):
            pass

        def rollback(self):
            pass

    class Service:
        def __init__(self, *_args):
            pass

        def delete_session(self, *_args):
            return receipt

        def deletion_complete(self, _receipt):
            return failure != "database"

    class Manager:
        def __init__(self, _settings):
            pass

        async def cleanup_deleted(self, *_args):
            if failure == "workspace":
                raise SandboxCleanupUnverified("uncertain")

    monkeypatch.setattr(chat_router, "ChatSessionService", Service)
    monkeypatch.setattr(chat_router, "SandboxSessionManager", Manager)

    with pytest.raises(Exception) as exc_info:
        asyncio.run(
            chat_router.delete_session(
                session_id,
                user={"hf_user_id": "owner-1", "username": "owner"},
                db=DB(),
                settings=Settings(),
            )
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["code"] == "chat_deletion_unverified"


def test_delete_session_workspace_failure_rolls_back_before_commit(monkeypatch):
    session_id = uuid.uuid4()
    receipt = ChatDeletionReceipt(session_id, "sb-1", None, None, None)
    events: list[str] = []

    class DB:
        def commit(self):
            events.append("commit")

        def rollback(self):
            events.append("rollback")

    class Service:
        def __init__(self, *_args):
            pass

        def delete_session(self, *_args):
            events.append("delete")
            return receipt

    class Manager:
        def __init__(self, _settings):
            pass

        async def cleanup_deleted(self, *_args):
            events.append("verify-workspace")
            raise SandboxCleanupUnverified("uncertain")

    monkeypatch.setattr(chat_router, "ChatSessionService", Service)
    monkeypatch.setattr(chat_router, "SandboxSessionManager", Manager)

    with pytest.raises(Exception):
        asyncio.run(
            chat_router.delete_session(
                session_id,
                user={"hf_user_id": "owner-1", "username": "owner"},
                db=DB(),
                settings=Settings(),
            )
        )

    assert events == ["delete", "verify-workspace", "rollback"]


def test_archive_old_sessions_endpoint_commits_owner_scoped_archive(monkeypatch):
    calls = []

    class Service:
        def __init__(self, _db, _settings):
            pass

        def archive_old_sessions(self, owner, *, days):
            calls.append((owner.hf_user_id, days))
            return 7

    db = SimpleNamespace(commit=lambda: calls.append("commit"), rollback=lambda: None)
    monkeypatch.setattr(chat_router, "ChatSessionService", Service)

    response = chat_router.archive_old_sessions(
        user={"hf_user_id": "owner-1", "username": "owner"},
        db=db,
        settings=object(),
    )

    assert response.archived_count == 7
    assert calls == [("owner-1", 30), "commit"]


def test_archive_old_sessions_marks_selected_rows_without_deleting():
    rows = [SimpleNamespace(archived_at=None), SimpleNamespace(archived_at=None)]

    class Result:
        def scalars(self):
            return rows

    class FakeDB:
        def __init__(self):
            self.calls = 0
            self.flushed = False

        def execute(self, _query):
            self.calls += 1
            return None if self.calls == 1 else Result()

        def flush(self):
            self.flushed = True

    db = FakeDB()
    archived = ChatSessionService(db, object()).archive_old_sessions(
        ChatOwner(hf_user_id="owner-1", hf_username="owner")
    )

    assert archived == 2
    assert db.flushed
    assert all(row.archived_at is not None for row in rows)


def test_archive_oldest_sessions_endpoint_commits_owner_scoped_archive(monkeypatch):
    calls = []

    class Service:
        def __init__(self, _db, _settings):
            pass

        def archive_oldest_sessions(self, owner, *, limit):
            calls.append((owner.hf_user_id, limit))
            return 50

    db = SimpleNamespace(commit=lambda: calls.append("commit"), rollback=lambda: None)
    monkeypatch.setattr(chat_router, "ChatSessionService", Service)

    response = chat_router.archive_oldest_sessions(
        user={"hf_user_id": "owner-1", "username": "owner"},
        db=db,
        settings=object(),
    )

    assert response.archived_count == 50
    assert calls == [("owner-1", 50), "commit"]


def test_archive_oldest_sessions_marks_at_most_selected_rows_without_deleting():
    rows = [SimpleNamespace(archived_at=None) for _ in range(50)]

    class Result:
        def scalars(self):
            return rows

    class FakeDB:
        def __init__(self):
            self.calls = 0
            self.flushed = False

        def execute(self, _query):
            self.calls += 1
            return None if self.calls == 1 else Result()

        def flush(self):
            self.flushed = True

    db = FakeDB()
    archived = ChatSessionService(db, object()).archive_oldest_sessions(
        ChatOwner(hf_user_id="owner-1", hf_username="owner"), limit=50
    )

    assert archived == 50
    assert db.flushed
    assert all(row.archived_at is not None for row in rows)


def test_chat_session_quota_error_states_the_exact_limit():
    class FakeDB:
        scalar_query = ""

        def execute(self, _query):
            return None

        def scalar(self, query):
            self.scalar_query = str(query)
            return 100

    db = FakeDB()
    settings = SimpleNamespace(
        chat_model_choices=[{"id": "model"}],
        chat_model_routes={"model": "route"},
        chat_session_limit=100,
    )

    with pytest.raises(ChatServiceError) as exc_info:
        ChatSessionService(db, settings).create_session(
            ChatOwner(hf_user_id="owner-1", hf_username="owner")
        )

    assert exc_info.value.code == "chat_session_quota_exceeded"
    assert "chat_sessions.archived_at IS NULL" in db.scalar_query
    assert str(exc_info.value) == (
        "You can have at most 100 chats. Archive old chats or delete a chat to "
        "create another."
    )


def test_sse_serialization_preserves_unicode_and_newlines():
    frame = sse_event("answer_delta", text="héllo\nworld")
    assert frame.startswith(b"data: ")
    assert frame.endswith(b"\n\n")
    assert json.loads(frame[6:-2])["text"] == "héllo\nworld"


def test_sse_event_allows_stopped_done_terminal():
    frame = sse_event("done", followups=[], finish_reason="stopped")
    assert json.loads(frame[6:-2])["finish_reason"] == "stopped"


def test_chat_projection_preserves_sse_block_order():
    projection = ChatTurnProjection()
    projection.apply("answer_delta", {"text": "Before tool."})
    projection.apply(
        "tool_call",
        {"id": "tool-1", "name": "Bash", "args": {"command": "pwc task list"}},
    )
    projection.apply(
        "tool_result",
        {
            "id": "tool-1",
            "status": "success",
            "took_ms": 12,
            "content": [{"type": "text", "text": "done", "truncated": False}],
            "metadata": {"exit_code": 0, "output_truncated": False},
        },
    )
    projection.apply("reasoning_start", {})
    projection.apply("reasoning_delta", {"text": "Check another benchmark."})
    projection.apply("reasoning_end", {})
    projection.apply("answer_delta", {"text": "After tool."})

    blocks = projection.completed_blocks()

    assert [block["kind"] for block in blocks] == [
        "answer",
        "tool",
        "reasoning",
        "answer",
    ]
    assert [block["text"] for block in blocks if block["kind"] == "answer"] == [
        "Before tool.",
        "After tool.",
    ]


def test_chat_projection_collapses_consecutive_duplicate_reasoning():
    projection = ChatTurnProjection()
    for _ in range(2):
        projection.apply("reasoning_start", {})
        projection.apply("reasoning_delta", {"text": "**Same plan**"})
        projection.apply("reasoning_end", {})

    assert projection.completed_blocks() == [
        {"kind": "reasoning", "text": "**Same plan**"}
    ]


def test_stream_boundary_normalizer_repairs_nested_and_extra_reasoning_events():
    async def source():
        for event in [
            {"type": "reasoning_start"},
            {"type": "reasoning_delta", "text": "First"},
            {"type": "reasoning_start"},
            {"type": "reasoning_delta", "text": "Second"},
            {"type": "reasoning_end"},
            {"type": "reasoning_end"},
            {"type": "done"},
        ]:
            yield event

    async def collect():
        return [event async for event in sequential_reasoning_events(source())]

    assert [event["type"] for event in asyncio.run(collect())] == [
        "reasoning_start",
        "reasoning_delta",
        "reasoning_end",
        "reasoning_start",
        "reasoning_delta",
        "reasoning_end",
        "done",
    ]


def test_model_registry_exposes_stable_ids_not_provider_routes():
    production = Settings(environment="production")
    assert [choice["id"] for choice in production.chat_model_choices] == [
        "deepseek-ai/DeepSeek-V4-Flash-0731",
    ]
    staging = Settings(
        environment="staging", chat_openrouter_server_funded_enabled=True
    )
    assert [choice["id"] for choice in staging.chat_model_choices] == [
        "deepseek-ai/DeepSeek-V4-Flash-0731",
        "openai/gpt-5.6-luna",
        "openai/gpt-5.6-terra",
    ]
    assert production.chat_model_routes["deepseek-ai/DeepSeek-V4-Flash-0731"] == (
        "deepseek-ai/DeepSeek-V4-Flash-0731:fastest"
    )
    for legacy_id in (
        "google/gemma-4-31B-it",
        "zai-org/GLM-5.2",
        "moonshotai/Kimi-K3",
        "openai/gpt-oss-120b",
        "deepseek-ai/DeepSeek-V4-Flash",
    ):
        assert (
            production.chat_model_routes[legacy_id]
            == production.chat_model_routes["deepseek-ai/DeepSeek-V4-Flash-0731"]
        )
    assert (
        production.chat_model_providers["deepseek-ai/DeepSeek-V4-Flash-0731"]
        == "huggingface"
    )
    assert staging.chat_model_routes["openai/gpt-5.6-luna"] == "openai/gpt-5.6-luna"
    assert staging.chat_model_routes["openai/gpt-5.6-terra"] == "openai/gpt-5.6-terra"
    assert staging.chat_route_providers[staging.chat_luna_route] == "openrouter"


def test_title_and_display_projection_bounds():
    assert (
        normalize_title('  "Vision   Transformer Trends."  ')
        == "Vision Transformer Trends"
    )
    assert len(fallback_title("word " * 100)) <= 80
    with pytest.raises(ValueError):
        DISPLAY_BLOCKS_ADAPTER.validate_python(
            [
                {
                    "kind": "tool",
                    "id": "t",
                    "name": "search_papers",
                    "args": {"secret": "not allowed"},
                    "status": "done",
                    "hits": 0,
                    "took_ms": 1,
                    "results": [],
                }
            ]
        )


def test_spooled_transcript_recovery_replays_main_and_subpaths(tmp_path):
    session_id = "00000000-0000-0000-0000-000000000123"
    recovery = tmp_path / "pwc-chat-recovery"
    project = recovery / "attempt" / "projects" / "project-key"
    project.mkdir(parents=True)
    main_entries = [{"type": "user", "uuid": "u1"}]
    (project / f"{session_id}.jsonl").write_text(
        json.dumps(main_entries[0]) + "\n", encoding="utf-8"
    )
    subpath = project / session_id / "subagents"
    subpath.mkdir(parents=True)
    (subpath / "agent-one.jsonl").write_text(
        json.dumps({"type": "assistant", "uuid": "u2"}) + "\n",
        encoding="utf-8",
    )

    class FakeStore:
        def __init__(self):
            self.rows = {}

        async def append(self, key, entries):
            self.rows[(key["session_id"], key.get("subpath"))] = entries

        async def load(self, key):
            return self.rows.get((key["session_id"], key.get("subpath")))

    store = FakeStore()
    settings = get_settings().model_copy(
        update={"chat_recovery_spool_dir": str(recovery)}
    )
    recovered = asyncio.run(
        reconcile_spooled_session(
            settings,
            store,
            project_key="project-key",
            sdk_session_id=uuid.UUID(session_id),
        )
    )
    assert recovered is True
    assert store.rows[(session_id, None)] == main_entries
    assert store.rows[(session_id, "subagents/agent-one")][0]["uuid"] == "u2"
    assert not (recovery / "attempt").exists()


def test_search_limiter_denies_third_call():
    limiter = SearchCallLimiter(2)
    request = {"tool_name": SEARCH_TOOL_NAME}
    first = asyncio.run(limiter(request, None, None))
    second = asyncio.run(limiter(request, None, None))
    third = asyncio.run(limiter(request, None, None))
    assert first["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert second["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert third["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_sdk_adapter_streams_reasoning_tool_result_and_answer():
    adapter = SDKEventAdapter(show_reasoning=True)
    messages = [
        StreamEvent(
            uuid="1",
            session_id="s",
            event={
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "thinking"},
            },
        ),
        StreamEvent(
            uuid="2",
            session_id="s",
            event={
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "thinking_delta", "thinking": "Search first"},
            },
        ),
        StreamEvent(
            uuid="3",
            session_id="s",
            event={"type": "content_block_stop", "index": 0},
        ),
        StreamEvent(
            uuid="4",
            session_id="s",
            event={
                "type": "content_block_start",
                "index": 1,
                "content_block": {
                    "type": "tool_use",
                    "id": "tool-1",
                    "name": SEARCH_TOOL_NAME,
                    "input": {},
                },
            },
        ),
        StreamEvent(
            uuid="5",
            session_id="s",
            event={
                "type": "content_block_delta",
                "index": 1,
                "delta": {
                    "type": "input_json_delta",
                    "partial_json": '{"query":"VLMs","top_k":3}',
                },
            },
        ),
        StreamEvent(
            uuid="6",
            session_id="s",
            event={"type": "content_block_stop", "index": 1},
        ),
        UserMessage(
            content=[
                ToolResultBlock(
                    tool_use_id="tool-1",
                    content=json.dumps(
                        {"hits": 1, "took_ms": 9, "results": [{"route_id": "1"}]}
                    ),
                )
            ]
        ),
        StreamEvent(
            uuid="7",
            session_id="s",
            event={
                "type": "content_block_delta",
                "index": 2,
                "delta": {"type": "text_delta", "text": "Answer"},
            },
        ),
        ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=2,
            session_id="s",
        ),
    ]
    events = [event for message in messages for event in adapter.feed(message)]
    assert [event["type"] for event in events] == [
        "reasoning_start",
        "reasoning_delta",
        "reasoning_end",
        "tool_call",
        "tool_result",
        "answer_delta",
        "usage",
        "done",
    ]
    assert events[3]["args"] == {"query": "VLMs", "top_k": 3}
    assert events[4]["results"] == [{"route_id": "1"}]


def test_sdk_adapter_complete_messages_do_not_need_partial_events():
    adapter = SDKEventAdapter(show_reasoning=True)
    events = adapter.feed(
        AssistantMessage(
            model="test",
            content=[
                ThinkingBlock(thinking="plan", signature="sig"),
                ToolUseBlock(id="t", name=SEARCH_TOOL_NAME, input={"query": "x"}),
                TextBlock(text="answer"),
            ],
        )
    )
    assert [event["type"] for event in events] == [
        "reasoning_start",
        "reasoning_delta",
        "reasoning_end",
        "tool_call",
        "answer_delta",
    ]


def test_sdk_adapter_does_not_reset_partial_flags_on_intermediate_snapshots():
    adapter = SDKEventAdapter(show_reasoning=True)
    messages = [
        StreamEvent(
            uuid="1",
            session_id="s",
            event={"type": "message_start", "message": {}},
        ),
        StreamEvent(
            uuid="2",
            session_id="s",
            event={
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "thinking"},
            },
        ),
        StreamEvent(
            uuid="3",
            session_id="s",
            event={
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "thinking_delta", "thinking": "Same plan"},
            },
        ),
        AssistantMessage(model="test", content=[]),
        AssistantMessage(
            model="test",
            content=[ThinkingBlock(thinking="Same plan", signature="sig")],
        ),
        StreamEvent(
            uuid="4",
            session_id="s",
            event={"type": "content_block_stop", "index": 0},
        ),
    ]

    events = [event for message in messages for event in adapter.feed(message)]

    assert events == [
        {"type": "reasoning_start"},
        {"type": "reasoning_delta", "text": "Same plan"},
        {"type": "reasoning_end"},
    ]


def test_sdk_adapter_closes_reasoning_before_next_message_start():
    adapter = SDKEventAdapter(show_reasoning=True)
    messages = [
        StreamEvent(
            uuid="1", session_id="s", event={"type": "message_start", "message": {}}
        ),
        StreamEvent(
            uuid="2",
            session_id="s",
            event={
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "thinking"},
            },
        ),
        StreamEvent(
            uuid="3",
            session_id="s",
            event={
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "thinking_delta", "thinking": "First"},
            },
        ),
        StreamEvent(
            uuid="4", session_id="s", event={"type": "message_start", "message": {}}
        ),
        StreamEvent(
            uuid="5",
            session_id="s",
            event={
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "thinking"},
            },
        ),
    ]

    events = [event for message in messages for event in adapter.feed(message)]

    assert [event["type"] for event in events] == [
        "reasoning_start",
        "reasoning_delta",
        "reasoning_end",
        "reasoning_start",
    ]


def test_sdk_adapter_surfaces_hugging_face_billing_errors():
    adapter = SDKEventAdapter(show_reasoning=False)

    events = adapter.feed(
        AssistantMessage(model="test", content=[], error="billing_error")
    )

    assert events == [
        {
            "type": "error",
            "code": "hf_inference_billing_exhausted",
            "message": (
                "Hugging Face could not bill this request. Your included credits "
                "may be exhausted; enable or review pay-as-you-go billing in Settings."
            ),
        }
    ]


@pytest.mark.parametrize(
    ("provider_error", "code"),
    [
        ("authentication_failed", "hf_inference_credential_expired"),
        ("rate_limit", "provider_rate_limit"),
        ("server_error", "provider_unavailable"),
        ("invalid_request", "provider_invalid_request"),
        ("unknown", "provider_error"),
    ],
)
def test_sdk_adapter_keeps_provider_failures_distinct(provider_error, code):
    events = SDKEventAdapter(show_reasoning=False).feed(
        AssistantMessage(model="test", content=[], error=provider_error)
    )

    assert events[0]["type"] == "error"
    assert events[0]["code"] == code


def test_sdk_adapter_hides_leading_whitespace_and_over_budget_searches():
    adapter = SDKEventAdapter(show_reasoning=True, maximum_search_calls=2)
    events = []
    for message in [
        AssistantMessage(model="test", content=[TextBlock(text="\n\n")]),
        AssistantMessage(
            model="test",
            content=[
                ToolUseBlock(id="t1", name=SEARCH_TOOL_NAME, input={"query": "one"})
            ],
        ),
        AssistantMessage(
            model="test",
            content=[
                ToolUseBlock(id="t2", name=SEARCH_TOOL_NAME, input={"query": "two"})
            ],
        ),
        AssistantMessage(
            model="test",
            content=[
                ToolUseBlock(id="t3", name=SEARCH_TOOL_NAME, input={"query": "three"})
            ],
        ),
        UserMessage(
            content=[
                ToolResultBlock(
                    tool_use_id="t3", content="The search limit was reached"
                )
            ]
        ),
        AssistantMessage(model="test", content=[TextBlock(text="Final answer")]),
    ]:
        events.extend(adapter.feed(message))

    assert [event["type"] for event in events] == [
        "tool_call",
        "tool_call",
        "answer_delta",
    ]
    assert [event.get("id") for event in events[:2]] == ["t1", "t2"]


class _FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def join(self, *_args):
        return self

    def filter(self, _condition):
        return self

    def order_by(self, *_args):
        return self

    def all(self):
        return self.rows


class _FakeSession:
    def __init__(self, papers):
        self.papers = papers
        self.closed = False

    def query(self, *entities):
        if len(entities) == 1 and entities[0] is chat_mcp.DBPaper:
            return _FakeQuery(self.papers)
        return _FakeQuery([])

    def close(self):
        self.closed = True


def test_search_payload_supports_external_rows_and_bounds_content(monkeypatch):
    paper = SimpleNamespace(
        id=9,
        arxiv_id=None,
        source="external",
        source_url="https://example.com/release",
        thumbnail_url="/api/thumbnails/custom/9.webp",
        title="Release",
        abstract="x" * 5_000,
        date_published=date(2026, 7, 1),
        conference=None,
        citation_count=4,
    )
    session = _FakeSession([paper])
    relation_data = {
        "authors": {9: ["Lab"]},
        "tasks": {9: [SimpleNamespace(name="Language Modeling", slug="lm")]},
        "methods": {9: [SimpleNamespace(name="Transformer", slug="transformer")]},
        "repositories": {
            9: [SimpleNamespace(url="https://github.com/acme/model", num_stars=10)]
        },
        "project_pages": {9: [SimpleNamespace(url="https://acme.example/model")]},
    }

    class FakePaperService:
        def __init__(self, _db):
            pass

        def search_papers(self, query, limit, mode):
            assert query == "model"
            assert limit == 3
            assert mode == "keyword"
            return [SimpleNamespace(id="9")]

        def _get_paper_relation_data(self, ids, include_resources, card_view):
            assert ids == [9]
            assert include_resources and card_view
            return relation_data

        def _resolve_thumbnail_url(self, paper):
            return paper.thumbnail_url

    monkeypatch.setattr(chat_mcp, "PaperService", FakePaperService)
    payload = chat_mcp.search_papers_payload(
        "model", 3, session_factory=lambda: session
    )
    hit = payload["results"][0]
    assert session.closed
    assert hit["route_id"] == "9"
    assert hit["metadata"]["source"] == "external"
    assert hit["metadata"]["thumbnail_url"] == "/api/thumbnails/custom/9.webp"
    assert len(hit["content"]) == 4_000
    assert hit["content_truncated"] is True
    assert chat_mcp._serialized_size(payload) <= 40_000


def test_result_byte_cap_handles_multibyte_content():
    metadata = {
        "arxiv_id": None,
        "source": "external",
        "source_url": "https://example.com",
        "authors": [],
        "published": None,
        "conference": None,
        "citation_count": None,
        "tasks": [],
        "methods": [],
        "repositories": [],
        "project_pages": [],
    }
    payload = {
        "hits": 10,
        "took_ms": 1,
        "results": [
            {
                "route_id": str(index),
                "title": "paper",
                "content": "界" * 4_000,
                "content_truncated": False,
                "metadata": dict(metadata),
            }
            for index in range(10)
        ],
    }
    chat_mcp._enforce_result_bytes(payload)
    assert chat_mcp._serialized_size(payload) <= chat_mcp.MAX_RESULT_BYTES
    assert payload["results"][-1]["content_truncated"] is True


def test_agent_options_expose_only_search(tmp_path):
    settings = get_settings().model_copy(
        update={
            "hf_token": "shared-nielsr-token",
            "chat_max_search_calls": 2,
        }
    )
    options, _ = build_agent_options(
        settings, tmp_path, provider_token="connected-user-token"
    )
    assert options.tools == []
    assert options.allowed_tools == [SEARCH_TOOL_NAME]
    assert options.setting_sources == []
    assert options.skills == []
    assert options.plugins == []
    assert options.fallback_model is None
    assert options.env["ANTHROPIC_API_KEY"] == "connected-user-token"
    assert options.env["ANTHROPIC_AUTH_TOKEN"] == "connected-user-token"
    assert options.env["ANTHROPIC_BASE_URL"] == "https://router.huggingface.co"
    assert "shared-nielsr-token" not in options.env.values()
    assert "HF_BILL_TO" not in options.env
    assert "ANTHROPIC_CUSTOM_HEADERS" not in options.env
    assert "at most 2 times" in options.system_prompt
    assert (
        "[repo_id](https://huggingface.co/datasets/<repo_id>)" in options.system_prompt
    )

    openrouter, _ = build_agent_options(
        settings,
        tmp_path,
        provider_token="openrouter-token",
        provider_base_url="https://openrouter.ai/api",
        model_route=settings.chat_luna_route,
    )
    assert openrouter.model == "openai/gpt-5.6-luna"
    assert openrouter.env["ANTHROPIC_BASE_URL"] == "https://openrouter.ai/api"
    assert openrouter.env["ANTHROPIC_AUTH_TOKEN"] == "openrouter-token"


def test_failed_turn_keeps_partial_tool_projection():
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    message_id = uuid.uuid4()
    session = SimpleNamespace(
        id=session_id,
        hf_user_id="hf-user",
        active_turn_id=turn_id,
        active_turn_expires_at=None,
        projection_bytes=0,
        updated_at=None,
    )
    message = SimpleNamespace(status="generating", error_code=None, display_blocks=[])

    class FakeResult:
        def scalar_one_or_none(self):
            return session

    class FakeDB:
        def execute(self, _query):
            return FakeResult()

        def get(self, _model, key):
            return message if key == message_id else None

    admission = SimpleNamespace(
        session_id=session_id,
        turn_id=turn_id,
        user_message_id=message_id,
    )
    blocks = [
        {
            "kind": "tool",
            "id": "t1",
            "name": "search_papers",
            "args": {"query": "object detection"},
            "status": "done",
            "hits": 0,
            "took_ms": 10,
            "results": [],
        }
    ]

    ChatSessionService(FakeDB(), get_settings()).fail_turn(
        ChatOwner(hf_user_id="hf-user", hf_username="tester"),
        admission,
        "provider_error",
        display_blocks=blocks,
    )

    assert message.status == "error"
    assert message.error_code == "provider_error"
    assert message.display_blocks == blocks
    assert session.active_turn_id is None
    assert session.projection_bytes > 0


def test_completed_turn_persists_finish_reason_in_authenticated_history():
    from backend.routers.chat import _message

    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    user_message_id = uuid.uuid4()
    session = SimpleNamespace(
        id=session_id,
        hf_user_id="hf-user",
        active_turn_id=turn_id,
        last_sequence=1,
        message_count=1,
        projection_bytes=0,
        updated_at=None,
    )
    user_message = SimpleNamespace(status="generating")

    class FakeResult:
        def scalar_one_or_none(self):
            return session

    class FakeDB:
        def __init__(self):
            self.added = []

        def execute(self, _query):
            return FakeResult()

        def get(self, _model, key):
            return user_message if key == user_message_id else None

        def add(self, value):
            self.added.append(value)

        def flush(self):
            for value in self.added:
                value.revision = 1
                value.created_at = datetime.now(UTC)

    db = FakeDB()
    admission = TurnAdmission(
        session_id=session_id,
        turn_id=turn_id,
        user_message_id=user_message_id,
        selected_model="smoke-model",
        model_route="smoke-route",
        sdk_session_id=None,
        sdk_project_key=None,
        is_first_turn=False,
    )

    assistant = ChatSessionService(db, get_settings()).complete_turn(
        ChatOwner(hf_user_id="hf-user", hf_username="tester"),
        admission,
        answer="Bounded answer",
        citations=[],
        followups=[],
        display_blocks=[],
        finish_reason="tool_limit",
    )

    assert assistant.finish_reason == "tool_limit"
    assert _message(assistant).finish_reason == "tool_limit"


def test_agent_timeout_emits_typed_error_and_closes_sdk_stream(monkeypatch):
    from backend.services import chat_agent_service

    state = {"closed": False}

    async def fake_query(**_kwargs):
        try:
            await asyncio.sleep(1)
            yield None
        finally:
            state["closed"] = True

    async def collect():
        settings = get_settings().model_copy(
            update={"hf_token": "test", "chat_timeout_seconds": 0.01}
        )
        return [
            event
            async for event in stream_agent_events(
                "hello",
                settings,
                provider_token="connected-user-token",
                model_route=settings.chat_glm_route,
                session_store=None,
                resume=None,
            )
        ]

    monkeypatch.setattr(chat_agent_service, "sdk_query", fake_query)
    events = asyncio.run(collect())
    assert events == [
        {
            "type": "error",
            "code": "provider_timeout",
            "message": "The model provider timed out. Try again shortly.",
        }
    ]
    assert state["closed"] is True


def test_chat_endpoint_requires_authentication(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "chat_enabled", True)
    monkeypatch.setattr(settings, "hf_token", "test-token")
    monkeypatch.setattr(
        chat_router,
        "inference_credential_for_request",
        lambda *_args: SimpleNamespace(token="user-inference-token", bill_to=None),
    )
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/chat/stream",
            json={"message": "hello", "client_message_id": "id"},
        )
    assert response.status_code == 401


def test_chat_endpoint_stream_contract(monkeypatch):
    from backend.routers import chat as chat_router
    from backend.services import chat_stream_service

    async def fake_stream(_prompt, _settings, **_kwargs):
        yield {"type": "answer_delta", "text": "hello"}
        yield {"type": "done", "followups": [], "finish_reason": "success"}

    async def fake_title(_prompt, _settings, **_kwargs):
        # Let research finish first: title events must still reach the client.
        assert _kwargs["provider_token"] == "title-test-token"
        assert _kwargs["bill_to"] == "huggingface"
        await asyncio.sleep(0.01)
        yield "Research chat"

    admission = SimpleNamespace(
        session_id="00000000-0000-0000-0000-000000000001",
        turn_id="00000000-0000-0000-0000-000000000002",
        user_message_id="00000000-0000-0000-0000-000000000003",
        selected_model="zai-org/GLM-5.2",
        model_route="zai-org/GLM-5.2:together",
        sdk_session_id=None,
        sdk_project_key=None,
        is_first_turn=False,
        replay_assistant=None,
        is_replacement=False,
        prompt_revision=1,
        title_should_generate=True,
        execution_backend="local_mcp",
    )

    class FakeDB:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def commit(self):
            pass

    class FakeService:
        def __init__(self, *_args):
            pass

        def begin_turn(self, *_args, **_kwargs):
            return admission

        def begin_title(self, *_args, **_kwargs):
            return uuid.UUID("00000000-0000-0000-0000-000000000004")

        def complete_title(self, *_args, **_kwargs):
            return "Research chat"

        def complete_turn(self, *_args, **_kwargs):
            pass

    settings = get_settings()
    monkeypatch.setattr(settings, "chat_enabled", True)
    monkeypatch.setattr(settings, "hf_token", "test-token")
    monkeypatch.setattr(settings, "chat_title_generation_enabled", True)
    monkeypatch.setattr(settings, "chat_title_hf_token", "title-test-token")
    monkeypatch.setattr(settings, "chat_title_bill_to", "huggingface")
    monkeypatch.setattr(
        chat_router,
        "inference_credential_for_request",
        lambda *_args: SimpleNamespace(token="user-inference-token", bill_to=None),
    )

    class FakeRunner:
        sdk_directory = settings.chat_agent_cwd

        def events(self):
            return fake_stream("", settings)

        async def cancel(self):
            return None

        async def close(self):
            return None

    monkeypatch.setattr(
        chat_stream_service,
        "create_chat_turn_runner",
        lambda **_kwargs: FakeRunner(),
    )
    monkeypatch.setattr(chat_stream_service, "stream_title", fake_title)

    class FakeTitleBudget:
        def __init__(self, *_args):
            pass

        def reserve_call(self, *_args):
            return None

        def mark_dispatched(self, *_args):
            return None

        def settle_call(self, *_args, **_kwargs):
            return 1

    monkeypatch.setattr(chat_stream_service, "ChatTitleBudgetService", FakeTitleBudget)
    monkeypatch.setattr(chat_router, "ChatSessionService", FakeService)
    monkeypatch.setattr(chat_stream_service, "ChatSessionService", FakeService)
    monkeypatch.setattr(chat_router.db_manager, "_session_local", FakeDB)
    app = create_app()
    app.dependency_overrides[require_user] = lambda: {
        "source": "cookie",
        "username": "tester",
        "hf_user_id": "hf-test-sub",
    }
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/chat/stream",
            json={"message": "hello", "client_message_id": "id"},
        )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache, no-store, no-transform"
    assert response.content.startswith(
        b": " + (b" " * chat_router.SSE_PROXY_FLUSH_PADDING_BYTES) + b"\n\n"
    )
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert [event["type"] for event in events] == [
        "stream_start",
        "answer_delta",
        "done",
        "session_title_start",
        "session_title_delta",
        "session_title_done",
    ]


def test_closing_stream_persists_interrupted_turn(monkeypatch):
    from backend.services import chat_stream_service

    admission = TurnAdmission(
        session_id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
        user_message_id=uuid.uuid4(),
        selected_model="smoke-model",
        model_route="smoke-route",
        sdk_session_id=None,
        sdk_project_key=None,
        is_first_turn=True,
    )
    persisted = []
    released = []
    monkeypatch.setattr(
        chat_stream_service,
        "_persist_failure",
        lambda *args: persisted.append(args),
    )

    async def scenario():
        orchestrator = ChatStreamOrchestrator(
            settings=get_settings().model_copy(update={"environment": "development"}),
            owner=ChatOwner(hf_user_id="hf-user", hf_username="tester"),
            admission=admission,
            prompt="hello",
            request_id=str(uuid.uuid4()),
            title_token=None,
            is_disconnected=lambda: asyncio.sleep(0, result=False),
            release_admission=lambda: asyncio.sleep(0, result=released.append(True)),
        )
        stream = orchestrator.events()
        first = await anext(stream)
        await stream.aclose()
        return first, orchestrator

    first, orchestrator = asyncio.run(scenario())

    assert first.event == "stream_start"
    assert persisted[0][2] == admission
    assert persisted[0][3:] == ("interrupted", True, [])
    assert orchestrator.terminal == "interrupted"
    assert released == [True]


def test_chat_endpoint_rejects_when_capacity_is_occupied(monkeypatch, caplog):
    from backend.routers import chat as chat_router

    calls = {"begin_turn": 0, "runner": 0}

    class FakeDB:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def rollback(self):
            return None

    class NoCapacity:
        def __init__(self, *_args):
            pass

        def begin_turn(self, *_args, **_kwargs):
            calls["begin_turn"] += 1
            raise ChatServiceError(
                "chat_capacity",
                429,
                "Research capacity is currently occupied",
                active_count=2,
            )

    settings = get_settings()
    monkeypatch.setattr(settings, "chat_enabled", True)
    monkeypatch.setattr(settings, "hf_token", "test-token")
    monkeypatch.setattr(
        chat_router,
        "inference_credential_for_request",
        lambda *_args: SimpleNamespace(token="user-inference-token", bill_to=None),
    )
    monkeypatch.setattr(chat_router, "ChatSessionService", NoCapacity)
    monkeypatch.setattr(chat_router.db_manager, "_session_local", FakeDB)
    monkeypatch.setattr(
        chat_router,
        "ChatStreamOrchestrator",
        lambda **_kwargs: calls.__setitem__("runner", calls["runner"] + 1),
    )
    app = create_app()
    app.dependency_overrides[require_user] = lambda: {
        "source": "cookie",
        "username": "tester",
        "hf_user_id": "hf-test-sub",
    }
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/chat/stream",
            json={"message": "hello", "client_message_id": "id"},
        )
    assert response.status_code == 429
    assert response.json()["detail"]["code"] == "chat_capacity"
    assert response.headers["retry-after"] == "5"
    assert calls == {"begin_turn": 1, "runner": 0}
    assert "chat capacity denied environment=" in caplog.text
    assert "ceiling=" in caplog.text
    assert "denial_count=" in caplog.text
    assert "hello" not in caplog.text


def test_new_chat_capacity_rejection_precedes_session_creation(monkeypatch):
    class FakeDB:
        def __init__(self):
            self.counts = iter((0, 2))

        def execute(self, _query):
            return None

        def scalar(self, _query):
            return next(self.counts)

    settings = get_settings().model_copy(update={"chat_max_concurrency": 2})
    service = ChatSessionService(FakeDB(), settings)
    created = []
    monkeypatch.setattr(
        service,
        "create_session",
        lambda *_args, **_kwargs: created.append(True),
    )

    with pytest.raises(ChatServiceError) as error:
        service.begin_turn(
            ChatOwner(hf_user_id="third-user", hf_username="third"),
            session_id=None,
            client_message_id="third-request",
            text="This content must not be stored",
        )

    assert error.value.code == "chat_capacity"
    assert error.value.active_count == 2
    assert created == []


def test_one_user_can_admit_two_concurrent_active_turns(monkeypatch):
    class FakeDB:
        def __init__(self):
            self.counts = iter((1, 1))

        def execute(self, _query):
            return None

        def scalar(self, _query):
            return next(self.counts)

    class ReachedSessionCreation(Exception):
        pass

    def reached_creation(*_args, **_kwargs):
        raise ReachedSessionCreation

    settings = get_settings().model_copy(
        update={"chat_max_concurrency": 2, "chat_user_max_concurrency": 2}
    )
    service = ChatSessionService(FakeDB(), settings)
    monkeypatch.setattr(
        service,
        "create_session",
        reached_creation,
    )

    with pytest.raises(ReachedSessionCreation):
        service.begin_turn(
            ChatOwner(hf_user_id="same-user", hf_username="same"),
            session_id=None,
            client_message_id="second-request",
            text="A second concurrent turn is allowed",
        )
