"""Bounded extraction of trusted usage from native OpenAI Responses SSE."""

from __future__ import annotations

import json
from dataclasses import dataclass

MAX_ACCOUNTING_EVENT_BYTES = 256 * 1024


@dataclass(frozen=True)
class ExtractedOpenAIUsage:
    response_id: str | None = None
    service_tier: str | None = None
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    cache_write_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    outcome: str | None = None
    cost_microusd: int | None = None
    tool_call_count: int = 0

    @property
    def prompt_tokens(self) -> int | None:
        return self.input_tokens

    @property
    def completion_tokens(self) -> int | None:
        return self.output_tokens

    @property
    def cache_read_tokens(self) -> int | None:
        return self.cached_input_tokens

    @property
    def generation_id(self) -> str | None:
        return self.response_id

    @property
    def provider(self) -> str:
        return "openai"


class OpenAIResponsesUsageExtractor:
    """Inspect complete SSE frames without changing forwarded provider bytes."""

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._usage = ExtractedOpenAIUsage()
        self.saw_token_delta = False
        self.saw_tool_call = False
        self._tool_call_ids: set[str] = set()

    def feed(self, chunk: bytes) -> None:
        if not chunk:
            return
        self._buffer.extend(chunk)
        while True:
            boundary = self._next_boundary()
            if boundary is None:
                if len(self._buffer) > MAX_ACCOUNTING_EVENT_BYTES:
                    self._buffer.clear()
                return
            end, separator_length = boundary
            event = bytes(self._buffer[:end])
            del self._buffer[: end + separator_length]
            if len(event) <= MAX_ACCOUNTING_EVENT_BYTES:
                self._parse_event(event)

    def _next_boundary(self) -> tuple[int, int] | None:
        candidates = [
            (index, size)
            for index, size in (
                (self._buffer.find(b"\n\n"), 2),
                (self._buffer.find(b"\r\n\r\n"), 4),
            )
            if index >= 0
        ]
        return min(candidates, default=None)

    def _parse_event(self, event: bytes) -> None:
        data = [
            line[5:].lstrip(b" ")
            for line in event.replace(b"\r\n", b"\n").split(b"\n")
            if line.startswith(b"data:")
        ]
        if not data:
            return
        raw = b"\n".join(data)
        if raw in {b"", b"[DONE]"}:
            return
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        self._inspect(payload)

    def _inspect(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        event_type = payload.get("type")
        if event_type in {
            "response.output_text.delta",
            "response.reasoning_summary_text.delta",
            "response.function_call_arguments.delta",
        }:
            self.saw_token_delta = True
        if event_type in {
            "response.function_call_arguments.delta",
            "response.function_call_arguments.done",
        }:
            self.saw_tool_call = True
            call_id = payload.get("item_id") or payload.get("call_id")
            self._tool_call_ids.add(
                call_id if isinstance(call_id, str) else "uncorrelated"
            )
        if event_type == "response.output_item.added":
            item = payload.get("item")
            if isinstance(item, dict) and item.get("type") == "function_call":
                self.saw_tool_call = True
                call_id = item.get("id") or item.get("call_id")
                self._tool_call_ids.add(
                    call_id if isinstance(call_id, str) else "uncorrelated"
                )
        response = payload.get("response")
        if not isinstance(response, dict):
            response = payload
        response_id = self._text(response.get("id"), 255)
        service_tier = self._text(response.get("service_tier"), 32)
        usage = response.get("usage")
        current = self._usage
        self._usage = ExtractedOpenAIUsage(
            response_id=response_id or current.response_id,
            service_tier=service_tier or current.service_tier,
            input_tokens=self._prefer(
                self._usage_integer(usage, "input_tokens"), current.input_tokens
            ),
            cached_input_tokens=self._detail_integer(
                usage, "input_tokens_details", "cached_tokens"
            )
            if self._detail_integer(usage, "input_tokens_details", "cached_tokens")
            is not None
            else current.cached_input_tokens,
            cache_write_tokens=self._prefer(
                self._detail_integer(
                    usage, "input_tokens_details", "cache_write_tokens"
                ),
                self._prefer(
                    self._detail_integer(
                        usage, "input_tokens_details", "cache_creation_tokens"
                    ),
                    current.cache_write_tokens,
                ),
            ),
            output_tokens=self._prefer(
                self._usage_integer(usage, "output_tokens"), current.output_tokens
            ),
            reasoning_tokens=self._prefer(
                self._detail_integer(
                    usage, "output_tokens_details", "reasoning_tokens"
                ),
                current.reasoning_tokens,
            ),
            outcome=(
                "completed"
                if event_type == "response.completed"
                else "failed"
                if event_type in {"response.failed", "error"}
                else "incomplete"
                if event_type == "response.incomplete"
                else current.outcome
            ),
            tool_call_count=len(self._tool_call_ids),
        )

    @staticmethod
    def _integer(value: object) -> int | None:
        return (
            value
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0
            else None
        )

    @staticmethod
    def _prefer(value: int | None, fallback: int | None) -> int | None:
        return fallback if value is None else value

    def _usage_integer(self, usage: object, key: str) -> int | None:
        return self._integer(usage.get(key)) if isinstance(usage, dict) else None

    def _detail_integer(self, usage: object, group: str, key: str) -> int | None:
        if not isinstance(usage, dict) or not isinstance(usage.get(group), dict):
            return None
        return self._integer(usage[group].get(key))

    @staticmethod
    def _text(value: object, limit: int) -> str | None:
        return value[:limit] if isinstance(value, str) and value else None

    def result(self) -> ExtractedOpenAIUsage:
        return self._usage


def classify_openai_error(status_code: int | None, body: bytes = b"") -> str:
    """Map structured provider failures without leaking upstream error content."""

    error_type = ""
    error_code = ""
    if len(body) <= MAX_ACCOUNTING_EVENT_BYTES:
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = None
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict):
            error_type = str(error.get("type") or "").lower()
            error_code = str(error.get("code") or "").lower()
    if status_code in {401, 403}:
        return "openai_unavailable"
    if status_code == 429:
        quota_markers = {
            "insufficient_quota",
            "billing_hard_limit_reached",
            "usage_limit_reached",
            "monthly_limit_reached",
        }
        if error_code in quota_markers or error_type in quota_markers:
            return "openai_budget_exhausted"
        return "openai_rate_limited"
    if status_code == 400:
        return "openai_invalid_request"
    return "openai_unavailable"
