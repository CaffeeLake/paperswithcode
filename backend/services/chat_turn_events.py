"""Typed internal chat-turn events and lifecycle transitions.

This is a compatibility seam: orchestration still exchanges the established
dictionary frames, while this module gives new code a closed vocabulary and a
lossless conversion boundary.  Keeping the conversion here makes the eventual
orchestrator migration mechanical rather than a protocol change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, ClassVar


class TerminalOutcome(StrEnum):
    """Closed terminal outcomes used by the existing ``done`` frame."""

    SUCCESS = "success"
    MAX_TURNS = "max_turns"
    TOOL_LIMIT = "tool_limit"
    STOPPED = "stopped"


class InterruptionReason(StrEnum):
    """Closed reasons for a turn that was intentionally interrupted."""

    CLIENT_DISCONNECT = "client_disconnect"
    STREAM_CLOSED = "stream_closed"
    STREAM_CANCELLED = "stream_cancelled"
    WORKER_CANCELLED = "worker_cancelled"


class TurnTerminalState(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class ArtifactEventType(StrEnum):
    START = "artifact_start"
    READY = "artifact_ready"
    ERROR = "artifact_error"


@dataclass(frozen=True, kw_only=True)
class _TypedEvent:
    """Base class retaining legacy payload fields verbatim."""

    payload: dict[str, Any] = field(default_factory=dict)
    event_type: ClassVar[str]

    def to_legacy(self) -> dict[str, Any]:
        return {"type": self.event_type, **self.payload}


@dataclass(frozen=True, kw_only=True)
class ResearchFinishedEvent(_TypedEvent):
    """The research producer has exhausted its source stream."""

    event_type: ClassVar[str] = "_research_finished"


@dataclass(frozen=True, kw_only=True)
class TitleEvent(_TypedEvent):
    """A public title update emitted by the concurrent title producer."""

    event_type: ClassVar[str] = "session_title_done"

    @property
    def title(self) -> str:
        return str(self.payload["title"])


@dataclass(frozen=True, kw_only=True)
class TitleFinishedEvent(_TypedEvent):
    """The title producer has reached its terminal barrier."""

    event_type: ClassVar[str] = "_title_finished"


@dataclass(frozen=True, kw_only=True)
class PersistenceEvent(_TypedEvent):
    """A durable SDK-session binding event."""

    event_type: ClassVar[str] = "_sdk_session"

    @property
    def session_id(self) -> str:
        return str(self.payload["session_id"])


@dataclass(frozen=True, kw_only=True)
class MirrorFailureEvent(_TypedEvent):
    """The transcript mirror failed after or during execution."""

    event_type: ClassVar[str] = "_mirror_error"

    @property
    def key(self) -> dict[str, Any]:
        value = self.payload.get("key") or {}
        return value if isinstance(value, dict) else {}


@dataclass(frozen=True, kw_only=True)
class TelemetryEvent(_TypedEvent):
    """Private execution-limit and recovery telemetry."""

    event_type: ClassVar[str] = "_execution_telemetry"

    @property
    def execution_limit_reached(self) -> bool:
        return bool(self.payload.get("execution_limit_reached", False))


@dataclass(frozen=True, kw_only=True)
class UsageEvent(_TypedEvent):
    """Provider usage reported after an SDK result."""

    event_type: ClassVar[str] = "usage"

    @property
    def usage(self) -> dict[str, Any]:
        value = self.payload.get("usage") or {}
        return value if isinstance(value, dict) else {}


@dataclass(frozen=True)
class ArtifactEvent:
    """Artifact publication lifecycle frame with its exact legacy payload."""

    kind: ArtifactEventType
    payload: dict[str, Any] = field(default_factory=dict)

    def to_legacy(self) -> dict[str, Any]:
        return {"type": self.kind.value, **self.payload}


@dataclass(frozen=True)
class CompletionEvent:
    """A public completion frame with a closed outcome."""

    outcome: TerminalOutcome
    payload: dict[str, Any] = field(default_factory=dict)

    def to_legacy(self) -> dict[str, Any]:
        return {
            "type": "done",
            **self.payload,
            "finish_reason": self.outcome.value,
        }


@dataclass(frozen=True)
class FailureEvent:
    """A public failure frame or an interruption recorded by orchestration."""

    code: str | None = None
    message: str | None = None
    interruption: InterruptionReason | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def to_legacy(self) -> dict[str, Any]:
        if self.interruption is not None:
            raise ValueError("Interrupted turns have no public error frame")
        event = {"type": "error", **self.payload}
        if self.message is not None:
            event["message"] = self.message
        if self.code is not None:
            event["code"] = self.code
        return event


@dataclass(frozen=True, kw_only=True)
class CancellationEvent(_TypedEvent):
    """A worker cancellation before the orchestrator emits ``done: stopped``."""

    event_type: ClassVar[str] = "_cancelled"
    reason: InterruptionReason = InterruptionReason.WORKER_CANCELLED


@dataclass(frozen=True)
class LegacyPassthroughEvent:
    """An established event outside this initial typed migration seam."""

    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_legacy(self) -> dict[str, Any]:
        return {"type": self.event_type, **self.payload}


ChatTurnEvent = (
    ResearchFinishedEvent
    | TitleEvent
    | TitleFinishedEvent
    | PersistenceEvent
    | MirrorFailureEvent
    | TelemetryEvent
    | UsageEvent
    | ArtifactEvent
    | CompletionEvent
    | FailureEvent
    | CancellationEvent
    | LegacyPassthroughEvent
)


def from_legacy_event(event: dict[str, Any]) -> ChatTurnEvent:
    """Convert one existing dictionary frame without altering its wire shape."""

    payload = {key: value for key, value in event.items() if key != "type"}
    event_type = str(event.get("type") or "")
    if event_type == "_research_finished":
        return ResearchFinishedEvent(payload=payload)
    if event_type == "session_title_done":
        return TitleEvent(payload=payload)
    if event_type == "_title_finished":
        return TitleFinishedEvent(payload=payload)
    if event_type == "_sdk_session":
        return PersistenceEvent(payload=payload)
    if event_type == "_mirror_error":
        return MirrorFailureEvent(payload=payload)
    if event_type == "_execution_telemetry":
        return TelemetryEvent(payload=payload)
    if event_type == "usage":
        return UsageEvent(payload=payload)
    if event_type in ArtifactEventType._value2member_map_:
        return ArtifactEvent(ArtifactEventType(event_type), payload)
    if event_type == "done":
        return CompletionEvent(
            TerminalOutcome(str(payload.pop("finish_reason", "success"))), payload
        )
    if event_type == "error":
        return FailureEvent(
            code=payload.pop("code", None),
            message=payload.pop("message", None),
            payload=payload,
        )
    if event_type == "_cancelled":
        return CancellationEvent(payload=payload)
    return LegacyPassthroughEvent(event_type, payload)


@dataclass(frozen=True)
class ChatTurnLifecycle:
    """Closed lifecycle state for the concurrent research and title producers."""

    title_requested: bool = False
    research_finished: bool = False
    title_finished: bool = False
    terminal: TurnTerminalState = TurnTerminalState.ACTIVE
    outcome: TerminalOutcome | None = None
    interruption: InterruptionReason | None = None
    failure_code: str | None = None

    @property
    def ready_to_complete(self) -> bool:
        return self.research_finished and (
            not self.title_requested or self.title_finished
        )

    def transition(self, event: ChatTurnEvent) -> "ChatTurnLifecycle":
        if self.terminal is not TurnTerminalState.ACTIVE:
            raise ValueError("Cannot transition a terminal chat turn")
        if isinstance(event, ResearchFinishedEvent):
            if self.research_finished:
                raise ValueError("Research already finished")
            return self._replace(research_finished=True)
        if isinstance(event, TitleFinishedEvent):
            if not self.title_requested or self.title_finished:
                raise ValueError("Title is not awaiting completion")
            return self._replace(title_finished=True)
        if isinstance(event, CompletionEvent):
            terminal = (
                TurnTerminalState.INTERRUPTED
                if event.outcome is TerminalOutcome.STOPPED
                else TurnTerminalState.COMPLETED
            )
            return self._replace(terminal=terminal, outcome=event.outcome)
        if isinstance(event, (FailureEvent, CancellationEvent, MirrorFailureEvent)):
            interruption = (
                event.interruption
                if isinstance(event, FailureEvent)
                else (event.reason if isinstance(event, CancellationEvent) else None)
            )
            return self._replace(
                terminal=(
                    TurnTerminalState.INTERRUPTED
                    if interruption is not None
                    else TurnTerminalState.FAILED
                ),
                interruption=interruption,
                failure_code=(
                    event.code
                    if isinstance(event, FailureEvent)
                    else (
                        "transcript_mirror_error"
                        if isinstance(event, MirrorFailureEvent)
                        else "interrupted"
                    )
                ),
            )
        return self

    def persistence_outcome(self) -> tuple[str, str | None, str | None]:
        """Return legacy ``status``, ``finish_reason``, and failure code values."""

        if self.terminal is TurnTerminalState.COMPLETED:
            assert self.outcome is not None
            return "complete", self.outcome.value, None
        if self.terminal is TurnTerminalState.INTERRUPTED:
            return "interrupted", None, self.failure_code or "interrupted"
        if self.terminal is TurnTerminalState.FAILED:
            return "error", None, self.failure_code or "provider_error"
        raise ValueError("Active chat turns do not have a persisted outcome")

    def _replace(self, **changes: Any) -> "ChatTurnLifecycle":
        values = {
            "title_requested": self.title_requested,
            "research_finished": self.research_finished,
            "title_finished": self.title_finished,
            "terminal": self.terminal,
            "outcome": self.outcome,
            "interruption": self.interruption,
            "failure_code": self.failure_code,
        }
        values.update(changes)
        return ChatTurnLifecycle(**values)
