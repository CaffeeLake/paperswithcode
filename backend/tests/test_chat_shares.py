from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.responses import Response

from backend.config import get_settings
from backend.database.connection import get_database_session
from backend.main import create_app
from backend.models.chat import ChatShareDetail, PublicChatMessage
from backend.models.database import ChatShare
from backend.routers.chat import get_shared_chat
from backend.services.chat_session_service import ChatOwner, ChatServiceError
from backend.services.chat_share_service import ChatShareService


class _Result:
    def __init__(self, value=None, values=None):
        self.value = value
        self.values = values or []

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        return self

    def __iter__(self):
        return iter(self.values)


class _ShareDB:
    def __init__(self, session, messages):
        self.session = session
        self.source_messages = messages
        self.share = None
        self.manifest = []

    def execute(self, statement):
        sql = str(statement)
        if "FROM chat_sessions" in sql:
            return _Result(self.session)
        if "FROM chat_messages" in sql:
            return _Result(values=self.source_messages)
        if "FROM chat_shares" in sql:
            return _Result(self.share)
        if sql.startswith("DELETE FROM chat_share_messages"):
            self.manifest = []
            return _Result()
        raise AssertionError(sql)

    def add(self, value):
        if isinstance(value, ChatShare):
            self.share = value

    def add_all(self, values):
        self.manifest = list(values)

    def flush(self):
        if self.share and self.share.created_at is None:
            self.share.created_at = datetime.now(UTC)


def _session(*, busy=False):
    return SimpleNamespace(
        id=uuid.uuid4(),
        hf_user_id="hf-owner",
        active_turn_id=uuid.uuid4() if busy else None,
        active_turn_expires_at=datetime.now(UTC) + timedelta(minutes=1)
        if busy
        else None,
    )


def _row(sequence: int):
    return SimpleNamespace(id=uuid.uuid4(), sequence=sequence)


def test_create_or_refresh_retains_capability_and_replaces_ordered_manifest():
    session = _session()
    first = _row(1)
    second = _row(2)
    db = _ShareDB(session, [first, second])
    service = ChatShareService(db, get_settings())
    owner = ChatOwner(hf_user_id="hf-owner", hf_username="owner")

    created = service.create_or_refresh(owner, session.id)
    first_share_id = created.id
    assert [entry.message_id for entry in db.manifest] == [first.id, second.id]
    assert [entry.position for entry in db.manifest] == [0, 1]

    third = _row(3)
    db.source_messages = [first, third]
    refreshed = service.create_or_refresh(owner, session.id)
    assert refreshed.id == first_share_id
    assert [entry.message_id for entry in db.manifest] == [first.id, third.id]
    assert refreshed.updated_at >= created.created_at


@pytest.mark.parametrize(
    ("session", "messages", "code"),
    [(_session(busy=True), [_row(1)], "session_busy"), (_session(), [], "empty_chat")],
)
def test_create_share_rejects_busy_and_empty_chats(session, messages, code):
    service = ChatShareService(_ShareDB(session, messages), get_settings())
    with pytest.raises(ChatServiceError) as exc_info:
        service.create_or_refresh(
            ChatOwner(hf_user_id="hf-owner", hf_username="owner"), session.id
        )
    assert exc_info.value.code == code


class _PublicDB:
    def __init__(self, share):
        self.share = share

    def execute(self, statement):
        assert "FROM chat_shares" in str(statement)
        params = statement.compile().params
        requested = next(iter(params.values()), None)
        if self.share is not None and requested != self.share.id:
            return _Result(None)
        return _Result(self.share)


