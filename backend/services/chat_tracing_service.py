"""Langfuse tracing for the trusted side of sandboxed chat turns."""

from __future__ import annotations

import hashlib
import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from langfuse import Langfuse, propagate_attributes

from backend.config import Settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=4)
def _client(
    environment: str,
    release: str,
    public_key: str,
    secret_key: str,
    base_url: str,
) -> Langfuse:
    return Langfuse(
        public_key=public_key,
        secret_key=secret_key,
        base_url=base_url,
        environment=environment,
        release=release,
    )


def _configured_client(settings: Settings) -> Langfuse | None:
    if not settings.chat_langfuse_enabled or settings.environment != "staging":
        return None
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY", "")
    base_url = os.environ.get("LANGFUSE_BASE_URL", "")
    if not public_key or not secret_key or not base_url:
        logger.warning(
            "chat Langfuse tracing disabled because credentials are incomplete"
        )
        return None
    return _client(
        settings.environment,
        settings.release_id,
        public_key,
        secret_key,
        base_url,
    )


def _usage_details(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    aliases = {
        "input": ("input_tokens", "inputTokens"),
        "output": ("output_tokens", "outputTokens"),
        "cache_read_input": (
            "cache_read_input_tokens",
            "cacheReadInputTokens",
        ),
        "cache_creation_input": (
            "cache_creation_input_tokens",
            "cacheCreationInputTokens",
        ),
    }
    details: dict[str, int] = {}
    for target, sources in aliases.items():
        count = next(
            (
                candidate
                for source in sources
                if isinstance((candidate := value.get(source)), int) and candidate >= 0
            ),
            None,
        )
        if count is not None:
            details[target] = count
    return details


class ChatTurnTrace:
    """Best-effort observation lifecycle for one research-chat turn."""

    def __init__(
        self,
        root: Any,
        *,
        prompt: str,
        model: str,
        execution_backend: str,
        display_prompt: str | None = None,
    ) -> None:
        self.root = root
        self.prompt = prompt
        self.display_prompt = display_prompt or prompt
        self.execution_backend = execution_backend
        self.generation = root.start_observation(
            name="generate-research-response",
            as_type="generation",
            input=[{"role": "user", "content": prompt}],
            model=model,
            metadata={
                "aggregation": "agent-run",
                "ttft_semantics": "first-worker-delta",
            },
        )
        self.title_generation: Any | None = None
        self.tools: dict[str, Any] = {}
        self.sandbox_acquisition: Any | None = None
        self.capability_installation: Any | None = None
        self.model_dispatch: Any | None = None
        self.first_worker_delta_recorded = False
        self.usage: dict[str, int] = {}
        self.usage_by_phase: dict[str, dict[str, int]] = {}
        self.cost: dict[str, float] = {}
        self.answer = ""
        self.status = "interrupted"
        self.closed = False

    @property
    def trace_id(self) -> str:
        return self.root.trace_id

    def start_title(self, model: str) -> None:
        if self.title_generation is None:
            self.title_generation = self.root.start_observation(
                name="generate-session-title",
                as_type="generation",
                input=[{"role": "user", "content": self.display_prompt}],
                model=model,
            )

    def finish_title(self, title: str, *, fallback: bool) -> None:
        if self.title_generation is None:
            return
        self.title_generation.update(
            output=title,
            level="WARNING" if fallback else "DEFAULT",
            status_message="deterministic fallback used" if fallback else None,
        ).end()
        self.title_generation = None

    def record_usage(self, event: dict[str, Any]) -> None:
        details = _usage_details(event.get("usage"))
        for key, value in details.items():
            self.usage[key] = self.usage.get(key, 0) + value
        phase = str(event.get("phase") or "research")
        phase_usage = self.usage_by_phase.setdefault(phase, {})
        for key, value in details.items():
            phase_usage[key] = phase_usage.get(key, 0) + value
        cost = event.get("total_cost_usd")
        if isinstance(cost, (int, float)) and cost >= 0:
            self.cost["total"] = self.cost.get("total", 0.0) + float(cost)
        self.generation.update(metadata={"usage_by_phase": self.usage_by_phase})

    def record_event(self, kind: str, event: dict[str, Any]) -> None:
        """Advance operational spans from sanitized worker lifecycle events."""

        if kind == "sandbox_start" and self.sandbox_acquisition is None:
            self.sandbox_acquisition = self.root.start_observation(
                name="acquire-sandbox",
                as_type="span",
                metadata={"execution_backend": self.execution_backend},
            )
            return
        if kind == "sandbox_ready":
            self._finish_sandbox_acquisition(event)
            if self.capability_installation is None:
                self.capability_installation = self.root.start_observation(
                    name="install-sandbox-capability",
                    as_type="span",
                )
            return
        if kind == "workspace_ready":
            self._finish_model_dispatch()
            return
        if kind in {"reasoning_delta", "tool_call", "answer_delta"}:
            self._record_first_worker_delta()
            return
        if kind == "_execution_telemetry":
            self.generation.update(
                metadata={
                    "aggregation": "agent-run",
                    "execution_policy": event,
                }
            )
            return
        if kind != "_latency":
            return

        phase = str(event.get("phase") or "")
        if phase in {"sandbox_acquisition_ms", "sandbox_acquisition_started"}:
            self._finish_sandbox_acquisition(event)
        elif phase in {"capability_install_ms", "broker_capability_installed"}:
            self._finish_capability_installation(event)
        elif phase in {"sdk_dispatch_ms", "sdk_query_dispatched"}:
            self._finish_model_dispatch(event)
        elif phase == "first_worker_delta":
            self._record_first_worker_delta()

    def _finish_sandbox_acquisition(self, event: dict[str, Any]) -> None:
        if self.sandbox_acquisition is None:
            return
        self.sandbox_acquisition.update(
            output={
                "acquisition_outcome": event.get("acquisition_outcome"),
                "elapsed_ms": event.get("elapsed_ms"),
            }
        ).end()
        self.sandbox_acquisition = None

    def _finish_capability_installation(self, event: dict[str, Any]) -> None:
        if self.capability_installation is not None:
            self.capability_installation.update(
                output={"elapsed_ms": event.get("elapsed_ms")}
            ).end()
            self.capability_installation = None
        if self.model_dispatch is None:
            self.model_dispatch = self.root.start_observation(
                name="dispatch-model-request",
                as_type="span",
            )

    def _finish_model_dispatch(self, event: dict[str, Any] | None = None) -> None:
        if self.model_dispatch is None:
            return
        self.model_dispatch.update(
            output={"elapsed_ms": (event or {}).get("elapsed_ms")}
        ).end()
        self.model_dispatch = None

    def _record_first_worker_delta(self) -> None:
        if self.first_worker_delta_recorded:
            return
        self.first_worker_delta_recorded = True
        self.generation.update(completion_start_time=datetime.now(UTC))

    def start_tool(self, event: dict[str, Any]) -> None:
        tool_id = str(event.get("id") or "")
        if not tool_id or tool_id in self.tools:
            return
        names = {
            "search_papers": "search-papers",
            "Bash": "run-bash-command",
            "Read": "read-file",
            "Grep": "search-files",
            "WebFetch": "fetch-web-page",
        }
        tool_name = str(event.get("name") or "tool")
        observation_type = "retriever" if tool_name == "search_papers" else "tool"
        self.tools[tool_id] = self.root.start_observation(
            name=names.get(tool_name, "use-tool"),
            as_type=observation_type,
            input=event.get("args") or {},
            metadata={"tool_name": tool_name},
        )

    def finish_tool(self, event: dict[str, Any]) -> None:
        tool = self.tools.pop(str(event.get("id") or ""), None)
        if tool is None:
            return
        status = str(event.get("status") or "success")
        output = event.get("results")
        if output is None:
            output = event.get("content") or []
        tool.update(
            output=output,
            metadata={"duration_ms": event.get("took_ms", 0)},
            level="ERROR" if status == "error" else "DEFAULT",
            status_message=status,
        ).end()

    def finish(self, answer: str, status: str) -> None:
        self.answer = answer
        self.status = status

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        level = "ERROR" if self.status in {"error", "interrupted"} else "DEFAULT"
        for observation in (
            self.sandbox_acquisition,
            self.capability_installation,
            self.model_dispatch,
        ):
            if observation is not None:
                observation.update(
                    level="WARNING", status_message="turn ended before phase completed"
                ).end()
        self.sandbox_acquisition = None
        self.capability_installation = None
        self.model_dispatch = None
        for tool in self.tools.values():
            tool.update(
                level="WARNING", status_message="turn ended before tool result"
            ).end()
        self.tools.clear()
        if self.title_generation is not None:
            self.title_generation.update(
                level="WARNING", status_message="title generation did not finish"
            ).end()
            self.title_generation = None
        output = [{"role": "assistant", "content": self.answer}]
        self.generation.update(
            output=output,
            usage_details=self.usage or None,
            cost_details=self.cost or None,
            level=level,
            status_message=self.status,
        ).end()
        self.root.update(output=output, level=level, status_message=self.status).end()


class NullChatTurnTrace:
    trace_id = ""

    def start_title(self, _model: str) -> None:
        return

    def finish_title(self, _title: str, *, fallback: bool) -> None:
        del fallback

    def record_usage(self, _event: dict[str, Any]) -> None:
        return

    def record_event(self, _kind: str, _event: dict[str, Any]) -> None:
        return

    def start_tool(self, _event: dict[str, Any]) -> None:
        return

    def finish_tool(self, _event: dict[str, Any]) -> None:
        return

    def finish(self, _answer: str, _status: str) -> None:
        return

    def close(self) -> None:
        return


@contextmanager
def trace_chat_turn(
    *,
    settings: Settings,
    request_id: str,
    session_id: str,
    user_id: str,
    prompt: str,
    model: str,
    execution_backend: str,
    is_replacement: bool,
    display_prompt: str | None = None,
) -> Iterator[ChatTurnTrace | NullChatTurnTrace]:
    """Create one trace per turn and one Langfuse session per conversation."""

    try:
        client = _configured_client(settings)
    except Exception:
        logger.exception("chat Langfuse client initialization failed")
        client = None
    if client is None:
        yield NullChatTurnTrace()
        return
    pseudonymous_user = hashlib.sha256(user_id.encode()).hexdigest()
    trace_id = client.create_trace_id(seed=request_id)
    trace: ChatTurnTrace | None = None
    try:
        with propagate_attributes(
            user_id=pseudonymous_user,
            session_id=session_id,
            metadata={
                "request_id": request_id,
                "execution_backend": execution_backend,
                "is_replacement": str(is_replacement).lower(),
            },
            version=settings.release_id,
            tags=["chat", "research-assistant", execution_backend],
            trace_name="answer-research-question",
            environment=settings.environment,
        ):
            root = client.start_observation(
                trace_context={"trace_id": trace_id},
                name="answer-research-question",
                as_type="agent",
                input=[{"role": "user", "content": prompt}],
                metadata={"request_id": request_id},
            )
            trace = ChatTurnTrace(
                root,
                prompt=prompt,
                display_prompt=display_prompt or prompt,
                model=model,
                execution_backend=execution_backend,
            )
            try:
                yield trace
            except BaseException as exc:
                trace.finish(
                    trace.answer,
                    "interrupted" if not isinstance(exc, Exception) else "error",
                )
                raise
            finally:
                try:
                    trace.close()
                except Exception:
                    logger.exception(
                        "chat Langfuse trace finalization failed request_id=%s",
                        request_id,
                    )
                logger.info(
                    "chat Langfuse trace complete request_id=%s trace_id=%s",
                    request_id,
                    trace.trace_id,
                )
    except BaseException:
        if trace is None:
            logger.exception("chat Langfuse trace initialization failed")
            yield NullChatTurnTrace()
            return
        raise
