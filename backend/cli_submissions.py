"""Repository-only submission review CLI.

Apply remains fail-closed until the complete Phase 4 rollout gate is enabled.
"""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.models.database import PendingPaperEdit
from backend.services.catalog_mutation_service import json_safe
from backend.services.pending_edit_service import PendingEditService


CODEX_SUBMISSION_APPLY_ENABLED = False


def register_submission_commands(commands) -> None:
    submissions = commands.add_parser(
        "submissions", help="Inspect the community submission queue"
    )
    subcommands = submissions.add_subparsers(dest="submissions_command", required=True)
    listing = subcommands.add_parser("list")
    _environment_argument(listing)
    listing.add_argument("--status", choices=["pending", "approved", "rejected"])
    listing.add_argument("--limit", type=int, default=50, choices=range(1, 101))
    listing.add_argument("--json", action="store_true")
    listing.set_defaults(handler=list_submissions)

    show = subcommands.add_parser("show")
    show.add_argument("id", type=int)
    _environment_argument(show)
    show.add_argument("--json", action="store_true")
    show.set_defaults(handler=show_submission)

    decide = subcommands.add_parser("decide")
    decide.add_argument("id", type=int)
    _environment_argument(decide)
    decide.add_argument(
        "--decision", required=True, choices=["approve", "reject", "needs-human"]
    )
    decide.add_argument("--resolved-payload-file", type=Path)
    decide.add_argument("--review-file", type=Path, required=True)
    decide.add_argument("--review-run-id", type=uuid.UUID, required=True)
    decide.add_argument("--confirm", required=True, choices=["APPLY_SUBMISSION_REVIEW"])
    decide.add_argument("--json", action="store_true")
    decide.set_defaults(handler=decide_submission)


def _environment_argument(parser) -> None:
    parser.add_argument(
        "--environment", required=True, choices=["production", "staging"]
    )


def _verified_database(db, selected: str) -> dict:
    settings = get_settings()
    row = db.execute(
        text("SELECT current_user, current_schema(), current_schemas(false)")
    ).one()
    expected_schema = "staging" if selected == "staging" else "public"
    identity = {
        "selected_environment": selected,
        "configured_environment": settings.environment,
        "database_role": row[0],
        "database_schema": row[1],
        "search_path_schemas": list(row[2]),
    }
    if settings.environment != selected:
        raise ValueError("Selected environment does not match PWC_ENVIRONMENT")
    if row[0] != settings.db_user or row[1] != expected_schema:
        raise ValueError("Database role/schema does not match the selected environment")
    return identity


def _serialize(row: PendingPaperEdit) -> dict:
    return {
        "id": row.id,
        "paper_id": row.paper_id,
        "hf_subject": row.hf_subject,
        "hf_username": row.hf_username,
        "is_author": row.is_author,
        "edit_type": row.edit_type,
        "status": row.status,
        "proposed_payload": row.proposed_payload,
        "current_payload": row.current_payload,
        "applied_payload": row.applied_payload,
        "result_entity_type": row.result_entity_type,
        "result_entity_id": row.result_entity_id,
        "conflict_payload": row.conflict_payload,
        "reviewed_by_kind": row.reviewed_by_kind,
        "review_run_id": str(row.review_run_id) if row.review_run_id else None,
        "review_model": row.review_model,
        "review_evidence": row.review_evidence,
        "created_at": row.created_at,
        "reviewed_at": row.reviewed_at,
    }


def _emit(payload: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(json_safe(payload), indent=2, sort_keys=True))
    else:
        print(json.dumps(json_safe(payload), sort_keys=True))


def list_submissions(args: argparse.Namespace) -> int:
    with db_manager.session_local() as db:
        identity = _verified_database(db, args.environment)
        rows, total = PendingEditService(db).list_edits(
            status=args.status, limit=args.limit
        )
        _emit(
            {
                "database": identity,
                "count": total,
                "results": [_serialize(row) for row in rows],
            },
            args.json,
        )
    return 0


def show_submission(args: argparse.Namespace) -> int:
    with db_manager.session_local() as db:
        identity = _verified_database(db, args.environment)
        service = PendingEditService(db)
        row = service.get(args.id)
        current = (
            service._build_snapshot(row.paper_id, row.edit_type)
            if row.paper_id is not None
            else {}
        )
        _emit(
            {
                "database": identity,
                "submission": _serialize(row),
                "canonical_now": current,
            },
            args.json,
        )
    return 0


def _load_review(args: argparse.Namespace) -> dict:
    if args.review_file.stat().st_size > 131_072:
        raise ValueError("Review artifact exceeds 128 KiB")
    artifact = json.loads(args.review_file.read_text())
    if not isinstance(artifact, dict):
        raise ValueError("Review artifact must be a JSON object")
    required = {
        "decision",
        "rationale",
        "sources",
        "duplicate_checks",
        "confidence",
        "unresolved_questions",
        "model",
        "workflow_version",
        "codex_task_id",
        "reviewed_revision",
        "material_changes",
    }
    missing = sorted(required - artifact.keys())
    if missing:
        raise ValueError(f"Review artifact is missing: {', '.join(missing)}")
    normalized_decision = args.decision.replace("-", "_")
    if artifact["decision"] != normalized_decision:
        raise ValueError("Review artifact decision does not match --decision")
    return artifact


def decide_submission(args: argparse.Namespace) -> int:
    artifact = _load_review(args)
    resolved_payload = None
    if args.resolved_payload_file:
        resolved_payload = json.loads(args.resolved_payload_file.read_text())
    if args.decision in {"approve", "reject"} and not CODEX_SUBMISSION_APPLY_ENABLED:
        raise ValueError(
            "Codex submission apply is disabled until the complete security rollout gate passes"
        )
    with db_manager.session_local() as db:
        identity = _verified_database(db, args.environment)
        row = (
            db.query(PendingPaperEdit)
            .filter(PendingPaperEdit.id == args.id)
            .with_for_update()
            .first()
        )
        if row is None:
            raise ValueError("Submission not found")
        if args.decision != "needs-human":
            raise ValueError("Codex submission apply is currently recommendation-only")
        if row.status != "pending":
            raise ValueError("Only pending submissions can receive a recommendation")
        evidence = {**artifact, "resolved_payload": resolved_payload}
        if row.review_run_id == args.review_run_id and row.review_evidence == evidence:
            _emit({"database": identity, "submission": _serialize(row)}, args.json)
            return 0
        row.reviewed_by_kind = "codex"
        row.reviewed_by = "Codex"
        row.review_run_id = args.review_run_id
        row.review_model = str(artifact["model"])[:255]
        row.review_evidence = evidence
        row.reviewed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(row)
        _emit({"database": identity, "submission": _serialize(row)}, args.json)
    return 0
