"""Prepare one exclusive, signed submission-review batch for the HF launcher.

This process retains database access locally. The remote reviewer receives only
the generated immutable manifest and its scoped callbacks.
"""

from __future__ import annotations

import argparse
import uuid
from datetime import UTC, datetime
from pathlib import Path

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.models.database import AutonomousRun
from backend.services.autonomous_operations_repository import (
    AutonomousOperationsRepository,
    Operator,
    RunContext,
)
from backend.services.autonomous_submission_service import AutonomousSubmissionService


def prepare_review_batch(
    *, run_id: uuid.UUID, manifest_file: Path, limit: int = 25
) -> int:
    settings = get_settings()
    if not settings.autonomous_submission_enabled:
        raise RuntimeError("Autonomous submission review is disabled")
    context = RunContext(
        run_id=run_id,
        operator=Operator.SUBMISSIONS,
        dry_run=False,
        manifest_revision="submission-review-v1",
    )
    with db_manager.session_local() as db:
        repository = AutonomousOperationsRepository()
        if db.get(AutonomousRun, run_id) is None:
            repository.append_run(
                db, context=context, status="completed", now=datetime.now(UTC)
            )
            db.commit()
        else:
            repository.assert_run_context(db, context)
        service = AutonomousSubmissionService(
            db,
            signing_secret=settings.autonomous_submission_callback_secret.encode(),
            callback_base_url=settings.autonomous_submission_callback_base_url,
        )
        batch = service.claim_submission_batch(run_id, limit=limit)
        if not batch:
            return 0
        service.write_manifest(manifest_file, service.build_submission_manifest(batch))
        reviewed = service.review_submission_batch(
            batch,
            budget_usd=settings.autonomous_submission_run_budget_usd,
        )
        for item in reviewed:
            service.apply_submission_decision(item.callback_token, item.decision)
        return len(batch)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", type=uuid.UUID, required=True)
    parser.add_argument("--manifest-file", type=Path, required=True)
    parser.add_argument("--limit", type=int, choices=range(1, 26), default=25)
    args = parser.parse_args()
    claimed = prepare_review_batch(
        run_id=args.run_id,
        manifest_file=args.manifest_file,
        limit=args.limit,
    )
    print(f"AUTONOMOUS_SUBMISSION_REVIEW claimed={claimed} run_id={args.run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
