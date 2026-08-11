"""Private contributor history and admin audit endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from backend.database.connection import get_database_session
from backend.services.catalog_mutation_service import CatalogMutationService
from backend.services.contribution_audit_service import (
    ContributionAuditEventNotFoundError,
    ContributionAuditRollbackError,
    ContributionAuditService,
)
from backend.utils.auth import require_admin, require_contributor_role

router = APIRouter()


@router.get("/contributions")
def own_contributions(
    cursor: str | None = None,
    limit: int = Query(25, ge=1, le=100),
    actor: dict = Depends(require_contributor_role),
    db: Session = Depends(get_database_session),
):
    return CatalogMutationService(db).list_events(
        actor_subject=actor["hf_subject"], cursor=cursor, limit=limit
    )


@router.get("/admin/catalog-audit")
def catalog_audit(
    cursor: str | None = None,
    limit: int = Query(25, ge=1, le=100),
    actor: dict = Depends(require_admin),
    db: Session = Depends(get_database_session),
):
    return ContributionAuditService(db).list_admin_audit(
        admin_subject=actor["hf_subject"], cursor=cursor, limit=limit
    )


@router.post("/admin/catalog-audit/acknowledge", status_code=204)
def acknowledge_catalog_audit(
    actor: dict = Depends(require_admin),
    db: Session = Depends(get_database_session),
):
    ContributionAuditService(db).acknowledge(actor["hf_subject"])


@router.post("/admin/catalog-audit/{event_id}/rollback")
def rollback_catalog_event(
    event_id: uuid.UUID,
    request: Request,
    actor: dict = Depends(require_admin),
    db: Session = Depends(get_database_session),
):
    request_id = request.headers.get("X-Request-ID") or str(id(request))
    try:
        return ContributionAuditService(db).rollback_event(
            event_id=event_id,
            actor=actor,
            request_id=request_id,
        )
    except ContributionAuditEventNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ContributionAuditRollbackError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
