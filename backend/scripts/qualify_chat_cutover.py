#!/usr/bin/env python3
"""Hold bounded synthetic staging chats open across an operator cutover."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy import select

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.models.database import ChatSession
from backend.scripts.qualify_chat_sandbox import settings_for_release
from backend.scripts.qualify_chat_soak import TurnResult, _turn

CONFIRMATION = "QUALIFY_STAGING_CHAT_CUTOVER"
MAX_TURNS = 2
DEFAULT_TURNS = 1
MAX_ROUNDS = 5
DEFAULT_ROUNDS = 3
PROMPT = (
    "Research and compare eight recent machine-learning papers across distinct "
    "topics. Cite the source for each paper, then summarize common research trends."
)


@dataclass(frozen=True)
class SessionState:
    session_id: str
    transcript_status: str
    active_turn: bool


def validate_turns(turns: int) -> None:
    if not 1 <= turns <= MAX_TURNS:
        raise SystemExit(f"--turns must be 1-{MAX_TURNS}")


def validate_rounds(rounds: int) -> None:
    if not 1 <= rounds <= MAX_ROUNDS:
        raise SystemExit(f"--rounds must be 1-{MAX_ROUNDS}")


def _session_states(session_ids: list[str]) -> list[SessionState]:
    ids = [uuid.UUID(value) for value in session_ids]
    with db_manager.session_local() as db:
        sessions = list(db.scalars(select(ChatSession).where(ChatSession.id.in_(ids))))
    return sorted(
        (
            SessionState(
                session_id=str(session.id),
                transcript_status=session.transcript_status,
                active_turn=session.active_turn_id is not None,
            )
            for session in sessions
        ),
        key=lambda item: item.session_id,
    )


async def _settled_session_states(
    session_ids: list[str], *, timeout_seconds: float = 30
) -> list[SessionState]:
    deadline = time.monotonic() + timeout_seconds
    while True:
        states = _session_states(session_ids)
        if len(states) == len(session_ids) and all(
            state.transcript_status == "ready" and not state.active_turn
            for state in states
        ):
            return states
        if time.monotonic() >= deadline:
            return states
        await asyncio.sleep(0.5)


async def _run(settings, *, turns: int, rounds: int) -> tuple[dict[str, object], bool]:
    run_id = uuid.uuid4().hex[:12]
    model = settings.chat_model_choices[0]["id"]
    results: list[TurnResult] = []
    for round_index in range(rounds):
        results.extend(
            await asyncio.gather(
                *(
                    _turn(
                        settings,
                        subject=(f"cutover-soak-{run_id}-{round_index}-{turn_index}"),
                        initial_model=model,
                        message=PROMPT,
                    )
                    for turn_index in range(turns)
                )
            )
        )
    session_ids = [
        result.session_id for result in results if result.session_id is not None
    ]
    states = (
        await _settled_session_states(session_ids)
        if len(session_ids) == turns * rounds
        else []
    )
    passed = (
        all(
            result.terminal == "done"
            and result.finish_reason in {"success", "tool_limit"}
            and not result.forced_termination
            for result in results
        )
        and len(states) == turns * rounds
        and all(
            state.transcript_status == "ready" and not state.active_turn
            for state in states
        )
    )
    return {
        "status": "passed" if passed else "failed",
        "release_id": settings.release_id,
        "worker_contract_version": settings.chat_worker_contract_version,
        "run_id": run_id,
        "requested": {
            "parallel_turns": turns,
            "rounds": rounds,
            "total_turns": turns * rounds,
        },
        "turns": [asdict(result) for result in results],
        "sessions": [asdict(state) for state in states],
    }, passed


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Hold synthetic staging chat streams open across a cutover"
    )
    result.add_argument("--turns", type=int, default=DEFAULT_TURNS)
    result.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS)
    result.add_argument("--release-dir", type=Path, required=True)
    result.add_argument("--confirm", required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.confirm != CONFIRMATION:
        raise SystemExit(f"--confirm must be {CONFIRMATION}")
    validate_turns(args.turns)
    validate_rounds(args.rounds)
    environment = get_settings()
    settings = settings_for_release(args.release_dir).model_copy(
        update={
            "session_cookie_name": environment.session_cookie_name,
            "chat_gemma_route": environment.chat_gemma_route,
            "chat_glm_route": environment.chat_glm_route,
            "chat_kimi_route": environment.chat_kimi_route,
        }
    )
    if settings.environment != "staging":
        raise SystemExit("Cutover qualification requires staging")
    report, passed = asyncio.run(_run(settings, turns=args.turns, rounds=args.rounds))
    print(json.dumps(report, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
