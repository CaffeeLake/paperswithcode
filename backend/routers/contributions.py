"""Private contributor history and admin audit endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from backend.database.connection import get_database_session
from backend.services.catalog_mutation_service import (
    CatalogMutationService,
    canonical_hash,
    json_safe,
)
from backend.models.database import CatalogMutationEvent
from backend.services.evaluation_curation_service import EvaluationCurationService
from backend.services.paper_curation_service import PaperCurationService
from backend.services.submission_rollback_service import SubmissionRollbackService
from backend.utils.auth import require_admin, require_contributor_role
from backend.utils.exceptions import DatabaseError, PaperNotFoundError

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
    service = CatalogMutationService(db)
    page = service.list_events(actor_subject=None, cursor=cursor, limit=limit)
    events_by_id = {
        str(row.id): row
        for row in db.query(CatalogMutationEvent)
        .filter(
            CatalogMutationEvent.id.in_(
                [uuid.UUID(item["id"]) for item in page["events"]]
            )
        )
        .all()
    }
    for item in page["events"]:
        item["rollback_eligible"] = _rollback_eligible(db, events_by_id[item["id"]])
    page["unread_contributor_count"] = service.unread_count(actor["hf_subject"])
    return page


def _rollback_eligible(db: Session, event: CatalogMutationEvent) -> bool:
    if event.operation == "rollback":
        return False
    try:
        if event.entity_type.startswith("paper_"):
            section = event.entity_type.removeprefix("paper_")
            current = PaperCurationService(db).snapshot(int(event.entity_id), section)
        elif event.entity_type == "evaluation":
            service = EvaluationCurationService(db)
            if event.entity_id.startswith("paper:"):
                current = service._paper_evaluations(
                    int(event.entity_id.split(":", 1)[1])
                )
            else:
                current = service.snapshot(int(event.entity_id))
        elif event.entity_type.startswith("submission_created_"):
            current = SubmissionRollbackService(db).snapshot(event)
        else:
            return False
    except (ValueError, PaperNotFoundError, DatabaseError):
        return False
    return canonical_hash(json_safe(current)) == canonical_hash(event.after_snapshot)


@router.post("/admin/catalog-audit/acknowledge", status_code=204)
def acknowledge_catalog_audit(
    actor: dict = Depends(require_admin),
    db: Session = Depends(get_database_session),
):
    CatalogMutationService(db).acknowledge(actor["hf_subject"])


@router.post("/admin/catalog-audit/{event_id}/rollback")
def rollback_catalog_event(
    event_id: uuid.UUID,
    request: Request,
    actor: dict = Depends(require_admin),
    db: Session = Depends(get_database_session),
):
    event = db.get(CatalogMutationEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Audit event not found")
    if event.operation == "rollback":
        raise HTTPException(
            status_code=409, detail="Rollback events cannot be rolled back"
        )
    request_id = request.headers.get("X-Request-ID") or str(id(request))
    if event.entity_type == "evaluation":
        rollback = EvaluationCurationService(db).rollback(
            event=event, actor=actor, request_id=request_id
        )
    elif event.entity_type.startswith("paper_"):
        rollback = PaperCurationService(db).rollback(
            event=event, actor=actor, request_id=request_id
        )
    elif event.entity_type.startswith("submission_created_"):
        rollback = SubmissionRollbackService(db).rollback(
            event=event, actor=actor, request_id=request_id
        )
    else:
        raise HTTPException(
            status_code=409, detail="This event type is not rollback eligible"
        )
    return CatalogMutationService.serialize_event(rollback)
