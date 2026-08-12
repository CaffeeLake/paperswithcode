"""Bounded, byte-transparent extraction of trusted OpenRouter usage data."""

from __future__ import annotations

import json
from dataclasses import dataclass

from backend.services.openrouter_user_budget_service import parse_provider_cost_microusd

MAX_ACCOUNTING_EVENT_BYTES = 256 * 1024


@dataclass(frozen=True)
class ExtractedOpenRouterUsage:
    cost_microusd: int | None
    generation_id: str | None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_creation_tokens: int | None = None
    reasoning_tokens: int | None = None
    provider: str | None = None


class OpenRouterUsageExtractor:
    """Inspect complete SSE events while callers forward original bytes."""

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._cost_microusd: int | None = None
        self._generation_id: str | None = None
        self._prompt_tokens: int | None = None
        self._completion_tokens: int | None = None
        self._cache_read_tokens: int | None = None
        self._cache_creation_tokens: int | None = None
        self._reasoning_tokens: int | None = None
        self._provider: str | None = None
        self._conflicting_cost = False

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
                self._parse_sse_event(event)

    def _next_boundary(self) -> tuple[int, int] | None:
        lf = self._buffer.find(b"\n\n")
        crlf = self._buffer.find(b"\r\n\r\n")
        candidates = [(lf, 2), (crlf, 4)]
        present = [candidate for candidate in candidates if candidate[0] >= 0]
        return min(present, default=None)

    def _parse_sse_event(self, event: bytes) -> None:
        data_lines: list[bytes] = []
        for line in event.replace(b"\r\n", b"\n").split(b"\n"):
            if line.startswith(b"data:"):
                data_lines.append(line[5:].lstrip(b" "))
        if not data_lines:
            return
        raw = b"\n".join(data_lines)
        if raw in {b"", b"[DONE]"}:
            return
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        self._inspect(payload)

    def inspect_complete_response(self, raw: bytes) -> None:
        if len(raw) > MAX_ACCOUNTING_EVENT_BYTES:
            return
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        self._inspect(payload)

    def _inspect(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        nested = payload.get("data")
        message = payload.get("message")
        source = (
            message
            if isinstance(message, dict)
            else nested
            if isinstance(nested, dict)
            else payload
        )
        generation_id = source.get("id", payload.get("id"))
        if isinstance(generation_id, str) and generation_id:
            self._generation_id = generation_id[:1000]
        provider = payload.get("provider", source.get("provider"))
        if isinstance(provider, str) and provider:
            self._provider = provider[:255]
        usage = payload.get("usage", source.get("usage"))
        if not isinstance(usage, dict):
            return
        cost = parse_provider_cost_microusd(usage.get("cost", usage.get("total_cost")))
        if cost is not None:
            if self._cost_microusd is not None and self._cost_microusd != cost:
                self._conflicting_cost = True
            else:
                self._cost_microusd = cost
        self._prompt_tokens = self._integer(
            usage.get("prompt_tokens", usage.get("input_tokens"))
        )
        self._completion_tokens = self._integer(
            usage.get("completion_tokens", usage.get("output_tokens"))
        )
        input_details = usage.get("input_tokens_details")
        prompt_details = usage.get("prompt_tokens_details")
        cache_details = (
            input_details
            if isinstance(input_details, dict)
            else prompt_details
            if isinstance(prompt_details, dict)
            else {}
        )
        self._cache_read_tokens = self._integer(
            usage.get(
                "cache_read_input_tokens",
                usage.get("cache_read_tokens", cache_details.get("cached_tokens")),
            )
        )
        self._cache_creation_tokens = self._integer(
            usage.get("cache_creation_input_tokens", usage.get("cache_write_tokens"))
        )
        output_details = usage.get("output_tokens_details")
        completion_details = usage.get("completion_tokens_details")
        reasoning_details = (
            output_details
            if isinstance(output_details, dict)
            else completion_details
            if isinstance(completion_details, dict)
            else {}
        )
        self._reasoning_tokens = self._integer(
            reasoning_details.get("reasoning_tokens", usage.get("reasoning_tokens"))
        )

    @staticmethod
    def _integer(value: object) -> int | None:
        return (
            value
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0
            else None
        )

    def result(self) -> ExtractedOpenRouterUsage:
        return ExtractedOpenRouterUsage(
            cost_microusd=None if self._conflicting_cost else self._cost_microusd,
            generation_id=self._generation_id,
            prompt_tokens=self._prompt_tokens,
            completion_tokens=self._completion_tokens,
            cache_read_tokens=self._cache_read_tokens,
            cache_creation_tokens=self._cache_creation_tokens,
            reasoning_tokens=self._reasoning_tokens,
            provider=self._provider,
        )
