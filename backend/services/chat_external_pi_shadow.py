"""Authenticated, non-executing compatibility probe for the external Pi worker."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class ExternalPiShadowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    protocol_version: int = Field(default=1, ge=1, le=1)
    request_id: str = Field(min_length=1, max_length=200)
    chat_session_id: uuid.UUID
    agent_session_id: uuid.UUID
    current_leaf_id: str | None = Field(default=None, max_length=255)
    prompt: str = Field(max_length=2 * 1024 * 1024)
    tool_names: tuple[str, ...] = Field(max_length=128)
    transcript_entries: tuple[dict[str, object], ...] = Field(
        min_length=1, max_length=2_000
    )

    @model_validator(mode="after")
    def validate_projection_inputs(self):
        if len(self.prompt.encode()) > 2 * 1024 * 1024:
            raise ValueError("External Pi shadow prompt is too large")
        if len(set(self.tool_names)) != len(self.tool_names) or any(
            not name or len(name) > 128 or any(char in name for char in "\r\n\0")
            for name in self.tool_names
        ):
            raise ValueError("External Pi shadow tool names are invalid")
        header = self.transcript_entries[0]
        if header.get("type") != "session" or header.get("id") != str(
            self.agent_session_id
        ):
            raise ValueError("External Pi shadow transcript header is invalid")
        if len(json.dumps(self.transcript_entries, separators=(",", ":")).encode()) > (
            25 * 1024 * 1024
        ):
            raise ValueError("External Pi shadow transcript is too large")
        return self

    @property
    def prompt_sha256(self) -> str:
        return hashlib.sha256(self.prompt.encode()).hexdigest()

    @property
    def tool_names_sha256(self) -> str:
        canonical = ",".join(sorted(self.tool_names))
        return hashlib.sha256(canonical.encode()).hexdigest()

    def wire_payload(self) -> dict[str, object]:
        return {
            "type": "shadow_compare",
            "protocol_version": self.protocol_version,
            "request_id": self.request_id,
            "chat_session_id": str(self.chat_session_id),
            "agent_session_id": str(self.agent_session_id),
            "current_leaf_id": self.current_leaf_id,
            "expected_prompt_sha256": self.prompt_sha256,
            "expected_tool_names_sha256": self.tool_names_sha256,
            "transcript_entries": list(self.transcript_entries),
        }


class ExternalPiShadowProjection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: str = Field(pattern=r"^shadow_projection$")
    protocol_version: int = Field(ge=1, le=1)
    request_id: str = Field(min_length=1, max_length=200)
    chat_session_id: uuid.UUID
    agent_session_id: uuid.UUID
    current_leaf_id: str | None = Field(default=None, max_length=255)
    entry_count: int = Field(ge=1, le=2_000)
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    tool_names_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    def compatible_with(self, request: ExternalPiShadowRequest) -> bool:
        return (
            self.protocol_version == request.protocol_version
            and self.request_id == request.request_id
            and self.chat_session_id == request.chat_session_id
            and self.agent_session_id == request.agent_session_id
            and self.current_leaf_id == request.current_leaf_id
            and self.entry_count == len(request.transcript_entries)
            and self.prompt_sha256 == request.prompt_sha256
            and self.tool_names_sha256 == request.tool_names_sha256
        )


@dataclass(slots=True)
class ExternalPiShadowClient:
    base_url: str
    token: str = field(repr=False)
    http: httpx.AsyncClient
    timeout_seconds: float = 5.0

    async def compare(
        self, request: ExternalPiShadowRequest
    ) -> ExternalPiShadowProjection:
        try:
            response = await self.http.post(
                f"{self.base_url.rstrip('/')}/v1/shadow",
                headers={"Authorization": f"Bearer {self.token}"},
                json=request.wire_payload(),
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            projection = ExternalPiShadowProjection.model_validate(response.json())
        except (httpx.HTTPError, ValueError, ValidationError) as error:
            raise RuntimeError(
                "External Pi shadow returned an invalid response"
            ) from error
        if not projection.compatible_with(request):
            raise RuntimeError("External Pi shadow compatibility mismatch")
        return projection
