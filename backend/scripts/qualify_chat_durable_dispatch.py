#!/usr/bin/env python3
"""Qualify durable turn dispatch without invoking a chat execution runtime."""

from __future__ import annotations

import argparse
import json
import statistics
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from backend.config import Settings, get_settings
from backend.database.connection import db_manager
from backend.models.database import ChatSession, ChatTurnJob
from backend.services.chat_turn_job_repository import (
    AccountBusy,
    ChatOverload,
    ChatTurnJobRepository,
    StaleTurnClaim,
    TurnLeaseClaim,
)
from deploy.release import validate_manifest

CONFIRMATION = "QUALIFY_STAGING_DURABLE_DISPATCH"
EXPECTED_OUTCOMES = {
    "idempotent_admission": "replayed",
    "same_owner_contention": "account_busy",
    "global_capacity": "chat_overload",
    "claim_heartbeat_transition": "waiting_model",
    "stale_fence": "stale_turn_claim",
    "terminal_write": "completed",
    "expiry_interruption": "lease_expired",
}


class QualificationRefused(RuntimeError):
    """The operator context is unsafe for durable-dispatch qualification."""


@dataclass(frozen=True, slots=True)
class SchemaAudit:
    schema: bool
    role: bool
    owner: bool
    privileges: bool
    indexes: bool
    constraints: bool


def validate_schema_audit(audit: SchemaAudit) -> None:
    for name, valid in asdict(audit).items():
        if not valid:
            raise QualificationRefused(f"PostgreSQL {name} contract mismatch")


