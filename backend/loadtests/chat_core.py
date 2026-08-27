"""Dependency-free contracts shared by the staging chat load-test adapter."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

STAGING_ORIGIN = "https://staging.paperswithcode.co"
CONFIRMATION = "RUN_BOUNDED_STAGING_CHAT_LOAD"
MAX_CHECKPOINT_USERS = 2
MAX_PROMPT_CHARS = 1024
MAX_OUTPUT_CHARS = 64 * 1024
PROTECTED_DAILY_SPEND_CAPS = (
    "PWC_CHAT_OPENAI_DAILY_BUDGET_USD",
    "PWC_CHAT_OPENROUTER_DAILY_BUDGET_USD",
)


class RunRefused(ValueError):
    """The operator configuration does not satisfy the staging safety gate."""


@dataclass(frozen=True)
class LoadProfile:
    name: str
    users: int
    spawn_rate: float
    cohort: str
    metric_label: str
    same_account: bool = False


@dataclass(frozen=True)
class RunConfig:
    host: str
    profile: LoadProfile
    synthetic_cookies: tuple[str, ...]
    max_users: int
    max_spend_usd: float
    protected_spend_cap_usd: float | None
    max_prompt_chars: int
    max_output_chars: int


PROFILES = {
    "bridge-smoke": LoadProfile(
        "bridge-smoke", 2, 1.0, "connection-only", "bridge_smoke"
    ),
    "steady-10": LoadProfile("steady-10", 10, 1.0, "stream", "steady_10"),
    "steady-25": LoadProfile("steady-25", 25, 2.0, "stream", "steady_25"),
    "steady-50": LoadProfile("steady-50", 50, 5.0, "stream", "steady_50"),
    "steady-100": LoadProfile("steady-100", 100, 10.0, "stream", "steady_100"),
    "burst": LoadProfile("burst", 25, 25.0, "stream", "burst"),
    "same-account-contention": LoadProfile(
        "same-account-contention",
        2,
        2.0,
        "stream",
        "same_account_contention",
        same_account=True,
    ),
    "reconnect": LoadProfile("reconnect", 2, 1.0, "reconnect", "reconnect"),
    "safe-cli": LoadProfile("safe-cli", 2, 1.0, "stream", "safe_cli"),
    "general-bash": LoadProfile("general-bash", 2, 1.0, "stream", "general_bash"),
    "overload": LoadProfile("overload", 3, 3.0, "stream", "overload"),
    "connection-only": LoadProfile(
        "connection-only", 2, 1.0, "connection-only", "connection_only"
    ),
}

_PROMPTS = {
    "safe-cli": "Reply with READY only. Do not call tools.",
    "general-bash": "Run `printf loadtest-ready` once, then report only the exit code.",
    "reconnect": "Reply with READY only. Do not call tools.",
    "same-account-contention": "Reply with READY only. Do not call tools.",
    "overload": "Reply with READY only. Do not call tools.",
    "stream": "Reply with READY only. Do not call tools.",
}


def _required(environment: Mapping[str, str], name: str, description: str) -> str:
    value = environment.get(name, "").strip()
    if not value:
        raise RunRefused(f"explicit {description} is required")
    return value


def _positive_int(raw: str, description: str, *, maximum: int) -> int:
    try:
        value = int(raw)
    except ValueError as error:
        raise RunRefused(f"{description} must be an integer") from error
    if not 1 <= value <= maximum:
        raise RunRefused(f"{description} must be between 1 and {maximum}")
    return value


def load_run_config(environment: Mapping[str, str]) -> RunConfig:
    """Validate the complete fail-closed operator envelope from environment."""

    host = _required(environment, "PWC_LOADTEST_HOST", "host")
    if host != STAGING_ORIGIN:
        raise RunRefused(f"host must be the exact staging origin {STAGING_ORIGIN}")
    confirmation = _required(environment, "PWC_LOADTEST_CONFIRM", "confirmation")
    if confirmation != CONFIRMATION:
        raise RunRefused(f"confirmation must equal {CONFIRMATION}")
    profile_name = _required(environment, "PWC_LOADTEST_PROFILE", "profile selection")
    try:
        profile = PROFILES[profile_name]
    except KeyError as error:
        raise RunRefused("profile selection is not recognized") from error
    if profile.users > MAX_CHECKPOINT_USERS:
        raise RunRefused(
            f"profile {profile.name} is definition-only above the two-user checkpoint"
        )

    raw_cookies = _required(
        environment,
        "PWC_LOADTEST_SYNTHETIC_COOKIES",
        "dedicated synthetic session cookies",
    )
    try:
        cookies = json.loads(raw_cookies)
    except json.JSONDecodeError as error:
        raise RunRefused("synthetic session cookies must be a JSON array") from error
    if (
        not isinstance(cookies, list)
        or not cookies
        or not all(isinstance(cookie, str) and cookie.strip() for cookie in cookies)
    ):
        raise RunRefused("dedicated synthetic session cookies are required")
    synthetic_cookies = tuple(cookie.strip() for cookie in cookies)
    required_cookies = 1 if profile.same_account else profile.users
    if len(synthetic_cookies) < required_cookies:
        raise RunRefused(
            f"profile requires at least {required_cookies} synthetic session cookies"
        )
    if not profile.same_account and len(set(synthetic_cookies)) < required_cookies:
        raise RunRefused(
            f"profile requires at least {required_cookies} distinct synthetic session cookies"
        )

    max_users = _positive_int(
        _required(environment, "PWC_LOADTEST_MAX_USERS", "user envelope"),
        "user envelope",
        maximum=MAX_CHECKPOINT_USERS,
    )
    if max_users < profile.users:
        raise RunRefused("user envelope is below the selected profile")
    raw_spend = _required(environment, "PWC_LOADTEST_MAX_SPEND_USD", "spend envelope")
    try:
        max_spend_usd = float(raw_spend)
    except ValueError as error:
        raise RunRefused("spend envelope must be numeric") from error
    if not math.isfinite(max_spend_usd):
        raise RunRefused("spend envelope must be finite")
    if max_spend_usd < 0 or max_spend_usd > 10:
        raise RunRefused("spend envelope must be between 0 and 10 USD")
    protected_spend_cap_usd: float | None = None
    if profile.cohort == "connection-only":
        if max_spend_usd != 0:
            raise RunRefused("connection-only profiles require a zero spend envelope")
    else:
        if max_spend_usd <= 0:
            raise RunRefused("stream profiles require a positive spend envelope")
        loaded_caps = [
            environment[name]
            for name in PROTECTED_DAILY_SPEND_CAPS
            if name in environment
        ]
        if not loaded_caps:
            raise RunRefused("protected daily spend cap is required")
        try:
            declared_spend = Decimal(raw_spend)
            protected_caps = [Decimal(raw_cap.strip()) for raw_cap in loaded_caps]
        except (InvalidOperation, AttributeError) as error:
            raise RunRefused("protected daily spend cap is invalid") from error
        if any(not cap.is_finite() or cap <= 0 for cap in protected_caps):
            raise RunRefused("protected daily spend cap is invalid")
        if any(cap != declared_spend for cap in protected_caps):
            raise RunRefused(
                "protected daily spend cap does not match declared envelope"
            )
        protected_spend_cap_usd = float(declared_spend)

    max_prompt_chars = _positive_int(
        _required(environment, "PWC_LOADTEST_MAX_PROMPT_CHARS", "prompt bound"),
        "prompt bound",
        maximum=MAX_PROMPT_CHARS,
    )
    max_output_chars = _positive_int(
        _required(environment, "PWC_LOADTEST_MAX_OUTPUT_CHARS", "output bound"),
        "output bound",
        maximum=MAX_OUTPUT_CHARS,
    )
    return RunConfig(
        host=host,
        profile=profile,
        synthetic_cookies=synthetic_cookies,
        max_users=max_users,
        max_spend_usd=max_spend_usd,
        protected_spend_cap_usd=protected_spend_cap_usd,
        max_prompt_chars=max_prompt_chars,
        max_output_chars=max_output_chars,
    )


def build_turn_request(
    profile: LoadProfile, *, client_message_id: str, max_prompt_chars: int
) -> dict[str, object]:
    """Build one bounded synthetic turn for executable future profiles."""

    if profile.cohort == "connection-only":
        raise RunRefused("connection-only profile does not admit chat turns")
    prompt = _PROMPTS.get(profile.name, _PROMPTS["stream"])
    if len(prompt) > max_prompt_chars:
        raise RunRefused("profile prompt fixture exceeds the configured prompt bound")
    return {
        "message": prompt,
        "session_id": None,
        "client_message_id": client_message_id,
        "web_search_enabled": False,
        "reasoning_effort": "low",
    }


class SSEParseError(ValueError):
    """A bounded, content-free SSE protocol failure."""


class SSEParser:
    """Incrementally parse JSON objects from SSE ``data`` fields."""

    def __init__(self, *, max_event_bytes: int = 128 * 1024) -> None:
        if max_event_bytes < 1:
            raise ValueError("max_event_bytes must be positive")
        self._maximum = max_event_bytes
        self._buffer = bytearray()

    def feed(self, chunk: bytes) -> list[dict[str, Any]]:
        self._buffer.extend(chunk)
        events: list[dict[str, Any]] = []
        while True:
            normalized = bytes(self._buffer).replace(b"\r\n", b"\n")
            separator = normalized.find(b"\n\n")
            if separator < 0:
                if len(self._buffer) > self._maximum:
                    raise SSEParseError(f"SSE event exceeds {self._maximum} bytes")
                return events
            raw = normalized[:separator]
            consumed = self._consumed_bytes(separator + 2)
            del self._buffer[:consumed]
            if len(raw) > self._maximum:
                raise SSEParseError(f"SSE event exceeds {self._maximum} bytes")
            parsed = self._parse_frame(raw)
            if parsed is not None:
                events.append(parsed)

    def close(self) -> list[dict[str, Any]]:
        if not self._buffer:
            return []
        normalized = bytes(self._buffer).replace(b"\r\n", b"\n")
        self._buffer.clear()
        if len(normalized) > self._maximum:
            raise SSEParseError(f"SSE event exceeds {self._maximum} bytes")
        parsed = self._parse_frame(normalized)
        return [] if parsed is None else [parsed]

    def _consumed_bytes(self, normalized_length: int) -> int:
        consumed = 0
        normalized = 0
        data = self._buffer
        while consumed < len(data) and normalized < normalized_length:
            if (
                data[consumed] == 13
                and consumed + 1 < len(data)
                and data[consumed + 1] == 10
            ):
                consumed += 2
            else:
                consumed += 1
            normalized += 1
        return consumed

    @staticmethod
    def _parse_frame(raw: bytes) -> dict[str, Any] | None:
        data_lines = []
        for line in raw.split(b"\n"):
            if not line.startswith(b"data:"):
                continue
            value = line[5:]
            if value.startswith(b" "):
                value = value[1:]
            data_lines.append(value)
        data = b"\n".join(data_lines)
        if not data or data == b"[DONE]":
            return None
        try:
            event = json.loads(data)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SSEParseError("SSE data is not valid JSON") from error
        if not isinstance(event, dict):
            raise SSEParseError("SSE data must be a JSON object")
        return event


def classify_event(event: Mapping[str, Any]) -> str:
    """Return a fixed-cardinality metric label for a parsed public event."""

    event_type = event.get("type")
    if event_type == "stream_start":
        return "admission"
    if event_type == "done":
        return "terminal"
    if event_type == "error":
        code = event.get("code")
        if code == "account_busy":
            return "account_busy"
        if code in {"chat_overload", "chat_capacity"}:
            return "overload"
        return "stream_error"
    return "event"


def classify_refusal(payload: object) -> str:
    """Classify an HTTP error body without using its unbounded message text."""

    if not isinstance(payload, Mapping):
        return "stream_error"
    detail = payload.get("detail")
    if not isinstance(detail, Mapping):
        return "stream_error"
    code = detail.get("code")
    if code == "account_busy":
        return "account_busy"
    if code in {"chat_overload", "chat_capacity"}:
        return "overload"
    return "stream_error"


def classify_refusal_bytes(data: bytes, *, max_bytes: int = 4096) -> str:
    """Parse a bounded HTTP refusal body into a fixed-cardinality label."""

    if len(data) > max_bytes:
        return "stream_error"
    try:
        payload = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "stream_error"
    return classify_refusal(payload)


@dataclass(frozen=True)
class Metric:
    name: str
    elapsed_ms: int
    success: bool


class StreamMetricTracker:
    """Derive explicit milestones; never infer terminal time from HTTP timing."""

    def __init__(
        self,
        *,
        first_event_name: str = "chat.first_event",
        record_admission: bool = True,
    ) -> None:
        self._saw_event = False
        self._first_event_name = first_event_name
        self._record_admission = record_admission

    def observe(self, event: Mapping[str, Any], *, elapsed_ms: int) -> list[Metric]:
        metrics: list[Metric] = []
        if not self._saw_event:
            self._saw_event = True
            metrics.append(Metric(self._first_event_name, elapsed_ms, True))
        classification = classify_event(event)
        if classification == "admission" and self._record_admission:
            metrics.append(Metric("chat.admission", elapsed_ms, True))
        elif classification == "terminal":
            metrics.append(Metric("chat.terminal", elapsed_ms, True))
        elif classification in {"stream_error", "account_busy", "overload"}:
            metrics.append(Metric(f"chat.{classification}", elapsed_ms, False))
        return metrics


@dataclass(frozen=True)
class StreamBatch:
    events: list[dict[str, Any]]
    metrics: list[Metric]


class BoundedSSEStream:
    """Apply identical parsing, output, and terminal rules to an SSE stream."""

    def __init__(self, *, max_output_chars: int, replay: bool = False) -> None:
        self._parser = SSEParser(max_event_bytes=max(4096, max_output_chars * 2))
        self._tracker = StreamMetricTracker(
            first_event_name="chat.first_replay" if replay else "chat.first_event",
            record_admission=not replay,
        )
        self._maximum_output = max_output_chars
        self._output_chars = 0
        self._finished = False
        self._successful_terminal = False

    @property
    def finished(self) -> bool:
        return self._finished

    @property
    def successful_terminal(self) -> bool:
        return self._successful_terminal

    def feed(self, chunk: bytes, *, elapsed_ms: int) -> StreamBatch:
        if self._finished:
            raise SSEParseError("SSE event arrived after terminal event")
        return self._observe(self._parser.feed(chunk), elapsed_ms=elapsed_ms)

    def close(self, *, elapsed_ms: int) -> StreamBatch:
        if self._finished:
            return StreamBatch([], [])
        return self._observe(self._parser.close(), elapsed_ms=elapsed_ms)

    def _observe(self, events: list[dict[str, Any]], *, elapsed_ms: int) -> StreamBatch:
        metrics: list[Metric] = []
        for event in events:
            metrics.extend(self._tracker.observe(event, elapsed_ms=elapsed_ms))
            event_type = event.get("type")
            if event_type in {"answer_delta", "reasoning_delta"}:
                text = event.get("text")
                self._output_chars += len(text) if isinstance(text, str) else 0
                if self._output_chars > self._maximum_output:
                    raise SSEParseError("stream output exceeded configured bound")
            if event_type in {"done", "error"}:
                self._finished = True
                self._successful_terminal = event_type == "done"
                break
        return StreamBatch(events, metrics)
