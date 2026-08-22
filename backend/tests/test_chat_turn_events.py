"""Contract tests for the typed chat-turn seam.

The orchestrator still consumes legacy dictionaries.  These tests pin the
lossless conversion and lifecycle rules until it is migrated to the typed
events directly.
"""

from __future__ import annotations

import pytest

from backend.services.chat_turn_events import (
    ChatTurnLifecycle,
    CompletionEvent,
    FailureEvent,
    InterruptionReason,
    ResearchFinishedEvent,
    TerminalOutcome,
    TitleFinishedEvent,
    TurnTerminalState,
    from_legacy_event,
)
from backend.services.chat_stream_service import ChatStreamFrame


@pytest.mark.parametrize(
    "legacy",
    [
        {"type": "_research_finished"},
        {"type": "session_title_done", "title": "A title"},
        {"type": "_title_finished"},
        {"type": "_sdk_session", "session_id": "sdk-session"},
        {"type": "_mirror_error", "key": {"session_id": "sdk-session"}},
        {
            "type": "_execution_telemetry",
            "maximum_tool_calls": 8,
            "execution_limit_reached": False,
        },
        {"type": "usage", "usage": {"input_tokens": 2}, "model_usage": {}},
        {
            "type": "artifact_start",
            "publication_id": "poster-1",
            "identifier": "paper-poster",
            "kind": "posterly",
            "title": "Paper poster",
        },
        {"type": "done", "followups": [], "finish_reason": "success"},
        {"type": "error", "code": "provider_error", "message": "Unavailable"},
    ],
)
def test_typed_event_conversion_preserves_legacy_frames(legacy):
    assert from_legacy_event(legacy).to_legacy() == legacy


def test_typed_event_conversion_preserves_transport_frame_payload():
    frame = ChatStreamFrame("done", {"followups": ["Next"], "finish_reason": "success"})

    event = from_legacy_event({"type": frame.event, **frame.payload})

    assert event.to_legacy() == {
        "type": "done",
        "followups": ["Next"],
        "finish_reason": "success",
    }


def test_lifecycle_allows_title_and_research_to_finish_in_either_order():
    lifecycle = ChatTurnLifecycle(title_requested=True)

    lifecycle = lifecycle.transition(TitleFinishedEvent())
    assert lifecycle.research_finished is False
    assert lifecycle.title_finished is True

    lifecycle = lifecycle.transition(ResearchFinishedEvent())
    assert lifecycle.ready_to_complete

    completed = lifecycle.transition(CompletionEvent(TerminalOutcome.SUCCESS))
    assert completed.terminal is TurnTerminalState.COMPLETED


def test_lifecycle_preserves_completion_and_interruption_persistence_outcomes():
    for outcome in (
        TerminalOutcome.SUCCESS,
        TerminalOutcome.MAX_TURNS,
        TerminalOutcome.TOOL_LIMIT,
    ):
        completed = ChatTurnLifecycle().transition(CompletionEvent(outcome))
        assert completed.persistence_outcome() == ("complete", outcome.value, None)

    interrupted = ChatTurnLifecycle().transition(
        FailureEvent(interruption=InterruptionReason.CLIENT_DISCONNECT)
    )
    assert interrupted.terminal is TurnTerminalState.INTERRUPTED
    assert interrupted.persistence_outcome() == ("interrupted", None, "interrupted")

    failed = ChatTurnLifecycle().transition(FailureEvent(code="provider_rate_limit"))
    assert failed.persistence_outcome() == ("error", None, "provider_rate_limit")


def test_lifecycle_rejects_events_after_a_terminal_outcome():
    lifecycle = ChatTurnLifecycle().transition(CompletionEvent(TerminalOutcome.SUCCESS))

    with pytest.raises(ValueError, match="terminal"):
        lifecycle.transition(ResearchFinishedEvent())
