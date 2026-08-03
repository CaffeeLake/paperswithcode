"""Durable chat-turn orchestration and projection.

The HTTP router admits a turn and serializes frames. This module owns the
provider/title task lifecycle, durable state transitions, and projection of
provider events into persisted display blocks.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from claude_agent_sdk import fork_session_via_store
from claude_agent_sdk._internal.session_store import project_key_for_directory

from backend.config import Settings
from backend.database.connection import db_manager
from backend.services.chat_capability_service import ChatCapabilityService
from backend.services.chat_citation_service import cited_route_ids, resolve_citations
from backend.services.chat_latency_service import ChatLatencyService
from backend.services.chat_sandbox_service import SandboxError
from backend.services.chat_session_service import (
    ChatOwner,
    ChatServiceError,
    ChatSessionService,
    TurnAdmission,
)
from backend.services.chat_title_service import (
    fallback_title,
    normalize_title,
    stream_title,
)
from backend.services.chat_tracing_service import (
    ChatTurnTrace,
    NullChatTurnTrace,
    trace_chat_turn,
)
from backend.services.chat_transcript_recovery import reconcile_spooled_session
from backend.services.chat_turn_runner import ChatTurnRunner, create_chat_turn_runner
from backend.services.openrouter_user_budget_service import OpenRouterUserBudgetService
from backend.services.postgres_sdk_session_store import PostgresSDKSessionStore

logger = logging.getLogger(__name__)
HEARTBEAT_SECONDS = 15.0


@dataclass(frozen=True)
class ChatStreamFrame:
    """One transport-neutral frame for the router to serialize."""

    event: str | None
    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def heartbeat(cls) -> ChatStreamFrame:
        return cls(event=None)


async def sequential_reasoning_events(events: AsyncIterator[dict[str, Any]]):
    """Repair delayed Luna reasoning boundaries before projection and SSE."""
    reasoning_open = False
    async for event in events:
        kind = event.get("type")
        if kind == "reasoning_start":
            if reasoning_open:
                yield {"type": "reasoning_end"}
            reasoning_open = True
        elif kind == "reasoning_end":
            if not reasoning_open:
                continue
            reasoning_open = False
        elif kind in {"done", "error"} and reasoning_open:
            yield {"type": "reasoning_end"}
            reasoning_open = False
        yield event
    if reasoning_open:
        yield {"type": "reasoning_end"}


@dataclass
class ChatTurnProjection:
    """Typed mutable projection of provider events into display state."""

    answer_parts: list[str] = field(default_factory=list)
    blocks: list[dict[str, Any]] = field(default_factory=list)
    reasoning: dict[str, Any] | None = None
    tools: dict[str, dict[str, Any]] = field(default_factory=dict)
    citations: list[dict[str, Any]] = field(default_factory=list)

    def completed_blocks(self) -> list[dict[str, Any]]:
        return [
            {**block, "done": True} if block.get("kind") == "answer" else block
            for block in self.blocks
            if (block.get("kind") != "tool" or block.get("status") != "running")
            and block is not self.reasoning
        ]

    def apply(self, kind: str, event: dict[str, Any]) -> None:
        if kind == "reasoning_start":
            self.reasoning = {"kind": "reasoning", "text": ""}
            self.blocks.append(self.reasoning)
        elif kind == "reasoning_delta" and self.reasoning is not None:
            self.reasoning["text"] += event["text"]
        elif kind == "reasoning_end" and self.reasoning is not None:
            current = self.reasoning
            self.reasoning = None
            if (
                len(self.blocks) >= 2
                and self.blocks[-1] is current
                and self.blocks[-2].get("kind") == "reasoning"
                and self.blocks[-2].get("text") == current.get("text")
            ):
                self.blocks.pop()
        elif kind == "tool_call":
            self._start_tool(event)
        elif kind == "tool_result":
            self._finish_tool(event)
        elif kind == "answer_delta":
            self._append_answer(event["text"])

    def _append_answer(self, text: str) -> None:
        self.answer_parts.append(text)
        if self.blocks and self.blocks[-1].get("kind") == "answer":
            self.blocks[-1]["text"] += text
            return
        self.blocks.append({"kind": "answer", "text": text, "done": False})

    def _start_tool(self, event: dict[str, Any]) -> None:
        legacy_tool = event["name"] == "search_papers"
        tool: dict[str, Any] = {
            "kind": "tool",
            "schema_version": 1 if legacy_tool else 2,
            "id": event["id"],
            "name": event["name"],
            "args": event["args"],
            "status": "done" if legacy_tool else "running",
            "took_ms": 0,
        }
        if legacy_tool:
            tool.update({"hits": 0, "results": []})
        else:
            tool.update(
                {
                    "content": [],
                    "metadata": {"exit_code": None, "output_truncated": False},
                }
            )
        self.blocks.append(tool)
        self.tools[event["id"]] = tool

    def _finish_tool(self, event: dict[str, Any]) -> None:
        tool = self.tools.get(event["id"])
        if tool and event.get("status") is not None:
            tool.update(
                {
                    "status": event["status"],
                    "took_ms": event["took_ms"],
                    "content": event["content"],
                    "metadata": event.get("metadata")
                    or {"exit_code": None, "output_truncated": False},
                }
            )
        elif tool:
            tool.update(
                {
                    "hits": event["hits"],
                    "took_ms": event["took_ms"],
                    "results": event["results"],
                }
            )
        for result in event.get("results") or []:
            metadata = result.get("metadata", {})
            self.citations.append(
                {
                    "position": len(self.citations),
                    "route_id": result["route_id"],
                    "title": result["title"],
                    "source_url": metadata.get("source_url")
                    or (
                        f"https://arxiv.org/abs/{metadata['arxiv_id']}"
                        if metadata.get("arxiv_id")
                        else None
                    ),
                    "authors": [
                        author.get("name", "") for author in metadata.get("authors", [])
                    ],
                    "published": metadata.get("published"),
                    "conference": metadata.get("conference"),
                }
            )

    def finalize(self, db) -> tuple[str, list[dict[str, Any]]]:
        answer = "".join(self.answer_parts)
        if not any(block.get("kind") == "answer" for block in self.blocks):
            self.blocks.append({"kind": "answer", "text": "", "done": True})
        else:
            for block in self.blocks:
                if block.get("kind") == "answer":
                    block["done"] = True
        text = "\n".join(
            block.get("text", "")
            for block in self.blocks
            if block.get("kind") in {"reasoning", "answer"}
        )
        resolved = resolve_citations(db, text)
        if resolved:
            self.citations = resolved
        else:
            cited = set(re.findall(r"\]\(paper:([^) \t\n]{1,200})\)", text))
            self.citations = [
                item for item in self.citations if item["route_id"] in cited
            ]
        citations_by_id = {item["route_id"]: item for item in self.citations}
        for block in self.blocks:
            if block.get("kind") not in {"reasoning", "answer"}:
                continue
            block["citations"] = [
                citations_by_id[route_id]
                for route_id in cited_route_ids(block.get("text", ""))
                if route_id in citations_by_id
            ]
        return answer, self.citations


def _persist_failure(
    owner: ChatOwner,
    settings: Settings,
    admission: TurnAdmission,
    code: str,
    interrupted: bool,
    display_blocks: list[dict[str, Any]] | None = None,
) -> None:
    with db_manager.session_local() as db:
        try:
            ChatSessionService(db, settings).fail_turn(
                owner, admission, code, interrupted, display_blocks
            )
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("chat cleanup failed session_id=%s", admission.session_id)


def _persist_preparation_failure(
    owner: ChatOwner,
    settings: Settings,
    admission: TurnAdmission,
    code: str,
) -> None:
    with db_manager.session_local() as db:
        try:
            ChatSessionService(db, settings).abort_prepared_edit(owner, admission, code)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception(
                "chat edit preparation cleanup failed session_id=%s",
                admission.session_id,
            )


async def _prepare_replacement(
    owner: ChatOwner,
    settings: Settings,
    admission: TurnAdmission,
    store: PostgresSDKSessionStore,
    on_activated: Callable[[], None] | None = None,
) -> uuid.UUID | None:
    old_id = admission.sdk_session_id
    if not admission.is_replacement:
        return old_id
    session_directory = (
        "/workspace"
        if getattr(admission, "execution_backend", "local_mcp") == "modal_cli"
        else settings.chat_agent_cwd
    )
    project_key = project_key_for_directory(session_directory)
    replacement_id: uuid.UUID | None = None
    logger.info(
        "chat edit preparing session_id=%s target_id=%s source_sdk_id=%s cutoff_id=%s",
        admission.session_id,
        admission.replacement_target_id,
        old_id,
        admission.resume_boundary_id,
    )
    try:
        if old_id is not None and admission.resume_boundary_id:
            result = await fork_session_via_store(
                store,
                str(old_id),
                directory=session_directory,
                up_to_message_id=str(admission.resume_boundary_id),
            )
            replacement_id = uuid.UUID(result.session_id)
            with db_manager.session_local() as db:
                recorded = ChatSessionService(db, settings).record_prepared_fork(
                    owner, admission, replacement_id, project_key
                )
                if not recorded:
                    db.rollback()
                    raise ChatServiceError("stale_turn", 409, "The edit turn changed")
                db.commit()
        with db_manager.session_local() as db:
            activated = ChatSessionService(db, settings).activate_edit(
                owner,
                admission,
                replacement_id,
                project_key,
            )
            if not activated:
                db.rollback()
                raise ChatServiceError("stale_turn", 409, "The edit turn changed")
            db.commit()
    except BaseException:
        if replacement_id:
            with contextlib.suppress(Exception):
                await store.delete(
                    {"project_key": project_key, "session_id": str(replacement_id)}
                )
        logger.info(
            "chat edit activation outcome session_id=%s target_id=%s outcome=failed",
            admission.session_id,
            admission.replacement_target_id,
        )
        raise
    logger.info(
        "chat edit activation outcome session_id=%s target_id=%s fork_sdk_id=%s outcome=activated",
        admission.session_id,
        admission.replacement_target_id,
        replacement_id,
    )
    if on_activated:
        on_activated()
    if old_id is not None:
        try:
            await store.delete(
                {
                    "project_key": admission.sdk_project_key or project_key,
                    "session_id": str(old_id),
                }
            )
            logger.info(
                "chat edit transcript cleanup session_id=%s source_sdk_id=%s outcome=deleted",
                admission.session_id,
                old_id,
            )
        except Exception as exc:  # noqa: BLE001 - cleanup leaks must not undo activation
            logger.warning(
                "chat edit transcript cleanup session_id=%s source_sdk_id=%s outcome=leaked error=%s",
                admission.session_id,
                old_id,
                type(exc).__name__,
            )
    return replacement_id


async def _title_events(
    owner: ChatOwner,
    settings: Settings,
    admission: TurnAdmission,
    token: uuid.UUID,
    prompt: str,
    queue: asyncio.Queue,
    trace: ChatTurnTrace | NullChatTurnTrace,
) -> None:
    started = time.perf_counter()
    await queue.put({"type": "session_title_start"})
    pieces: list[str] = []
    fallback = False
    try:
        if not owner.hf_inference_token:
            raise RuntimeError("Hugging Face user billing is not connected")
        async for delta in stream_title(
            prompt,
            settings,
            provider_token=owner.hf_inference_token,
            bill_to=owner.hf_inference_bill_to,
        ):
            pieces.append(delta)
            await queue.put({"type": "session_title_delta", "text": delta})
        title = normalize_title("".join(pieces))
        if not title:
            raise ValueError("empty title")
    except Exception:
        fallback = True
        title = fallback_title(prompt)
    final = None
    try:
        with db_manager.session_local() as db:
            final = ChatSessionService(db, settings).complete_title(
                owner, admission.session_id, token, title, fallback=fallback
            )
            db.commit()
    except Exception as exc:
        logger.warning(
            "chat title persistence failed session_id=%s error=%s",
            admission.session_id,
            type(exc).__name__,
        )
    if final:
        await queue.put({"type": "session_title_done", "title": final})
    trace.finish_title(final or title, fallback=fallback)
    logger.info(
        "chat provider call complete call_class=title_generation session=%s "
        "duration_ms=%.1f outcome=%s",
        hashlib.sha256(str(admission.session_id).encode()).hexdigest()[:12],
        (time.perf_counter() - started) * 1000,
        "fallback" if fallback else "success",
    )
    await queue.put({"type": "_title_finished"})


def _log_background_task_result(task: asyncio.Task) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        return
    except Exception as exc:
        logger.warning("chat background task failed error=%s", type(exc).__name__)


class ChatStreamOrchestrator:
    """Run one admitted turn and yield transport-neutral stream frames."""

    def __init__(
        self,
        *,
        settings: Settings,
        owner: ChatOwner,
        admission: TurnAdmission,
        prompt: str,
        request_id: str,
        title_token: uuid.UUID | None,
        is_disconnected: Callable[[], Awaitable[bool]],
        release_admission: Callable[[], Awaitable[None]],
    ) -> None:
        self.settings = settings
        self.owner = owner
        self.admission = admission
        self.prompt = prompt
        self.request_id = request_id
        self.title_token = title_token
        self.is_disconnected = is_disconnected
        self.release_admission = release_admission
        self.principal_hash = hashlib.sha256(owner.hf_user_id.encode()).hexdigest()[:12]
        self.started = time.perf_counter()
        self.terminal = "disconnect"
        self.projection = ChatTurnProjection()
        self.store = PostgresSDKSessionStore()
        self.research_task: asyncio.Task | None = None
        self.title_task: asyncio.Task | None = None
        self.runner: ChatTurnRunner | None = None
        self.mirror_recovery: tuple[str, uuid.UUID] | None = None
        self.edit_activated = False
        self.first_application_delta_recorded = False
        self.trace: ChatTurnTrace | NullChatTurnTrace = NullChatTurnTrace()

    async def events(self) -> AsyncIterator[ChatStreamFrame]:
        if self.admission.replay_assistant:
            async for frame in self._events():
                yield frame
            return
        with trace_chat_turn(
            settings=self.settings,
            request_id=self.request_id,
            session_id=str(self.admission.session_id),
            user_id=self.owner.hf_user_id,
            prompt=self.prompt,
            model=self.admission.model_route,
            execution_backend=self.admission.execution_backend,
            is_replacement=self.admission.is_replacement,
        ) as trace:
            self.trace = trace
            async for frame in self._events():
                yield frame

    async def _events(self) -> AsyncIterator[ChatStreamFrame]:
        try:
            yield ChatStreamFrame(
                "stream_start",
                {
                    "request_id": self.request_id,
                    "session_id": self.admission.session_id,
                    "provider_execution": self.admission.replay_assistant is None,
                },
            )
            if self.admission.replay_assistant:
                yield ChatStreamFrame(
                    "answer_delta", {"text": self.admission.replay_assistant.content}
                )
                yield ChatStreamFrame(
                    "done",
                    {
                        "followups": self.admission.replay_assistant.followups or [],
                        "finish_reason": "success",
                    },
                )
                self.terminal = "success"
                return

            replacement_ready, resume_id = await self._replacement_or_error()
            if not replacement_ready:
                self.trace.finish("", "error")
                yield ChatStreamFrame(
                    "error",
                    {
                        "message": "Couldn’t resend this message. Your original conversation was restored.",
                        "code": "replacement_prepare_failed",
                    },
                )
                return

            queue: asyncio.Queue = asyncio.Queue()
            self.runner = create_chat_turn_runner(
                settings=self.settings,
                owner=self.owner,
                admission=self.admission,
                prompt=self.prompt,
                request_id=self.request_id,
                resume_id=resume_id,
                store=self.store,
            )
            self.research_task = asyncio.create_task(self._produce_research(queue))
            if self.title_token:
                self.trace.start_title(self.settings.chat_title_model)
                self.title_task = asyncio.create_task(
                    _title_events(
                        self.owner,
                        self.settings,
                        self.admission,
                        self.title_token,
                        self.prompt,
                        queue,
                        self.trace,
                    )
                )
            async for frame in self._consume(queue):
                yield frame
            await self._reconcile_mirror()
            if self.title_task:
                with contextlib.suppress(asyncio.CancelledError):
                    await self.title_task
        except asyncio.CancelledError:
            await self._cancel_runner()
            if self.admission.is_replacement and not self.edit_activated:
                await asyncio.shield(
                    asyncio.to_thread(
                        _persist_preparation_failure,
                        self.owner,
                        self.settings,
                        self.admission,
                        "interrupted",
                    )
                )
            else:
                await asyncio.shield(
                    asyncio.to_thread(
                        _persist_failure,
                        self.owner,
                        self.settings,
                        self.admission,
                        "interrupted",
                        True,
                        self.projection.completed_blocks(),
                    )
                )
            self.terminal = "interrupted"
            raise
        except Exception as exc:
            logger.warning(
                "chat stream persistence failed session_id=%s error=%s",
                self.admission.session_id,
                type(exc).__name__,
            )
            _persist_failure(
                self.owner,
                self.settings,
                self.admission,
                "persistence_error",
                False,
            )
            self.terminal = "error"
            self.trace.finish("".join(self.projection.answer_parts), "error")
            yield ChatStreamFrame(
                "error",
                {
                    "message": (
                        "The response could not be saved. You can retry this prompt."
                    ),
                    "code": "persistence_error",
                },
            )
        finally:
            await self._close()

    async def _replacement_or_error(self) -> tuple[bool, uuid.UUID | None]:
        try:
            resume_id = await _prepare_replacement(
                self.owner,
                self.settings,
                self.admission,
                self.store,
                lambda: setattr(self, "edit_activated", True),
            )
            return True, resume_id
        except Exception as exc:
            logger.warning(
                "chat replacement preparation failed session_id=%s error=%s",
                self.admission.session_id,
                type(exc).__name__,
            )
            _persist_preparation_failure(
                self.owner, self.settings, self.admission, "replacement_prepare_failed"
            )
            self.terminal = "error"
            return False, None

    async def _produce_research(self, queue: asyncio.Queue) -> None:
        try:
            assert self.runner is not None
            async for event in sequential_reasoning_events(self.runner.events()):
                await queue.put(event)
        except asyncio.CancelledError:
            raise
        except SandboxError as exc:
            await queue.put({"type": "error", "message": str(exc), "code": exc.code})
        except Exception as exc:
            logger.warning(
                "chat research producer failed session_id=%s error=%s",
                self.admission.session_id,
                type(exc).__name__,
            )
            await queue.put(
                {
                    "type": "error",
                    "message": "The model provider is unavailable.",
                    "code": "provider_error",
                }
            )
        finally:
            await queue.put({"type": "_research_finished"})

    async def _consume(self, queue: asyncio.Queue) -> AsyncIterator[ChatStreamFrame]:
        research_finished = False
        title_finished = self.title_task is None
        last_write = time.monotonic()
        while not (research_finished and title_finished):
            try:
                event = await asyncio.wait_for(queue.get(), timeout=1)
            except TimeoutError:
                if await self.is_disconnected():
                    raise asyncio.CancelledError
                if time.monotonic() - last_write >= HEARTBEAT_SECONDS:
                    yield ChatStreamFrame.heartbeat()
                    last_write = time.monotonic()
                continue
            if await self.is_disconnected():
                raise asyncio.CancelledError
            event = dict(event)
            kind = event.pop("type")
            self.trace.record_event(kind, event)
            if kind == "_research_finished":
                research_finished = True
                continue
            if kind == "_title_finished":
                title_finished = True
                continue
            if kind == "_sdk_session":
                self._bind_sdk_session(event)
                continue
            if kind == "_mirror_error":
                frame = self._fail_mirror(event)
                self.trace.finish("".join(self.projection.answer_parts), self.terminal)
                yield frame
                if self.research_task:
                    self.research_task.cancel()
                continue
            if kind == "_cancelled":
                _persist_failure(
                    self.owner,
                    self.settings,
                    self.admission,
                    "interrupted",
                    True,
                    self.projection.completed_blocks(),
                )
                self.terminal = "stopped"
                self.trace.finish("".join(self.projection.answer_parts), "stopped")
                yield ChatStreamFrame(
                    "done", {"followups": [], "finish_reason": "stopped"}
                )
                continue
            if kind == "_latency":
                self._record_latency_phase(
                    str(event["phase"]),
                    int(event["elapsed_ms"]),
                    acquisition_outcome=event.get("acquisition_outcome"),
                )
                continue
            if kind == "usage":
                self.trace.record_usage(event)
                continue

            elapsed_ms = round((time.perf_counter() - self.started) * 1000)
            if kind == "workspace_ready":
                self._record_latency_phase("sdk_query_dispatched", elapsed_ms)
            if not self.first_application_delta_recorded and kind in {
                "reasoning_delta",
                "tool_call",
                "answer_delta",
            }:
                self.first_application_delta_recorded = True
                self._record_latency_phase("first_worker_delta", elapsed_ms)
                self._record_latency_phase("first_application_sse_delta", elapsed_ms)

            self.projection.apply(kind, event)
            if kind == "tool_call":
                self.trace.start_tool(event)
            elif kind == "tool_result":
                self.trace.finish_tool(event)
            if kind == "error":
                budget_interrupted = event.get("code") in {
                    "chat_temporarily_disabled",
                    "chat_disabled_interrupted",
                }
                if budget_interrupted:
                    event["code"] = "chat_disabled_interrupted"
                    event["message"] = (
                        "Chat was disabled while this response was running. "
                        "The partial response is saved. Please try again later."
                    )
                provider = self.settings.chat_route_providers.get(
                    self.admission.model_route
                )
                if provider == "openrouter":
                    with db_manager.session_local() as error_db:
                        funded_code = ChatCapabilityService(
                            error_db
                        ).provider_error_for_turn(
                            self.admission.session_id, self.admission.turn_id
                        )
                        if funded_code:
                            event["code"] = funded_code
                            if funded_code == "openrouter_monthly_budget_exhausted":
                                usage = OpenRouterUserBudgetService(
                                    error_db, self.settings
                                ).status_percentage(self.owner.hf_user_id)
                                reset = usage.resets_at.isoformat().replace(
                                    "+00:00", "Z"
                                )
                                event["message"] = (
                                    "You have used this month's Papers With Code "
                                    f"OpenRouter allowance. It resets at {reset}."
                                )
                            elif funded_code == "openrouter_unavailable":
                                event["message"] = (
                                    "OpenRouter is currently unavailable. However, "
                                    "you can still bring your own key in Settings."
                                )
                            elif funded_code == "openrouter_byok_credential_invalid":
                                event["message"] = (
                                    "Your OpenRouter API key is no longer valid. "
                                    "Reconnect it in Settings, then try again."
                                )
                            elif funded_code == "openrouter_byok_billing_error":
                                event["message"] = (
                                    "OpenRouter could not bill your API key. Review "
                                    "your OpenRouter credits and spending limits."
                                )
                            elif funded_code == "openrouter_byok_rate_limit":
                                event["message"] = (
                                    "Your OpenRouter API key is temporarily rate-limited."
                                )
                _persist_failure(
                    self.owner,
                    self.settings,
                    self.admission,
                    event.get("code") or "provider_error",
                    budget_interrupted,
                    self.projection.completed_blocks(),
                )
                self.terminal = "error"
                self.trace.finish("".join(self.projection.answer_parts), "error")
            elif kind == "done":
                self._complete_turn(event)
                event["citations"] = self.projection.citations
                self.terminal = event.get("finish_reason", "success")
                self.trace.finish("".join(self.projection.answer_parts), self.terminal)
            yield ChatStreamFrame(kind, event)
            last_write = time.monotonic()
        if self.research_task:
            with contextlib.suppress(asyncio.CancelledError):
                await self.research_task

    def _bind_sdk_session(self, event: dict[str, Any]) -> None:
        assert self.runner is not None
        sdk_id = uuid.UUID(event["session_id"])
        with db_manager.session_local() as db:
            ChatSessionService(db, self.settings).bind_sdk_session(
                self.owner,
                self.admission.session_id,
                self.admission.turn_id,
                sdk_id,
                project_key_for_directory(self.runner.sdk_directory),
            )
            db.commit()

    def _fail_mirror(self, event: dict[str, Any]) -> ChatStreamFrame:
        mirror_key = event.get("key") or {}
        mirror_session_id = mirror_key.get("session_id")
        mirror_project_key = mirror_key.get("project_key")
        logger.warning(
            "chat transcript mirror failed session_id=%s sdk_session_id=%s error=%s",
            self.admission.session_id,
            mirror_session_id,
            str(event.get("error") or "unknown")[:500],
        )
        if mirror_session_id and mirror_project_key:
            sdk_id = uuid.UUID(mirror_session_id)
            with db_manager.session_local() as db:
                ChatSessionService(db, self.settings).bind_sdk_session(
                    self.owner,
                    self.admission.session_id,
                    self.admission.turn_id,
                    sdk_id,
                    mirror_project_key,
                )
                db.commit()
            self.mirror_recovery = (mirror_project_key, sdk_id)
        terminal = event.get("terminal")
        completed_result = (
            event.get("result_available") is True
            and isinstance(terminal, dict)
            and terminal.get("type") == "done"
        )
        with db_manager.session_local() as db:
            service = ChatSessionService(db, self.settings)
            service.mark_transcript_degraded(
                self.owner, self.admission.session_id, self.admission.turn_id
            )
            if completed_result:
                terminal_payload = {
                    key: value
                    for key, value in terminal.items()
                    if key not in {"v", "type", "request_id"}
                }
                answer, citations = self.projection.finalize(db)
                service.complete_turn(
                    self.owner,
                    self.admission,
                    answer,
                    citations,
                    terminal_payload.get("followups", []),
                    self.projection.blocks,
                    terminal_payload.get("finish_reason", "success"),
                )
            else:
                service.fail_turn(
                    self.owner,
                    self.admission,
                    "transcript_mirror_error",
                    False,
                    self.projection.completed_blocks(),
                )
            db.commit()
        if completed_result:
            self.terminal = terminal_payload.get("finish_reason", "success")
            logger.warning(
                "chat transcript mirror failed after model result session_id=%s",
                self.admission.session_id,
            )
            return ChatStreamFrame(
                "done",
                {
                    **terminal_payload,
                    "citations": self.projection.citations,
                    "transcript_status": "degraded",
                    "warning": (
                        "The answer was saved, but its research transcript is "
                        "temporarily unavailable. Follow-up actions are disabled."
                    ),
                },
            )
        self.terminal = "error"
        logger.warning(
            "chat transcript mirror failed before model result session_id=%s",
            self.admission.session_id,
        )
        return ChatStreamFrame(
            "error",
            {
                "message": "The conversation could not be saved.",
                "code": "transcript_mirror_error",
            },
        )

    def _complete_turn(self, event: dict[str, Any]) -> None:
        with db_manager.session_local() as db:
            answer, citations = self.projection.finalize(db)
            ChatSessionService(db, self.settings).complete_turn(
                self.owner,
                self.admission,
                answer,
                citations,
                event.get("followups", []),
                self.projection.blocks,
                event.get("finish_reason", "success"),
            )
            db.commit()

    async def _reconcile_mirror(self) -> None:
        if not self.mirror_recovery:
            return
        project_key, sdk_id = self.mirror_recovery
        try:
            recovered = await reconcile_spooled_session(
                self.settings,
                self.store,
                project_key=project_key,
                sdk_session_id=sdk_id,
            )
        except Exception as exc:
            recovered = False
            logger.warning(
                "chat transcript reconciliation failed session_id=%s error=%s",
                self.admission.session_id,
                type(exc).__name__,
            )
        if recovered:
            with db_manager.session_local() as db:
                ChatSessionService(db, self.settings).mark_transcript_ready(
                    self.owner, self.admission.session_id, sdk_id
                )
                db.commit()

    async def _cancel_runner(self) -> None:
        if self.runner and self.research_task and not self.research_task.done():
            with contextlib.suppress(Exception):
                await asyncio.shield(self.runner.cancel())

    async def _close(self) -> None:
        # Starlette may close an async response generator with GeneratorExit
        # instead of delivering CancelledError. Persist the interruption here
        # as a last resort so a disconnected browser cannot leave the turn
        # generating until its lease expires.
        if self.terminal == "disconnect":
            if self.admission.is_replacement and not self.edit_activated:
                await asyncio.shield(
                    asyncio.to_thread(
                        _persist_preparation_failure,
                        self.owner,
                        self.settings,
                        self.admission,
                        "interrupted",
                    )
                )
            else:
                await asyncio.shield(
                    asyncio.to_thread(
                        _persist_failure,
                        self.owner,
                        self.settings,
                        self.admission,
                        "interrupted",
                        True,
                        self.projection.completed_blocks(),
                    )
                )
            self.terminal = "interrupted"
        await self._cancel_runner()
        if self.runner:
            with contextlib.suppress(Exception):
                await asyncio.shield(self.runner.close())
        if self.research_task and not self.research_task.done():
            self.research_task.cancel()
        if self.research_task:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self.research_task
        if self.title_task and not self.title_task.done():
            self.title_task.add_done_callback(_log_background_task_result)
        logger.info(
            "chat request complete request_id=%s principal=%s duration_ms=%.1f finish=%s",
            self.request_id,
            self.principal_hash,
            (time.perf_counter() - self.started) * 1000,
            self.terminal,
        )
        status = {
            "success": "complete",
            "max_turns": "complete",
            "tool_limit": "complete",
            "stopped": "stopped",
            "error": "error",
        }.get(self.terminal, "interrupted")
        if self.settings.environment == "staging":
            try:
                with db_manager.session_local() as db:
                    ChatLatencyService(db).finalize(
                        self.request_id,
                        status,
                        round((time.perf_counter() - self.started) * 1000),
                    )
                    db.commit()
            except Exception as exc:
                logger.warning(
                    "chat latency finalize failed request_id=%s error=%s",
                    self.request_id,
                    type(exc).__name__,
                )
        await self.release_admission()

    def _record_latency_phase(
        self,
        phase: str,
        elapsed_ms: int,
        *,
        acquisition_outcome: str | None = None,
    ) -> None:
        if self.settings.environment != "staging":
            return
        try:
            with db_manager.session_local() as db:
                ChatLatencyService(db).record_phase(
                    self.request_id,
                    phase,
                    elapsed_ms,
                    acquisition_outcome=acquisition_outcome,
                )
                db.commit()
        except Exception as exc:
            logger.warning(
                "chat latency phase failed request_id=%s phase=%s error=%s",
                self.request_id,
                phase,
                type(exc).__name__,
            )
