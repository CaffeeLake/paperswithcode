"""Deterministic, content-free fault schedules for durable external turns."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, TypeAlias

_OPAQUE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_FAULT_ACTIONS = frozenset(
    {
        "model_start",
        "subscriber_detach",
        "subscriber_process_lost",
        "subscriber_cursor_reattach",
        "worker_socket_lost",
        "worker_exact_claim_reattach",
        "worker_drain",
        "executor_start",
        "executor_response_lost",
        "executor_attach",
        "cancel_requested",
        "executor_attach_cancel",
        "queued",
        "terminal_completed",
        "terminal_cancelled",
        "terminal_log_lost",
    }
)


@dataclass(frozen=True, slots=True)
class OperationIdentity:
    turn_id: str
    tool_call_id: str
    attempt: int

    def __post_init__(self) -> None:
        if (
            not _OPAQUE_ID.fullmatch(self.turn_id)
            or not _OPAQUE_ID.fullmatch(self.tool_call_id)
            or type(self.attempt) is not int
            or self.attempt < 0
        ):
            raise ValueError("fault schedule operation identity is invalid")


FaultAction: TypeAlias = str | tuple[str, OperationIdentity]


@dataclass(frozen=True, slots=True)
class FaultSchedule:
    name: str
    steps: tuple[FaultAction, ...]

    @property
    def operation_identities(self) -> tuple[OperationIdentity, ...]:
        return tuple(
            dict.fromkeys(step[1] for step in self.steps if isinstance(step, tuple))
        )

    @property
    def content_free(self) -> bool:
        return bool(_OPAQUE_ID.fullmatch(self.name.replace("_", "-"))) and all(
            isinstance(step, tuple)
            or bool(_OPAQUE_ID.fullmatch(step.replace("_", "-")))
            for step in self.steps
        )


@dataclass(frozen=True, slots=True)
class FaultResult:
    model_starts: int
    executor_starts_by_operation: Counter[OperationIdentity]
    terminal_cause: Literal["completed", "cancelled"]
    durable_terminal_commits: int
    terminal_log_records: int
    queued_states: int

    @property
    def executor_starts(self) -> int:
        return sum(self.executor_starts_by_operation.values())


def built_in_fault_schedules():
    executor_loss = OperationIdentity("turn-0005", "tool-0001", 0)
    cancellation = OperationIdentity("turn-0006", "tool-0001", 0)
    schedules = {
        "browser_disconnect": FaultSchedule(
            "browser_disconnect",
            (
                "model_start",
                "subscriber_detach",
                "subscriber_cursor_reattach",
                "terminal_completed",
            ),
        ),
        "api_subscriber_process_loss": FaultSchedule(
            "api_subscriber_process_loss",
            (
                "model_start",
                "subscriber_process_lost",
                "subscriber_cursor_reattach",
                "terminal_completed",
            ),
        ),
        "external_websocket_loss": FaultSchedule(
            "external_websocket_loss",
            (
                "model_start",
                "worker_socket_lost",
                "worker_exact_claim_reattach",
                "terminal_completed",
            ),
        ),
        "worker_drain": FaultSchedule(
            "worker_drain",
            ("model_start", "worker_drain", "terminal_completed"),
        ),
        "executor_response_loss": FaultSchedule(
            "executor_response_loss",
            (
                "model_start",
                ("executor_start", executor_loss),
                "executor_response_lost",
                ("executor_attach", executor_loss),
                "terminal_completed",
            ),
        ),
        "cancellation": FaultSchedule(
            "cancellation",
            (
                "model_start",
                ("executor_start", cancellation),
                "cancel_requested",
                ("executor_attach_cancel", cancellation),
                "terminal_cancelled",
            ),
        ),
    }
    return MappingProxyType(schedules)


def simulate_fault_schedule(schedule: FaultSchedule) -> FaultResult:
    """Reduce a schedule from durable actions, never from best-effort logs."""
    if not schedule.content_free:
        raise ValueError("fault schedule must be content free")
    model_starts = 0
    executor_starts: Counter[OperationIdentity] = Counter()
    terminal_cause: Literal["completed", "cancelled"] | None = None
    durable_terminal_commits = 0
    terminal_log_records = 0
    queued_states = 0
    started_operations: set[OperationIdentity] = set()

    for step in schedule.steps:
        action = step[0] if isinstance(step, tuple) else step
        identity = step[1] if isinstance(step, tuple) else None
        if action not in _FAULT_ACTIONS:
            raise ValueError("fault schedule contains an unknown action")
        if action == "model_start":
            model_starts += 1
            if model_starts > 1:
                raise ValueError("fault schedule repeated the model start")
        elif action == "executor_start":
            assert identity is not None
            executor_starts[identity] += 1
            started_operations.add(identity)
            if executor_starts[identity] > 1:
                raise ValueError("fault schedule repeated an executor operation")
        elif action in {"executor_attach", "executor_attach_cancel"}:
            if identity not in started_operations:
                raise ValueError(
                    "fault schedule attached an unknown executor operation"
                )
        elif action == "queued":
            queued_states += 1
        elif action in {"terminal_completed", "terminal_cancelled"}:
            durable_terminal_commits += 1
            terminal_log_records += 1
            if durable_terminal_commits > 1:
                raise ValueError("fault schedule repeated the terminal commit")
            terminal_cause = (
                "completed" if action == "terminal_completed" else "cancelled"
            )
        elif action == "terminal_log_lost":
            terminal_log_records = max(0, terminal_log_records - 1)

    if model_starts != 1 or durable_terminal_commits != 1 or terminal_cause is None:
        raise ValueError("fault schedule lacks one model start and terminal outcome")
    return FaultResult(
        model_starts=model_starts,
        executor_starts_by_operation=executor_starts,
        terminal_cause=terminal_cause,
        durable_terminal_commits=durable_terminal_commits,
        terminal_log_records=terminal_log_records,
        queued_states=queued_states,
    )