def inspect_postgresql_contract(db: Session) -> SchemaAudit:
    """Audit the staging table through content-free PostgreSQL aggregates."""

    if db.bind is None or db.bind.dialect.name != "postgresql":
        raise QualificationRefused("qualification requires PostgreSQL")
    row = (
        db.execute(
            text(
                """
            WITH expected_columns(name, data_type, nullable, max_length) AS (
                VALUES
                    ('turn_id','uuid',false,NULL),
                    ('chat_session_id','uuid',false,NULL),
                    ('hf_user_id','character varying',false,255),
                    ('request_id','character varying',false,200),
                    ('revision','integer',false,NULL),
                    ('dispatch_class','character varying',false,32),
                    ('dispatch_route','character varying',false,255),
                    ('state','character varying',false,24),
                    ('worker_id','character varying',true,128),
                    ('worker_generation','bigint',true,NULL),
                    ('lease_generation','bigint',true,NULL),
                    ('app_release_id','character varying',false,255),
                    ('worker_contract_version','character varying',false,128),
                    ('admitted_at','timestamp with time zone',false,NULL),
                    ('dispatched_at','timestamp with time zone',true,NULL),
                    ('started_at','timestamp with time zone',true,NULL),
                    ('heartbeat_at','timestamp with time zone',true,NULL),
                    ('lease_expires_at','timestamp with time zone',true,NULL),
                    ('terminal_at','timestamp with time zone',true,NULL),
                    ('failure_code','character varying',true,64),
                    ('last_agent_session_id','uuid',true,NULL),
                    ('last_resume_boundary_id','text',true,NULL)
            ), actual_columns AS (
                SELECT column_name AS name, data_type, is_nullable = 'YES' AS nullable,
                       character_maximum_length AS max_length
                FROM information_schema.columns
                WHERE table_schema = 'staging' AND table_name = 'chat_turn_jobs'
            ), column_drift AS (
                SELECT 1 FROM expected_columns e FULL JOIN actual_columns a USING (name)
                WHERE e.name IS NULL OR a.name IS NULL
                   OR e.data_type <> a.data_type OR e.nullable <> a.nullable
                   OR e.max_length IS DISTINCT FROM a.max_length
            ), table_info AS (
                SELECT oid, relowner, relacl FROM pg_class
                WHERE oid = to_regclass('staging.chat_turn_jobs')
            ), required_constraints(name, kind) AS (
                VALUES
                    ('chat_turn_jobs_pkey','p'),
                    ('chat_turn_jobs_request_id_key','u'),
                    ('chat_turn_jobs_chat_session_id_fkey','f'),
                    ('chat_turn_jobs_revision_check','c'),
                    ('chat_turn_jobs_worker_generation_check','c'),
                    ('chat_turn_jobs_lease_generation_check','c'),
                    ('chat_turn_jobs_state_check','c'),
                    ('chat_turn_jobs_lease_fields_check','c'),
                    ('chat_turn_jobs_terminal_timestamp_check','c'),
                    ('chat_turn_jobs_failure_code_check','c')
            ), actual_constraints AS (
                SELECT conname AS name, contype::text AS kind, convalidated
                FROM pg_constraint
                WHERE conrelid = to_regclass('staging.chat_turn_jobs')
            ), required_indexes(name, fragment, unique_required, partial_required) AS (
                VALUES
                    ('idx_chat_turn_jobs_claim',
                     '(state, admitted_at, turn_id)',false,false),
                    ('idx_chat_turn_jobs_expiry',
                     '(state, lease_expires_at)',false,false),
                    ('uq_chat_turn_jobs_nonterminal_owner',
                     '(hf_user_id)',true,true)
            )
            SELECT
                current_schema() = 'staging'
                    AND to_regclass('staging.chat_turn_jobs') IS NOT NULL
                    AND NOT EXISTS (SELECT FROM column_drift) AS schema,
                current_user = 'pwc_staging' AS role,
                (SELECT pg_get_userbyid(relowner) = 'pwc_staging_owner'
                 FROM table_info) AS owner,
                has_table_privilege(current_user, to_regclass('staging.chat_turn_jobs'),
                                    'SELECT,INSERT,UPDATE,DELETE')
                    AND NOT has_table_privilege(to_regrole('paperswithcode_user'),
                                                to_regclass('staging.chat_turn_jobs'),
                                                'SELECT,INSERT,UPDATE,DELETE')
                    AND NOT EXISTS (
                        SELECT FROM table_info t,
                             LATERAL aclexplode(
                                 coalesce(t.relacl, acldefault('r', t.relowner))
                             ) a
                        WHERE a.grantee = 0 AND a.privilege_type IN
                            ('SELECT','INSERT','UPDATE','DELETE')
                    ) AS privileges,
                NOT EXISTS (
                    SELECT FROM required_indexes r
                    LEFT JOIN pg_indexes i ON i.schemaname = 'staging'
                        AND i.tablename = 'chat_turn_jobs' AND i.indexname = r.name
                    LEFT JOIN pg_class c
                        ON c.oid = to_regclass(i.schemaname || '.' || i.indexname)
                    LEFT JOIN pg_index x ON x.indexrelid = c.oid
                    WHERE i.indexname IS NULL
                       OR i.indexdef NOT LIKE '%' || r.fragment || '%'
                       OR x.indisunique <> r.unique_required
                       OR (x.indpred IS NOT NULL) <> r.partial_required
                ) AS indexes,
                NOT EXISTS (
                    SELECT FROM required_constraints r
                    LEFT JOIN actual_constraints a USING (name)
                    WHERE a.name IS NULL OR a.kind <> r.kind OR NOT a.convalidated
                ) AS constraints
            """
            )
        )
        .mappings()
        .one()
    )
    return SchemaAudit(
        **{name: bool(row[name]) for name in SchemaAudit.__annotations__}
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Qualify staging durable dispatch through its repository contract"
    )
    result.add_argument("--release-dir", type=Path, required=True)
    result.add_argument("--confirm", required=True)
    return result


def validate_operator_context(
    *,
    confirmation: str,
    environment: Settings,
    release_id: str,
    worker_contract_version: str,
) -> None:
    if confirmation != CONFIRMATION:
        raise QualificationRefused("qualification confirmation is invalid")
    if environment.environment != "staging":
        raise QualificationRefused("qualification requires staging")
    if environment.release_id != release_id:
        raise QualificationRefused("live and immutable release identities differ")
    if environment.chat_worker_contract_version != worker_contract_version:
        raise QualificationRefused("live and immutable worker contracts differ")
    if not environment.chat_durable_turn_dispatch_enabled:
        raise QualificationRefused("durable dispatch bridge is disabled")
    if environment.db_search_path.split(",", 1)[0].strip() != "staging":
        raise QualificationRefused("qualification requires the staging search path")


