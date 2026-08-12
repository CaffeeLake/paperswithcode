"""Canonical content-free control manifest for Claude/Pi isolation runs."""

from __future__ import annotations

import hashlib
import json


def manifest(*, model_route: str, provider: str, prompt_sha256: str) -> dict:
    return {
        "schema": "pwc-chat-harness-isolation-v1",
        "model_route": model_route,
        "provider": provider,
        "reasoning_effort": "high",
        "prompt_sha256": prompt_sha256,
        "tools": ["Bash", "Read", "search_web"],
        "web_fetch_enabled": False,
        "maximum_tool_calls": 12,
        "maximum_tool_rounds": 6,
        "maximum_direct_searches": 4,
        "maximum_web_searches": 3,
        "self_extension_enabled": False,
        "third_party_extensions_enabled": False,
    }


def sha256(*, model_route: str, provider: str, prompt_sha256: str) -> str:
    payload = json.dumps(
        manifest(
            model_route=model_route,
            provider=provider,
            prompt_sha256=prompt_sha256,
        ),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()
