"""Atomic durable admission bridge for the existing chat transaction."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import ChatTurnJob
from backend.services.chat_turn_job_repository import (
    ChatTurnJobRepository,
    IdempotencyMismatch,
    TurnAdmissionPreflight,
)


@dataclass(frozen=True, slots=True)
class DurableAdmissionPreflight:
    request_id: str
    requested_session_id: uuid.UUID | None
    existing_job: ChatTurnJob | None
    repository_preflight: TurnAdmissionPreflight


class ChatTurnAdmissionCoordinator:
    """Compose durable ownership with the caller's session transaction."""

    def __init__(
        self,
        db: Session,
        settings: Settings,
        *,
        repository: ChatTurnJobRepository | None = None,
    ):
        self.db = db
        self.settings = settings
        self.repository = repository or ChatTurnJobRepository()

    def preflight(
        self,
        *,
        hf_user_id: str,
        request_id: str,
        requested_session_id: uuid.UUID | None,
    ) -> DurableAdmissionPreflight:
        result = self.repository.preflight_admission(
            self.db,
            hf_user_id=hf_user_id,
            request_id=request_id,
            chat_session_id=requested_session_id,
            emergency_capacity=self.settings.chat_max_concurrency,
        )
        return DurableAdmissionPreflight(
            request_id=request_id,
            requested_session_id=requested_session_id,
            existing_job=result.existing_job,
            repository_preflight=result,
        )

    def admit(
        self,
        preflight: DurableAdmissionPreflight,
        *,
        turn_id: uuid.UUID,
        chat_session_id: uuid.UUID,
        hf_user_id: str,
        revision: int,
        dispatch_route: str,
        app_release_id: str,
        worker_contract_version: str,
        now: datetime,
    ) -> ChatTurnJob:
        admitted = self.repository.admit_preflighted(
            self.db,
            preflight=preflight.repository_preflight,
            turn_id=turn_id,
            chat_session_id=chat_session_id,
            hf_user_id=hf_user_id,
            request_id=preflight.request_id,
            revision=revision,
            dispatch_class="interactive",
            dispatch_route=dispatch_route,
            app_release_id=app_release_id,
            worker_contract_version=worker_contract_version,
            now=now,
        )
        return admitted.job

    def validate_replay(
        self,
        preflight: DurableAdmissionPreflight,
        *,
        turn_id: uuid.UUID,
        chat_session_id: uuid.UUID,
        hf_user_id: str,
        revision: int,
        dispatch_route: str,
        app_release_id: str,
        worker_contract_version: str,
        now: datetime,
    ) -> ChatTurnJob:
        if preflight.existing_job is None:
            raise IdempotencyMismatch("Durable replay has no persisted turn job")
        return self.admit(
            preflight,
            turn_id=turn_id,
            chat_session_id=chat_session_id,
            hf_user_id=hf_user_id,
            revision=revision,
            dispatch_route=dispatch_route,
            app_release_id=app_release_id,
            worker_contract_version=worker_contract_version,
            now=now,
        )
