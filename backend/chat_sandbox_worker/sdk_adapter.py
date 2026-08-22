"""Canonical, dependency-light Claude SDK message-to-chat-event adapter."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    StreamEvent,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

ToolName = Callable[[str], str]
ToolAllowed = Callable[[str, str, dict[str, Any]], bool]
ToolResultFormatter = Callable[[ToolResultBlock, str, str], dict[str, Any] | None]
TerminalResultFormatter = Callable[[ResultMessage], list[dict[str, Any]]]


def _identity(value: str) -> str:
    return value


def _allow_all(_tool_id: str, _name: str, _args: dict[str, Any]) -> bool:
    return True


def _format_terminal_result(message: ResultMessage) -> list[dict[str, Any]]:
    limited = "max_turn" in message.subtype
    if message.is_error and not limited:
        return [
            {
                "type": "error",
                "code": "gateway_unavailable",
                "message": "The research run failed.",
            }
        ]
    if limited:
        return [{"type": "_execution_limit", "reason": "max_turns"}]
    return [{"type": "done", "followups": [], "finish_reason": "success"}]


@dataclass(frozen=True)
class SDKEventPolicy:
    """Deployment-owned tool projection choices for :class:`SDKEventAdapter`.

    Protocol parsing and event ordering remain shared. Each execution backend
    supplies its own public tool names, call ceiling/suppression decision, and
    optional result formatter without copying that parser.
    """

    tool_name: ToolName = _identity
    allow_tool_call: ToolAllowed = _allow_all
    on_tool_batch: Callable[[list[str]], None] | None = None
    format_tool_result: ToolResultFormatter | None = None
    format_terminal_result: TerminalResultFormatter = _format_terminal_result
    unique_tool_ids: bool = True


class SDKEventAdapter:
    """Stateful conversion from streamed and complete SDK messages to events."""

    def __init__(
        self,
        *,
        show_reasoning: bool,
        policy: SDKEventPolicy | None = None,
        on_tool_batch: Callable[[list[str]], None] | None = None,
    ):
        self.show_reasoning = show_reasoning
        self.policy = (
            replace(policy or SDKEventPolicy(), on_tool_batch=on_tool_batch)
            if on_tool_batch
            else policy or SDKEventPolicy()
        )
        self.reasoning_open = False
        self.answer_started = False
        self.saw_text_delta = False
        self.saw_thinking_delta = False
        self.terminal = False
        self.block_kinds: dict[int, str] = {}
        self.tool_blocks: dict[int, dict[str, Any]] = {}
        self.current_tool_ids: dict[str, str] = {}
        self.pending_tool_ids: dict[str, list[str | None]] = {}
        self.tool_id_occurrences: dict[str, int] = {}
        self.allocated_tool_ids: set[str] = set()
        self.tool_names: dict[str, str] = {}

    def _close_reasoning(self) -> list[dict[str, Any]]:
        if not self.reasoning_open:
            return []
        self.reasoning_open = False
        return [{"type": "reasoning_end"}]

    def _allocate_tool_id(self, raw_tool_id: str) -> str:
        if not self.policy.unique_tool_ids:
            return raw_tool_id
        occurrence = self.tool_id_occurrences.get(raw_tool_id, 0) + 1
        tool_id = raw_tool_id if occurrence == 1 else f"{raw_tool_id}#{occurrence}"
        while tool_id in self.allocated_tool_ids:
            occurrence += 1
            tool_id = f"{raw_tool_id}#{occurrence}"
        self.tool_id_occurrences[raw_tool_id] = occurrence
        self.allocated_tool_ids.add(tool_id)
        return tool_id

    def _tool_call(self, block: dict[str, Any]) -> list[dict[str, Any]]:
        raw_tool_id = str(block.get("id") or "")
        if not raw_tool_id or raw_tool_id in self.current_tool_ids:
            return []
        value = block.get("input")
        fragments = "".join(block.get("fragments", []))
        if fragments:
            try:
                value = json.loads(fragments)
            except json.JSONDecodeError:
                return []
        elif not isinstance(value, dict):
            value = {}
        name = self.policy.tool_name(str(block.get("name") or ""))
        if not self.policy.allow_tool_call(raw_tool_id, name, value):
            self.pending_tool_ids.setdefault(raw_tool_id, []).append(None)
            return []
        tool_id = self._allocate_tool_id(raw_tool_id)
        self.current_tool_ids[raw_tool_id] = tool_id
        self.pending_tool_ids.setdefault(raw_tool_id, []).append(tool_id)
        self.tool_names[tool_id] = name
        return [{"type": "tool_call", "id": tool_id, "name": name, "args": value}]

    def tool_result_id(self, raw_tool_id: str) -> str | None:
        pending = self.pending_tool_ids.get(raw_tool_id)
        if not pending:
            return raw_tool_id
        tool_id = pending.pop(0)
        if not pending:
            self.pending_tool_ids.pop(raw_tool_id, None)
        self.current_tool_ids.pop(raw_tool_id, None)
        return tool_id

    def _tool_result(self, block: ToolResultBlock) -> list[dict[str, Any]]:
        tool_id = self.tool_result_id(block.tool_use_id)
        if tool_id is None:
            return []
        name = self.tool_names.pop(tool_id, "")
        if self.policy.format_tool_result:
            event = self.policy.format_tool_result(block, tool_id, name)
            return [event] if event is not None else []
        return [
            {
                "type": "tool_result",
                "id": tool_id,
                "status": "error" if block.is_error else "success",
                "content": block.content,
            }
        ]

    def _stream(self, message: StreamEvent) -> list[dict[str, Any]]:
        raw = message.event
        kind = raw.get("type")
        events: list[dict[str, Any]] = []
        index = int(raw.get("index", 0))
        if kind == "message_start":
            events.extend(self._close_reasoning())
            self.current_tool_ids.clear()
            self.saw_text_delta = False
            self.saw_thinking_delta = False
            self.block_kinds.clear()
            self.tool_blocks.clear()
        elif kind == "content_block_start":
            block = raw.get("content_block") or {}
            block_kind = block.get("type", "")
            self.block_kinds[index] = block_kind
            if block_kind == "thinking" and self.show_reasoning:
                events.extend(self._close_reasoning())
                self.reasoning_open = True
                events.append({"type": "reasoning_start"})
            elif block_kind == "tool_use":
                events.extend(self._close_reasoning())
                self.tool_blocks[index] = {
                    "id": block.get("id"),
                    "name": block.get("name"),
                    "input": block.get("input") if block.get("input") else None,
                    "fragments": [],
                }
            elif block_kind == "text":
                events.extend(self._close_reasoning())
        elif kind == "content_block_delta":
            delta = raw.get("delta") or {}
            if delta.get("type") == "thinking_delta" and self.show_reasoning:
                self.saw_thinking_delta = True
                if not self.reasoning_open:
                    self.reasoning_open = True
                    events.append({"type": "reasoning_start"})
                if delta.get("thinking"):
                    events.append(
                        {"type": "reasoning_delta", "text": delta["thinking"]}
                    )
            elif delta.get("type") == "text_delta":
                events.extend(self._close_reasoning())
                text = delta.get("text", "")
                if text and (self.answer_started or text.strip()):
                    self.answer_started = True
                    self.saw_text_delta = True
                    events.append({"type": "answer_delta", "text": text})
            elif delta.get("type") == "input_json_delta":
                self.tool_blocks.setdefault(
                    index, {"id": "", "name": "", "input": None, "fragments": []}
                )["fragments"].append(delta.get("partial_json", ""))
        elif kind == "content_block_stop":
            if self.block_kinds.get(index) == "thinking":
                events.extend(self._close_reasoning())
            elif self.block_kinds.get(index) == "tool_use":
                events.extend(self._tool_call(self.tool_blocks.get(index, {})))
        elif kind == "message_stop":
            events.extend(self._close_reasoning())
            if self.policy.on_tool_batch:
                self.policy.on_tool_batch(
                    [
                        str(block.get("id") or "")
                        for block in self.tool_blocks.values()
                        if block.get("id")
                    ]
                )
        return events

    def feed(self, message: Any) -> list[dict[str, Any]]:
        if isinstance(message, StreamEvent):
            return self._stream(message)
        events: list[dict[str, Any]] = []
        if isinstance(message, AssistantMessage):
            if message.error:
                self.terminal = True
                if message.error == "billing_error":
                    return [
                        {
                            "type": "error",
                            "code": "hf_inference_billing_exhausted",
                            "message": "Hugging Face could not bill this request. Your included credits may be exhausted; enable or review pay-as-you-go billing in Settings.",
                        }
                    ]
                provider_errors = {
                    "authentication_failed": (
                        "hf_inference_credential_expired",
                        "Your Hugging Face Inference Providers authorization is missing or expired. Re-sign in with Hugging Face to continue.",
                    ),
                    "rate_limit": (
                        "provider_rate_limit",
                        "The selected model is temporarily rate-limited. Try again shortly.",
                    ),
                    "server_error": (
                        "provider_unavailable",
                        "The model provider is temporarily unavailable. Try again shortly.",
                    ),
                    "invalid_request": (
                        "provider_invalid_request",
                        "The model provider rejected this request.",
                    ),
                }
                code, text = provider_errors.get(
                    message.error, ("provider_error", "The model provider failed.")
                )
                return [{"type": "error", "code": code, "message": text}]
            tool_ids = [
                block.id for block in message.content if isinstance(block, ToolUseBlock)
            ]
            if tool_ids and self.policy.on_tool_batch:
                self.policy.on_tool_batch(tool_ids)
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    events.extend(
                        self._tool_call(
                            {"id": block.id, "name": block.name, "input": block.input}
                        )
                    )
                elif isinstance(block, ThinkingBlock) and not self.saw_thinking_delta:
                    if self.show_reasoning and block.thinking:
                        events.extend(self._close_reasoning())
                        events.extend(
                            [
                                {"type": "reasoning_start"},
                                {"type": "reasoning_delta", "text": block.thinking},
                                {"type": "reasoning_end"},
                            ]
                        )
                elif (
                    isinstance(block, TextBlock)
                    and not self.saw_text_delta
                    and block.text
                    and (self.answer_started or block.text.strip())
                ):
                    self.answer_started = True
                    events.append({"type": "answer_delta", "text": block.text})
        elif isinstance(message, UserMessage) and isinstance(message.content, list):
            for block in message.content:
                if isinstance(block, ToolResultBlock):
                    events.extend(self._tool_result(block))
        elif isinstance(message, ResultMessage):
            events.extend(self._close_reasoning())
            self.terminal = True
            events.append(
                {
                    "type": "usage",
                    "usage": message.usage or {},
                    "model_usage": message.model_usage or {},
                    "total_cost_usd": message.total_cost_usd,
                    "provider_requests": message.num_turns,
                }
            )
            events.extend(self.policy.format_terminal_result(message))
        return events
