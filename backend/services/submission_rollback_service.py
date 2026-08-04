"""Compensating rollback for entities created by approved submissions."""

from sqlalchemy.orm import Session

from backend.models.database import (
    CatalogMutationEvent,
    Conference,
    Dataset,
    Method,
    Metric,
    Paper,
    Task,
)
from backend.services.catalog_mutation_service import (
    CatalogMutationService,
    canonical_hash,
)
from backend.services.pending_edit_service import PendingEditService
from backend.utils.exceptions import DatabaseError


class SubmissionRollbackService:
    MODEL_BY_TYPE = {
        "paper": Paper,
        "task": Task,
        "method": Method,
        "dataset": Dataset,
        "metric": Metric,
        "conference": Conference,
    }

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def entity_type(event: CatalogMutationEvent) -> str:
        prefix = "submission_created_"
        if not event.entity_type.startswith(prefix):
            raise DatabaseError("This is not a created-entity submission event")
        entity_type = event.entity_type.removeprefix(prefix)
        if entity_type not in SubmissionRollbackService.MODEL_BY_TYPE:
            raise DatabaseError("Unsupported submission entity type")
        return entity_type

    def snapshot(self, event: CatalogMutationEvent, *, lock: bool = False):
        entity_type = self.entity_type(event)
        entity_id = int(event.entity_id)
        model = self.MODEL_BY_TYPE[entity_type]
        query = self.db.query(model).filter(model.id == entity_id)
        row = query.with_for_update().first() if lock else query.first()
        if row is None:
            return {}
        return PendingEditService(self.db)._created_entity_snapshot(
            entity_type, entity_id
        )

    def rollback(self, *, event: CatalogMutationEvent, actor: dict, request_id: str):
        entity_type = self.entity_type(event)
        entity_id = int(event.entity_id)
        model = self.MODEL_BY_TYPE[entity_type]

        def remove() -> None:
            row = self.db.get(model, entity_id)
            if row is None:
                raise DatabaseError("Created entity no longer exists")
            self.db.delete(row)

        _, rollback_event, _ = CatalogMutationService(self.db).mutate(
            actor=actor,
            operation="rollback",
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            request_payload={"rollback_of": str(event.id)},
            idempotency_key=f"rollback:{event.id}",
            expected_version=canonical_hash(event.after_snapshot),
            snapshot=lambda: self.snapshot(event, lock=True),
            apply=remove,
            request_id=request_id,
            rollback_of_event_id=event.id,
        )
        return rollback_event
