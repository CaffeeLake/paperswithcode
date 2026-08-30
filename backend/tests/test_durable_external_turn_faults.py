from __future__ import annotations

from collections import Counter

import pytest

from backend.loadtests.durable_external_turn_faults import (
    FaultSchedule,
    OperationIdentity,
    built_in_fault_schedules,
    simulate_fault_schedule,
)


@pytest.mark.parametrize(
    ("name", "terminal_cause", "executor_starts"),
    (
        ("browser_disconnect", "completed", 0),
        ("api_subscriber_process_loss", "completed", 0),
        ("external_websocket_loss", "completed", 0),
        ("worker_drain", "completed", 0),
        ("executor_response_loss", "completed", 1),
        ("cancellation", "cancelled", 1),
    ),
)
def test_fault_schedule_preserves_single_model_and_executor_operation(
    name: str, terminal_cause: str, executor_starts: int
) -> None:
    """Catches reconnect paths that replay model or executor work."""
    result = simulate_fault_schedule(built_in_fault_schedules()[name])

    assert result.model_starts == 1
    assert result.executor_starts == executor_starts
    assert result.terminal_cause == terminal_cause
    assert result.durable_terminal_commits == 1
    assert result.queued_states == 0
    assert all(count <= 1 for count in result.executor_starts_by_operation.values())


def test_all_six_fault_schedules_are_content_free_and_have_stable_identity() -> None:
    """Catches a schedule accidentally retaining prompts, commands, or tokens."""
    schedules = built_in_fault_schedules()

    assert tuple(schedules) == (
        "browser_disconnect",
        "api_subscriber_process_loss",
        "external_websocket_loss",
        "worker_drain",
        "executor_response_loss",
        "cancellation",
    )
    assert all(schedule.content_free for schedule in schedules.values())
    operation_ids = [
        operation
        for schedule in schedules.values()
        for operation in schedule.operation_identities
    ]
    assert operation_ids == [
        OperationIdentity("turn-0005", "tool-0001", 0),
        OperationIdentity("turn-0006", "tool-0001", 0),
    ]


def test_duplicate_start_steps_cannot_forge_exactly_once_evidence() -> None:
    """Catches a simulator/report path that hides duplicate provider execution."""
    schedule = FaultSchedule(
        name="duplicate_model_start",
        steps=("model_start", "model_start", "terminal_completed"),
    )

    with pytest.raises(ValueError, match="model start"):
        simulate_fault_schedule(schedule)


def test_unknown_fault_action_cannot_forge_recovery_evidence() -> None:
    schedule = FaultSchedule(
        name="forged_recovery",
        steps=("model_start", "unverified_reattach", "terminal_completed"),
    )

    with pytest.raises(ValueError, match="unknown action"):
        simulate_fault_schedule(schedule)


def test_executor_identity_is_counted_directly_not_inferred_from_logs() -> None:
    """Catches Task 10's parked log undercount being mistaken for durable truth."""
    identity = OperationIdentity("turn-0001", "tool-0001", 0)
    result = simulate_fault_schedule(
        FaultSchedule(
            name="terminal_log_loss",
            steps=(
                "model_start",
                ("executor_start", identity),
                ("executor_attach", identity),
                "terminal_completed",
                "terminal_log_lost",
            ),
        )
    )

    assert result.executor_starts_by_operation == Counter({identity: 1})
    assert result.durable_terminal_commits == 1
    assert result.terminal_log_records == 0
    assert result.terminal_cause == "completed"
