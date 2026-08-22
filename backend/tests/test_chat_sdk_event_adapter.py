"""Contract coverage shared by local and sandbox SDK event projections."""

from __future__ import annotations

import json

import pytest
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

from backend.chat_sandbox_worker.sdk_adapter import SDKEventAdapter, SDKEventPolicy
from backend.services.chat_agent_service import SDKEventAdapter as LocalSDKEventAdapter


def _messages():
    return [
        StreamEvent(
            uuid="1",
            session_id="session",
            event={
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "thinking"},
            },
        ),
        StreamEvent(
            uuid="2",
            session_id="session",
            event={
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "thinking_delta", "thinking": "Plan"},
            },
        ),
        StreamEvent(
            uuid="3",
            session_id="session",
            event={"type": "content_block_stop", "index": 0},
        ),
        AssistantMessage(
            model="test",
            content=[ToolUseBlock(id="call", name="mcp__web__search_web", input={})],
        ),
        UserMessage(content=[ToolResultBlock(tool_use_id="call", content="first")]),
        AssistantMessage(
            model="test",
            content=[ToolUseBlock(id="call", name="Bash", input={"command": "pwd"})],
        ),
        UserMessage(content=[ToolResultBlock(tool_use_id="call", content="second")]),
        AssistantMessage(
            model="test",
            content=[
                ThinkingBlock(thinking="late", signature="sig"),
                TextBlock(text="Answer"),
            ],
        ),
        ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=2,
            session_id="session",
        ),
    ]


@pytest.mark.parametrize("adapter_class", [SDKEventAdapter, LocalSDKEventAdapter])
def test_sdk_event_adapter_contract_covers_both_execution_paths(adapter_class):
    batches: list[list[str]] = []
    adapter = adapter_class(
        show_reasoning=True,
        policy=SDKEventPolicy(
            tool_name=lambda name: name.removeprefix("mcp__web__"),
            on_tool_batch=batches.append,
        ),
    )

    events = [event for message in _messages() for event in adapter.feed(message)]

    assert [event["type"] for event in events] == [
        "reasoning_start",
        "reasoning_delta",
        "reasoning_end",
        "tool_call",
        "tool_result",
        "tool_call",
        "tool_result",
        "answer_delta",
        "usage",
        "done",
    ]
    assert [event["id"] for event in events if event["type"] == "tool_call"] == [
        "call",
        "call#2",
    ]
    assert [event["id"] for event in events if event["type"] == "tool_result"] == [
        "call",
        "call#2",
    ]
    assert events[3]["name"] == "search_web"
    assert batches == [["call"], ["call"]]


def test_sdk_event_adapter_policy_can_suppress_a_tool_and_its_result():
    adapter = SDKEventAdapter(
        show_reasoning=False,
        policy=SDKEventPolicy(allow_tool_call=lambda _id, name, _args: name != "Read"),
    )

    events = [
        event
        for message in [
            AssistantMessage(
                model="test",
                content=[
                    ToolUseBlock(id="keep", name="Bash", input={}),
                    ToolUseBlock(id="hide", name="Read", input={}),
                ],
            ),
            UserMessage(
                content=[
                    ToolResultBlock(tool_use_id="keep", content=json.dumps({})),
                    ToolResultBlock(tool_use_id="hide", content=json.dumps({})),
                ]
            ),
        ]
        for event in adapter.feed(message)
    ]

    assert [(event["type"], event["id"]) for event in events] == [
        ("tool_call", "keep"),
        ("tool_result", "keep"),
    ]
