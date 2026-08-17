"""Authenticated user feedback for Langfuse chat traces."""

from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import ChatMessageRecord, ChatSession
from backend.services.chat_tracing_service import configured_chat_client


class ChatFeedbackUnavailable(Exception):
    """Raised when feedback cannot be delivered to the configured trace store."""


class ChatFeedbackService:
    SCORE_NAME = "user-thumbs"

    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    def submit(
        self,
        *,
        owner_id: str,
        assistant_message_id: uuid.UUID,
        value: bool,
        comment: str | None = None,
    ) -> bool:
        message = self.db.execute(
            select(ChatMessageRecord.turn_id, ChatMessageRecord.session_id)
            .join(ChatSession, ChatSession.id == ChatMessageRecord.session_id)
            .where(
                ChatMessageRecord.id == assistant_message_id,
                ChatMessageRecord.role == "assistant",
                ChatMessageRecord.status == "complete",
                ChatSession.hf_user_id == owner_id,
            )
        ).one_or_none()
        if message is None:
            return False

        trace_id = self.db.execute(
            select(ChatMessageRecord.langfuse_trace_id)
            .where(
                ChatMessageRecord.turn_id == message.turn_id,
                ChatMessageRecord.session_id == message.session_id,
                ChatMessageRecord.role == "user",
            )
            .order_by(ChatMessageRecord.sequence.desc())
            .limit(1)
        ).scalar_one_or_none()
        if not trace_id:
            raise ChatFeedbackUnavailable

        client = configured_chat_client(self.settings)
        if client is None:
            raise ChatFeedbackUnavailable

        score_id = hashlib.sha256(
            f"{self.settings.environment}:{self.SCORE_NAME}:{assistant_message_id}".encode()
        ).hexdigest()[:32]
        normalized_comment = None
        if comment is not None:
            normalized_comment = comment.strip() or None
        client.create_score(
            trace_id=trace_id,
            score_id=score_id,
            name=self.SCORE_NAME,
            value=1.0 if value else 0.0,
            data_type="BOOLEAN",
            comment=normalized_comment,
            metadata={"assistant_message_id": str(assistant_message_id)},
        )
        return True
