"""Durable delivery of sandbox spend-circuit alerts."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import (
    ChatSandboxBudgetState,
    ChatSandboxCircuitEvent,
)

logger = logging.getLogger(__name__)

ALERT_BATCH_SIZE = 10
DELIVERY_ATTEMPT_LIMIT = 5
DELIVERY_LEASE_SECONDS = 30
WEBHOOK_TIMEOUT_SECONDS = 5

SessionFactory = Callable[[], Session]
UtcClock = Callable[[], datetime]


class SpendAlertWebhookPoster(Protocol):
    """Typed boundary for posting one alert payload."""

    async def post_json(
        self,
        url: str,
        payload: Mapping[str, str],
        *,
        timeout_seconds: float,
    ) -> None: ...


class HttpxSpendAlertWebhookPoster:
    """Post spend alerts with a short, per-request HTTP client."""

    async def post_json(
        self,
        url: str,
        payload: Mapping[str, str],
        *,
        timeout_seconds: float,
    ) -> None:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()


class SpendAlertChannel(StrEnum):
    PRIMARY = "primary"
    FALLBACK = "fallback"


@dataclass(frozen=True)
class SpendAlertDeliveryClaim:
    """Exact delivery generation that may finalize an event."""

    event_id: uuid.UUID
    channel: SpendAlertChannel
    attempt: int
    lease_expires_at: datetime
    environment: str
    payload: dict[str, str]


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class ChatSandboxSpendAlertDispatcher:
    """Claim, post, and exactly finalize bounded spend-alert batches."""

    def __init__(
        self,
        settings: Settings,
        *,
        session_factory: SessionFactory,
        webhook_poster: SpendAlertWebhookPoster | None = None,
        utcnow: UtcClock | None = None,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.webhook_poster = webhook_poster or HttpxSpendAlertWebhookPoster()
        self.utcnow = utcnow or (lambda: datetime.now(UTC))

    async def deliver_pending(self) -> int:
        """Deliver primary alerts, then eligible fallbacks, oldest first."""

        primary_url = self.settings.chat_sandbox_slack_webhook_url
        if not primary_url:
            return 0

        delivered = await self._deliver_batch(
            SpendAlertChannel.PRIMARY,
            primary_url,
        )
        await self._deliver_batch(
            SpendAlertChannel.FALLBACK,
            self.settings.chat_sandbox_alert_fallback_webhook_url,
        )
        return delivered

    async def _deliver_batch(
        self,
        channel: SpendAlertChannel,
        url: str,
    ) -> int:
        event_ids = self._candidate_ids(channel)
        delivered = 0
        for event_id in event_ids:
            claim = self._claim(event_id, channel)
            if claim is None:
                continue
            try:
                await self.webhook_poster.post_json(
                    url,
                    claim.payload,
                    timeout_seconds=WEBHOOK_TIMEOUT_SECONDS,
                )
            except Exception as error:
                if channel is SpendAlertChannel.PRIMARY:
                    logger.critical(
                        "chat spend alert delivery failed event_id=%s error=%s",
                        event_id,
                        type(error).__name__,
                    )
                else:
                    logger.critical(
                        "chat spend fallback alert delivery failed "
                        "event_id=%s error=%s",
                        event_id,
                        type(error).__name__,
                    )
                self._finalize_failure(claim)
                continue
            if self._finalize_success(claim):
                delivered += 1
        return delivered

    def _candidate_ids(self, channel: SpendAlertChannel) -> list[uuid.UUID]:
        now = _as_utc(self.utcnow())
        statement = (
            select(ChatSandboxCircuitEvent.id)
            .join(
                ChatSandboxBudgetState,
                ChatSandboxBudgetState.id == ChatSandboxCircuitEvent.budget_state_id,
            )
            .where(ChatSandboxBudgetState.environment == self.settings.environment)
        )
        if channel is SpendAlertChannel.PRIMARY:
            statement = statement.where(
                ChatSandboxCircuitEvent.delivery_state.in_(
                    ["pending", "retry", "delivering"]
                ),
                ChatSandboxCircuitEvent.delivery_attempts < DELIVERY_ATTEMPT_LIMIT,
                (
                    ChatSandboxCircuitEvent.next_delivery_attempt_at.is_(None)
                    | (ChatSandboxCircuitEvent.next_delivery_attempt_at <= now)
                ),
            )
        else:
            statement = statement.where(
                ChatSandboxCircuitEvent.delivery_state == "failed",
                ChatSandboxCircuitEvent.fallback_delivery_state.in_(
                    ["pending", "retry", "delivering"]
                ),
                ChatSandboxCircuitEvent.fallback_delivery_attempts
                < DELIVERY_ATTEMPT_LIMIT,
                (
                    ChatSandboxCircuitEvent.fallback_next_delivery_attempt_at.is_(None)
                    | (ChatSandboxCircuitEvent.fallback_next_delivery_attempt_at <= now)
                ),
            )
        with self.session_factory() as db:
            return list(
                db.execute(
                    statement.order_by(ChatSandboxCircuitEvent.created_at).limit(
                        ALERT_BATCH_SIZE
                    )
                ).scalars()
            )

    def _claim(
        self,
        event_id: uuid.UUID,
        channel: SpendAlertChannel,
    ) -> SpendAlertDeliveryClaim | None:
        with self.session_factory() as db, db.begin():
            event = self._load_event(db, event_id)
            now = _as_utc(self.utcnow())
            if event is None or not self._eligible(event, channel, now):
                return None
            lease_expires_at = now + timedelta(seconds=DELIVERY_LEASE_SECONDS)
            if channel is SpendAlertChannel.PRIMARY:
                event.delivery_attempts += 1
                event.delivery_state = "delivering"
                event.next_delivery_attempt_at = lease_expires_at
                attempt = event.delivery_attempts
                payload = self._primary_payload(event)
            else:
                event.fallback_delivery_attempts += 1
                event.fallback_delivery_state = "delivering"
                event.fallback_next_delivery_attempt_at = lease_expires_at
                attempt = event.fallback_delivery_attempts
                payload = self._fallback_payload(event)
            return SpendAlertDeliveryClaim(
                event_id=event.id,
                channel=channel,
                attempt=attempt,
                lease_expires_at=lease_expires_at,
                environment=self.settings.environment,
                payload=payload,
            )

    def _finalize_success(self, claim: SpendAlertDeliveryClaim) -> bool:
        with self.session_factory() as db, db.begin():
            event = self._load_event(db, claim.event_id, environment=claim.environment)
            if event is None or not self._matches_claim(event, claim):
                return False
            now = _as_utc(self.utcnow())
            if claim.channel is SpendAlertChannel.PRIMARY:
                event.delivery_state = "delivered"
                event.next_delivery_attempt_at = None
                event.delivered_at = now
            else:
                event.fallback_delivery_state = "delivered"
                event.fallback_next_delivery_attempt_at = None
                event.fallback_delivered_at = now
            return True

    def _finalize_failure(self, claim: SpendAlertDeliveryClaim) -> bool:
        with self.session_factory() as db, db.begin():
            event = self._load_event(db, claim.event_id, environment=claim.environment)
            if event is None or not self._matches_claim(event, claim):
                return False
            next_attempt_at = _as_utc(self.utcnow()) + timedelta(
                seconds=min(300, 15 * (2**claim.attempt))
            )
            if claim.channel is SpendAlertChannel.PRIMARY:
                event.delivery_state = (
                    "failed" if claim.attempt >= DELIVERY_ATTEMPT_LIMIT else "retry"
                )
                event.next_delivery_attempt_at = next_attempt_at
            else:
                event.fallback_delivery_state = (
                    "failed" if claim.attempt >= DELIVERY_ATTEMPT_LIMIT else "retry"
                )
                event.fallback_next_delivery_attempt_at = next_attempt_at
            return True

    def _load_event(
        self,
        db: Session,
        event_id: uuid.UUID,
        *,
        environment: str | None = None,
    ) -> ChatSandboxCircuitEvent | None:
        return db.execute(
            select(ChatSandboxCircuitEvent)
            .join(
                ChatSandboxBudgetState,
                ChatSandboxBudgetState.id == ChatSandboxCircuitEvent.budget_state_id,
            )
            .where(
                ChatSandboxCircuitEvent.id == event_id,
                ChatSandboxBudgetState.environment
                == (self.settings.environment if environment is None else environment),
            )
            .with_for_update(of=ChatSandboxCircuitEvent)
        ).scalar_one_or_none()

    @staticmethod
    def _eligible(
        event: ChatSandboxCircuitEvent,
        channel: SpendAlertChannel,
        now: datetime,
    ) -> bool:
        if channel is SpendAlertChannel.PRIMARY:
            return (
                event.delivery_state in {"pending", "retry", "delivering"}
                and event.delivery_attempts < DELIVERY_ATTEMPT_LIMIT
                and ChatSandboxSpendAlertDispatcher._is_due(
                    event.next_delivery_attempt_at,
                    now,
                )
            )
        return (
            event.delivery_state == "failed"
            and event.fallback_delivery_state in {"pending", "retry", "delivering"}
            and event.fallback_delivery_attempts < DELIVERY_ATTEMPT_LIMIT
            and ChatSandboxSpendAlertDispatcher._is_due(
                event.fallback_next_delivery_attempt_at,
                now,
            )
        )

    @staticmethod
    def _is_due(value: datetime | None, now: datetime) -> bool:
        return value is None or _as_utc(value) <= now

    @staticmethod
    def _matches_claim(
        event: ChatSandboxCircuitEvent,
        claim: SpendAlertDeliveryClaim,
    ) -> bool:
        if claim.channel is SpendAlertChannel.PRIMARY:
            state = event.delivery_state
            attempts = event.delivery_attempts
            deadline = event.next_delivery_attempt_at
        else:
            state = event.fallback_delivery_state
            attempts = event.fallback_delivery_attempts
            deadline = event.fallback_next_delivery_attempt_at
        return (
            state == "delivering"
            and attempts == claim.attempt
            and deadline is not None
            and _as_utc(deadline) == claim.lease_expires_at
        )

    def _primary_payload(
        self,
        event: ChatSandboxCircuitEvent,
    ) -> dict[str, str]:
        details = event.details
        return {
            "text": (
                f"PwC chat compute {event.severity}: {event.event_type}; "
                f"environment={details.get('environment')}; cycle={details.get('billing_cycle')}; "
                f"release={details.get('release')}; effective_microusd={details.get('effective_microusd')}; "
                f"provider_floor_microusd={details.get('provider_floor_microusd')}; "
                f"threshold_microusd={details.get('threshold_microusd')}; "
                f"provider_reserve_microusd={details.get('remaining_provider_reserve_microusd')}; "
                f"state={details.get('circuit_state')}; live={details.get('live_count')}; "
                f"uncertain={details.get('uncertain_count')}; reconciliation_age_seconds={details.get('reconciliation_age_seconds')}; event_id={event.id}; "
                f"dashboard=/cron-dashboard; runbook={self.settings.chat_sandbox_runbook_url}"
            )
        }

    def _fallback_payload(
        self,
        event: ChatSandboxCircuitEvent,
    ) -> dict[str, str]:
        return {
            "text": (
                "PwC chat compute primary alert delivery failed; "
                f"environment={event.details.get('environment')}; "
                f"severity=critical; event_id={event.id}; "
                f"runbook={self.settings.chat_sandbox_runbook_url}"
            )
        }