def run_qualification(
    *,
    session_factory: Callable[[], Session],
    release_id: str,
    worker_contract_version: str,
    schema_audit: SchemaAudit,
) -> dict[str, Any]:
    """Exercise the content-free repository contract and always remove its rows."""

    validate_schema_audit(schema_audit)
    run_token = uuid.uuid4().hex
    session_ids = [uuid.uuid4() for _ in range(4)]
    owners = [f"qualify-{run_token}-{index}" for index in (0, 0, 1, 2)]
    turn_ids: list[uuid.UUID] = []
    timings: list[float] = []
    outcomes: dict[str, str] = {}
    cleanup = {"clean": False, "jobs_deleted": 0, "sessions_deleted": 0}

    def scenario(name: str, operation: Callable[[], str]) -> None:
        started = time.monotonic()
        outcome = operation()
        expected = EXPECTED_OUTCOMES[name]
        if outcome != expected:
            raise RuntimeError(
                f"durable qualification invariant failed for {name}: {outcome}"
            )
        outcomes[name] = outcome
        timings.append((time.monotonic() - started) * 1000)

    with session_factory() as db:
        repository = ChatTurnJobRepository(
            advisory_locker=(
                (lambda *_args: None) if db.bind.dialect.name == "sqlite" else None
            )
        )
        sessions = [
            ChatSession(
                id=session_id,
                hf_user_id=owner,
                hf_username=owner,
                selected_model="qualification",
            )
            for session_id, owner in zip(session_ids, owners, strict=True)
        ]

        def admit(index: int, *, capacity: int = 2, request: str | None = None):
            turn_id = uuid.uuid4()
            request_id = request or f"qualify-{run_token}-{uuid.uuid4().hex}"
            result = repository.admit(
                db,
                turn_id=turn_id,
                chat_session_id=sessions[index].id,
                hf_user_id=sessions[index].hf_user_id,
                request_id=request_id,
                revision=1,
                dispatch_class="qualification",
                dispatch_route="durable-repository",
                app_release_id=release_id,
                worker_contract_version=worker_contract_version,
                now=datetime.now(UTC),
                emergency_capacity=capacity,
            )
            if result.created:
                turn_ids.append(turn_id)
            return result

        try:
            db.add_all(sessions)
            db.commit()
            first_request = f"qualify-{run_token}-replay"
            first = admit(0, request=first_request)
            db.commit()

            def replay() -> str:
                result = repository.admit(
                    db,
                    turn_id=first.job.turn_id,
                    chat_session_id=sessions[0].id,
                    hf_user_id=sessions[0].hf_user_id,
                    request_id=first_request,
                    revision=1,
                    dispatch_class="qualification",
                    dispatch_route="durable-repository",
                    app_release_id=release_id,
                    worker_contract_version=worker_contract_version,
                    now=datetime.now(UTC),
                    emergency_capacity=2,
                )
                return "replayed" if not result.created else "created"

            scenario("idempotent_admission", replay)

            def owner_contention() -> str:
                try:
                    admit(1)
                except AccountBusy as error:
                    return error.code
                return "admitted"

            scenario("same_owner_contention", owner_contention)
            second = admit(2)
            db.commit()

            def capacity_rejection() -> str:
                try:
                    admit(3)
                except ChatOverload as error:
                    return error.code
                return "admitted"

            scenario("global_capacity", capacity_rejection)
            now = datetime.now(UTC)
            claim = repository.claim(
                db,
                turn_id=first.job.turn_id,
                worker_id=f"qualification-{run_token}",
                worker_generation=1,
                now=now,
                lease_seconds=30,
            )

            def claimed_lifecycle() -> str:
                repository.heartbeat(
                    db, claim=claim, now=now + timedelta(seconds=1), lease_seconds=30
                )
                repository.transition(
                    db, claim=claim, state="running", now=now + timedelta(seconds=2)
                )
                job = repository.transition(
                    db,
                    claim=claim,
                    state="waiting_model",
                    now=now + timedelta(seconds=3),
                )
                return job.state

            scenario("claim_heartbeat_transition", claimed_lifecycle)

            def stale_fence() -> str:
                stale = TurnLeaseClaim(
                    turn_id=claim.turn_id,
                    worker_id=claim.worker_id,
                    worker_generation=claim.worker_generation,
                    lease_generation=claim.lease_generation + 1,
                )
                try:
                    repository.heartbeat(
                        db,
                        claim=stale,
                        now=now + timedelta(seconds=4),
                        lease_seconds=30,
                    )
                except StaleTurnClaim:
                    return "stale_turn_claim"
                return "accepted"

            scenario("stale_fence", stale_fence)

            def terminal_write() -> str:
                terminal = repository.write_terminal(
                    db,
                    claim=claim,
                    state="completed",
                    now=now + timedelta(seconds=5),
                )
                replayed = repository.write_terminal(
                    db,
                    claim=claim,
                    state="completed",
                    now=now + timedelta(seconds=6),
                )
                if replayed.turn_id != terminal.turn_id:
                    return "failed"
                return replayed.state

            scenario("terminal_write", terminal_write)
            expiry_claim = repository.claim(
                db,
                turn_id=second.job.turn_id,
                worker_id=f"qualification-expiry-{run_token}",
                worker_generation=1,
                now=now,
                lease_seconds=1,
            )

            def expiry() -> str:
                interrupted = repository.interrupt_expired(
                    db, now=now + timedelta(seconds=2), limit=1
                )
                if interrupted != 1:
                    return "expiry_count_mismatch"
                job = repository.load_by_turn(db, expiry_claim.turn_id)
                return job.failure_code if job is not None else "missing"

            scenario("expiry_interruption", expiry)
            db.commit()
        finally:
            db.rollback()
            deleted_jobs = db.execute(
                delete(ChatTurnJob).where(ChatTurnJob.turn_id.in_(turn_ids))
            ).rowcount
            deleted_sessions = db.execute(
                delete(ChatSession).where(ChatSession.id.in_(session_ids))
            ).rowcount
            db.commit()
            remaining_jobs = db.scalar(
                select(ChatTurnJob.turn_id)
                .where(ChatTurnJob.turn_id.in_(turn_ids))
                .limit(1)
            )
            remaining_sessions = db.scalar(
                select(ChatSession.id).where(ChatSession.id.in_(session_ids)).limit(1)
            )
            cleanup = {
                "clean": remaining_jobs is None and remaining_sessions is None,
                "jobs_deleted": deleted_jobs,
                "sessions_deleted": deleted_sessions,
            }

    return {
        "release": {
            "release_id": release_id,
            "worker_contract_version": worker_contract_version,
        },
        "scenarios": {"requested": 7, "passed": len(outcomes), "failed": 0},
        "outcomes": outcomes,
        "timing_ms": {
            "count": len(timings),
            "min": min(timings),
            "p50": statistics.median(timings),
            "max": max(timings),
        },
        "cleanup": cleanup,
        "schema_audit": asdict(schema_audit),
    }


def main() -> int:
    args = parser().parse_args()
    release_dir = args.release_dir.resolve(strict=True)
    manifest = validate_manifest(release_dir, "staging")
    runtime = manifest.get("chat_runtime")
    if not isinstance(runtime, dict):
        raise QualificationRefused("release has no durable chat contract")
    worker_contract_version = runtime.get("worker_contract_version")
    if not isinstance(worker_contract_version, str) or not worker_contract_version:
        raise QualificationRefused("release worker contract is missing")
    environment = get_settings()
    validate_operator_context(
        confirmation=args.confirm,
        environment=environment,
        release_id=manifest["release_id"],
        worker_contract_version=worker_contract_version,
    )
    with db_manager.session_local() as db:
        audit = inspect_postgresql_contract(db)
    report = run_qualification(
        session_factory=db_manager.session_local,
        release_id=manifest["release_id"],
        worker_contract_version=worker_contract_version,
        schema_audit=audit,
    )
    if not report["cleanup"]["clean"]:
        raise RuntimeError("durable qualification cleanup failed")
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
