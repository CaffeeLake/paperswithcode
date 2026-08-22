"""Compatibility tests for typed chat-turn events and lifecycle states."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from backend.services.chat_turn_event_service import (
    ChatTurnLifecycle,
    CompletionEvent,
    MirrorFailureEvent,
    PersistedTurnStatus,
    ResearchFinishedEvent,
    TerminalOutcome,
    TitleFinishedEvent,
    TurnFinalizationState,
    TurnTerminalState,
    from_legacy_event,
)


@pytest.mark.parametrize(
    "legacy",
    [
        {"type": "_research_finished"},
        {"type": "session_title_done", "title": "A title"},
        {"type": "_title_finished"},
        {"type": "_sdk_session", "session_id": "sdk-session"},
        {"type": "_mirror_error", "key": {"session_id": "sdk-session"}},
        {"type": "_execution_telemetry", "execution_limit_reached": False},
        {"type": "usage", "usage": {"input_tokens": 2}, "model_usage": {}},
        {"type": "usage", "usage": None, "extra": {"values": []}},
        {
            "type": "artifact_start",
            "publication_id": "poster-1",
            "identifier": "poster",
            "title": "Poster",
        },
        {
            "type": "artifact_error",
            "publication_id": "poster-1",
            "code": "failed",
            "message": "Nope",
        },
        {"type": "done"},
        {"type": "done", "finish_reason": "future_outcome"},
        {"type": "done", "followups": [], "finish_reason": "success"},
        {"type": "error", "code": "provider_error", "message": "Unavailable"},
    ],
)
def test_legacy_conversion_is_lossless_for_optional_fields(legacy):
    assert from_legacy_event(legacy).to_legacy() == legacy


def test_typed_events_are_frozen_and_extras_cannot_replace_type():
    event = from_legacy_event({"type": "usage", "usage": {"input_tokens": 2}})
    with pytest.raises(FrozenInstanceError):
        event.usage = {}  # type: ignore[misc]
    with pytest.raises(TypeError):
        event.usage["input_tokens"] = 3  # type: ignore[index]
    assert event.to_legacy()["type"] == "usage"


def test_real_stream_order_allows_done_before_research_producer_finishes():
    lifecycle = ChatTurnLifecycle().transition(CompletionEvent(TerminalOutcome.SUCCESS))
    assert lifecycle.finalization is TurnFinalizationState.AWAITING_PRODUCERS

    lifecycle = lifecycle.transition(ResearchFinishedEvent())
    assert lifecycle.terminal is TurnTerminalState.COMPLETED
    assert lifecycle.finalization is TurnFinalizationState.FINALIZED


def test_lifecycle_allows_title_and_research_to_finish_in_either_order():
    lifecycle = ChatTurnLifecycle(title_requested=True)
    lifecycle = lifecycle.transition(TitleFinishedEvent())
    lifecycle = lifecycle.transition(ResearchFinishedEvent())
    lifecycle = lifecycle.transition(CompletionEvent(TerminalOutcome.TOOL_LIMIT))
    assert lifecycle.finalization is TurnFinalizationState.FINALIZED
    assert lifecycle.persistence_outcome().finish_reason is TerminalOutcome.TOOL_LIMIT


def test_mirror_failure_after_a_result_is_completed_with_degraded_transcript():
    lifecycle = ChatTurnLifecycle().transition(
        MirrorFailureEvent(
            result_available=True,
            terminal={"type": "done", "finish_reason": "success"},
        )
    )

    persisted = lifecycle.persistence_outcome()
    assert lifecycle.terminal is TurnTerminalState.COMPLETED_DEGRADED
    assert persisted.status is PersistedTurnStatus.COMPLETE
    assert persisted.transcript_degraded is True


def test_mirror_failure_without_a_result_is_an_error():
    persisted = (
        ChatTurnLifecycle().transition(MirrorFailureEvent()).persistence_outcome()
    )
    assert persisted.status is PersistedTurnStatus.ERROR
    assert persisted.error_code == "transcript_mirror_error"
