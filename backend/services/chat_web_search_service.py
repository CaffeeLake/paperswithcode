"""Trusted, provider-neutral web search with bounded Exa transport and budget."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from ipaddress import ip_address
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.database.connection import db_manager
from backend.models.database import (
    ChatWebSearchBudgetState,
    ChatWebSearchCircuitEvent,
    ChatWebSearchOwnerUsage,
)

logger = logging.getLogger(__name__)


class WebSearchError(RuntimeError):
    def __init__(self, code: str, message: str, *, error_class: str):
        super().__init__(message)
        self.code = code
        self.error_class = error_class


class WebSearchUnavailable(WebSearchError):
    def __init__(self, error_class: str = "unavailable"):
        super().__init__(
            "web_search_unavailable",
            "Web search is temporarily unavailable.",
            error_class=error_class,
        )


class WebSearchValidationError(WebSearchError):
    def __init__(self, message: str = "Invalid web search request."):
        super().__init__(
            "web_search_invalid_request", message, error_class="validation"
        )


@dataclass(frozen=True)
class ProviderFailure:
    error_class: str
    retryable: bool
    retry_after: float | None = None
    opens_budget: bool = False
    opens_auth: bool = False


def opaque_owner(owner_id: str) -> str:
    return hashlib.sha256(owner_id.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


def _cycle(now: datetime) -> tuple[date, datetime]:
    start = date(now.year, now.month, 1)
    if now.month == 12:
        end = datetime(now.year + 1, 1, 1, tzinfo=UTC)
    else:
        end = datetime(now.year, now.month + 1, 1, tzinfo=UTC)
    return start, end


def _aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def _serialized_size(payload: object) -> int:
    return len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode())


def _hostname_denied(host: str, denylist: set[str]) -> bool:
    return any(host == item or host.endswith(f".{item}") for item in denylist)


def normalize_https_url(value: object, denylist: set[str]) -> str | None:
    if not isinstance(value, str) or len(value) > 2_000:
        return None
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        if (
            parsed.scheme != "https"
            or not host
            or not host.isascii()
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in {None, 443}
        ):
            return None
        host = host.lower().rstrip(".")
        if host == "localhost" or host.endswith((".local", ".internal", ".localhost")):
            return None
        try:
            address = ip_address(host)
        except ValueError:
            pass
        else:
            if not address.is_global:
                return None
        if _hostname_denied(host, denylist):
            return None
        return urlunsplit(("https", host, parsed.path or "/", parsed.query, ""))
    except ValueError:
        return None


def normalize_exa_payload(raw: object, settings: Settings) -> dict[str, Any]:
    if not isinstance(raw, dict) or not isinstance(raw.get("results"), list):
        raise WebSearchUnavailable("malformed_response")
    denylist = {
        item.strip().lower().rstrip(".")
        for item in settings.chat_web_search_domain_denylist.split(",")
        if item.strip()
    }
    results: list[dict[str, str | None]] = []
    for candidate in raw["results"]:
        if not isinstance(candidate, dict):
            continue
        url = normalize_https_url(candidate.get("url"), denylist)
        if url is None:
            continue
        title = " ".join(str(candidate.get("title") or "Untitled source").split())[:500]
        published = candidate.get("publishedDate")
        published_date = str(published)[:32] if published else None
        image_url = normalize_https_url(candidate.get("image"), denylist)
        favicon_url = normalize_https_url(candidate.get("favicon"), denylist)
        if image_url and len(image_url) > 1_000:
            image_url = None
        if favicon_url and len(favicon_url) > 1_000:
            favicon_url = None
        highlights = candidate.get("highlights")
        if isinstance(highlights, list):
            excerpt = "\n".join(item for item in highlights if isinstance(item, str))
        else:
            excerpt = ""
        results.append(
            {
                "title": title or "Untitled source",
                "url": url,
                "published_date": published_date,
                "excerpt": excerpt[:4_000],
                "image_url": image_url,
                "favicon_url": favicon_url,
            }
        )
        if len(results) >= settings.chat_web_search_result_count:
            break
    payload: dict[str, Any] = {"results": results}
    return _bound_payload(payload, settings.chat_web_search_max_result_bytes)


def _bound_payload(payload: dict[str, Any], maximum: int) -> dict[str, Any]:
    results = payload["results"]
    for result in reversed(results):
        while result["excerpt"] and _serialized_size(payload) > maximum:
            raw_excerpt = str(result["excerpt"])
            excess = _serialized_size(payload) - maximum
            result["excerpt"] = raw_excerpt[: max(0, len(raw_excerpt) - excess - 16)]
        if _serialized_size(payload) <= maximum:
            break
    for result in reversed(results):
        if _serialized_size(payload) <= maximum:
            break
        result["published_date"] = None
    for field in ("favicon_url", "image_url"):
        for result in reversed(results):
            if _serialized_size(payload) <= maximum:
                break
            result[field] = None
    while results and _serialized_size(payload) > maximum:
        results.pop()
    if _serialized_size(payload) > maximum:
        raise WebSearchUnavailable("result_too_large")
    return payload


class ChatWebSearchBudgetService:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings

    def configured(self) -> bool:
        return bool(
            self.settings.chat_web_search_enabled
            and self.settings.chat_web_search_provider == "exa"
            and self.settings.chat_web_search_exa_api_key
            and self.settings.chat_web_search_monthly_hard_calls
            >= self.settings.chat_web_search_monthly_warning_calls
        )

    def _lock(self, cycle: date) -> None:
        bind = self.db.get_bind()
        if bind is not None and bind.dialect.name == "postgresql":
            self.db.execute(
                select(
                    func.pg_advisory_xact_lock(
                        func.hashtextextended(
                            f"chat-web-search:{self.settings.environment}:{cycle}", 0
                        )
                    )
                )
            )

    def _state(
        self, *, create: bool, lock: bool = False
    ) -> ChatWebSearchBudgetState | None:
        now = _now()
        cycle, end = _cycle(now)
        if lock:
            self._lock(cycle)
        query = select(ChatWebSearchBudgetState).where(
            ChatWebSearchBudgetState.environment == self.settings.environment,
            ChatWebSearchBudgetState.billing_cycle == cycle,
        )
        if lock:
            query = query.with_for_update()
        state = self.db.execute(query).scalar_one_or_none()
        if state is None and create:
            state = ChatWebSearchBudgetState(
                id=uuid.uuid4(),
                environment=self.settings.environment,
                billing_cycle=cycle,
                cycle_end_at=end,
                warning_calls=self.settings.chat_web_search_monthly_warning_calls,
                hard_limit_calls=self.settings.chat_web_search_monthly_hard_calls,
            )
            self.db.add(state)
            self.db.flush()
        if state is not None and (
            state.warning_calls != self.settings.chat_web_search_monthly_warning_calls
            or state.hard_limit_calls
            != self.settings.chat_web_search_monthly_hard_calls
        ):
            state.warning_calls = self.settings.chat_web_search_monthly_warning_calls
            state.hard_limit_calls = self.settings.chat_web_search_monthly_hard_calls
        if (
            state is not None
            and state.call_count >= state.hard_limit_calls
            and state.circuit_state != "tripped"
        ):
            state.circuit_state = "tripped"
            state.trip_reason = "monthly_budget"
            state.updated_at = _now()
            self._event(state, "budget_tripped", details={"calls": state.call_count})
        return state

    def _event(
        self,
        state: ChatWebSearchBudgetState,
        event_type: str,
        *,
        error_class: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        self.db.add(
            ChatWebSearchCircuitEvent(
                id=uuid.uuid4(),
                budget_state_id=state.id,
                event_type=event_type,
                error_class=error_class,
                details=details or {},
            )
        )

    def _refresh_cooldown(self, state: ChatWebSearchBudgetState) -> None:
        cooldown_until = _aware(state.cooldown_until)
        if (
            state.circuit_state == "cooldown"
            and cooldown_until
            and cooldown_until <= _now()
        ):
            state.circuit_state = (
                "warning" if state.call_count >= state.warning_calls else "armed"
            )
            state.trip_reason = None
            state.cooldown_until = None
            state.updated_at = _now()
            self._event(state, "cooldown_closed")

    def available(self) -> bool:
        if not self.configured():
            return False
        state = self._state(create=False)
        if state is None:
            return True
        self._refresh_cooldown(state)
        if state.call_count >= state.hard_limit_calls:
            return False
        return state.circuit_state not in {"cooldown", "tripped"}

    def reserve_attempt(self, owner_hash: str) -> int:
        if not self.configured():
            raise WebSearchUnavailable("not_configured")
        state = self._state(create=True, lock=True)
        assert state is not None
        self._refresh_cooldown(state)
        if state.circuit_state in {"cooldown", "tripped"}:
            raise WebSearchUnavailable(state.trip_reason or state.circuit_state)
        if state.call_count >= state.hard_limit_calls:
            if state.circuit_state != "tripped":
                state.circuit_state = "tripped"
                state.trip_reason = "monthly_budget"
                self._event(
                    state, "budget_tripped", details={"calls": state.call_count}
                )
            raise WebSearchUnavailable("monthly_budget")
        state.call_count += 1
        state.updated_at = _now()
        if state.call_count >= state.hard_limit_calls:
            state.circuit_state = "tripped"
            state.trip_reason = "monthly_budget"
            self._event(state, "budget_tripped", details={"calls": state.call_count})
        elif state.call_count >= state.warning_calls and state.circuit_state == "armed":
            state.circuit_state = "warning"
            self._event(state, "budget_warning", details={"calls": state.call_count})
        cycle, _end = _cycle(_now())
        owner = self.db.get(
            ChatWebSearchOwnerUsage,
            {
                "environment": self.settings.environment,
                "billing_cycle": cycle,
                "owner_hash": owner_hash,
            },
        )
        if owner is None:
            owner = ChatWebSearchOwnerUsage(
                environment=self.settings.environment,
                billing_cycle=cycle,
                owner_hash=owner_hash,
                call_count=1,
            )
            self.db.add(owner)
        else:
            owner.call_count += 1
        owner.updated_at = _now()
        self.db.flush()
        return state.call_count

    def record_success(
        self, *, latency_ms: int, result_count: int, cost_microusd: int
    ) -> None:
        state = self._state(create=True, lock=True)
        assert state is not None
        state.success_count += 1
        state.provider_cost_microusd += cost_microusd
        state.last_latency_ms = latency_ms
        state.last_result_count = result_count
        state.last_provider_error_class = None
        state.updated_at = _now()

    def record_failure(self, failure: ProviderFailure, *, latency_ms: int) -> None:
        state = self._state(create=True, lock=True)
        assert state is not None
        state.failure_count += 1
        state.last_latency_ms = latency_ms
        state.last_result_count = None
        state.last_provider_error_class = failure.error_class
        state.updated_at = _now()
        if failure.opens_budget or failure.opens_auth:
            state.circuit_state = "tripped"
            state.trip_reason = (
                "provider_budget" if failure.opens_budget else "provider_auth"
            )
            state.cooldown_until = None
            self._event(
                state,
                "provider_circuit_tripped",
                error_class=failure.error_class,
            )
        elif failure.retryable:
            state.circuit_state = "cooldown"
            state.trip_reason = "transient_provider_failure"
            state.cooldown_until = _now() + timedelta(
                seconds=self.settings.chat_web_search_transient_cooldown_seconds
            )
            self._event(
                state,
                "transient_cooldown_opened",
                error_class=failure.error_class,
            )

    def status(self) -> dict[str, Any]:
        now = _now()
        cycle, end = _cycle(now)
        state = self._state(create=True, lock=True)
        assert state is not None
        self._refresh_cooldown(state)
        events = list(
            self.db.execute(
                select(ChatWebSearchCircuitEvent)
                .where(ChatWebSearchCircuitEvent.budget_state_id == state.id)
                .order_by(ChatWebSearchCircuitEvent.created_at.desc())
                .limit(20)
            ).scalars()
        )
        return {
            "environment": self.settings.environment,
            "billing_cycle": cycle.isoformat(),
            "cycle_end_at": end,
            "available": self.configured()
            and state.call_count < state.hard_limit_calls
            and state.circuit_state not in {"cooldown", "tripped"},
            "warning_calls": state.warning_calls,
            "hard_limit_calls": state.hard_limit_calls,
            "call_count": state.call_count,
            "remaining_calls": max(0, state.hard_limit_calls - state.call_count),
            "success_count": state.success_count,
            "failure_count": state.failure_count,
            "provider_cost_microusd": state.provider_cost_microusd,
            "last_latency_ms": state.last_latency_ms,
            "last_result_count": state.last_result_count,
            "circuit_state": state.circuit_state,
            "trip_reason": state.trip_reason,
            "cooldown_until": state.cooldown_until,
            "last_provider_error_class": state.last_provider_error_class,
            "events": [
                {
                    "id": str(event.id),
                    "type": event.event_type,
                    "error_class": event.error_class,
                    "created_at": event.created_at,
                    "details": event.details or {},
                }
                for event in events
            ],
        }


def web_search_available(settings: Settings) -> bool:
    try:
        with db_manager.session_local() as db:
            available = ChatWebSearchBudgetService(db, settings).available()
            db.commit()
            return available
    except Exception as error:
        logger.warning(
            "web search availability check failed error=%s", type(error).__name__
        )
        return False


def _provider_failure(response: httpx.Response) -> ProviderFailure:
    status = response.status_code
    retry_after: float | None = None
    try:
        retry_after = max(0.0, float(response.headers.get("Retry-After", "")))
    except ValueError:
        pass
    if status == 402:
        return ProviderFailure("payment_required", False, opens_budget=True)
    if status in {401, 403}:
        return ProviderFailure("authentication", False, opens_auth=True)
    if status == 429:
        return ProviderFailure("rate_limit", True, retry_after=retry_after)
    if 500 <= status <= 599:
        return ProviderFailure("server_error", True, retry_after=retry_after)
    return ProviderFailure("invalid_request", False)


async def _dispatch_exa(
    query: str, settings: Settings, timeout: float
) -> httpx.Response:
    payload: dict[str, Any] = {
        "query": query,
        "type": "fast",
        "numResults": settings.chat_web_search_result_count,
        "contents": {
            "highlights": {"maxCharacters": 4_000},
            "maxAgeHours": -1,
        },
    }
    if denylist := [
        item.strip()
        for item in settings.chat_web_search_domain_denylist.split(",")
        if item.strip()
    ]:
        payload["excludeDomains"] = denylist
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        return await client.post(
            settings.chat_web_search_exa_url,
            headers={
                "x-api-key": settings.chat_web_search_exa_api_key,
                "Content-Type": "application/json",
            },
            json=payload,
        )


def _cost_microusd(raw: dict[str, Any]) -> int:
    cost = raw.get("costDollars")
    value = cost.get("total") if isinstance(cost, dict) else cost
    try:
        dollars = float(value)
    except (TypeError, ValueError):
        return 0
    if not 0 <= dollars <= 100:
        return 0
    return round(dollars * 1_000_000)


async def search_web(
    query: str, settings: Settings, *, owner_hash: str
) -> dict[str, Any]:
    query = query.strip()
    if not query or len(query) > settings.chat_web_search_query_max_chars:
        raise WebSearchValidationError(
            f"query must contain between 1 and {settings.chat_web_search_query_max_chars} characters"
        )
    started = time.monotonic()
    deadline = started + settings.chat_web_search_timeout_seconds
    last_failure: ProviderFailure | None = None
    attempts = 0
    while attempts < 2:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            last_failure = ProviderFailure("timeout", True)
            break
        with db_manager.session_local() as budget_db:
            ChatWebSearchBudgetService(budget_db, settings).reserve_attempt(owner_hash)
            budget_db.commit()
        attempts += 1
        try:
            async with asyncio.timeout(remaining):
                response = await _dispatch_exa(query, settings, remaining)
        except (TimeoutError, httpx.TransportError):
            last_failure = ProviderFailure("timeout", True)
        else:
            if response.status_code == 200:
                try:
                    raw_payload = response.json()
                    payload = normalize_exa_payload(raw_payload, settings)
                except (ValueError, json.JSONDecodeError):
                    last_failure = ProviderFailure("malformed_response", False)
                except WebSearchError as error:
                    last_failure = ProviderFailure(error.error_class, False)
                else:
                    payload["took_ms"] = round((time.monotonic() - started) * 1_000)
                    payload = _bound_payload(
                        payload, settings.chat_web_search_max_result_bytes
                    )
                    with db_manager.session_local() as budget_db:
                        ChatWebSearchBudgetService(budget_db, settings).record_success(
                            latency_ms=payload["took_ms"],
                            result_count=len(payload["results"]),
                            cost_microusd=_cost_microusd(raw_payload),
                        )
                        budget_db.commit()
                    logger.info(
                        "web search completed provider=exa attempts=%s results=%s latency_ms=%s",
                        attempts,
                        len(payload["results"]),
                        payload["took_ms"],
                    )
                    return payload
            else:
                last_failure = _provider_failure(response)
        assert last_failure is not None
        if not last_failure.retryable or attempts >= 2:
            break
        delay = min(last_failure.retry_after or 0.15, 1.0)
        if time.monotonic() + delay >= deadline:
            break
        await asyncio.sleep(delay)
    failure = last_failure or ProviderFailure("unavailable", True)
    with db_manager.session_local() as budget_db:
        ChatWebSearchBudgetService(budget_db, settings).record_failure(
            failure,
            latency_ms=round((time.monotonic() - started) * 1_000),
        )
        budget_db.commit()
    logger.warning(
        "web search failed provider=exa attempts=%s error_class=%s latency_ms=%s",
        attempts,
        failure.error_class,
        round((time.monotonic() - started) * 1_000),
    )
    raise WebSearchUnavailable(failure.error_class)


class WebSearchTurnGateway:
    """Request-local ceiling and failure latch shared by both execution paths."""

    def __init__(self, settings: Settings, owner_hash: str):
        self.settings = settings
        self.owner_hash = owner_hash
        self.calls = 0
        self.failed = False

    async def search(self, query: str) -> dict[str, Any]:
        if self.failed or self.calls >= self.settings.chat_web_search_max_calls:
            raise WebSearchUnavailable("turn_limit")
        self.calls += 1
        try:
            return await search_web(query, self.settings, owner_hash=self.owner_hash)
        except WebSearchUnavailable:
            self.failed = True
            raise
