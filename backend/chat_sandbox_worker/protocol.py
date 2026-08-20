"""Versioned, bounded stdout protocol for one sandbox worker."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

FRAME_PREFIX = "@@PWC_CHAT_V1@@"
ARTIFACT_EVENT_PREFIX = "@@PWC_ARTIFACT@@"
# Inline-paper turns can contain three independently bounded paper contexts.
# Keep the transport ceiling above the server-built prompt ceiling while still
# rejecting unexpectedly large worker frames before parsing them.
MAX_RUN_PROMPT_BYTES = 2 * 1024 * 1024
MAX_FRAME_BYTES = MAX_RUN_PROMPT_BYTES + 256 * 1024
MAX_WIRE_FRAME_BYTES = MAX_FRAME_BYTES + len(FRAME_PREFIX.encode()) + 1


class ProtocolError(RuntimeError):
    pass


class WorkerEventValidator:
    """Validate the event sequence emitted by one worker process."""

    allowed = {
        "worker_ready",
        "workspace_ready",
        "_sdk_session",
        "_mirror_error",
        "_execution_telemetry",
        "_latency",
        "_mcp_readiness",
        "usage",
        "reasoning_start",
        "reasoning_delta",
        "reasoning_end",
        "tool_call",
        "tool_result",
        "app_start",
        "app_result",
        "artifact_start",
        "artifact_ready",
        "artifact_error",
        "answer_delta",
        "done",
        "error",
        "worker_done",
    }

    def __init__(self):
        self.tools: set[str] = set()
        self.results: set[str] = set()
        self.apps: set[str] = set()
        self.artifacts: dict[str, tuple[str, str]] = {}
        self.artifact_terminal: set[str] = set()
        self.terminal = False
        self.worker_done = False

    def accept(
        self, event: dict[str, Any], *, allow_terminal_less_stop: bool = False
    ) -> None:
        kind = event.get("type")
        if kind not in self.allowed:
            raise ProtocolError("Unknown worker event type")
        if self.worker_done:
            raise ProtocolError("Worker event followed worker completion")
        if self.terminal and kind in {"done", "error"}:
            raise ProtocolError("Duplicate terminal worker event")
        if self.terminal and kind != "worker_done":
            raise ProtocolError("Worker event followed a terminal event")
        if kind == "tool_call":
            tool_id = str(event.get("id") or "")
            if not tool_id or tool_id in self.tools:
                raise ProtocolError("Duplicate or invalid tool call")
            self.tools.add(tool_id)
        elif kind == "tool_result":
            tool_id = str(event.get("id") or "")
            if tool_id not in self.tools or tool_id in self.results:
                raise ProtocolError("Uncorrelated or duplicate tool result")
            self.results.add(tool_id)
        elif kind == "app_start":
            tool_id = str(event.get("id") or "")
            if not tool_id or tool_id in self.apps:
                raise ProtocolError("Duplicate or invalid App start")
            self.apps.add(tool_id)
        elif kind == "app_result":
            tool_id = str(event.get("id") or "")
            if tool_id not in self.apps or tool_id in self.results:
                raise ProtocolError("Uncorrelated or duplicate App result")
            self.results.add(tool_id)
        elif kind == "artifact_start":
            publication_id = str(event.get("publication_id") or "")
            identifier = str(event.get("identifier") or "")
            artifact_kind = str(event.get("kind") or "")
            if (
                not publication_id
                or publication_id in self.artifacts
                or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", publication_id) is None
                or re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", identifier) is None
                or len(identifier) > 80
                or not isinstance(event.get("title"), str)
                or not 1 <= len(event["title"]) <= 300
                or artifact_kind != "posterly"
            ):
                raise ProtocolError("Duplicate or invalid artifact start")
            self.artifacts[publication_id] = (identifier, artifact_kind)
        elif kind in {"artifact_ready", "artifact_error"}:
            publication_id = str(event.get("publication_id") or "")
            expected = self.artifacts.get(publication_id)
            if expected is None or publication_id in self.artifact_terminal:
                raise ProtocolError("Uncorrelated or duplicate artifact terminal")
            if kind == "artifact_ready" and (
                str(event.get("identifier") or "") != expected[0]
                or str(event.get("kind") or "") != expected[1]
                or event.get("gate_status") not in {"passed", "warnings", "failed"}
                or not isinstance(event.get("version"), int)
                or int(event["version"]) < 1
                or event.get("preview_mime") != "image/png"
                or event.get("source_language") != "html"
                or not isinstance(event.get("total_bytes"), int)
                or not 0 <= int(event["total_bytes"]) <= 32 * 1024 * 1024
            ):
                raise ProtocolError("Inconsistent artifact terminal")
            if kind == "artifact_ready":
                try:
                    uuid.UUID(str(event.get("artifact_id")))
                    uuid.UUID(str(event.get("version_id")))
                except ValueError:
                    raise ProtocolError("Invalid artifact identifiers") from None
            self.artifact_terminal.add(publication_id)
        elif kind in {"done", "error", "_mirror_error"}:
            if set(self.artifacts) != self.artifact_terminal:
                raise ProtocolError("Terminal event with an unfinished artifact")
            self.terminal = True
        elif kind == "worker_done":
            status = event.get("status")
            if status not in {"complete", "stopped"}:
                raise ProtocolError("Invalid worker completion status")
            if status == "complete" and not self.terminal:
                raise ProtocolError(
                    "Worker completed without a semantic terminal event"
                )
            if (
                status == "stopped"
                and not self.terminal
                and not allow_terminal_less_stop
            ):
                raise ProtocolError("Worker stopped without a correlated cancellation")
            self.worker_done = True


def encode_frame(payload: dict[str, Any]) -> bytes:
    value = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    if len(value) > MAX_FRAME_BYTES:
        raise ProtocolError("Worker frame is too large")
    return FRAME_PREFIX.encode() + value + b"\n"


def decode_frame(line: bytes) -> dict[str, Any]:
    if not line.startswith(FRAME_PREFIX.encode()):
        raise ProtocolError("Invalid worker frame prefix")
    payload = line[len(FRAME_PREFIX) :]
    if len(payload) > MAX_FRAME_BYTES:
        raise ProtocolError("Worker frame is too large")
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as error:
        raise ProtocolError("Invalid worker frame JSON") from error
    if not isinstance(value, dict) or value.get("v") != 1:
        raise ProtocolError("Unsupported worker protocol version")
    return value


def artifact_events_from_output(output: str) -> list[dict[str, Any]]:
    """Extract the dedicated helper's bounded publication receipt."""
    line = next(
        (
            line
            for line in output.splitlines()
            if line.startswith(ARTIFACT_EVENT_PREFIX)
        ),
        None,
    )
    if line is None or len(line.encode()) > 16 * 1024:
        return []
    try:
        ready = json.loads(line[len(ARTIFACT_EVENT_PREFIX) :])
    except json.JSONDecodeError:
        return []
    required = {
        "publication_id",
        "artifact_id",
        "version_id",
        "identifier",
        "version",
        "kind",
        "title",
        "preview_mime",
        "source_language",
        "gate_status",
        "total_bytes",
    }
    if not isinstance(ready, dict) or set(ready) != required:
        return []
    start = {
        "type": "artifact_start",
        **{
            key: ready[key] for key in ("publication_id", "identifier", "kind", "title")
        },
    }
    return [start, {"type": "artifact_ready", **ready}]
