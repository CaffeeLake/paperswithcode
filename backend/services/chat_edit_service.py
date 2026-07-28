"""Transactional state transitions for preparing and activating chat edits."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.models.database import (
    ChatMessageRecord,
    ChatSDKSessionSummary,
    ChatSDKTranscriptEntry,
    ChatSession,
)

if TYPE_CHECKING:
    from backend.services.chat_session_service import TurnAdmission


PREPARING_STATUS = "preparing"
INACTIVE_STATUSES = ("superseded", PREPARING_STATUS)


class ChatEditService:
    """Owns the durable preparation/activation state machine for message edits."""

    def __init__(self, db: Session):
        self.db = db

    def expire_preparation(
        self, session: ChatSession, message: ChatMessageRecord
    ) -> None:
        self._delete_recorded_fork(message)
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

    def _delete_recorded_fork(self, message: ChatMessageRecord) -> None:
        if (
            message.prepared_fork_sdk_session_id is None
            or message.prepared_fork_sdk_project_key is None
        ):
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
