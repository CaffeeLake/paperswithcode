#!/usr/bin/env python3
"""Run sanitized persistent-chat follow-up and clean-cancel qualification."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import modal
from sqlalchemy import select

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.models.database import ChatSandboxLease, ChatTurnLatency
from backend.routers.auth import _encode_legacy_session
from backend.scripts.qualify_chat_sandbox import settings_for_release

CONFIRMATION = "QUALIFY_STAGING_CHAT_SOAK"
PROMPT = "Reply with one concise acknowledgement."
LONG_PROMPT = (
    "Briefly research two recent machine-learning papers and compare their topics."
)


@dataclass(frozen=True)
class TurnResult:
    request_id: str | None
    session_id: str | None
    terminal: str
    finish_reason: str | None
    error_code: str | None
    elapsed_ms: int
    forced_termination: bool


def _token(settings, subject: str) -> str:
    return _encode_legacy_session({"sub": subject, "username": subject})


async def _turn(
    settings,
    *,
    subject: str,
    session_id: str | None = None,
    initial_model: str | None = None,
    cancel_mode: str | None = None,
) -> TurnResult:
    token = _token(settings, subject)
    payload: dict[str, Any] = {
        "message": LONG_PROMPT if cancel_mode is not None else PROMPT,
        "client_message_id": str(uuid.uuid4()),
    }
    if session_id is not None:
        payload["session_id"] = session_id
    if initial_model is not None:
        payload["initial_model"] = initial_model
    request_id: str | None = None
    landed_session_id = session_id
    terminal = "stream_ended"
    finish_reason: str | None = None
    error_code: str | None = None
    cancel_sent = False
    forced_termination = False
    started = time.perf_counter()
    async with httpx.AsyncClient(
        timeout=240,
        cookies={settings.session_cookie_name: token},
    ) as client:
        async with client.stream(
            "POST",
            "http://127.0.0.1:8001/api/v1/chat/stream",
            json=payload,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                event = json.loads(line[6:])
                kind = str(event.get("type") or "")
                if kind == "stream_start":
                    request_id = str(event["request_id"])
                    landed_session_id = str(event["session_id"])
                if (
                    cancel_mode is not None
                    and kind == "workspace_ready"
                    and landed_session_id is not None
                    and not cancel_sent
                ):
                    cancel_sent = True
                    if cancel_mode == "forced":
                        with db_manager.session_local() as db:
                            sandbox_id = db.scalar(
                                select(ChatSandboxLease.modal_sandbox_id).where(
                                    ChatSandboxLease.chat_session_id
                                    == uuid.UUID(landed_session_id)
                                )
                            )
                        if sandbox_id:
                            sandbox = await modal.Sandbox.from_id.aio(sandbox_id)
                            await sandbox.terminate.aio(wait=False)
                            forced_termination = True
                    cancel = await client.post(
                        "http://127.0.0.1:8001/api/v1/chat/sessions/"
                        f"{landed_session_id}/cancel"
                    )
                    cancel.raise_for_status()
                if kind == "error":
                    terminal = "error"
                    error_code = str(event.get("code")) if event.get("code") else None
                elif kind == "done":
                    terminal = "done"
                    finish_reason = (
                        str(event.get("finish_reason"))
                        if event.get("finish_reason")
                        else None
                    )
    return TurnResult(
        request_id=request_id,
        session_id=landed_session_id,
        terminal=terminal,
        finish_reason=finish_reason,
        error_code=error_code,
        elapsed_ms=round((time.perf_counter() - started) * 1000),
        forced_termination=forced_termination,
    )


def _latency_rows(session_ids: set[uuid.UUID], started_at: datetime):
    with db_manager.session_local() as db:
        return list(
            db.execute(
                select(ChatTurnLatency).where(
                    ChatTurnLatency.chat_session_id.in_(session_ids),
                    ChatTurnLatency.admitted_at >= started_at,
                )
            ).scalars()
        )


async def _run(
    settings,
    *,
    sessions: int,
    followups: int,
    cancellations: int,
    forced_cancellations: int,
):
    run_id = uuid.uuid4().hex[:12]
    started_at = datetime.now(UTC)
    turns: list[TurnResult] = []
    normal_turns: list[TurnResult] = []
    session_ids: set[uuid.UUID] = set()
    model_switched = False
    cross_owner_rejected = False
    model_choices = settings.chat_model_choices
    for index in range(sessions):
        subject = f"soak-followup-{run_id}-{index}"
        first = await _turn(
            settings,
            subject=subject,
            initial_model=model_choices[0]["id"],
        )
        turns.append(first)
        normal_turns.append(first)
        if first.session_id is None:
            continue
        session_ids.add(uuid.UUID(first.session_id))
        for followup_index in range(followups):
            if index == 0 and followup_index == 1 and len(model_choices) > 1:
                token = _token(settings, subject)
                async with httpx.AsyncClient(
                    timeout=30,
                    cookies={settings.session_cookie_name: token},
                ) as client:
                    changed = await client.patch(
                        "http://127.0.0.1:8001/api/v1/chat/sessions/"
                        f"{first.session_id}",
                        json={"selected_model": model_choices[1]["id"]},
                    )
                    changed.raise_for_status()
                    model_switched = (
                        changed.json().get("selected_model") == model_choices[1]["id"]
                    )
            followup_result = await _turn(
                settings,
                subject=subject,
                session_id=first.session_id,
            )
            turns.append(followup_result)
            normal_turns.append(followup_result)
        if index == 0:
            other_subject = f"soak-cross-owner-{run_id}"
            async with httpx.AsyncClient(
                timeout=30,
                cookies={settings.session_cookie_name: _token(settings, other_subject)},
            ) as client:
                denied = await client.get(
                    f"http://127.0.0.1:8001/api/v1/chat/sessions/{first.session_id}"
                )
                cross_owner_rejected = denied.status_code == 404

    cancellations_landed: list[TurnResult] = []
    for index in range(cancellations):
        result = await _turn(
            settings,
            subject=f"soak-cancel-{run_id}-{index}",
            cancel_mode="clean",
        )
        cancellations_landed.append(result)
        turns.append(result)
        if result.session_id is not None:
            session_ids.add(uuid.UUID(result.session_id))

    forced_landed: list[TurnResult] = []
    for index in range(forced_cancellations):
        result = await _turn(
            settings,
            subject=f"soak-forced-cancel-{run_id}-{index}",
            cancel_mode="forced",
        )
        forced_landed.append(result)
        turns.append(result)
        if result.session_id is not None:
            session_ids.add(uuid.UUID(result.session_id))

    latency = _latency_rows(session_ids, started_at) if session_ids else []
    latency_by_request = {str(row.request_id): row for row in latency}
    followup_rows = [row for row in latency if row.traffic_class == "followup"]
    clean_cancellations = sum(
        result.request_id is not None
        and result.request_id in latency_by_request
        and latency_by_request[result.request_id].terminal_status == "stopped"
        for result in cancellations_landed
    )
    forced_failures = sum(
        result.forced_termination
        and result.request_id is not None
        and result.request_id in latency_by_request
        and latency_by_request[result.request_id].terminal_status == "error"
        for result in forced_landed
    )
    normal_successes = sum(
        result.terminal == "done" and result.finish_reason in {"success", "tool_limit"}
        for result in normal_turns
    )
    successful_turns = normal_successes + clean_cancellations
    expected_followups = sessions * followups
    passed = (
        successful_turns == len(normal_turns) + cancellations
        and len(followup_rows) == expected_followups
        and clean_cancellations == cancellations
        and forced_failures == forced_cancellations
        and (sessions == 0 or cross_owner_rejected)
        and (sessions == 0 or followups < 2 or model_switched)
    )
    return {
        "status": "passed" if passed else "failed",
        "release_id": settings.release_id,
        "worker_contract_version": settings.chat_worker_contract_version,
        "run_id": run_id,
        "requested": {
            "sessions": sessions,
            "followups_per_session": followups,
            "clean_cancellations": cancellations,
            "forced_cancellation_failures": forced_cancellations,
        },
        "observed": {
            "turns": len(turns),
            "successful_turns": successful_turns,
            "followup_rows": len(followup_rows),
            "clean_cancellations": clean_cancellations,
            "forced_cancellation_failures": forced_failures,
            "cross_owner_rejected": cross_owner_rejected,
            "model_switched": model_switched,
            "error_codes": sorted(
                {result.error_code for result in turns if result.error_code is not None}
            ),
        },
        "turns": [asdict(result) for result in turns],
    }, passed


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Qualify staging follow-ups, model changes, and clean cancellation"
    )
    result.add_argument("--followup-sessions", type=int, default=13)
    result.add_argument("--followups-per-session", type=int, default=4)
    result.add_argument("--clean-cancellations", type=int, default=20)
    result.add_argument("--forced-cancellations", type=int, default=10)
    result.add_argument("--release-dir", type=Path, required=True)
    result.add_argument("--confirm", required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.confirm != CONFIRMATION:
        raise SystemExit(f"--confirm must be {CONFIRMATION}")
    if not 0 <= args.followup_sessions <= 50:
        raise SystemExit("--followup-sessions must be 0-50")
    if not 0 <= args.followups_per_session <= 4:
        raise SystemExit("--followups-per-session must be 0-4")
    if not 0 <= args.clean_cancellations <= 50:
        raise SystemExit("--clean-cancellations must be 0-50")
    if not 0 <= args.forced_cancellations <= 20:
        raise SystemExit("--forced-cancellations must be 0-20")
    environment = get_settings()
    settings = settings_for_release(args.release_dir).model_copy(
        update={
            "session_cookie_name": environment.session_cookie_name,
            "chat_gpt_oss_route": environment.chat_gpt_oss_route,
            "chat_glm_route": environment.chat_glm_route,
            "chat_kimi_route": environment.chat_kimi_route,
        }
    )
    if settings.environment != "staging":
        raise SystemExit("Soak qualification requires staging")
    report, passed = asyncio.run(
        _run(
            settings,
            sessions=args.followup_sessions,
            followups=args.followups_per_session,
            cancellations=args.clean_cancellations,
            forced_cancellations=args.forced_cancellations,
        )
    )
    print(json.dumps(report, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
