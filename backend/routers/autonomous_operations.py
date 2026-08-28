"""Admin-only supervision and controls for autonomous operators."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database.connection import get_database_session
from backend.models.api import (
    AutonomousBaselineRequest,
    AutonomousManualModeRequest,
    AutonomousOperationsResponse,
    AutonomousOperatorStateRequest,
)
from backend.services.autonomous_operations_repository import (
    AutonomousOperationsRepository,
    AutonomousStateConflict,
    Operator,
)
from backend.utils.auth import require_admin


router = APIRouter(prefix="/admin/autonomous-operations", tags=["admin"])


def _actor(admin: dict) -> str:
    identity = admin.get("hf_subject") or admin.get("username") or "api-token"
    if not isinstance(identity, str):
        raise HTTPException(status_code=403, detail="Admin identity is invalid")
    return f"admin:{identity}"


def _conflict(db: Session, error: AutonomousStateConflict) -> None:
    db.rollback()
    raise HTTPException(
        status_code=409,
        detail={"code": "stale_revision", "message": str(error)},
    ) from error


@router.get("", response_model=AutonomousOperationsResponse)
def get_autonomous_operations(
    _admin: dict = Depends(require_admin),
    db: Session = Depends(get_database_session),
) -> AutonomousOperationsResponse:
    snapshot = AutonomousOperationsRepository().get_admin_snapshot(db)
    return AutonomousOperationsResponse.model_validate(snapshot)


@router.patch("/manual-mode", response_model=AutonomousOperationsResponse)
def set_manual_mode(
    request: AutonomousManualModeRequest,
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_database_session),
) -> AutonomousOperationsResponse:
    repository = AutonomousOperationsRepository()
    try:
        repository.set_manual_mode(
            db,
            enabled=request.enabled,
            expected_revision=request.expected_revision,
            actor=_actor(admin),
            now=datetime.now(UTC),
        )
        db.commit()
    except AutonomousStateConflict as error:
        _conflict(db, error)
    return AutonomousOperationsResponse.model_validate(
        repository.get_admin_snapshot(db)
    )


@router.patch("/operators/{operator}", response_model=AutonomousOperationsResponse)
def set_operator_state(
    operator: Operator,
    request: AutonomousOperatorStateRequest,
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_database_session),
) -> AutonomousOperationsResponse:
    repository = AutonomousOperationsRepository()
    try:
        repository.set_operator_enabled(
            db,
            operator=operator,
            enabled=request.enabled,
            expected_revision=request.expected_revision,
            actor=_actor(admin),
            now=datetime.now(UTC),
        )
        db.commit()
    except AutonomousStateConflict as error:
        _conflict(db, error)
    return AutonomousOperationsResponse.model_validate(
        repository.get_admin_snapshot(db)
    )


@router.post("/chat-baseline", response_model=AutonomousOperationsResponse)
def qualify_chat_baseline(
    request: AutonomousBaselineRequest,
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_database_session),
) -> AutonomousOperationsResponse:
    repository = AutonomousOperationsRepository()
    try:
        repository.qualify_chat_baseline(
            db,
            sha=request.sha,
            actor=_actor(admin),
            expected_revision=request.expected_revision,
            now=datetime.now(UTC),
        )
        db.commit()
    except AutonomousStateConflict as error:
        _conflict(db, error)
    return AutonomousOperationsResponse.model_validate(
        repository.get_admin_snapshot(db)
    )