def test_public_projection_preserves_bounded_blocks_and_omits_private_fields():
    user_id = uuid.uuid4()
    assistant_id = uuid.uuid4()
    tool = {
        "kind": "tool",
        "schema_version": 2,
        "id": "tool-1",
        "name": "Bash",
        "args": {"command": "pwc task list"},
        "status": "running",
        "content": [{"type": "text", "text": "bounded output", "truncated": False}],
        "metadata": {"exit_code": None, "output_truncated": False},
    }
    citation = {
        "position": 0,
        "route_id": "2501.00001",
        "title": "A paper",
        "source_url": "https://arxiv.org/abs/2501.00001",
    }
    user = SimpleNamespace(
        id=user_id,
        role="user",
        content="private-title-is-not-here",
        status="complete",
        display_blocks=[],
        citations=[],
        error_code=None,
    )
    assistant = SimpleNamespace(
        id=assistant_id,
        role="assistant",
        content="Answer",
        status="complete",
        display_blocks=[
            {"kind": "reasoning", "text": "bounded reasoning"},
            tool,
            {
                "kind": "answer",
                "text": "Answer",
                "done": True,
                "citations": [citation],
            },
        ],
        citations=[citation],
        finish_reason="tool_limit",
        model_route="secret-provider-route",
        followups=["private followup"],
        error_code=None,
    )
    now = datetime.now(UTC)
    share = SimpleNamespace(
        id=uuid.uuid4(),
        created_at=now,
        updated_at=now,
        messages=[
            SimpleNamespace(position=0, message=user),
            SimpleNamespace(position=1, message=assistant),
        ],
    )

    detail = ChatShareService(_PublicDB(share), get_settings()).get_public(
        str(share.id)
    )
    payload = detail.model_dump(mode="json")

    assert payload["messages"][1]["finish_reason"] == "tool_limit"
    assert payload["messages"][1]["display_blocks"][1]["status"] == "error"
    serialized = str(payload)
    assert "secret-provider-route" not in serialized
    assert "private followup" not in serialized
    assert set(payload) == {"share_id", "created_at", "updated_at", "messages"}
    assert "title" not in payload


@pytest.mark.parametrize("status", ["error", "interrupted"])
def test_failed_and_interrupted_rows_expand_to_stable_public_assistant(status):
    row = SimpleNamespace(
        id=uuid.uuid4(),
        role="user",
        content="Question",
        status=status,
        display_blocks=[{"kind": "reasoning", "text": "Partial"}],
        citations=[],
        error_code="provider_error",
    )
    now = datetime.now(UTC)
    share = SimpleNamespace(
        id=uuid.uuid4(),
        created_at=now,
        updated_at=now,
        messages=[SimpleNamespace(position=0, message=row)],
    )
    messages = (
        ChatShareService(_PublicDB(share), get_settings())
        .get_public(str(share.id))
        .messages
    )

    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[1].display_state == (
        "interrupted" if status == "interrupted" else "failed"
    )
    assert messages[1].display_blocks[0].kind == "reasoning"
    assert (messages[1].finish_reason == "stopped") == (status == "interrupted")
    assert (messages[1].error is not None) == (status == "error")


def test_missing_and_malformed_share_ids_have_same_generic_error():
    service = ChatShareService(_PublicDB(None), get_settings())
    errors = []
    for share_id in ("not-a-uuid", str(uuid.uuid4())):
        with pytest.raises(ChatServiceError) as exc_info:
            service.get_public(share_id)
        errors.append((exc_info.value.status_code, str(exc_info.value)))
    assert errors == [(404, "Shared conversation not found")] * 2


def test_public_route_sets_no_store_without_an_authentication_dependency():
    now = datetime.now(UTC)
    share = SimpleNamespace(
        id=uuid.uuid4(),
        created_at=now,
        updated_at=now,
        messages=[],
    )
    response = Response()
    detail = get_shared_chat(str(share.id), response, _PublicDB(share), get_settings())

    assert detail.share_id == share.id
    assert response.headers["Cache-Control"] == "no-store"


def test_public_http_get_is_anonymous_and_no_store(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "chat_enabled", True)
    monkeypatch.setattr(settings, "hf_token", "test-token")
    now = datetime.now(UTC)
    share = SimpleNamespace(
        id=uuid.uuid4(),
        created_at=now,
        updated_at=now,
        messages=[],
    )
    app = create_app()
    app.dependency_overrides[get_database_session] = lambda: _PublicDB(share)

    with TestClient(app) as client:
        response = client.get(f"/api/v1/chat/shares/{share.id}")
        missing = client.get(f"/api/v1/chat/shares/{uuid.uuid4()}")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert missing.status_code == 404
    assert missing.headers["Cache-Control"] == "no-store"
    assert missing.json()["detail"]["message"] == "Shared conversation not found"


def test_public_models_forbid_unexpected_private_fields():
    with pytest.raises(ValidationError):
        PublicChatMessage(
            id=uuid.uuid4(),
            role="user",
            content="Question",
            model="private",
        )
    with pytest.raises(ValidationError):
        ChatShareDetail(
            share_id=uuid.uuid4(),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            messages=[],
            title="Private title",
        )
