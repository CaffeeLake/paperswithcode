"""Detached ownership and durable replay for research-chat turn streams."""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.database import ChatMessageRecord, ChatSession
from backend.services.chat_edit_service import PREPARING_STATUS, ChatEditService
from backend.services.chat_stream_service import ChatStreamFrame
from backend.services.chat_turn_event_repository import (
    JournalFrame,
    JournalLimitExceeded,
    TurnEventJournal,
    UnsequencedJournalEvent,
)
from backend.services.chat_turn_job_repository import (
    TERMINAL_STATES,
    ChatTurnJobRepository,
    ExpiryProjectionMismatch,
    StaleTurnClaim,
    TurnLeaseClaim,
    classify_expired_turn,
)

_T = TypeVar("_T")
_FAILURE_CODE = re.compile(r"^[a-z0-9][a-z0-9_]{0,63}$")

Transaction = Callable[[Callable[[Session], _T]], Awaitable[_T]]
TerminalPersistence = Callable[[TurnLeaseClaim, str, str | None], Awaitable[None]]
LifecycleObserver = Callable[[str, str | None, int], None]
logger = logging.getLogger(__name__)


class ExpiredDetachedTurnReconciler:
    """Terminalize bounded expired owners without replaying model or tool work."""

    def __init__(
        self,
        *,
        transaction: Transaction,
        jobs: ChatTurnJobRepository | None = None,
        journal: TurnEventJournal | None = None,
        observe: LifecycleObserver | None = None,
    ) -> None:
        self._transaction = transaction
        self._jobs = jobs or ChatTurnJobRepository()
        self._journal = journal or TurnEventJournal(jobs=self._jobs)
        self._observe = observe or (lambda _event, _code, _value: None)

    async def reconcile(self, *, now: datetime, limit: int) -> dict[str, int]:
        if now.tzinfo is None or limit <= 0 or limit > 100:
            raise ValueError("Expired detached reconciliation bound is invalid")

        def terminalize_expired_turns(
            db: Session,
        ) -> tuple[tuple[uuid.UUID, str], ...]:
            outcomes: list[tuple[uuid.UUID, str]] = []
            edits = ChatEditService(db)
            for job in self._jobs.load_expired_for_reconciliation(
                db, now=now, limit=limit
            ):
                claim = self._jobs.claim_for(job)
                session = db.execute(
                    select(ChatSession)
                    .where(ChatSession.id == job.chat_session_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                ).scalar_one_or_none()
                message = db.execute(
                    select(ChatMessageRecord)
                    .where(
                        ChatMessageRecord.session_id == job.chat_session_id,
                        ChatMessageRecord.turn_id == job.turn_id,
                        ChatMessageRecord.role == "user",
                    )
                    .with_for_update()
                    .execution_options(populate_existing=True)
                ).scalar_one_or_none()
                if (
                    session is None
                    or message is None
                    or session.hf_user_id != job.hf_user_id
                    or session.active_turn_id != job.turn_id
                    or message.status not in {"generating", PREPARING_STATUS}
                ):
                    raise ExpiryProjectionMismatch(
                        "Expired detached turn projection mismatches"
                    )
                failure_code = classify_expired_turn(job)
                self._jobs.interrupt_expired_claim(
                    db,
                    claim=claim,
                    failure_code=failure_code,
                    now=now,
                )
                if message.status == PREPARING_STATUS:
                    edits.expire_preparation(session, message)
                message.status = "interrupted"
                message.error_code = failure_code
                session.active_turn_id = None
                session.active_turn_expires_at = None
                session.updated_at = now
                outcomes.append((job.turn_id, failure_code))
            return tuple(outcomes)

        outcomes = await self._transaction(terminalize_expired_turns)
        counts: dict[str, int] = {}
        for _turn_id, code in outcomes:
            counts[code] = counts.get(code, 0) + 1
        for code, count in counts.items():
            self._observe("typed_failure", code, count)
        if outcomes:
            turn_ids = tuple(turn_id for turn_id, _code in outcomes)

            def cleanup_terminal_journal(db: Session) -> int:
                return sum(
                    self._journal.delete_terminal(db, turn_id=turn_id)
                    for turn_id in turn_ids
                )

            deleted = await self._transaction(cleanup_terminal_journal)
            self._observe("journal_cleanup", None, deleted)
        return counts


@dataclass(frozen=True, slots=True)
class DetachedTurn:
    turn_id: uuid.UUID
    claim: TurnLeaseClaim

    def __post_init__(self) -> None:
        if self.turn_id != self.claim.turn_id:
            raise ValueError("Detached turn does not match its claim")


@dataclass(slots=True)
class DetachedTurnHandle:
    turn: DetachedTurn
    source: AsyncIterator[ChatStreamFrame]
    source_task: asyncio.Task[None] = field(init=False)

    @property
    def claim(self) -> TurnLeaseClaim:
        return self.turn.claim


@dataclass(slots=True)
class _TurnNotificationState:
    condition: asyncio.Condition = field(default_factory=asyncio.Condition)
    producer_owned: bool = False
    subscriber_count: int = 0


class DetachedTurnCoordinator:
    """Own each local source once while serving every subscriber from the journal."""

    TOMBSTONE_REVALIDATION_BATCH = 100

    def __init__(
        self,
        *,
        transaction: Transaction,
        persist_terminal: TerminalPersistence,
        journal: TurnEventJournal | None = None,
        jobs: ChatTurnJobRepository | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        poll_seconds: float = 0.25,
        observe: LifecycleObserver | None = None,
    ) -> None:
        if poll_seconds <= 0:
            raise ValueError("Detached turn poll interval must be positive")
        self._transaction = transaction
        self._persist_terminal = persist_terminal
        self._jobs = jobs or ChatTurnJobRepository()
        self._journal = journal or TurnEventJournal(jobs=self._jobs)
        self._clock = clock
        self._poll_seconds = poll_seconds
        self._observe = observe or (lambda _event, _code, _value: None)
        self._handles: dict[uuid.UUID, DetachedTurnHandle] = {}
        self._notifications: dict[uuid.UUID, _TurnNotificationState] = {}
        self._ambiguous_turns: dict[uuid.UUID, TurnLeaseClaim] = {}
        self._cleanup_tasks: set[asyncio.Task[None]] = set()
        self._tombstone_reaper: asyncio.Task[None] | None = None
        self._start_lock = asyncio.Lock()

    @property
    def active_turn_count(self) -> int:
        return len(self._handles)

    @property
    def condition_count(self) -> int:
        return len(self._notifications)

    @property
    def notification_state_count(self) -> int:
        return len(self._notifications)

    @property
    def ambiguous_turn_count(self) -> int:
        return len(self._ambiguous_turns)

    async def start(
        self,
        *,
        turn: DetachedTurn,
        source: AsyncIterator[ChatStreamFrame],
    ) -> DetachedTurnHandle:
        async with self._start_lock:
            now = self._clock()
            ambiguous_claim = self._ambiguous_turns.get(turn.turn_id)
            if ambiguous_claim is not None:
                try:
                    claim_is_live = await self._transaction(
                        lambda db: self._claim_is_live(
                            db, claim=ambiguous_claim, now=now
                        )
                    )
                except Exception as error:
                    await self._close_source(source)
                    raise StaleTurnClaim(
                        "Detached turn outcome remains ambiguous"
                    ) from error
                if not claim_is_live:
                    self._drop_tombstone(turn.turn_id, ambiguous_claim)
                await self._close_source(source)
                raise StaleTurnClaim("Detached turn outcome is ambiguous")
            existing = self._handles.get(turn.turn_id)
            if existing is not None:
                await self._close_source(source)
                raise RuntimeError("Detached turn already has a local source")
            try:
                await self._transaction(
                    lambda db: self._jobs.require_live_claim(
                        db, claim=turn.claim, now=now
                    )
                )
            except BaseException:
                await self._close_source(source)
                raise
            self._acquire_producer(turn.turn_id)
            handle = DetachedTurnHandle(
                turn=turn,
                source=source,
            )
            self._handles[turn.turn_id] = handle
            self._observe("turn_state", "running", 1)
            handle.source_task = asyncio.create_task(self._pump(handle))
            return handle

    async def subscribe(
        self, *, turn_id: uuid.UUID, after_sequence: int
    ) -> AsyncIterator[JournalFrame]:
        if after_sequence < 0:
            raise ValueError("Journal replay cursor is invalid")
        notification = self._acquire_subscriber(turn_id)
        cursor = after_sequence
        try:
            while True:
                frames, terminal = await self._transaction(
                    lambda db: self._read(db, turn_id=turn_id, after_sequence=cursor)
                )
                for frame in frames:
                    cursor = frame.sequence
                    yield frame
                if terminal:
                    return
                async with notification.condition:
                    try:
                        await asyncio.wait_for(
                            notification.condition.wait(), timeout=self._poll_seconds
                        )
                    except TimeoutError:
                        pass
        finally:
            self._release_subscriber(turn_id, notification)

    async def interrupt_dispatch_failed(
        self,
        turn_id: uuid.UUID,
        *,
        worker_id: str,
        worker_generation: int,
        lease_seconds: int,
        admitted_before: datetime,
    ) -> bool:
        """Finish an admitted turn that failed before any worker lease existed."""
        job = await self._transaction(
            lambda db: self._jobs.interrupt_dispatch_failed(
                db,
                turn_id=turn_id,
                worker_id=worker_id,
                worker_generation=worker_generation,
                lease_seconds=lease_seconds,
                admitted_before=admitted_before,
                now=self._clock(),
            )
        )
        if job is not None:
            await self._publish(turn_id)
        return job is not None

    async def _pump(self, handle: DetachedTurnHandle) -> None:
        terminal_seen = False
        terminal_durable = False
        try:
            while True:
                try:
                    event = await anext(handle.source)
                except StopAsyncIteration:
                    break
                except Exception:
                    await self._fail_source(handle, "turn_failed")
                    terminal_seen = True
                    terminal_durable = True
                    break
                if event.event is None:
                    continue
                try:
                    frames = await self._transaction(
                        lambda db: self._journal.append(
                            db,
                            claim=handle.claim,
                            events=(
                                UnsequencedJournalEvent(
                                    event=event.event, payload=event.payload
                                ),
                            ),
                            now=self._clock(),
                        )
                    )
                except JournalLimitExceeded:
                    await self._persist_terminal_durably(
                        handle.claim, "failed", "event_journal_exhausted"
                    )
                    terminal_seen = True
                    terminal_durable = True
                    break
                self._observe("journal_events", None, len(frames))
                self._observe(
                    "journal_bytes",
                    None,
                    sum(len(self._journal._frame_bytes(frame)) for frame in frames),
                )
                terminal = self._terminal_for(event)
                if terminal is not None:
                    self._observe("turn_state", terminal[0], 1)
                    await self._persist_terminal_durably(handle.claim, *terminal)
                    terminal_seen = True
                    terminal_durable = True
                await self._publish(handle.turn.turn_id, frames)
                if terminal_seen:
                    break
            if not terminal_seen:
                await self._fail_source(handle, "turn_failed")
                terminal_durable = True
        finally:
            try:
                await self._publish(handle.turn.turn_id)
            finally:
                try:
                    await self._close_source(handle.source)
                finally:
                    if not terminal_durable:
                        try:
                            terminal_durable = await self._transaction(
                                lambda db: self._terminal_claim_is_durable(
                                    db, claim=handle.claim
                                )
                            )
                        except Exception:
                            terminal_durable = False
                    if terminal_durable:
                        self._evict_handle(handle)
                    else:
                        self._retain_ambiguous(handle)

    async def _fail_source(self, handle: DetachedTurnHandle, code: str) -> None:
        try:
            frames = await self._transaction(
                lambda db: self._journal.append(
                    db,
                    claim=handle.claim,
                    events=(
                        UnsequencedJournalEvent(
                            event="error",
                            payload={
                                "message": "The response could not be completed.",
                                "code": code,
                            },
                        ),
                    ),
                    now=self._clock(),
                )
            )
        except JournalLimitExceeded:
            code = "event_journal_exhausted"
            frames = ()
        await self._persist_terminal_durably(handle.claim, "failed", code)
        await self._publish(handle.turn.turn_id, frames)

    async def _persist_terminal_durably(
        self, claim: TurnLeaseClaim, state: str, failure_code: str | None
    ) -> None:
        await self._persist_terminal(claim, state, failure_code)
        confirmed = await self._transaction(
            lambda db: self._terminal_matches(
                db,
                claim=claim,
                state=state,
                failure_code=failure_code,
            )
        )
        if not confirmed:
            raise RuntimeError("Terminal persistence was not durable")

        def cleanup_terminal_journal(db: Session) -> int:
            return self._cleanup_terminal_journal(db, claim.turn_id)

        async def cleanup_after_replay_window() -> None:
            await asyncio.sleep(self._poll_seconds * 2)
            deleted = await self._transaction(cleanup_terminal_journal)
            self._observe("journal_cleanup", None, deleted)

        cleanup = asyncio.create_task(cleanup_after_replay_window())
        self._cleanup_tasks.add(cleanup)
        cleanup.add_done_callback(self._finish_cleanup)

    def _cleanup_terminal_journal(self, db: Session, turn_id: uuid.UUID) -> int:
        return self._journal.delete_terminal(db, turn_id=turn_id)

    def _finish_cleanup(self, task: asyncio.Task[None]) -> None:
        self._cleanup_tasks.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            logger.warning(
                "detached terminal journal cleanup failed error=%s",
                type(error).__name__,
            )

    def _evict_handle(self, handle: DetachedTurnHandle) -> None:
        turn_id = handle.turn.turn_id
        if self._handles.get(turn_id) is handle:
            self._handles.pop(turn_id, None)
            self._release_producer(turn_id)

    def _retain_ambiguous(self, handle: DetachedTurnHandle) -> None:
        self._evict_handle(handle)
        turn_id = handle.turn.turn_id
        self._ambiguous_turns[turn_id] = handle.claim
        self._ensure_tombstone_reaper()

    def _ensure_tombstone_reaper(self) -> None:
        if self._tombstone_reaper is None or self._tombstone_reaper.done():
            self._tombstone_reaper = asyncio.create_task(self._reap_tombstones())

    async def _reap_tombstones(self) -> None:
        try:
            while self._ambiguous_turns:
                await asyncio.sleep(self._poll_seconds)
                snapshot = tuple(self._ambiguous_turns.items())[
                    : self.TOMBSTONE_REVALIDATION_BATCH
                ]
                for turn_id, claim in snapshot:
                    try:
                        claim_is_live = await self._transaction(
                            lambda db, claim=claim: self._claim_is_live(
                                db, claim=claim, now=self._clock()
                            )
                        )
                    except Exception:
                        self._rotate_tombstone(turn_id, claim)
                        continue
                    if not claim_is_live:
                        self._drop_tombstone(turn_id, claim)
                    else:
                        self._rotate_tombstone(turn_id, claim)
        finally:
            self._tombstone_reaper = None

    def _drop_tombstone(self, turn_id: uuid.UUID, expected: TurnLeaseClaim) -> None:
        if self._ambiguous_turns.get(turn_id) == expected:
            self._ambiguous_turns.pop(turn_id, None)

    def _rotate_tombstone(self, turn_id: uuid.UUID, expected: TurnLeaseClaim) -> None:
        if self._ambiguous_turns.get(turn_id) == expected:
            self._ambiguous_turns.pop(turn_id, None)
            self._ambiguous_turns[turn_id] = expected

    def _terminal_matches(
        self,
        db: Session,
        *,
        claim: TurnLeaseClaim,
        state: str,
        failure_code: str | None,
    ) -> bool:
        job = self._jobs.load_by_turn(db, claim.turn_id)
        return (
            job is not None
            and job.state == state
            and job.failure_code == failure_code
            and self._jobs.claim_for(job) == claim
        )

    def _terminal_claim_is_durable(self, db: Session, *, claim: TurnLeaseClaim) -> bool:
        job = self._jobs.load_by_turn(db, claim.turn_id)
        return (
            job is not None
            and job.state in TERMINAL_STATES
            and self._jobs.claim_for(job) == claim
        )

    def _claim_is_live(
        self, db: Session, *, claim: TurnLeaseClaim, now: datetime
    ) -> bool:
        try:
            self._jobs.require_live_claim(db, claim=claim, now=now)
        except StaleTurnClaim:
            return False
        return True

    def _read(
        self, db: Session, *, turn_id: uuid.UUID, after_sequence: int
    ) -> tuple[Sequence[JournalFrame], bool]:
        frames = self._journal.read_after(
            db,
            turn_id=turn_id,
            after_sequence=after_sequence,
            limit=self._journal.MAX_TURN_EVENTS,
        )
        job = self._jobs.load_by_turn(db, turn_id)
        return frames, job is None or job.state in TERMINAL_STATES

    def _acquire_producer(self, turn_id: uuid.UUID) -> None:
        notification = self._notifications.setdefault(turn_id, _TurnNotificationState())
        if notification.producer_owned:
            raise RuntimeError("Detached turn already owns notification state")
        notification.producer_owned = True

    def _release_producer(self, turn_id: uuid.UUID) -> None:
        notification = self._notifications.get(turn_id)
        if notification is None or not notification.producer_owned:
            raise RuntimeError("Detached turn does not own notification state")
        notification.producer_owned = False
        self._drop_unused_notification(turn_id, notification)

    def _acquire_subscriber(self, turn_id: uuid.UUID) -> _TurnNotificationState:
        notification = self._notifications.setdefault(turn_id, _TurnNotificationState())
        notification.subscriber_count += 1
        return notification

    def _release_subscriber(
        self, turn_id: uuid.UUID, notification: _TurnNotificationState
    ) -> None:
        if self._notifications.get(turn_id) is not notification:
            raise RuntimeError("Detached turn notification state was replaced")
        if notification.subscriber_count <= 0:
            raise RuntimeError("Detached turn has no active subscriber")
        notification.subscriber_count -= 1
        self._drop_unused_notification(turn_id, notification)

    def _drop_unused_notification(
        self, turn_id: uuid.UUID, notification: _TurnNotificationState
    ) -> None:
        if not notification.producer_owned and notification.subscriber_count == 0:
            if self._notifications.get(turn_id) is notification:
                self._notifications.pop(turn_id)

    async def _publish(
        self, turn_id: uuid.UUID, _frames: Sequence[JournalFrame] = ()
    ) -> None:
        notification = self._notifications.get(turn_id)
        if notification is None:
            return
        async with notification.condition:
            notification.condition.notify_all()

    @staticmethod
    async def _close_source(source: AsyncIterator[ChatStreamFrame]) -> None:
        close = getattr(source, "aclose", None)
        if close is not None:
            await close()

    @staticmethod
    def _terminal_for(frame: ChatStreamFrame) -> tuple[str, str | None] | None:
        if frame.event == "done":
            if frame.payload.get("finish_reason") == "stopped":
                return "interrupted", "cancelled"
            return "completed", None
        if frame.event != "error":
            return None
        code = str(frame.payload.get("code") or "turn_failed")
        if _FAILURE_CODE.fullmatch(code) is None:
            code = "turn_failed"
        return "failed", code
