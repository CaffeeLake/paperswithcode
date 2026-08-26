"""Durable Stop workflow across database and sandbox control boundaries."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from backend.config import Settings
from backend.services.chat_sandbox_lease_lifecycle_coordinator import (
    SandboxCleanupUnverified,
)
from backend.services.chat_sandbox_provider import SandboxError
from backend.services.chat_sandbox_service import SandboxSessionManager
from backend.services.chat_sandbox_worker_transport import WorkerCancelStatus
from backend.services.chat_session_service import ChatOwner, ChatSessionService

logger = logging.getLogger(__name__)


class ChatTurnCancellationCoordinator:
    """Commit durable cancellation before signalling current runner control."""

    def __init__(
        self,
        db: Session,
        settings: Settings,
        manager: SandboxSessionManager,
    ) -> None:
        self.db = db
        self.settings = settings
        self.manager = manager
        self.sessions = ChatSessionService(db, settings)

    async def cancel(self, owner: ChatOwner, session_id: uuid.UUID) -> None:
        request = self.sessions.request_cancel(owner, session_id)
        self.db.commit()
        if request is None:
            return
        status: WorkerCancelStatus | None = None
        try:
            status = await self.manager.cancel_status(session_id, request.turn_id)
        except (SandboxError, SandboxCleanupUnverified):
            logger.exception(
                "Durable chat cancel delivery failed",
                extra={"chat_session_id": str(session_id)},
            )
        if status is WorkerCancelStatus.COMPLETED:
            return
        try:
            await self.manager.terminate(
                session_id, failure_code="cancel_control_missing"
            )
        except (SandboxError, SandboxCleanupUnverified):
            logger.exception(
                "Durable chat cancel termination failed",
                extra={"chat_session_id": str(session_id)},
            )
        self.sessions.interrupt_cancel_without_control(owner, request)
        self.db.commit()
