"""Public, unlisted snapshots of the bounded browser chat projection."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.chat import (
    DISPLAY_BLOCKS_ADAPTER,
    ChatShareDetail,
    PublicChatMessage,
)
from backend.models.database import (
    ChatMessageRecord,
    ChatShare,
)
from backend.services.chat_session_service import (
    ChatOwner,
    ChatServiceError,
    ChatSessionService,
)


def _now() -> datetime:
    return datetime.now(UTC)


SNAPSHOT_VERSION = 1
PUBLIC_MESSAGES_ADAPTER = TypeAdapter(list[PublicChatMessage])


def _failure_message(code: str | None) -> str:
    if code == "provider_error":
        return (
            "The model provider failed before completing the response. "
            "You can edit and retry your question."
        )
    if code == "persistence_error":
        return "The response could not be saved. You can edit and retry your question."
    if code == "transcript_mirror_error":
        return "The conversation could not be saved. Please try again in a new chat."
    return "The response did not complete. You can edit and retry your question."


def _public_blocks(row: ChatMessageRecord) -> list[dict]:
    blocks = DISPLAY_BLOCKS_ADAPTER.validate_python(row.display_blocks or [])
    projection: list[dict] = []
    for block in blocks:
        value = block.model_dump(mode="json", exclude_defaults=True)
        if value["kind"] == "tool" and value["status"] == "running":
            value["status"] = "error"
        projection.append(value)
    return projection


def _public_projection(rows: list[ChatMessageRecord]) -> list[PublicChatMessage]:
    public_messages: list[PublicChatMessage] = []
    for row in rows:
        if row.role == "assistant":
            public_messages.append(
                PublicChatMessage(
                    id=uuid.uuid4(),
                    role="assistant",
                    content=row.content,
                    display_blocks=_public_blocks(row),
                    citations=row.citations or [],
                    finish_reason=row.finish_reason,
                )
            )
            continue

        public_messages.append(
            PublicChatMessage(id=uuid.uuid4(), role="user", content=row.content)
        )
        if row.status not in {"error", "interrupted"}:
            continue
        interrupted = row.status == "interrupted"
        public_messages.append(
            PublicChatMessage(
                id=uuid.uuid4(),
                role="assistant",
                content="",
                display_blocks=_public_blocks(row),
                display_state="interrupted" if interrupted else "failed",
                finish_reason="stopped" if interrupted else None,
                error=None if interrupted else _failure_message(row.error_code),
            )
        )
    return public_messages


class ChatShareService:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.sessions = ChatSessionService(db, settings)

    def create_or_refresh(self, owner: ChatOwner, session_id: uuid.UUID) -> ChatShare:
        session = self.sessions._owned(owner, session_id, lock=True)
        if session.active_turn_id:
            raise ChatServiceError(
                "session_busy", 409, "Wait for the response to finish before sharing"
            )
        messages = list(
            self.db.execute(
                select(ChatMessageRecord)
                .where(
                    ChatMessageRecord.session_id == session.id,
                    ChatMessageRecord.status.notin_(["superseded", "preparing"]),
                )
                .order_by(ChatMessageRecord.sequence)
            ).scalars()
        )
        if not messages:
            raise ChatServiceError(
                "empty_chat", 409, "Start the conversation before sharing it"
            )
        public_messages = _public_projection(messages)
        snapshot = PUBLIC_MESSAGES_ADAPTER.dump_python(public_messages, mode="json")
        share = self.db.execute(
            select(ChatShare).where(ChatShare.chat_session_id == session.id)
        ).scalar_one_or_none()
        if share is None:
            share = ChatShare(
                id=uuid.uuid4(),
                chat_session_id=session.id,
                snapshot_version=SNAPSHOT_VERSION,
                messages=snapshot,
                updated_at=_now(),
            )
            self.db.add(share)
        else:
            share.snapshot_version = SNAPSHOT_VERSION
            share.messages = snapshot
            share.updated_at = _now()
        self.db.flush()
        return share

    def get_public(self, raw_share_id: str) -> ChatShareDetail:
        try:
            share_id = uuid.UUID(raw_share_id)
        except (TypeError, ValueError):
            raise ChatServiceError(
                "share_not_found", 404, "Shared conversation not found"
            ) from None
        share = self.db.execute(
            select(ChatShare).where(ChatShare.id == share_id)
        ).scalar_one_or_none()
        if share is None:
            raise ChatServiceError(
                "share_not_found", 404, "Shared conversation not found"
            )
        try:
            if share.snapshot_version != SNAPSHOT_VERSION:
                raise ValueError("unsupported snapshot version")
            public_messages = PUBLIC_MESSAGES_ADAPTER.validate_python(share.messages)
        except (TypeError, ValueError):
            raise ChatServiceError(
                "share_not_found", 404, "Shared conversation not found"
            ) from None

        return ChatShareDetail(
            share_id=share.id,
            created_at=share.created_at,
            updated_at=share.updated_at,
            messages=public_messages,
        )
