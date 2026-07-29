"""Audited contributor/admin evaluation mutations."""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.models.database import (
    CatalogMutationEvent,
    Evaluation as DBEvaluation,
    Paper as DBPaper,
)
from backend.services.catalog_mutation_service import (
    CatalogMutationService,
    canonical_hash,
)
from backend.services.evaluation_service import EvaluationService
from backend.utils.exceptions import DatabaseError


EVALUATION_FIELDS = (
    "id",
    "paper_id",
    "task_id",
    "dataset_id",
    "model_name",
    "harness",
    "methodology",
    "metrics",
    "uses_additional_data",
    "is_open",
    "best_rank",
    "best_metric",
    "evaluated_on",
    "external_source_url",
    "source_url",
    "external",
    "num_parameters",
    "hf_model_url",
    "created_at",
    "updated_at",
)


class EvaluationCurationService:
    def __init__(self, db: Session):
        self.db = db
        self.service = EvaluationService(db)

    def snapshot(self, evaluation_id: int, *, lock: bool = False) -> dict | None:
        query = self.db.query(DBEvaluation).filter(DBEvaluation.id == evaluation_id)
        row = query.with_for_update().first() if lock else query.first()
        if row is None:
            return None
        return {field: getattr(row, field) for field in EVALUATION_FIELDS}

    def state(self, evaluation_id: int) -> dict:
        snapshot = self.snapshot(evaluation_id)
        if snapshot is None:
            raise DatabaseError(f"Evaluation {evaluation_id} not found")
        return {
            "evaluation_id": evaluation_id,
            "version": canonical_hash(snapshot),
        }

    def collection_state(self, paper_id: int) -> dict:
        return {
            "paper_id": paper_id,
            "version": canonical_hash(self._paper_evaluations(paper_id)),
        }

    def create(self, *, payload: dict, mutation: dict):
        created_id: list[int] = []

        def apply() -> None:
            result = self.service.create_evaluation(**payload, commit=False)
            created_id.append(int(result.id))

        # Creation has no stale row. The stable entity is the paper-scoped
        # evaluation collection loaded by the editor.
        paper_id = int(payload["paper_id"])

        def snapshot():
            return self._paper_evaluations(paper_id, lock=True)

        after, event, replayed = CatalogMutationService(self.db).mutate(
            operation="create",
            entity_type="evaluation",
            entity_id=f"paper:{paper_id}",
            request_payload=payload,
            snapshot=snapshot,
            apply=apply,
            **mutation,
        )
        if not created_id:
            before_ids = {int(row["id"]) for row in (event.before_snapshot or [])}
            added = [
                int(row["id"])
                for row in (after or [])
                if int(row["id"]) not in before_ids
            ]
            if len(added) != 1:
                raise DatabaseError("Could not resolve idempotent evaluation result")
            created_id.append(added[0])
        return self.service.get_evaluation(created_id[0])

    def update(self, *, evaluation_id: int, payload: dict, mutation: dict):
        CatalogMutationService(self.db).mutate(
            operation="update",
            entity_type="evaluation",
            entity_id=str(evaluation_id),
            request_payload=payload,
            snapshot=lambda: self.snapshot(evaluation_id, lock=True),
            apply=lambda: self.service.update_evaluation(
                evaluation_id=evaluation_id, commit=False, **payload
            ),
            **mutation,
        )
        return self.service.get_evaluation(evaluation_id)

    def delete(self, *, evaluation_id: int, mutation: dict) -> None:
        CatalogMutationService(self.db).mutate(
            operation="delete",
            entity_type="evaluation",
            entity_id=str(evaluation_id),
            request_payload={},
            snapshot=lambda: self.snapshot(evaluation_id, lock=True),
            apply=lambda: self.service.delete_evaluation(evaluation_id, commit=False),
            **mutation,
        )

    def rollback(
        self, *, event: CatalogMutationEvent, actor: dict, request_id: str
    ) -> CatalogMutationEvent:
        is_collection = event.entity_id.startswith("paper:")
        evaluation_id = None if is_collection else int(event.entity_id)
        paper_id = int(event.entity_id.split(":", 1)[1]) if is_collection else None

        def restore() -> None:
            if not is_collection:
                self.service.restore_evaluation_snapshot(
                    event.before_snapshot, commit=False
                )
            else:
                current_rows = (
                    self.db.query(DBEvaluation)
                    .filter(DBEvaluation.paper_id == paper_id)
                    .all()
                )
                for row in current_rows:
                    self.db.delete(row)
                self.db.flush()
                for snapshot in event.before_snapshot or []:
                    self.service.restore_evaluation_snapshot(snapshot, commit=False)
            self._recalculate_snapshots(event.before_snapshot, event.after_snapshot)

        snapshot = (
            (lambda: self._paper_evaluations(int(paper_id), lock=True))
            if is_collection
            else (lambda: self.snapshot(int(evaluation_id), lock=True))
        )
        _, rollback_event, _ = CatalogMutationService(self.db).mutate(
            actor=actor,
            operation="rollback",
            entity_type="evaluation",
            entity_id=event.entity_id,
            request_payload={"rollback_of": str(event.id)},
            idempotency_key=f"rollback:{event.id}",
            expected_version=canonical_hash(event.after_snapshot),
            snapshot=snapshot,
            apply=restore,
            request_id=request_id,
            rollback_of_event_id=event.id,
        )
        return rollback_event

    def _recalculate_snapshots(self, *snapshots) -> None:
        leaderboards: set[tuple[int, int, str]] = set()
        for snapshot in snapshots:
            rows = snapshot if isinstance(snapshot, list) else [snapshot]
            for row in rows:
                if not row:
                    continue
                names = self.service._metric_names_for_rank_refresh(
                    row.get("metrics"), row.get("best_metric")
                )
                leaderboards.update(
                    (
                        int(row["task_id"]),
                        int(row["dataset_id"]),
                        name,
                    )
                    for name in names
                )
        for task_id, dataset_id, metric in leaderboards:
            self.service.recalculate_ranks(
                task_id, dataset_id, metric_name=metric, commit=False
            )

    def _paper_evaluations(self, paper_id: int, *, lock: bool = False) -> list[dict]:
        if lock:
            self.db.query(DBPaper).filter(
                DBPaper.id == paper_id
            ).with_for_update().one()
        query = (
            self.db.query(DBEvaluation)
            .filter(DBEvaluation.paper_id == paper_id)
            .order_by(DBEvaluation.id)
        )
        rows = query.with_for_update().all() if lock else query.all()
        return [
            {field: getattr(row, field) for field in EVALUATION_FIELDS} for row in rows
        ]

    def batch(self, *, paper_id: int, operations: list[dict], mutation: dict) -> dict:
        if mutation["actor"]["role"] == "contributor" and len(operations) > 50:
            raise ValueError(
                "Contributors may submit at most 50 evaluation operations per batch"
            )
        result_ids: list[int | None] = []

        def apply() -> None:
            for operation in operations:
                kind = operation["operation"]
                payload = operation.get("payload") or {}
                evaluation_id = operation.get("evaluation_id")
                if kind == "create":
                    if int(payload.get("paper_id", -1)) != paper_id:
                        raise ValueError(
                            "Every batch operation must target the same paper"
                        )
                    result = self.service.create_evaluation(**payload, commit=False)
                    result_ids.append(int(result.id))
                else:
                    row = self.db.get(DBEvaluation, evaluation_id)
                    if row is None or int(row.paper_id) != paper_id:
                        raise DatabaseError(
                            f"Evaluation {evaluation_id} is not on paper {paper_id}"
                        )
                    if kind == "update":
                        result = self.service.update_evaluation(
                            evaluation_id=evaluation_id,
                            commit=False,
                            **payload,
                        )
                        result_ids.append(int(result.id))
                    elif kind == "delete":
                        self.service.delete_evaluation(evaluation_id, commit=False)
                        result_ids.append(None)
                    else:
                        raise ValueError(f"Unsupported evaluation operation: {kind}")

        after, event, replayed = CatalogMutationService(self.db).mutate(
            operation="batch",
            entity_type="evaluation",
            entity_id=f"paper:{paper_id}",
            request_payload={"operations": operations},
            snapshot=lambda: self._paper_evaluations(paper_id, lock=True),
            apply=apply,
            **mutation,
        )
        return {
            "event_id": str(event.id),
            "replayed": replayed,
            "result_ids": result_ids if not replayed else None,
            "evaluations": after,
        }
