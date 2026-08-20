"""Non-secret worker limits supplied by the immutable image/release."""

from __future__ import annotations

import os
from dataclasses import dataclass

from backend.chat_execution_policy import validate_execution_limits


def _integer(name: str, default: int) -> int:
    return int(os.environ.get(name, str(default)))


def _number(name: str, default: float) -> float:
    return float(os.environ.get(name, str(default)))


@dataclass(frozen=True)
class WorkerSettings:
    chat_show_reasoning: bool = False
    chat_max_turns: int = 8
    chat_max_tool_calls: int = 12
    chat_max_direct_search_calls: int = 4
    chat_max_web_search_calls: int = 3
    chat_tool_result_max_bytes: int = 24 * 1024
    chat_turn_tool_output_max_bytes: int = 96 * 1024
    chat_bash_timeout_seconds: float = 30
    chat_agent_timeout_seconds: float = 180
    chat_posterly_timeout_seconds: float = 600
    chat_posterly_max_tool_rounds: int = 20
    chat_posterly_max_tool_calls: int = 40
    chat_posterly_tool_result_max_bytes: int = 192 * 1024
    chat_posterly_turn_tool_output_max_bytes: int = 1024 * 1024

    def __post_init__(self) -> None:
        validate_execution_limits(
            max_turns=self.chat_max_turns,
            max_tool_calls=self.chat_max_tool_calls,
            max_direct_searches=self.chat_max_direct_search_calls,
            max_web_searches=self.chat_max_web_search_calls,
        )

    @classmethod
    def from_environment(cls) -> "WorkerSettings":
        return cls(
            chat_show_reasoning=os.environ.get(
                "PWC_CHAT_SHOW_REASONING", "false"
            ).lower()
            in {"1", "true", "yes"},
            chat_max_turns=_integer("PWC_CHAT_MAX_TURNS", 8),
            chat_max_tool_calls=_integer("PWC_CHAT_MAX_TOOL_CALLS", 12),
            chat_max_direct_search_calls=_integer(
                "PWC_CHAT_MAX_DIRECT_SEARCH_CALLS", 4
            ),
            chat_max_web_search_calls=_integer("PWC_CHAT_MAX_WEB_SEARCH_CALLS", 3),
            chat_tool_result_max_bytes=_integer(
                "PWC_CHAT_TOOL_RESULT_MAX_BYTES", 24 * 1024
            ),
            chat_turn_tool_output_max_bytes=_integer(
                "PWC_CHAT_TURN_TOOL_OUTPUT_MAX_BYTES", 96 * 1024
            ),
            chat_bash_timeout_seconds=_number("PWC_CHAT_BASH_TIMEOUT_SECONDS", 30),
            chat_agent_timeout_seconds=_number("PWC_CHAT_AGENT_TIMEOUT_SECONDS", 180),
            chat_posterly_timeout_seconds=_number(
                "PWC_CHAT_POSTERLY_TIMEOUT_SECONDS", 600
            ),
            chat_posterly_max_tool_rounds=_integer(
                "PWC_CHAT_POSTERLY_MAX_TOOL_ROUNDS", 20
            ),
            chat_posterly_max_tool_calls=_integer(
                "PWC_CHAT_POSTERLY_MAX_TOOL_CALLS", 40
            ),
            chat_posterly_tool_result_max_bytes=_integer(
                "PWC_CHAT_POSTERLY_TOOL_RESULT_MAX_BYTES", 192 * 1024
            ),
            chat_posterly_turn_tool_output_max_bytes=_integer(
                "PWC_CHAT_POSTERLY_TURN_TOOL_OUTPUT_MAX_BYTES", 1024 * 1024
            ),
        )
