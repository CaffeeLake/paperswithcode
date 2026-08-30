"""Read-only proof that the configured external Pi endpoint can accept work."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from backend.config import Settings
from backend.database.connection import db_manager
from backend.services.chat_external_pi_shadow import ExternalPiWorkerControlClient
from backend.services.chat_external_worker_registry import (
    ChatExternalWorkerRepository,
    ExternalWorkerClaim,
    WorkerLeaseUnavailable,
)


async def validate_external_pi_readiness(settings: Settings) -> None:
    async with httpx.AsyncClient() as http:
        status = await ExternalPiWorkerControlClient(
            base_url=settings.chat_external_pi_worker_url,
            token=settings.chat_external_pi_worker_token,
            http=http,
            timeout_seconds=5.0,
        ).status()
    if (
        status.worker_generation is None
        or status.state != "ready"
        or status.release_id != settings.release_id
        or status.protocol != settings.chat_external_pi_worker_contract_version
        or status.active_sessions >= status.maximum_sessions
    ):
        raise WorkerLeaseUnavailable("External worker is not ready")
    claim = ExternalWorkerClaim(
        worker_id=status.worker_id,
        instance_id=status.instance_id,
        generation=status.worker_generation,
        release_id=status.release_id,
        contract_version=status.protocol,
    )
    with db_manager.session_local() as db:
        ChatExternalWorkerRepository(
            environment=settings.environment
        ).require_endpoint_ready(
            db,
            claim=claim,
            active_sessions=status.active_sessions,
            maximum_sessions=status.maximum_sessions,
            configured_maximum_sessions=settings.chat_external_pi_worker_max_sessions,
            now=datetime.now(UTC),
        )
