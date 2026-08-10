"""Transactional ownership, idempotency, leases, and projections for chat."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.chat_execution_policy import bounded_url_seed
from backend.models.chat import DISPLAY_BLOCKS_ADAPTER, CitationSnapshot
from backend.models.database import (
    ChatMessageRecord,
    ChatSandboxLease,
    ChatSDKSessionSummary,
    ChatSDKTranscriptEntry,
    ChatSession,
    ChatShare,
)
from backend.services.chat_edit_service import (
    INACTIVE_STATUSES,
    PREPARING_STATUS,
    ChatEditService,
)
from backend.services.chat_title_service import normalize_title


class ChatServiceError(Exception):
    def __init__(
        self,
        code: str,
        status_code: int,
        message: str,
        *,
        commit_changes: bool = False,
        active_count: int | None = None,
        details: dict[str, object] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.commit_changes = commit_changes
        self.active_count = active_count
        self.details = details or {}


@dataclass(frozen=True)
class ChatOwner:
    hf_user_id: str
    hf_username: str
    hf_inference_token: str | None = None
    hf_inference_bill_to: str | None = None
    openrouter_mode: str | None = None
    openrouter_token: str | None = None
    openrouter_credential_revision: uuid.UUID | None = None


@dataclass(frozen=True)
class ReplayAssistant:
    content: str
    followups: list[str]


@dataclass(frozen=True)
class TurnAdmission:
    session_id: uuid.UUID
    turn_id: uuid.UUID
    user_message_id: uuid.UUID
    selected_model: str
    model_route: str
    sdk_session_id: uuid.UUID | None
    sdk_project_key: str | None
    is_first_turn: bool
    replay_assistant: ReplayAssistant | None = None
    resume_boundary_id: uuid.UUID | None = None
    is_replacement: bool = False
    replacement_target_id: uuid.UUID | None = None
    replacement_target_sequence: int | None = None
    replacement_target_revision: int | None = None
    replacement_active_suffix_ids: tuple[uuid.UUID, ...] = ()
    prompt_revision: int = 1
    title_should_generate: bool = False
    execution_backend: str = "local_mcp"
    app_release_id: str = ""
    image_version: str = ""
    worker_contract_version: str = ""
    pwc_cli_version: str = ""
    system_prompt_sha256: str = ""
    web_search_enabled: bool = False
    fetchable_urls: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _ReplayOutcome:
    kind: Literal["continue", "admitted", "expired"]
    admission: TurnAdmission | None = None
    expired_message: ChatMessageRecord | None = None


@dataclass(frozen=True, slots=True)
class _CapacitySnapshot:
    other_active: int
    active_total: int


@dataclass(frozen=True, slots=True)
class _ReplacementPlan:
    prior: ChatMessageRecord | None
    active_suffix_ids: tuple[uuid.UUID, ...]
    turn_id: uuid.UUID
    revision: int


@dataclass(frozen=True, slots=True)
class _QuotaCalculation:
    new_projection_bytes: int
    reclaimed_projection_bytes: int
    resulting_session_bytes: int
    resulting_owner_bytes: int
    resulting_message_count: int


@dataclass(frozen=True, slots=True)
class _TranscriptResumeBoundary:
    id: uuid.UUID | None


@dataclass(frozen=True, slots=True)
class _TurnRuntimeDescriptor:
    execution_backend: str
    app_release_id: str
    image_version: str
    worker_contract_version: str
    pwc_cli_version: str
    system_prompt_sha256: str

    def persisted(self, value: str) -> str | None:
        return value if self.execution_backend == "modal_cli" else None


@dataclass(frozen=True, slots=True)
class _TurnCreationPlan:
    message_id: uuid.UUID
    replacement: _ReplacementPlan
    quota: _QuotaCalculation
    resume_boundary: _TranscriptResumeBoundary
    runtime: _TurnRuntimeDescriptor
    model: str
    model_route: str
    effective_prompt: str
    paper_mentions: list[dict]
    is_first_turn: bool
    title_should_generate: bool


@dataclass(frozen=True)
class ChatDeletionReceipt:
    session_id: uuid.UUID
    sandbox_id: str | None
    snapshot_id: str | None
    sdk_session_id: uuid.UUID | None
    sdk_project_key: str | None


def owner_from_user(
    user: dict,
    *,
    inference_token: str | None = None,
    inference_bill_to: str | None = None,
    openrouter_mode: str | None = None,
    openrouter_token: str | None = None,
    openrouter_credential_revision: uuid.UUID | None = None,
) -> ChatOwner:
    return ChatOwner(
        hf_user_id=user["hf_user_id"],
        hf_username=user["username"],
        hf_inference_token=inference_token,
        hf_inference_bill_to=inference_bill_to,
        openrouter_mode=openrouter_mode,
        openrouter_token=openrouter_token,
        openrouter_credential_revision=openrouter_credential_revision,
    )


def _now() -> datetime:
    return datetime.now(UTC)


def _normalized(value: str, limit: int) -> str:
    return " ".join(value.split())[:limit]


def _payload_bytes(*values: object) -> int:
    return sum(
        len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())
        for value in values
    )


def _message_projection_bytes(message: ChatMessageRecord) -> int:
    if message.role == "user":
        if message.effective_prompt is None:
            return len(message.content.encode())
        return (
            len(message.content.encode())
            + len(message.effective_prompt.encode())
            + _payload_bytes(message.paper_mentions or [])
        )
    return len(message.content.encode())


def _reclaimed_projection_bytes(messages: list[ChatMessageRecord]) -> int:
    return sum(
        _message_projection_bytes(message)
        + _payload_bytes(
            message.display_blocks or [],
            message.citations or [],
            message.followups or [],
        )
        for message in messages
    )


def _calculate_turn_quota(
    *,
    session_transcript_bytes: int,
    session_projection_bytes: int,
    owner_total_bytes: int,
    reclaimed_projection_bytes: int,
    new_projection_bytes: int,
    current_message_count: int,
    replacement_prefix_count: int | None,
) -> _QuotaCalculation:
    resulting_message_count = (
        current_message_count + 2
        if replacement_prefix_count is None
        else replacement_prefix_count + 2
    )
    return _QuotaCalculation(
        new_projection_bytes=new_projection_bytes,
        reclaimed_projection_bytes=reclaimed_projection_bytes,
        resulting_session_bytes=(
            session_transcript_bytes
            + session_projection_bytes
            - reclaimed_projection_bytes
            + new_projection_bytes
        ),
        resulting_owner_bytes=(
            owner_total_bytes - reclaimed_projection_bytes + new_projection_bytes
        ),
        resulting_message_count=resulting_message_count,
    )


def _build_replacement_plan(
    *,
    replacement_requested: bool,
    prior: ChatMessageRecord | None,
    active_suffix_ids: tuple[uuid.UUID, ...],
    sdk_session_id: uuid.UUID | None,
    sdk_project_key: str | None,
) -> _ReplacementPlan:
    if not replacement_requested:
        return _ReplacementPlan(
            prior=None,
            active_suffix_ids=(),
            turn_id=uuid.uuid4(),
            revision=1,
        )
    if prior is None:
        raise ChatServiceError(
            "invalid_replacement", 409, "This prompt can no longer be edited"
        )
    legacy_initial_retry = (
        prior.sequence == 1
        and prior.status in ("interrupted", "error")
        and active_suffix_ids == (prior.id,)
    )
    if prior.sequence == 1 and not legacy_initial_retry:
        raise ChatServiceError(
            "invalid_replacement",
            409,
            "Edit the first prompt by starting a new chat",
        )
    if prior.sequence > 1 and (
        sdk_session_id is None
        or not sdk_project_key
        or prior.sdk_resume_boundary_id is None
    ):
        raise ChatServiceError(
            "chat_transcript_unavailable",
            409,
            "This prompt cannot be edited because its transcript boundary is unavailable",
        )
    return _ReplacementPlan(
        prior=prior,
        active_suffix_ids=active_suffix_ids,
        turn_id=uuid.uuid4(),
        revision=prior.revision + 1,
    )


class ChatSessionService:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings
        self.edits = ChatEditService(db)

    def _owned(
        self, owner: ChatOwner, session_id: uuid.UUID, *, lock: bool = False
    ) -> ChatSession:
        query = select(ChatSession).where(
            ChatSession.id == session_id, ChatSession.hf_user_id == owner.hf_user_id
        )
        if lock:
            query = query.with_for_update()
        session = self.db.execute(query).scalar_one_or_none()
        if session is None:
            raise ChatServiceError("session_not_found", 404, "Chat session not found")
        return session

    def existing_effective_prompt(
        self,
        owner: ChatOwner,
        session_id: uuid.UUID | None,
        client_message_id: str,
    ) -> str | None:
        """Return an already-admitted turn input without preparing it again."""
        if session_id is None:
            return None
        return self.db.scalar(
            select(ChatMessageRecord.effective_prompt)
            .join(ChatSession, ChatSession.id == ChatMessageRecord.session_id)
            .where(
                ChatMessageRecord.session_id == session_id,
                ChatMessageRecord.client_message_id == client_message_id,
                ChatSession.hf_user_id == owner.hf_user_id,
            )
        )

    def fetchable_url_seed(
        self,
        session_id: uuid.UUID,
        *,
        current_message_id: uuid.UUID | None = None,
        replacement_target_sequence: int | None = None,
    ) -> list[str]:
        """Derive URL authorization only from the active application lineage."""

        active_status = ChatMessageRecord.status.notin_(INACTIVE_STATUSES)
        if current_message_id is not None:
            active_status = or_(
                active_status, ChatMessageRecord.id == current_message_id
            )
        query = select(ChatMessageRecord).where(
            ChatMessageRecord.session_id == session_id, active_status
        )
        if replacement_target_sequence is not None:
            boundary = ChatMessageRecord.sequence < replacement_target_sequence
            if current_message_id is not None:
                query = query.where(
                    or_(boundary, ChatMessageRecord.id == current_message_id)
                )
            else:
                query = query.where(boundary)
        rows = self.db.execute(query.order_by(ChatMessageRecord.sequence)).scalars()
        payloads: list[str] = []
        for row in rows:
            if row.status in INACTIVE_STATUSES and row.id != current_message_id:
                continue
            if (
                replacement_target_sequence is not None
                and row.sequence >= replacement_target_sequence
                and row.id != current_message_id
            ):
                continue
            if row.role == "user":
                payloads.append(row.effective_prompt or row.content)
                continue
            if row.role != "assistant":
                continue
            for block in row.display_blocks or []:
                if not isinstance(block, dict) or block.get("kind") != "tool":
                    continue
                if block.get("status") not in {"done", "success"}:
                    continue
                name = block.get("name")
                if name in {"Bash", "Read", "Grep"}:
                    for item in block.get("content") or []:
                        if isinstance(item, dict) and isinstance(item.get("text"), str):
                            payloads.append(item["text"])
                elif name == "search_papers":
                    # The validated legacy catalog projection is an explicitly
                    # approved source. WebFetch/search_web blocks are excluded.
                    payloads.append(
                        json.dumps(
                            block.get("results") or [],
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                    )
        return bounded_url_seed(payloads)

    def record_langfuse_trace_id(
        self, owner: ChatOwner, admission: TurnAdmission, trace_id: str
    ) -> None:
        if not trace_id:
            return
        session = self._owned(owner, admission.session_id, lock=True)
        message = self.db.get(ChatMessageRecord, admission.user_message_id)
        if (
            message
            and message.session_id == session.id
            and message.turn_id == admission.turn_id
        ):
            message.langfuse_trace_id = trace_id

    def _validate_model(self, model: str | None) -> tuple[str, str]:
        selected = model or self.settings.chat_model_choices[0]["id"]
        route = self.settings.chat_model_routes.get(selected)
        if route is None:
            raise ChatServiceError(
                "invalid_chat_model", 422, "Unsupported research model"
            )
        return selected, route

    def create_session(
        self, owner: ChatOwner, selected_model: str | None = None
    ) -> ChatSession:
        model, _ = self._validate_model(selected_model)
        self.db.execute(
            select(
                func.pg_advisory_xact_lock(func.hashtextextended(owner.hf_user_id, 0))
            )
        )
        count = (
            self.db.scalar(
                select(func.count())
                .select_from(ChatSession)
                .where(
                    ChatSession.hf_user_id == owner.hf_user_id,
                    ChatSession.archived_at.is_(None),
                )
            )
            or 0
        )
        if count >= self.settings.chat_session_limit:
            raise ChatServiceError(
                "chat_session_quota_exceeded",
                409,
                f"You can have at most {self.settings.chat_session_limit} chats. "
                "Archive old chats or delete a chat to create another.",
            )
        session_id = uuid.uuid4()
        allocation_bucket = (
            int.from_bytes(hashlib.sha256(session_id.bytes).digest()[:4], "big") % 100
        )
        provider = self.settings.chat_model_providers[model]
        if provider == "openrouter":
            # Trusted cost extraction and per-call reservation live at the
            # private gateway. Funded OpenRouter must never use local_mcp.
            execution_backend = "modal_cli"
        elif self.settings.chat_new_chat_modal_percentage == 0:
            execution_backend = self.settings.chat_default_backend
        else:
            execution_backend = (
                "modal_cli"
                if allocation_bucket < self.settings.chat_new_chat_modal_percentage
                else "local_mcp"
            )
        session = ChatSession(
            id=session_id,
            hf_user_id=owner.hf_user_id,
            hf_username=owner.hf_username,
            title="New chat",
            title_status="pending",
            selected_model=model,
            execution_backend=execution_backend,
            updated_at=_now(),
        )
        self.db.add(session)
        self.db.flush()
        return session

    def list_sessions(
        self, owner: ChatOwner, cursor: str | None, limit: int
    ) -> tuple[list[ChatSession], str | None]:
        query = select(ChatSession).where(
            ChatSession.hf_user_id == owner.hf_user_id,
            ChatSession.archived_at.is_(None),
        )
        if cursor:
            try:
                raw = base64.urlsafe_b64decode(
                    cursor + "=" * (-len(cursor) % 4)
                ).decode()
                timestamp, row_id = raw.rsplit("|", 1)
                before = datetime.fromisoformat(timestamp)
                cursor_id = uuid.UUID(row_id)
            except (ValueError, UnicodeDecodeError):
                raise ChatServiceError(
                    "invalid_cursor", 422, "Invalid session cursor"
                ) from None
            query = query.where(
                or_(
                    ChatSession.updated_at < before,
                    (ChatSession.updated_at == before) & (ChatSession.id < cursor_id),
                )
            )
        rows = list(
            self.db.execute(
                query.order_by(
                    ChatSession.updated_at.desc(), ChatSession.id.desc()
                ).limit(limit + 1)
            ).scalars()
        )
        has_more = len(rows) > limit
        rows = rows[:limit]
        next_cursor = None
        if has_more and rows:
            token = f"{rows[-1].updated_at.isoformat()}|{rows[-1].id}".encode()
            next_cursor = base64.urlsafe_b64encode(token).decode().rstrip("=")
        return rows, next_cursor

    def archive_old_sessions(self, owner: ChatOwner, *, days: int = 30) -> int:
        """Hide inactive old chats from history and the active-session quota."""
        self.db.execute(
            select(
                func.pg_advisory_xact_lock(func.hashtextextended(owner.hf_user_id, 0))
            )
        )
        now = _now()
        rows = list(
            self.db.execute(
                select(ChatSession)
                .where(
                    ChatSession.hf_user_id == owner.hf_user_id,
                    ChatSession.archived_at.is_(None),
                    ChatSession.updated_at < now - timedelta(days=days),
                    or_(
                        ChatSession.active_turn_id.is_(None),
                        ChatSession.active_turn_expires_at.is_(None),
                        ChatSession.active_turn_expires_at <= now,
                    ),
                )
                .with_for_update()
            ).scalars()
        )
        for session in rows:
            session.archived_at = now
        self.db.flush()
        return len(rows)

    def archive_oldest_sessions(self, owner: ChatOwner, *, limit: int = 50) -> int:
        """Hide up to ``limit`` least-recently-updated inactive chats."""
        self.db.execute(
            select(
                func.pg_advisory_xact_lock(func.hashtextextended(owner.hf_user_id, 0))
            )
        )
        now = _now()
        rows = list(
            self.db.execute(
                select(ChatSession)
                .where(
                    ChatSession.hf_user_id == owner.hf_user_id,
                    ChatSession.archived_at.is_(None),
                    or_(
                        ChatSession.active_turn_id.is_(None),
                        ChatSession.active_turn_expires_at.is_(None),
                        ChatSession.active_turn_expires_at <= now,
                    ),
                )
                .order_by(ChatSession.updated_at.asc(), ChatSession.id.asc())
                .limit(limit)
                .with_for_update()
            ).scalars()
        )
        for session in rows:
            session.archived_at = now
        self.db.flush()
        return len(rows)

    def get_session(
        self, owner: ChatOwner, session_id: uuid.UUID
    ) -> tuple[ChatSession, list[ChatMessageRecord]]:
        session = self._owned(owner, session_id)
        messages = list(
            self.db.execute(
                select(ChatMessageRecord)
                .where(
                    ChatMessageRecord.session_id == session.id,
                    ChatMessageRecord.status.notin_(INACTIVE_STATUSES),
                )
                .order_by(ChatMessageRecord.sequence)
            ).scalars()
        )
        return session, messages

    def rename_session(
        self, owner: ChatOwner, session_id: uuid.UUID, title: str
    ) -> ChatSession:
        session = self._owned(owner, session_id, lock=True)
        normalized = _normalized(title, 80)
        if not normalized:
            raise ChatServiceError("invalid_title", 422, "Title must not be empty")
        session.title = normalized
        session.title_source = "user"
        session.title_status = "complete"
        session.title_generation_id = None
        session.hf_username = owner.hf_username
        session.updated_at = _now()
        self.db.flush()
        return session

    def select_model(
        self, owner: ChatOwner, session_id: uuid.UUID, model: str
    ) -> ChatSession:
        selected, _ = self._validate_model(model)
        session = self._owned(owner, session_id, lock=True)
        if (
            session.active_turn_id
            and session.active_turn_expires_at
            and session.active_turn_expires_at > _now()
        ):
            raise ChatServiceError(
                "session_busy", 409, "This chat is generating a response"
            )
        session.selected_model = selected
        if self.settings.chat_model_providers[selected] == "openrouter":
            if session.execution_backend != "modal_cli":
                raise ChatServiceError(
                    "openrouter_gateway_required",
                    409,
                    "Start a new chat to use this OpenRouter model securely.",
                )
        session.hf_username = owner.hf_username
        session.updated_at = _now()
        self.db.flush()
        return session

    def _resolve_replay(
        self,
        session: ChatSession | None,
        *,
        client_message_id: str,
        web_search_enabled: bool,
        now: datetime,
    ) -> _ReplayOutcome:
        if session is None:
            return _ReplayOutcome(kind="continue")
        existing = self.db.execute(
            select(ChatMessageRecord).where(
                ChatMessageRecord.session_id == session.id,
                ChatMessageRecord.client_message_id == client_message_id,
            )
        ).scalar_one_or_none()
        if existing is None:
            return _ReplayOutcome(kind="continue")

        existing_web_search_enabled = getattr(existing, "web_search_enabled", False)
        if existing_web_search_enabled != web_search_enabled:
            raise ChatServiceError(
                "idempotency_conflict",
                409,
                "This request ID was already used with different Search permission",
            )
        assistant = self.db.execute(
            select(ChatMessageRecord).where(
                ChatMessageRecord.session_id == session.id,
                ChatMessageRecord.turn_id == existing.turn_id,
                ChatMessageRecord.role == "assistant",
            )
        ).scalar_one_or_none()
        if assistant:
            return _ReplayOutcome(
                kind="admitted",
                admission=TurnAdmission(
                    session_id=session.id,
                    turn_id=existing.turn_id,
                    user_message_id=existing.id,
                    selected_model=existing.model or session.selected_model,
                    model_route=(
                        existing.model_route
                        or self._validate_model(session.selected_model)[1]
                    ),
                    sdk_session_id=session.sdk_session_id,
                    sdk_project_key=session.sdk_project_key,
                    is_first_turn=existing.sequence == 1,
                    replay_assistant=ReplayAssistant(
                        content=assistant.content,
                        followups=list(assistant.followups or []),
                    ),
                    prompt_revision=existing.revision,
                    execution_backend=session.execution_backend,
                    web_search_enabled=existing_web_search_enabled,
                ),
            )
        if (
            existing.status in ("generating", PREPARING_STATUS)
            and session.active_turn_expires_at
            and session.active_turn_expires_at <= now
        ):
            return _ReplayOutcome(
                kind="expired",
                expired_message=existing,
            )
        if existing.status in ("interrupted", "error", "superseded"):
            raise ChatServiceError(
                "turn_requires_retry",
                409,
                "Retry or edit this prompt with a new request ID",
            )
        raise ChatServiceError(
            "turn_in_progress", 409, "This turn is already in progress"
        )

    def _apply_expired_replay(
        self, session: ChatSession, existing: ChatMessageRecord
    ) -> None:
        if existing.status == PREPARING_STATUS:
            self.edits.expire_preparation(session, existing)
        else:
            existing.status = "interrupted"
            existing.error_code = "lease_expired"
        if session.active_turn_id == existing.turn_id:
            session.active_turn_id = None
            session.active_turn_expires_at = None

    def _lock_admission_keys(self, owner: ChatOwner) -> None:
        """Lock the user admission key before the global capacity key."""
        self.db.execute(
            select(
                func.pg_advisory_xact_lock(
                    func.hashtextextended(f"chat-user:{owner.hf_user_id}", 0)
                )
            )
        )
        self.db.execute(
            select(
                func.pg_advisory_xact_lock(
                    func.hashtextextended("chat-global-active-turns", 0)
                )
            )
        )

    def _load_capacity_snapshot(
        self, owner: ChatOwner, session: ChatSession | None
    ) -> _CapacitySnapshot:
        other_active = self.db.scalar(
            select(func.count())
            .select_from(ChatSession)
            .where(
                ChatSession.hf_user_id == owner.hf_user_id,
                *((ChatSession.id != session.id,) if session is not None else ()),
                ChatSession.active_turn_id.is_not(None),
                ChatSession.active_turn_expires_at > func.now(),
            )
        )
        active_total = (
            self.db.scalar(
                select(func.count())
                .select_from(ChatSession)
                .where(
                    ChatSession.active_turn_id.is_not(None),
                    ChatSession.active_turn_expires_at > func.now(),
                )
            )
            or 0
        )
        return _CapacitySnapshot(
            other_active=other_active,
            active_total=active_total,
        )

    def _validate_capacity(self, capacity: _CapacitySnapshot) -> None:
        if capacity.other_active >= self.settings.chat_user_max_concurrency:
            raise ChatServiceError(
                "chat_capacity",
                429,
                "This account already has the maximum active research responses",
                active_count=capacity.active_total,
            )
        if capacity.active_total >= self.settings.chat_max_concurrency:
            raise ChatServiceError(
                "chat_capacity",
                429,
                "Research capacity is currently occupied",
                active_count=capacity.active_total,
            )

    def _load_expired_active_message(
        self, session: ChatSession, now: datetime
    ) -> ChatMessageRecord | None:
        if (
            session.active_turn_id
            and session.active_turn_expires_at
            and session.active_turn_expires_at > now
        ):
            raise ChatServiceError(
                "session_busy", 409, "This chat is generating a response"
            )
        if not session.active_turn_id:
            return None
        return self.db.execute(
            select(ChatMessageRecord).where(
                ChatMessageRecord.session_id == session.id,
                ChatMessageRecord.turn_id == session.active_turn_id,
                ChatMessageRecord.role == "user",
                ChatMessageRecord.status.in_(["generating", PREPARING_STATUS]),
            )
        ).scalar_one_or_none()

    def _apply_expired_active_turn(
        self, session: ChatSession, stale: ChatMessageRecord | None
    ) -> bool:
        if not session.active_turn_id:
            return False
        if stale:
            if stale.status == PREPARING_STATUS:
                self.edits.expire_preparation(session, stale)
            else:
                stale.status = "interrupted"
                stale.error_code = "lease_expired"
        session.active_turn_id = None
        session.active_turn_expires_at = None
        return True

    def _has_unresolved_turn(self, session: ChatSession) -> bool:
        return (
            self.db.execute(
                select(ChatMessageRecord.id).where(
                    ChatMessageRecord.session_id == session.id,
                    ChatMessageRecord.role == "user",
                    ChatMessageRecord.status.in_(["interrupted", "error"]),
                )
            ).first()
            is not None
        )

    def _load_owner_storage_bytes(self, owner: ChatOwner) -> int:
        return (
            self.db.scalar(
                select(
                    func.coalesce(
                        func.sum(
                            ChatSession.transcript_bytes + ChatSession.projection_bytes
                        ),
                        0,
                    )
                ).where(ChatSession.hf_user_id == owner.hf_user_id)
            )
            or 0
        )

    def _load_replacement_plan(
        self,
        session: ChatSession,
        *,
        replace_message_id: uuid.UUID | None,
        prior_revision: int | None,
    ) -> _ReplacementPlan:
        if replace_message_id is None:
            return _build_replacement_plan(
                replacement_requested=False,
                prior=None,
                active_suffix_ids=(),
                sdk_session_id=session.sdk_session_id,
                sdk_project_key=session.sdk_project_key,
            )
        prior = self.db.execute(
            select(ChatMessageRecord).where(
                ChatMessageRecord.id == replace_message_id,
                ChatMessageRecord.session_id == session.id,
                ChatMessageRecord.role == "user",
                ChatMessageRecord.revision == prior_revision,
                ChatMessageRecord.status.notin_(INACTIVE_STATUSES),
            )
        ).scalar_one_or_none()
        if prior is None:
            return _build_replacement_plan(
                replacement_requested=True,
                prior=None,
                active_suffix_ids=(),
                sdk_session_id=session.sdk_session_id,
                sdk_project_key=session.sdk_project_key,
            )
        active_suffix_ids = tuple(
            self.db.execute(
                select(ChatMessageRecord.id)
                .where(
                    ChatMessageRecord.session_id == session.id,
                    ChatMessageRecord.sequence >= prior.sequence,
                    ChatMessageRecord.status.notin_(INACTIVE_STATUSES),
                )
                .order_by(ChatMessageRecord.sequence)
            ).scalars()
        )
        return _build_replacement_plan(
            replacement_requested=True,
            prior=prior,
            active_suffix_ids=active_suffix_ids,
            sdk_session_id=session.sdk_session_id,
            sdk_project_key=session.sdk_project_key,
        )

    def _load_reclaimed_projection_bytes(self, replacement: _ReplacementPlan) -> int:
        if not replacement.active_suffix_ids or not isinstance(self.db, Session):
            return 0
        suffix_rows = list(
            self.db.execute(
                select(ChatMessageRecord).where(
                    ChatMessageRecord.id.in_(replacement.active_suffix_ids)
                )
            ).scalars()
        )
        return _reclaimed_projection_bytes(suffix_rows)

    def _load_replacement_prefix_count(
        self, session: ChatSession, replacement: _ReplacementPlan
    ) -> int | None:
        if replacement.prior is None:
            return None
        return (
            self.db.scalar(
                select(func.count())
                .select_from(ChatMessageRecord)
                .where(
                    ChatMessageRecord.session_id == session.id,
                    ChatMessageRecord.sequence < replacement.prior.sequence,
                    ChatMessageRecord.status.notin_(INACTIVE_STATUSES),
                )
            )
            or 0
        )

    def _validate_turn_storage_quota(self, quota: _QuotaCalculation) -> None:
        if (
            quota.resulting_session_bytes > self.settings.chat_session_byte_limit
            or quota.resulting_owner_bytes > self.settings.chat_user_byte_limit
        ):
            raise ChatServiceError(
                "chat_storage_quota_exceeded", 409, "Chat storage quota exceeded"
            )

    def _validate_turn_message_quota(self, quota: _QuotaCalculation) -> None:
        if quota.resulting_message_count > self.settings.chat_session_message_limit:
            raise ChatServiceError(
                "chat_message_quota_exceeded",
                409,
                "This chat has reached its message limit; start a new chat",
            )

    def _resolve_transcript_resume_boundary(
        self, session: ChatSession, replacement: _ReplacementPlan
    ) -> _TranscriptResumeBoundary:
        if replacement.prior is not None:
            return _TranscriptResumeBoundary(
                id=replacement.prior.sdk_resume_boundary_id
            )
        resume_boundary: uuid.UUID | None = None
        if session.sdk_session_id and session.sdk_project_key:
            boundary = self.db.scalar(
                select(ChatSDKTranscriptEntry.entry_uuid)
                .where(
                    ChatSDKTranscriptEntry.project_key == session.sdk_project_key,
                    ChatSDKTranscriptEntry.sdk_session_id == session.sdk_session_id,
                    ChatSDKTranscriptEntry.subpath == "",
                    ChatSDKTranscriptEntry.entry_uuid.is_not(None),
                    ChatSDKTranscriptEntry.entry["type"].astext.in_(
                        ["user", "assistant"]
                    ),
                )
                .order_by(ChatSDKTranscriptEntry.id.desc())
                .limit(1)
            )
            with contextlib.suppress(ValueError):
                resume_boundary = uuid.UUID(boundary) if boundary else None
        return _TranscriptResumeBoundary(id=resume_boundary)

    def _turn_runtime_descriptor(self, session: ChatSession) -> _TurnRuntimeDescriptor:
        return _TurnRuntimeDescriptor(
            execution_backend=session.execution_backend,
            app_release_id=self.settings.release_id,
            image_version=self.settings.chat_modal_image_version,
            worker_contract_version=self.settings.chat_worker_contract_version,
            pwc_cli_version=self.settings.chat_pwc_cli_version,
            system_prompt_sha256=self.settings.chat_system_prompt_sha256,
        )

    def _build_turn_creation_plan(
        self,
        session: ChatSession,
        *,
        replacement: _ReplacementPlan,
        quota: _QuotaCalculation,
        resume_boundary: _TranscriptResumeBoundary,
        model: str,
        model_route: str,
        effective_prompt: str,
        paper_mentions: list[dict],
    ) -> _TurnCreationPlan:
        is_first_turn = replacement.prior is None and session.message_count == 0
        return _TurnCreationPlan(
            message_id=uuid.uuid4(),
            replacement=replacement,
            quota=quota,
            resume_boundary=resume_boundary,
            runtime=self._turn_runtime_descriptor(session),
            model=model,
            model_route=model_route,
            effective_prompt=effective_prompt,
            paper_mentions=paper_mentions,
            is_first_turn=is_first_turn,
            title_should_generate=(is_first_turn and session.title_source != "user"),
        )

    def _apply_turn_creation(
        self,
        session: ChatSession,
        owner: ChatOwner,
        plan: _TurnCreationPlan,
        *,
        client_message_id: str,
        text: str,
        web_search_enabled: bool,
        update_web_search_preference: bool,
        now: datetime,
    ) -> ChatMessageRecord:
        prior = plan.replacement.prior
        session.last_sequence += 1
        if prior is None:
            session.message_count += 1
        session.active_turn_id = plan.replacement.turn_id
        session.active_turn_expires_at = now + timedelta(
            seconds=self.settings.chat_timeout_seconds + 30
        )
        session.hf_username = owner.hf_username
        if update_web_search_preference:
            session.web_search_enabled = web_search_enabled
        session.updated_at = now
        session.projection_bytes += plan.quota.new_projection_bytes
        message = ChatMessageRecord(
            id=plan.message_id,
            session_id=session.id,
            turn_id=plan.replacement.turn_id,
            sequence=session.last_sequence,
            role="user",
            content=text,
            paper_mentions=plan.paper_mentions,
            effective_prompt=plan.effective_prompt,
            client_message_id=client_message_id,
            web_search_enabled=web_search_enabled,
            revision=plan.replacement.revision,
            supersedes_message_id=prior.id if prior else None,
            sdk_resume_boundary_id=plan.resume_boundary.id,
            status=PREPARING_STATUS if prior is not None else "generating",
            model=plan.model,
            model_route=plan.model_route,
            app_release_id=plan.runtime.app_release_id,
            sandbox_image_version=plan.runtime.persisted(plan.runtime.image_version),
            worker_contract_version=plan.runtime.persisted(
                plan.runtime.worker_contract_version
            ),
            pwc_cli_version=plan.runtime.persisted(plan.runtime.pwc_cli_version),
            system_prompt_sha256=plan.runtime.persisted(
                plan.runtime.system_prompt_sha256
            ),
            last_attempted_at=now,
        )
        self.db.add(message)
        self.db.flush()
        return message

    @staticmethod
    def _turn_admission(
        session: ChatSession,
        plan: _TurnCreationPlan,
        fetchable_urls: tuple[str, ...],
        *,
        web_search_enabled: bool,
    ) -> TurnAdmission:
        prior = plan.replacement.prior
        return TurnAdmission(
            session_id=session.id,
            turn_id=plan.replacement.turn_id,
            user_message_id=plan.message_id,
            selected_model=plan.model,
            model_route=plan.model_route,
            sdk_session_id=session.sdk_session_id,
            sdk_project_key=session.sdk_project_key,
            is_first_turn=plan.is_first_turn,
            resume_boundary_id=plan.resume_boundary.id,
            is_replacement=prior is not None,
            replacement_target_id=prior.id if prior else None,
            replacement_target_sequence=prior.sequence if prior else None,
            replacement_target_revision=prior.revision if prior else None,
            replacement_active_suffix_ids=plan.replacement.active_suffix_ids,
            prompt_revision=plan.replacement.revision,
            title_should_generate=plan.title_should_generate,
            execution_backend=plan.runtime.execution_backend,
            app_release_id=plan.runtime.app_release_id,
            image_version=plan.runtime.image_version,
            worker_contract_version=plan.runtime.worker_contract_version,
            pwc_cli_version=plan.runtime.pwc_cli_version,
            system_prompt_sha256=plan.runtime.system_prompt_sha256,
            web_search_enabled=web_search_enabled,
            fetchable_urls=fetchable_urls,
        )

    def begin_turn(
        self,
        owner: ChatOwner,
        *,
        session_id: uuid.UUID | None,
        client_message_id: str,
        text: str,
        effective_prompt: str | None = None,
        paper_mentions: list[dict] | None = None,
        initial_model: str | None = None,
        replace_message_id: uuid.UUID | None = None,
        prior_revision: int | None = None,
        web_search_enabled: bool = False,
        update_web_search_preference: bool = True,
    ) -> TurnAdmission:
        session = (
            None if session_id is None else self._owned(owner, session_id, lock=True)
        )
        now = _now()
        replay = self._resolve_replay(
            session,
            client_message_id=client_message_id,
            web_search_enabled=web_search_enabled,
            now=now,
        )
        if replay.kind == "admitted":
            assert replay.admission is not None
            return replay.admission
        if replay.kind == "expired":
            assert session is not None
            assert replay.expired_message is not None
            self._apply_expired_replay(session, replay.expired_message)
            raise ChatServiceError(
                "turn_requires_retry",
                409,
                "Retry or edit the interrupted prompt with a new request ID",
                commit_changes=True,
            )

        if session is not None and session.transcript_status == "degraded":
            raise ChatServiceError(
                "chat_transcript_degraded",
                409,
                "This chat is awaiting transcript recovery and cannot be resumed",
            )

        self._lock_admission_keys(owner)
        capacity = self._load_capacity_snapshot(owner, session)
        self._validate_capacity(capacity)

        # Capacity admission precedes creation so a rejected new-chat request
        # cannot leave behind a session or any message state.
        if session is None:
            session = self.create_session(owner, initial_model)

        stale = self._load_expired_active_message(session, now)
        recovered_expired_lease = self._apply_expired_active_turn(session, stale)
        if self._has_unresolved_turn(session) and replace_message_id is None:
            raise ChatServiceError(
                "turn_requires_retry",
                409,
                "Retry or edit the interrupted prompt first",
                commit_changes=recovered_expired_lease,
            )
        effective_prompt = effective_prompt if effective_prompt is not None else text
        paper_mentions = paper_mentions or []
        new_projection_bytes = (
            len(text.encode())
            + len(effective_prompt.encode())
            + _payload_bytes(paper_mentions)
        )
        owner_total_bytes = self._load_owner_storage_bytes(owner)
        model, model_route = self._validate_model(session.selected_model)
        replacement = self._load_replacement_plan(
            session,
            replace_message_id=replace_message_id,
            prior_revision=prior_revision,
        )
        reclaimed_projection_bytes = self._load_reclaimed_projection_bytes(replacement)
        quota = _calculate_turn_quota(
            session_transcript_bytes=session.transcript_bytes,
            session_projection_bytes=session.projection_bytes,
            owner_total_bytes=owner_total_bytes,
            reclaimed_projection_bytes=reclaimed_projection_bytes,
            new_projection_bytes=new_projection_bytes,
            current_message_count=session.message_count,
            replacement_prefix_count=None,
        )
        self._validate_turn_storage_quota(quota)
        replacement_prefix_count = self._load_replacement_prefix_count(
            session, replacement
        )
        quota = _calculate_turn_quota(
            session_transcript_bytes=session.transcript_bytes,
            session_projection_bytes=session.projection_bytes,
            owner_total_bytes=owner_total_bytes,
            reclaimed_projection_bytes=reclaimed_projection_bytes,
            new_projection_bytes=new_projection_bytes,
            current_message_count=session.message_count,
            replacement_prefix_count=replacement_prefix_count,
        )
        self._validate_turn_message_quota(quota)
        resume_boundary = self._resolve_transcript_resume_boundary(session, replacement)
        plan = self._build_turn_creation_plan(
            session,
            replacement=replacement,
            quota=quota,
            resume_boundary=resume_boundary,
            model=model,
            model_route=model_route,
            effective_prompt=effective_prompt,
            paper_mentions=paper_mentions,
        )
        message = self._apply_turn_creation(
            session,
            owner,
            plan,
            client_message_id=client_message_id,
            text=text,
            web_search_enabled=web_search_enabled,
            update_web_search_preference=update_web_search_preference,
            now=now,
        )
        fetchable_urls = tuple(
            self.fetchable_url_seed(
                session.id,
                current_message_id=message.id,
                replacement_target_sequence=(
                    replacement.prior.sequence if replacement.prior else None
                ),
            )
        )
        return self._turn_admission(
            session,
            plan,
            fetchable_urls,
            web_search_enabled=web_search_enabled,
        )

    def bind_sdk_session(
        self,
        owner: ChatOwner,
        session_id: uuid.UUID,
        turn_id: uuid.UUID,
        sdk_session_id: uuid.UUID,
        project_key: str,
    ) -> bool:
        session = self._owned(owner, session_id, lock=True)
        if session.active_turn_id != turn_id:
            return False
        if session.sdk_session_id is None:
            session.sdk_session_id = sdk_session_id
            session.sdk_project_key = project_key
            session.transcript_status = "ready"
            session.transcript_bytes = (
                self.db.scalar(
                    select(
                        func.coalesce(func.sum(ChatSDKTranscriptEntry.byte_size), 0)
                    ).where(
                        ChatSDKTranscriptEntry.project_key == project_key,
                        ChatSDKTranscriptEntry.sdk_session_id == sdk_session_id,
                    )
                )
                or 0
            )
        return session.sdk_session_id == sdk_session_id

    def activate_edit(
        self,
        owner: ChatOwner,
        admission: TurnAdmission,
        replacement_sdk_session_id: uuid.UUID | None,
        project_key: str,
    ) -> bool:
        session = self._owned(owner, admission.session_id, lock=True)
        return self.edits.activate(
            session,
            admission,
            replacement_sdk_session_id,
            project_key,
        )

    def record_prepared_fork(
        self,
        owner: ChatOwner,
        admission: TurnAdmission,
        fork_sdk_session_id: uuid.UUID,
        project_key: str,
    ) -> bool:
        session = self._owned(owner, admission.session_id, lock=True)
        return self.edits.record_fork(
            session, admission, fork_sdk_session_id, project_key
        )

    def abort_prepared_edit(
        self,
        owner: ChatOwner,
        admission: TurnAdmission,
        code: str = "edit_prepare_failed",
    ) -> None:
        session = self._owned(owner, admission.session_id, lock=True)
        self.edits.abort(session, admission, code)

    def complete_turn(
        self,
        owner: ChatOwner,
        admission: TurnAdmission,
        answer: str,
        citations: list[dict],
        followups: list[str],
        display_blocks: list[dict],
        finish_reason: str,
    ) -> ChatMessageRecord:
        session = self._owned(owner, admission.session_id, lock=True)
        user_message = self.db.get(ChatMessageRecord, admission.user_message_id)
        if not user_message or session.active_turn_id != admission.turn_id:
            raise ChatServiceError("stale_turn", 409, "The chat turn lease changed")
        if finish_reason not in {"success", "max_turns", "tool_limit"}:
            raise ChatServiceError(
                "invalid_finish_reason", 422, "Unsupported completion state"
            )
        validated_blocks = [
            block.model_dump(mode="json", exclude_defaults=True)
            for block in DISPLAY_BLOCKS_ADAPTER.validate_python(display_blocks)
        ]
        validated_citations = [
            CitationSnapshot.model_validate(item).model_dump(mode="json")
            for item in citations[:20]
        ]
        if _payload_bytes(validated_blocks) > 256_000:
            raise ChatServiceError(
                "projection_too_large", 422, "The assistant projection is too large"
            )
        if _payload_bytes(validated_citations) > 64_000:
            raise ChatServiceError(
                "citations_too_large", 422, "The citation projection is too large"
            )
        followups = [
            _normalized(value, 500) for value in followups[:5] if value.strip()
        ]
        projection_bytes = len(answer.encode()) + _payload_bytes(
            validated_blocks, validated_citations, followups
        )
        session.last_sequence += 1
        assistant = ChatMessageRecord(
            id=uuid.uuid4(),
            session_id=session.id,
            turn_id=admission.turn_id,
            sequence=session.last_sequence,
            role="assistant",
            content=answer,
            citations=validated_citations,
            followups=followups[:5],
            display_blocks=validated_blocks,
            status="complete",
            model=admission.selected_model,
            model_route=admission.model_route,
            app_release_id=admission.app_release_id or None,
            sandbox_image_version=admission.image_version or None,
            worker_contract_version=admission.worker_contract_version or None,
            pwc_cli_version=admission.pwc_cli_version or None,
            system_prompt_sha256=admission.system_prompt_sha256 or None,
            finish_reason=finish_reason,
        )
        self.db.add(assistant)
        user_message.status = "complete"
        session.message_count += 1
        session.projection_bytes += projection_bytes
        session.active_turn_id = None
        session.active_turn_expires_at = None
        session.updated_at = _now()
        self.db.flush()
        return assistant

    def fail_turn(
        self,
        owner: ChatOwner,
        admission: TurnAdmission,
        code: str,
        interrupted: bool = False,
        display_blocks: list[dict] | None = None,
    ) -> None:
        session = self._owned(owner, admission.session_id, lock=True)
        if session.active_turn_id != admission.turn_id:
            return
        message = self.db.get(ChatMessageRecord, admission.user_message_id)
        if message:
            if self.edits.fail_preparation(session, message, code):
                return
            message.status = "interrupted" if interrupted else "error"
            message.error_code = code
            if display_blocks:
                validated_blocks = [
                    block.model_dump(mode="json", exclude_defaults=True)
                    for block in DISPLAY_BLOCKS_ADAPTER.validate_python(display_blocks)
                ]
                if _payload_bytes(validated_blocks) > 256_000:
                    raise ChatServiceError(
                        "projection_too_large",
                        422,
                        "The partial assistant projection is too large",
                    )
                message.display_blocks = validated_blocks
                session.projection_bytes += _payload_bytes(validated_blocks)
        session.active_turn_id = None
        session.active_turn_expires_at = None
        session.updated_at = _now()

    def mark_transcript_degraded(
        self, owner: ChatOwner, session_id: uuid.UUID, turn_id: uuid.UUID
    ) -> None:
        session = self._owned(owner, session_id, lock=True)
        if session.active_turn_id == turn_id:
            session.transcript_status = "degraded"

    def mark_transcript_ready(
        self,
        owner: ChatOwner,
        session_id: uuid.UUID,
        sdk_session_id: uuid.UUID,
    ) -> bool:
        session = self._owned(owner, session_id, lock=True)
        if session.sdk_session_id != sdk_session_id:
            return False
        session.transcript_status = "ready"
        return True

    def begin_title(
        self, owner: ChatOwner, session_id: uuid.UUID, revision: int = 1
    ) -> uuid.UUID | None:
        session = self._owned(owner, session_id, lock=True)
        if session.title_source == "user" or (
            session.title_prompt_revision == revision
            and session.title_status in ("generating", "complete", "fallback")
        ):
            return None
        token = uuid.uuid4()
        session.title_generation_id = token
        session.title_prompt_revision = revision
        session.title_status = "generating"
        return token

    def complete_title(
        self,
        owner: ChatOwner,
        session_id: uuid.UUID,
        token: uuid.UUID,
        title: str,
        *,
        fallback: bool,
    ) -> str | None:
        session = self._owned(owner, session_id, lock=True)
        if session.title_generation_id != token or session.title_source == "user":
            return None
        normalized = normalize_title(title) or "New chat"
        session.title = normalized
        session.title_source = "fallback" if fallback else "llm"
        session.title_status = "fallback" if fallback else "complete"
        session.title_model = self.settings.chat_title_model
        session.title_generated_at = _now()
        session.title_generation_id = None
        session.updated_at = _now()
        return normalized

    def delete_session(
        self, owner: ChatOwner, session_id: uuid.UUID
    ) -> ChatDeletionReceipt:
        session = self.db.execute(
            select(ChatSession)
            .where(
                ChatSession.id == session_id, ChatSession.hf_user_id == owner.hf_user_id
            )
            .with_for_update()
        ).scalar_one_or_none()
        if session is None:
            return ChatDeletionReceipt(session_id, None, None, None, None)
        if (
            session.active_turn_id
            and session.active_turn_expires_at
            and session.active_turn_expires_at > _now()
        ):
            raise ChatServiceError(
                "session_busy", 409, "Stop generation before deleting this chat"
            )
        if session.sdk_session_id and session.sdk_project_key:
            self.db.execute(
                delete(ChatSDKTranscriptEntry).where(
                    ChatSDKTranscriptEntry.project_key == session.sdk_project_key,
                    ChatSDKTranscriptEntry.sdk_session_id == session.sdk_session_id,
                )
            )
            self.db.execute(
                delete(ChatSDKSessionSummary).where(
                    ChatSDKSessionSummary.project_key == session.sdk_project_key,
                    ChatSDKSessionSummary.sdk_session_id == session.sdk_session_id,
                )
            )
        sandbox_id = (
            session.sandbox_lease.modal_sandbox_id if session.sandbox_lease else None
        )
        snapshot_id = (
            session.sandbox_lease.workspace_snapshot_id
            if session.sandbox_lease
            else None
        )
        receipt = ChatDeletionReceipt(
            session_id=session.id,
            sandbox_id=sandbox_id,
            snapshot_id=snapshot_id,
            sdk_session_id=session.sdk_session_id,
            sdk_project_key=session.sdk_project_key,
        )
        self.db.delete(session)
        return receipt

    def deletion_complete(self, receipt: ChatDeletionReceipt) -> bool:
        """Verify durable transcript, share, lease, and SDK state disappeared."""
        checks = [
            select(ChatSession.id).where(ChatSession.id == receipt.session_id),
            select(ChatMessageRecord.id).where(
                ChatMessageRecord.session_id == receipt.session_id
            ),
            select(ChatShare.id).where(ChatShare.chat_session_id == receipt.session_id),
            select(ChatSandboxLease.chat_session_id).where(
                ChatSandboxLease.chat_session_id == receipt.session_id
            ),
        ]
        if receipt.sdk_session_id and receipt.sdk_project_key:
            checks.extend(
                [
                    select(ChatSDKTranscriptEntry.id).where(
                        ChatSDKTranscriptEntry.project_key == receipt.sdk_project_key,
                        ChatSDKTranscriptEntry.sdk_session_id == receipt.sdk_session_id,
                    ),
                    select(ChatSDKSessionSummary.id).where(
                        ChatSDKSessionSummary.project_key == receipt.sdk_project_key,
                        ChatSDKSessionSummary.sdk_session_id == receipt.sdk_session_id,
                    ),
                ]
            )
        return all(self.db.execute(query).first() is None for query in checks)
