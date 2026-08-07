"""Strict API and durable projection models for authenticated research chat."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    field_validator,
    model_validator,
)

StrictText = Annotated[str, StringConstraints(max_length=8000)]
AuthorName = Annotated[str, StringConstraints(max_length=300)]
FinishReason = Literal["success", "max_turns", "tool_limit"]


class PaperMentionRequest(BaseModel):
    """One browser-selected occurrence in UTF-16 textarea coordinates."""

    model_config = ConfigDict(extra="forbid")

    route_id: Annotated[
        str, StringConstraints(min_length=1, max_length=200, strip_whitespace=True)
    ]
    title: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    start: int = Field(ge=0, le=16_000)
    end: int = Field(gt=0, le=16_000)


class PaperMentionSnapshot(BaseModel):
    """Safe durable/UI projection of one server-resolved paper mention."""

    model_config = ConfigDict(extra="forbid")

    occurrence_id: str = Field(min_length=1, max_length=32)
    route_id: str = Field(min_length=1, max_length=200)
    paper_id: str = Field(min_length=1, max_length=64)
    arxiv_id: str | None = Field(default=None, max_length=50)
    title: str = Field(min_length=1, max_length=500)
    source: Literal["arxiv", "external"]
    source_url: str | None = Field(default=None, max_length=2000)
    start: int = Field(ge=0, le=16_000)
    end: int = Field(gt=0, le=16_000)
    paper_version: str | None = Field(default=None, max_length=32)
    metadata_updated_at: str | None = Field(default=None, max_length=64)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    content_truncated: bool
    content_available: bool
    included_bytes: int = Field(ge=0, le=81_920)
    context_reference: dict[str, str] | None = None


def _utf16_slice(value: str, start: int, end: int) -> str:
    raw = value.encode("utf-16-le")
    if end * 2 > len(raw):
        raise ValueError("Paper mention range is outside the message")
    try:
        return raw[start * 2 : end * 2].decode("utf-16-le")
    except UnicodeDecodeError as exc:
        raise ValueError("Paper mention range must align to UTF-16 characters") from exc


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: StrictText
    session_id: uuid.UUID | None = None
    client_message_id: Annotated[
        str, StringConstraints(min_length=1, max_length=200, strip_whitespace=True)
    ]
    initial_model: str | None = None
    replace_message_id: uuid.UUID | None = None
    prior_revision: int | None = Field(default=None, ge=1)
    web_search_enabled: bool = False
    paper_mentions: list[PaperMentionRequest] = Field(
        default_factory=list, max_length=10
    )

    @model_validator(mode="after")
    def validate_message(self) -> "ChatRequest":
        if not self.message.strip():
            raise ValueError("Message must not be empty")
        if (self.replace_message_id is None) != (self.prior_revision is None):
            raise ValueError(
                "Replacement message and revision must be supplied together"
            )
        previous_end = -1
        distinct: set[str] = set()
        for mention in self.paper_mentions:
            if mention.start < previous_end or mention.end <= mention.start:
                raise ValueError(
                    "Paper mention ranges must be ordered and non-overlapping"
                )
            marker = _utf16_slice(self.message, mention.start, mention.end)
            if marker != f"@{mention.title}":
                raise ValueError(
                    "Paper mention range does not match its visible marker"
                )
            previous_end = mention.end
            distinct.add(mention.route_id)
        if len(distinct) > 3:
            raise ValueError("A message may mention at most three distinct papers")
        return self


class ChatBrowserLatencyRequest(BaseModel):
    """Content-free browser timing update for one admitted request."""

    model_config = ConfigDict(extra="forbid")

    submission_to_stream_start_ms: float | None = Field(
        default=None, ge=0, le=3_600_000, allow_inf_nan=False
    )
    submission_to_first_visible_delta_ms: float | None = Field(
        default=None, ge=0, le=3_600_000, allow_inf_nan=False
    )
    terminal_classification: (
        Literal["complete", "stopped", "error", "network_error", "aborted"] | None
    ) = None

    @model_validator(mode="after")
    def require_measurement(self) -> "ChatBrowserLatencyRequest":
        if (
            self.submission_to_stream_start_ms is None
            and self.submission_to_first_visible_delta_ms is None
            and self.terminal_classification is None
        ):
            raise ValueError("At least one browser timing field is required")
        return self


class ChatPaperMetadata(BaseModel):
    arxiv_id: str | None
    source: Literal["arxiv", "external"]
    source_url: str | None
    thumbnail_url: str | None = Field(default=None, max_length=1000)
    authors: list[dict[str, str]]
    published: str | None
    conference: str | None
    citation_count: int | None
    tasks: list[dict[str, str]]
    methods: list[dict[str, str]]
    repositories: list[dict[str, str | int | None]]
    project_pages: list[dict[str, str]]


class ChatPaperHit(BaseModel):
    route_id: str = Field(max_length=200)
    title: str = Field(max_length=500)
    content: str = Field(max_length=4000)
    content_truncated: bool
    metadata: ChatPaperMetadata


class CitationSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["paper", "web"] = "paper"
    position: int = Field(ge=0, le=100)
    route_id: str | None = Field(default=None, max_length=200)
    url: str | None = Field(default=None, max_length=2000)
    title: str = Field(max_length=500)
    excerpt: str | None = Field(default=None, max_length=4000)
    source_url: str | None = Field(default=None, max_length=2000)
    thumbnail_url: str | None = Field(default=None, max_length=1000)
    arxiv_id: str | None = Field(default=None, max_length=50)
    authors: list[AuthorName] = Field(default_factory=list, max_length=50)
    published: str | None = Field(default=None, max_length=32)
    conference: str | None = Field(default=None, max_length=200)
    citation_count: int | None = None

    @model_validator(mode="after")
    def validate_kind(self) -> "CitationSnapshot":
        if self.kind == "paper" and not self.route_id:
            raise ValueError("Paper citations require route_id")
        if self.kind == "web" and (
            not self.url or not self.url.startswith("https://") or self.route_id
        ):
            raise ValueError("Web citations require an HTTPS url and no route_id")
        return self


class ReasoningDisplayBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["reasoning"]
    text: str = Field(max_length=20_000)
    citations: list[CitationSnapshot] = Field(default_factory=list, max_length=20)


class ToolTextContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["text"] = "text"
    text: str = Field(max_length=24_900)
    truncated: bool = False


class ToolResultMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    exit_code: int | None = None
    output_truncated: bool = False


class ToolDisplayBlock(BaseModel):
    """Browser projection for both historical search and generic v2 tools."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["tool"]
    schema_version: Literal[1, 2] = 1
    id: str = Field(max_length=200)
    name: str = Field(min_length=1, max_length=64)
    args: dict[str, object]
    status: Literal["running", "done", "success", "error", "denied"]
    took_ms: int = Field(default=0, ge=0, le=600_000)
    content: list[ToolTextContent] = Field(default_factory=list, max_length=1)
    metadata: ToolResultMetadata = Field(default_factory=ToolResultMetadata)
    # Legacy v1 search projection. Retained until local_mcp history is retired.
    hits: int | None = Field(default=None, ge=0, le=10_000)
    results: list[ChatPaperHit] | None = Field(default=None, max_length=10)

    @field_validator("args")
    @classmethod
    def validate_args(cls, value: dict[str, object]) -> dict[str, object]:
        if len(json.dumps(value, ensure_ascii=False).encode()) > 2_000:
            raise ValueError("Tool arguments are too large")
        return value

    @model_validator(mode="after")
    def validate_schema(self) -> "ToolDisplayBlock":
        if self.schema_version == 1:
            if self.name != "search_papers":
                raise ValueError("Legacy tool blocks must be search_papers")
            if set(self.args) - {"query", "top_k", "mode"}:
                raise ValueError("Unsupported search tool arguments")
            if self.hits is None or self.results is None:
                raise ValueError("Legacy search blocks require hits and results")
        elif self.name not in {"Bash", "Read", "Grep", "WebFetch", "search_web"}:
            raise ValueError("Unsupported generic tool name")
        return self


class AnswerDisplayBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["answer"]
    text: str = Field(max_length=80_000)
    done: Literal[True] = True
    citations: list[CitationSnapshot] = Field(default_factory=list, max_length=20)


DisplayBlock = Annotated[
    Union[ReasoningDisplayBlock, ToolDisplayBlock, AnswerDisplayBlock],
    Field(discriminator="kind"),
]
DISPLAY_BLOCKS_ADAPTER = TypeAdapter(list[DisplayBlock])


class ChatMessageResponse(BaseModel):
    id: uuid.UUID
    turn_id: uuid.UUID
    sequence: int
    role: Literal["user", "assistant"]
    content: str
    paper_mentions: list[PaperMentionSnapshot] = Field(default_factory=list)
    revision: int
    status: str
    citations: list[CitationSnapshot] = Field(default_factory=list)
    followups: list[str] = Field(default_factory=list)
    display_blocks: list[DisplayBlock] = Field(default_factory=list)
    model: str | None = None
    finish_reason: FinishReason | None = None
    error_code: str | None = None
    created_at: datetime


class ChatShareSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    share_id: uuid.UUID
    public_path: str = Field(max_length=64)
    created_at: datetime
    updated_at: datetime


class PublicChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    role: Literal["user", "assistant"]
    content: str = Field(max_length=256_000)
    paper_mentions: list[PaperMentionSnapshot] = Field(default_factory=list)
    display_blocks: list[DisplayBlock] = Field(default_factory=list)
    citations: list[CitationSnapshot] = Field(default_factory=list, max_length=20)
    model: str | None = Field(default=None, max_length=255)
    display_state: Literal["complete", "interrupted", "failed"] = "complete"
    finish_reason: FinishReason | Literal["stopped"] | None = None
    error: str | None = Field(default=None, max_length=500)


class ChatShareDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    share_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    model: str | None = Field(default=None, max_length=255)
    model_label: str | None = Field(default=None, max_length=255)
    model_provider: Literal["huggingface", "openrouter"] | None = None
    messages: list[PublicChatMessage]


class ChatSessionSummary(BaseModel):
    id: uuid.UUID
    title: str
    selected_model: str
    created_at: datetime
    updated_at: datetime
    message_count: int
    is_busy: bool = False
    web_search_enabled: bool = False


class ChatSessionDetail(ChatSessionSummary):
    messages: list[ChatMessageResponse]
    transcript_status: str


class ChatSessionList(BaseModel):
    items: list[ChatSessionSummary]
    next_cursor: str | None = None


class ArchiveOldChatsResponse(BaseModel):
    archived_count: int = Field(ge=0)


class CreateSessionRequest(BaseModel):
    selected_model: str | None = None


class UpdateSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, max_length=80)
    selected_model: str | None = None

    @model_validator(mode="after")
    def one_change(self) -> "UpdateSessionRequest":
        if self.title is None and self.selected_model is None:
            raise ValueError("Supply a title or selected_model")
        if self.title is not None and not " ".join(self.title.split()):
            raise ValueError("Title must not be empty")
        return self


class _StrictEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StreamStartEvent(_StrictEvent):
    type: Literal["stream_start"]
    request_id: str
    session_id: uuid.UUID
    provider_execution: bool = True


class ReasoningStartEvent(_StrictEvent):
    type: Literal["reasoning_start"]


class ReasoningDeltaEvent(_StrictEvent):
    type: Literal["reasoning_delta"]
    text: str


class ReasoningEndEvent(_StrictEvent):
    type: Literal["reasoning_end"]


class ToolCallEvent(_StrictEvent):
    type: Literal["tool_call"]
    id: str
    name: str
    args: dict[str, object]


class ToolResultEvent(_StrictEvent):
    type: Literal["tool_result"]
    id: str
    status: Literal["success", "error", "denied"] | None = None
    took_ms: int
    content: list[ToolTextContent] | None = None
    metadata: ToolResultMetadata | None = None
    # Legacy local_mcp shape.
    hits: int | None = None
    results: list[ChatPaperHit] | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> "ToolResultEvent":
        legacy = self.hits is not None or self.results is not None
        generic = self.status is not None or self.content is not None
        if legacy == generic:
            raise ValueError("Tool result must be exactly one of legacy or generic")
        if legacy and (self.hits is None or self.results is None):
            raise ValueError("Legacy tool result requires hits and results")
        if generic and (self.status is None or self.content is None):
            raise ValueError("Generic tool result requires status and content")
        return self


class SandboxStartEvent(_StrictEvent):
    type: Literal["sandbox_start"]
    session_id: uuid.UUID


class SandboxReadyEvent(_StrictEvent):
    type: Literal["sandbox_ready"]
    session_id: uuid.UUID
    cold_start_ms: int = Field(ge=0, le=600_000)


class WorkspaceReadyEvent(_StrictEvent):
    """Backend-neutral marker emitted immediately before model query dispatch."""

    type: Literal["workspace_ready"]


class AnswerDeltaEvent(_StrictEvent):
    type: Literal["answer_delta"]
    text: str


class DoneEvent(_StrictEvent):
    type: Literal["done"]
    followups: list[str] = Field(default_factory=list)
    finish_reason: FinishReason | Literal["stopped"] = "success"
    citations: list[CitationSnapshot] = Field(default_factory=list, max_length=20)


class ErrorEvent(_StrictEvent):
    type: Literal["error"]
    message: str
    code: str | None = None


class SessionTitleStartEvent(_StrictEvent):
    type: Literal["session_title_start"]


class SessionTitleDeltaEvent(_StrictEvent):
    type: Literal["session_title_delta"]
    text: str


class SessionTitleDoneEvent(_StrictEvent):
    type: Literal["session_title_done"]
    title: str


ChatEvent = Annotated[
    Union[
        StreamStartEvent,
        ReasoningStartEvent,
        ReasoningDeltaEvent,
        ReasoningEndEvent,
        ToolCallEvent,
        ToolResultEvent,
        SandboxStartEvent,
        SandboxReadyEvent,
        WorkspaceReadyEvent,
        AnswerDeltaEvent,
        DoneEvent,
        ErrorEvent,
        SessionTitleStartEvent,
        SessionTitleDeltaEvent,
        SessionTitleDoneEvent,
    ],
    Field(discriminator="type"),
]
_CHAT_EVENT_ADAPTER = TypeAdapter(ChatEvent)


def sse_event(event_type: str, **payload: object) -> bytes:
    event = _CHAT_EVENT_ADAPTER.validate_python({"type": event_type, **payload})
    return (
        "data: "
        + json.dumps(
            event.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":")
        )
        + "\n\n"
    ).encode()
