"""Detached ownership and durable replay for research-chat turn streams."""

from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TypeVar

from sqlalchemy.orm import Session

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
    TurnLeaseClaim,
)

_T = TypeVar("_T")
_FAILURE_CODE = re.compile(r"^[a-z0-9][a-z0-9_]{0,63}$")

Transaction = Callable[[Callable[[Session], _T]], Awaitable[_T]]
TerminalPersistence = Callable[[TurnLeaseClaim, str, str | None], Awaitable[None]]


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
    condition: asyncio.Condition = field(default_factory=asyncio.Condition)
    source_task: asyncio.Task[None] = field(init=False)

    @property
    def claim(self) -> TurnLeaseClaim:
        return self.turn.claim

    async def publish(self, _frames: Sequence[JournalFrame] = ()) -> None:
        async with self.condition:
            self.condition.notify_all()


class DetachedTurnCoordinator:
    """Own each local source once while serving every subscriber from the journal."""

    def __init__(
        self,
        *,
        transaction: Transaction,
        persist_terminal: TerminalPersistence,
        journal: TurnEventJournal | None = None,
        jobs: ChatTurnJobRepository | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        poll_seconds: float = 0.25,
    ) -> None:
        if poll_seconds <= 0:
            raise ValueError("Detached turn poll interval must be positive")
        self._transaction = transaction
        self._persist_terminal = persist_terminal
        self._jobs = jobs or ChatTurnJobRepository()
        self._journal = journal or TurnEventJournal(jobs=self._jobs)
        self._clock = clock
        self._poll_seconds = poll_seconds
        self._handles: dict[uuid.UUID, DetachedTurnHandle] = {}
        self._conditions: dict[uuid.UUID, asyncio.Condition] = {}
        self._start_lock = asyncio.Lock()

    async def start(
        self,
        *,
        turn: DetachedTurn,
        source: AsyncIterator[ChatStreamFrame],
    ) -> DetachedTurnHandle:
        async with self._start_lock:
            existing = self._handles.get(turn.turn_id)
            if existing is not None:
                await self._close_source(source)
                return existing
            try:
                await self._transaction(
                    lambda db: self._jobs.require_live_claim(
                        db, claim=turn.claim, now=self._clock()
                    )
                )
            except BaseException:
                await self._close_source(source)
                raise
            handle = DetachedTurnHandle(
                turn=turn,
                source=source,
                condition=self._condition(turn.turn_id),
            )
            self._handles[turn.turn_id] = handle
            handle.source_task = asyncio.create_task(self._pump(handle))
            return handle

    async def subscribe(
        self, *, turn_id: uuid.UUID, after_sequence: int
    ) -> AsyncIterator[JournalFrame]:
        if after_sequence < 0:
            raise ValueError("Journal replay cursor is invalid")
        condition = self._condition(turn_id)
        cursor = after_sequence
        while True:
            frames, terminal = await self._transaction(
                lambda db: self._read(db, turn_id=turn_id, after_sequence=cursor)
            )
            for frame in frames:
                cursor = frame.sequence
                yield frame
            if terminal:
                return
            async with condition:
                try:
                    await asyncio.wait_for(condition.wait(), timeout=self._poll_seconds)
                except TimeoutError:
                    pass

    async def interrupt_dispatch_failed(
        self,
        turn_id: uuid.UUID,
        *,
        worker_id: str,
        worker_generation: int,
        lease_seconds: int,
    ) -> bool:
        """Finish an admitted turn that failed before any worker lease existed."""
        job = await self._transaction(
            lambda db: self._jobs.interrupt_dispatch_failed(
                db,
                turn_id=turn_id,
                worker_id=worker_id,
                worker_generation=worker_generation,
                lease_seconds=lease_seconds,
                now=self._clock(),
            )
        )
        if job is not None:
            condition = self._condition(turn_id)
            async with condition:
                condition.notify_all()
        return job is not None

    async def _pump(self, handle: DetachedTurnHandle) -> None:
        terminal_seen = False
        try:
            while True:
                try:
                    event = await anext(handle.source)
                except StopAsyncIteration:
                    break
                except Exception:
                    await self._fail_source(handle, "turn_failed")
                    terminal_seen = True
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
                    await self._persist_terminal(
                        handle.claim, "failed", "event_journal_exhausted"
                    )
                    terminal_seen = True
                    break
                terminal = self._terminal_for(event)
                if terminal is not None:
                    await self._persist_terminal(handle.claim, *terminal)
                    terminal_seen = True
                await handle.publish(frames)
                if terminal_seen:
                    break
            if not terminal_seen:
                await self._fail_source(handle, "turn_failed")
        finally:
            await handle.publish()
            await self._close_source(handle.source)

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
        await self._persist_terminal(handle.claim, "failed", code)
        await handle.publish(frames)

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

    def _condition(self, turn_id: uuid.UUID) -> asyncio.Condition:
        condition = self._conditions.get(turn_id)
        if condition is None:
            condition = asyncio.Condition()
            self._conditions[turn_id] = condition
        return condition

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
