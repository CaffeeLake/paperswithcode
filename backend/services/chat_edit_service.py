"""Transactional state transitions for preparing and activating chat edits."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.models.database import (
    ChatMessageRecord,
    ChatPiPreparedFork,
    ChatPiSession,
    ChatPiTranscriptEntry,
    ChatSDKSessionSummary,
    ChatSDKTranscriptEntry,
    ChatSession,
)

if TYPE_CHECKING:
    from backend.services.chat_session_service import TurnAdmission


PREPARING_STATUS = "preparing"
INACTIVE_STATUSES = ("superseded", PREPARING_STATUS)


def _projection_bytes(message: ChatMessageRecord) -> int:
    content = getattr(message, "content", "")
    if message.role == "user":
        effective_prompt = getattr(message, "effective_prompt", None)
        if effective_prompt is None:
            return len(content.encode())
        mentions = len(
            json.dumps(
                getattr(message, "paper_mentions", None) or [],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode()
        )
        return len(content.encode()) + len(effective_prompt.encode()) + mentions
    payload = len(
        json.dumps(
            getattr(message, "display_blocks", None) or [],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
    )
    payload += len(
        json.dumps(
            getattr(message, "citations", None) or [],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
    )
    payload += len(
        json.dumps(
            getattr(message, "followups", None) or [],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
    )
    return len(content.encode()) + payload


class ChatEditService:
    """Owns the durable preparation/activation state machine for message edits."""

    def __init__(self, db: Session):
        self.db = db

    def expire_preparation(
        self, session: ChatSession, message: ChatMessageRecord
    ) -> None:
        self._delete_recorded_fork(message)
        if hasattr(session, "projection_bytes"):
            session.projection_bytes = max(
                0, session.projection_bytes - _projection_bytes(message)
            )
        message.status = "superseded"
        message.error_code = "edit_prepare_lease_expired"
        if session.active_turn_id == message.turn_id:
            self._release_turn(session)

    def record_fork(
        self,
        session: ChatSession,
        admission: TurnAdmission,
        fork_sdk_session_id: uuid.UUID,
        project_key: str,
    ) -> bool:
        prepared = self.db.get(ChatMessageRecord, admission.user_message_id)
        prepared = self._current_preparation(session, admission, prepared)
        if prepared is None:
            return False
        prepared.prepared_fork_sdk_session_id = fork_sdk_session_id
        prepared.prepared_fork_sdk_project_key = project_key
        return True

    def activate(
        self,
        session: ChatSession,
        admission: TurnAdmission,
        replacement_sdk_session_id: uuid.UUID | None,
        project_key: str,
    ) -> bool:
        prepared = self.db.get(ChatMessageRecord, admission.user_message_id)
        prepared = self._current_preparation(session, admission, prepared)
        if (
            not admission.is_replacement
            or prepared is None
            or session.sdk_session_id != admission.sdk_session_id
            or session.sdk_project_key != admission.sdk_project_key
            or prepared.prepared_fork_sdk_session_id != replacement_sdk_session_id
            or prepared.prepared_fork_sdk_project_key
            != (project_key if replacement_sdk_session_id else None)
        ):
            return False

        target = self.db.get(ChatMessageRecord, admission.replacement_target_id)
        target = self._current_target(session, admission, target)
        if target is None:
            return False

        old_suffix = self._active_suffix(session.id, target.sequence, prepared.id)
        if tuple(message.id for message in old_suffix) != (
            admission.replacement_active_suffix_ids
        ):
            return False

        for message in old_suffix:
            message.status = "superseded"
            if hasattr(session, "projection_bytes"):
                session.projection_bytes = max(
                    0, session.projection_bytes - _projection_bytes(message)
                )
        prepared.status = "generating"
        prepared.error_code = None
        self._clear_recorded_fork(prepared)
        self._replace_transcript(session, replacement_sdk_session_id, project_key)
        self.db.flush()
        session.message_count = (
            self.db.scalar(
                select(func.count())
                .select_from(ChatMessageRecord)
                .where(
                    ChatMessageRecord.session_id == session.id,
                    ChatMessageRecord.status.notin_(INACTIVE_STATUSES),
                )
            )
            or 0
        )
        session.updated_at = datetime.now(UTC)
        return True

    def abort(
        self,
        session: ChatSession,
        admission: TurnAdmission,
        code: str,
    ) -> None:
        prepared = self.db.get(ChatMessageRecord, admission.user_message_id)
        if prepared and prepared.status == PREPARING_STATUS:
            self._delete_recorded_fork(prepared)
            if hasattr(session, "projection_bytes"):
                session.projection_bytes = max(
                    0, session.projection_bytes - _projection_bytes(prepared)
                )
            prepared.status = "superseded"
            prepared.error_code = code
        if session.active_turn_id == admission.turn_id:
            self._release_turn(session)
            session.updated_at = datetime.now(UTC)

    def fail_preparation(
        self,
        session: ChatSession,
        message: ChatMessageRecord,
        code: str,
    ) -> bool:
        if message.status != PREPARING_STATUS:
            return False
        self._delete_recorded_fork(message)
        if hasattr(session, "projection_bytes"):
            session.projection_bytes = max(
                0, session.projection_bytes - _projection_bytes(message)
            )
        message.status = "superseded"
        message.error_code = code
        self._release_turn(session)
        session.updated_at = datetime.now(UTC)
        return True

    @staticmethod
    def _current_preparation(
        session: ChatSession,
        admission: TurnAdmission,
        prepared: ChatMessageRecord | None,
    ) -> ChatMessageRecord | None:
        if (
            prepared
            and prepared.status == PREPARING_STATUS
            and session.active_turn_id == admission.turn_id
            and session.sdk_session_id == admission.sdk_session_id
        ):
            return prepared
        return None

    @staticmethod
    def _current_target(
        session: ChatSession,
        admission: TurnAdmission,
        target: ChatMessageRecord | None,
    ) -> ChatMessageRecord | None:
        if (
            target
            and target.session_id == session.id
            and target.role == "user"
            and target.status not in INACTIVE_STATUSES
            and target.sequence == admission.replacement_target_sequence
            and target.revision == admission.replacement_target_revision
        ):
            return target
        return None

    def _active_suffix(
        self, session_id: uuid.UUID, sequence: int, prepared_id: uuid.UUID
    ) -> list[ChatMessageRecord]:
        return list(
            self.db.execute(
                select(ChatMessageRecord)
                .where(
                    ChatMessageRecord.session_id == session_id,
                    ChatMessageRecord.sequence >= sequence,
                    ChatMessageRecord.id != prepared_id,
                    ChatMessageRecord.status.notin_(INACTIVE_STATUSES),
                )
                .order_by(ChatMessageRecord.sequence)
            ).scalars()
        )

    def _replace_transcript(
        self,
        session: ChatSession,
        sdk_session_id: uuid.UUID | None,
        project_key: str,
    ) -> None:
        if getattr(session, "agent_harness", "claude") == "pi":
            self._activate_pi_transcript(session, sdk_session_id)
            return
        session.sdk_session_id = sdk_session_id
        session.sdk_project_key = project_key if sdk_session_id else None
        session.transcript_status = "ready" if sdk_session_id else "pending"
        session.transcript_bytes = 0
        if sdk_session_id:
            session.transcript_bytes = (
                self.db.scalar(
                    select(
                        func.coalesce(func.sum(ChatSDKTranscriptEntry.byte_size), 0)
                    ).where(
                        ChatSDKTranscriptEntry.project_key == project_key,
                        ChatSDKTranscriptEntry.sdk_session_id == sdk_session_id,
                    )
                )
                or 0
            )

    def _activate_pi_transcript(
        self, session: ChatSession, fork_session_id: uuid.UUID | None
    ) -> None:
        active = self.db.execute(
            select(ChatPiSession)
            .where(ChatPiSession.chat_session_id == session.id)
            .with_for_update()
        ).scalar_one_or_none()
        if fork_session_id is None:
            if active is not None:
                self.db.delete(active)
            session.sdk_session_id = None
            session.sdk_project_key = None
            session.transcript_status = "pending"
            session.transcript_bytes = 0
            return
        prepared = self.db.execute(
            select(ChatPiPreparedFork)
            .where(
                ChatPiPreparedFork.chat_session_id == session.id,
                ChatPiPreparedFork.fork_session_id == fork_session_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if prepared is None:
            raise RuntimeError("prepared Pi transcript fork is missing")
        if active is not None:
            self.db.delete(active)
            self.db.flush()
        self.db.add(
            ChatPiSession(
                agent_session_id=fork_session_id,
                chat_session_id=session.id,
                current_leaf_id=prepared.boundary_entry_id,
                entry_count=prepared.entry_count,
                byte_size=prepared.byte_size,
                format_version=prepared.format_version,
            )
        )
        self.db.flush()
        for ordinal, entry in enumerate(prepared.entries):
            entry_type = str(entry.get("type") or "")
            entry_id = None if entry_type == "session" else entry.get("id")
            parent_entry_id = None if entry_type == "session" else entry.get("parentId")
            byte_size = len(
                json.dumps(entry, ensure_ascii=False, separators=(",", ":")).encode()
            )
            self.db.add(
                ChatPiTranscriptEntry(
                    agent_session_id=fork_session_id,
                    ordinal=ordinal,
                    entry_id=entry_id,
                    parent_entry_id=parent_entry_id,
                    entry_type=entry_type,
                    entry=entry,
                    byte_size=byte_size,
                )
            )
        self.db.delete(prepared)
        session.sdk_session_id = fork_session_id
        session.sdk_project_key = None
        session.transcript_status = "ready"
        session.transcript_bytes = prepared.byte_size

    def _delete_recorded_fork(self, message: ChatMessageRecord) -> None:
        if (
            message.prepared_fork_sdk_session_id is None
            or message.prepared_fork_sdk_project_key is None
        ):
            return
        session = (
            self.db.get(ChatSession, message.session_id)
            if hasattr(self.db, "get")
            else None
        )
        if session and getattr(session, "agent_harness", "claude") == "pi":
            self.db.execute(
                delete(ChatPiPreparedFork).where(
                    ChatPiPreparedFork.chat_session_id == session.id,
                    ChatPiPreparedFork.fork_session_id
                    == message.prepared_fork_sdk_session_id,
                )
            )
            self._clear_recorded_fork(message)
            return
        self.db.execute(
            delete(ChatSDKTranscriptEntry).where(
                ChatSDKTranscriptEntry.project_key
                == message.prepared_fork_sdk_project_key,
                ChatSDKTranscriptEntry.sdk_session_id
                == message.prepared_fork_sdk_session_id,
            )
        )
        self.db.execute(
            delete(ChatSDKSessionSummary).where(
                ChatSDKSessionSummary.project_key
                == message.prepared_fork_sdk_project_key,
                ChatSDKSessionSummary.sdk_session_id
                == message.prepared_fork_sdk_session_id,
            )
        )
        self._clear_recorded_fork(message)

    @staticmethod
    def _clear_recorded_fork(message: ChatMessageRecord) -> None:
        message.prepared_fork_sdk_session_id = None
        message.prepared_fork_sdk_project_key = None

    @staticmethod
    def _release_turn(session: ChatSession) -> None:
        session.active_turn_id = None
        session.active_turn_expires_at = None
