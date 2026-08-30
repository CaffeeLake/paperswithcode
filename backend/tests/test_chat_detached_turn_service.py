from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from backend.models.database import (
    ChatMessageRecord,
    ChatSession,
    ChatTurnEventChunk,
    ChatTurnJob,
)
from backend.services.chat_detached_turn_service import (
    DetachedTurn,
    DetachedTurnCoordinator,
    ExpiredDetachedTurnReconciler,
)
from backend.services.chat_live_stream_service import LiveChatStreamRegistry
from backend.services.chat_stream_service import ChatStreamFrame
from backend.services.chat_turn_event_repository import TurnEventJournal
from backend.services.chat_turn_job_repository import (
    ChatTurnJobRepository,
    StaleTurnClaim,
    TurnLeaseClaim,
)

NOW = datetime(2026, 8, 29, 12, tzinfo=UTC)


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


class Harness:
    def __init__(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:")
        ChatSession.__table__.create(engine)
        ChatMessageRecord.__table__.create(engine)
        ChatTurnJob.__table__.create(engine)
        ChatTurnEventChunk.__table__.create(engine)
        self.sessions = sessionmaker(engine, expire_on_commit=False)
        self.jobs = ChatTurnJobRepository(advisory_locker=lambda *_args: None)
        self.journal = TurnEventJournal(jobs=self.jobs)
        self.now = NOW
        self.terminal_error: Exception | None = None
        self.transaction_error: Exception | None = None
        self.transaction_calls = 0
        self.terminal_calls: list[tuple[str, str | None]] = []
        self.terminal_sequences: list[list[int]] = []
        self.turn, self.claim = self._claimed_turn()
        self.coordinator = DetachedTurnCoordinator(
            transaction=self.transaction,
            journal=self.journal,
            jobs=self.jobs,
            clock=lambda: self.now,
            persist_terminal=self.persist_terminal,
            poll_seconds=0.01,
        )

    def _claimed_turn(self) -> tuple[DetachedTurn, TurnLeaseClaim]:
        with self.sessions.begin() as db:
            session = ChatSession(
                id=uuid.uuid4(),
                hf_user_id="detached-owner",
                hf_username="detached-owner",
                selected_model="model",
            )
            db.add(session)
            job = ChatTurnJob(
                turn_id=uuid.uuid4(),
                chat_session_id=session.id,
                hf_user_id=session.hf_user_id,
                request_id=f"request-{uuid.uuid4()}",
                revision=1,
                dispatch_class="interactive",
                dispatch_route="external-pi",
                state="running",
                worker_id="worker-a",
                worker_generation=7,
                lease_generation=3,
                app_release_id="release-a",
                worker_contract_version="external-pi-v1",
                admitted_at=NOW - timedelta(seconds=2),
                dispatched_at=NOW - timedelta(seconds=2),
                started_at=NOW - timedelta(seconds=1),
                heartbeat_at=NOW,
                lease_expires_at=NOW + timedelta(seconds=30),
            )
            db.add(job)
        claim = TurnLeaseClaim(job.turn_id, "worker-a", 7, 3)
        return DetachedTurn(turn_id=job.turn_id, claim=claim), claim

    async def transaction(self, operation):
        self.transaction_calls += 1
        if self.transaction_error is not None:
            raise self.transaction_error
        with self.sessions.begin() as db:
            return operation(db)

    async def persist_terminal(
        self, claim: TurnLeaseClaim, state: str, failure_code: str | None
    ) -> None:
        self.terminal_calls.append((state, failure_code))
        self.terminal_sequences.append(
            await self.transaction(
                lambda db: [
                    frame.sequence
                    for frame in self.journal.read_after(
                        db, turn_id=claim.turn_id, after_sequence=0, limit=10
                    )
                ]
            )
        )
        if self.terminal_error is not None:
            raise self.terminal_error
        await self.transaction(
            lambda db: self.jobs.write_terminal(
                db,
                claim=claim,
                state=state,
                failure_code=failure_code,
                now=self.now,
            )
        )


def test_subscriber_cancellation_does_not_cancel_source_and_reconnect_replays() -> None:
    async def scenario() -> list[int]:
        harness = Harness()
        release = asyncio.Event()

        async def source():
            yield ChatStreamFrame("stream_start", {"request_id": "r1"})
            await release.wait()
            yield ChatStreamFrame("answer_delta", {"text": "Recovered"})
            yield ChatStreamFrame("done", {"finish_reason": "success"})

        stream = await harness.coordinator.start(turn=harness.turn, source=source())
        first = harness.coordinator.subscribe(
            turn_id=harness.turn.turn_id, after_sequence=0
        )
        assert (await anext(first)).sequence == 1
        await first.aclose()
        assert not stream.source_task.cancelled()

        release.set()
        await stream.source_task
        return [
            frame.sequence
            async for frame in harness.coordinator.subscribe(
                turn_id=harness.turn.turn_id, after_sequence=0
            )
        ]

    assert asyncio.run(scenario()) == [1, 2, 3]


def test_two_subscribers_receive_identical_ordered_frames() -> None:
    async def scenario() -> tuple[list[int], list[int]]:
        harness = Harness()

        async def source():
            yield ChatStreamFrame("stream_start")
            yield ChatStreamFrame("answer_delta", {"text": "answer"})
            yield ChatStreamFrame("done", {"finish_reason": "success"})

        stream = await harness.coordinator.start(turn=harness.turn, source=source())
        first = asyncio.create_task(
            _sequences(harness.coordinator, harness.turn.turn_id)
        )
        second = asyncio.create_task(
            _sequences(harness.coordinator, harness.turn.turn_id)
        )
        await stream.source_task
        return await first, await second

    assert asyncio.run(scenario()) == ([1, 2, 3], [1, 2, 3])


def test_terminal_event_flushes_pending_frames_in_one_transactional_chunk() -> None:
    async def scenario() -> tuple[list[tuple[int, int]], list[int]]:
        harness = Harness()

        async def source():
            yield ChatStreamFrame("stream_start")
            yield ChatStreamFrame("answer_delta", {"text": "answer"})
            yield ChatStreamFrame("done", {"finish_reason": "success"})

        stream = await harness.coordinator.start(turn=harness.turn, source=source())
        await stream.source_task
        with harness.sessions() as db:
            chunks = list(
                db.query(ChatTurnEventChunk)
                .order_by(ChatTurnEventChunk.first_sequence)
                .all()
            )
            return (
                [(chunk.first_sequence, chunk.last_sequence) for chunk in chunks],
                [len(chunk.events) for chunk in chunks],
            )

    assert asyncio.run(scenario()) == ([(1, 3)], [3])


def test_detached_boundary_records_post_start_batched_append_stale_once(
    monkeypatch,
) -> None:
    async def scenario() -> tuple[
        list[dict[str, object]], int, int, int, uuid.UUID, uuid.UUID
    ]:
        harness = Harness()
        release_second_batch = asyncio.Event()
        recorded: list[dict[str, object]] = []
        monkeypatch.setattr(
            "backend.services.chat_live_stream_service.record_qualification_event_safely",
            lambda **event: recorded.append(event) or True,
        )
        with harness.sessions() as db:
            job = harness.jobs.load_by_turn(db, harness.turn.turn_id)
            assert job is not None
            session_id = job.chat_session_id

        async def source():
            yield ChatStreamFrame("stream_start", {"request_id": "r1"})
            await release_second_batch.wait()
            yield ChatStreamFrame("answer_delta", {"text": "fenced"})
            yield ChatStreamFrame("done", {"finish_reason": "success"})

        registry = LiveChatStreamRegistry(detached_coordinator=harness.coordinator)
        stream = await registry.start_detached(
            session_id=session_id,
            owner_id="owner-1",
            turn=harness.turn,
            source=source(),
        )
        while True:
            with harness.sessions() as db:
                if db.query(ChatTurnEventChunk).count() == 1:
                    break
            await asyncio.sleep(0)
        with harness.sessions.begin() as db:
            job = harness.jobs.load_by_turn(db, harness.turn.turn_id)
            assert job is not None
            job.lease_generation += 1
        release_second_batch.set()

        with pytest.raises(StaleTurnClaim):
            await stream.source_task
        return (
            recorded,
            len(harness.terminal_calls),
            harness.coordinator.active_turn_count,
            harness.coordinator.ambiguous_turn_count,
            session_id,
            harness.turn.turn_id,
        )

    (
        recorded,
        terminal_calls,
        active_turns,
        ambiguous_turns,
        session_id,
        turn_id,
    ) = asyncio.run(scenario())
    assert recorded == [
        {
            "turn_id": turn_id,
            "chat_session_id": session_id,
            "event_type": "stale_fence",
        }
    ]
    assert terminal_calls == 0
    assert active_turns == 0
    assert ambiguous_turns == 1


def test_journal_batch_flushes_on_byte_bound_before_terminal() -> None:
    async def scenario() -> list[int]:
        harness = Harness()
        harness.coordinator = DetachedTurnCoordinator(
            transaction=harness.transaction,
            journal=harness.journal,
            jobs=harness.jobs,
            clock=lambda: harness.now,
            persist_terminal=harness.persist_terminal,
            poll_seconds=0.01,
            batch_max_bytes=180,
            batch_max_seconds=1,
        )

        async def source():
            yield ChatStreamFrame("answer_delta", {"text": "a" * 80})
            yield ChatStreamFrame("answer_delta", {"text": "b" * 80})
            yield ChatStreamFrame("done", {"finish_reason": "success"})

        stream = await harness.coordinator.start(turn=harness.turn, source=source())
        await stream.source_task
        with harness.sessions() as db:
            return [
                len(chunk.events)
                for chunk in db.query(ChatTurnEventChunk)
                .order_by(ChatTurnEventChunk.first_sequence)
                .all()
            ]

    assert asyncio.run(scenario()) == [1, 2]


def test_journal_batch_flushes_on_time_while_source_remains_open() -> None:
    async def scenario() -> tuple[int, bool]:
        harness = Harness()
        harness.coordinator = DetachedTurnCoordinator(
            transaction=harness.transaction,
            journal=harness.journal,
            jobs=harness.jobs,
            clock=lambda: harness.now,
            persist_terminal=harness.persist_terminal,
            poll_seconds=0.01,
            batch_max_bytes=64 * 1024,
            batch_max_seconds=0.01,
        )
        release = asyncio.Event()

        async def source():
            yield ChatStreamFrame("stream_start")
            await release.wait()
            yield ChatStreamFrame("done", {"finish_reason": "success"})

        stream = await harness.coordinator.start(turn=harness.turn, source=source())
        await asyncio.sleep(0.03)
        with harness.sessions() as db:
            chunks_before_terminal = db.query(ChatTurnEventChunk).count()
        source_still_running = not stream.source_task.done()
        release.set()
        await stream.source_task
        return chunks_before_terminal, source_still_running

    assert asyncio.run(scenario()) == (1, True)


async def _sequences(
    coordinator: DetachedTurnCoordinator, turn_id: uuid.UUID
) -> list[int]:
    return [
        frame.sequence
        async for frame in coordinator.subscribe(turn_id=turn_id, after_sequence=0)
    ]


def _remote_running_turn(harness: Harness, index: int) -> uuid.UUID:
    with harness.sessions.begin() as db:
        session = ChatSession(
            id=uuid.uuid4(),
            hf_user_id=f"remote-owner-{index}",
            hf_username=f"remote-owner-{index}",
            selected_model="model",
        )
        turn_id = uuid.uuid4()
        db.add(session)
        db.add(
            ChatTurnJob(
                turn_id=turn_id,
                chat_session_id=session.id,
                hf_user_id=session.hf_user_id,
                request_id=f"remote-request-{index}",
                revision=1,
                dispatch_class="interactive",
                dispatch_route="external-pi",
                state="running",
                worker_id=f"remote-worker-{index}",
                worker_generation=1,
                lease_generation=1,
                app_release_id="release-a",
                worker_contract_version="external-pi-v1",
                admitted_at=NOW,
                dispatched_at=NOW,
                started_at=NOW,
                heartbeat_at=NOW,
                lease_expires_at=NOW + timedelta(seconds=30),
            )
        )
    return turn_id


def test_remote_subscriber_disconnects_do_not_retain_per_turn_notifications() -> None:
    async def scenario() -> tuple[int, int]:
        harness = Harness()
        remote = DetachedTurnCoordinator(
            transaction=harness.transaction,
            journal=harness.journal,
            jobs=harness.jobs,
            clock=lambda: NOW,
            persist_terminal=harness.persist_terminal,
            poll_seconds=1,
        )
        for index in range(25):
            subscription = remote.subscribe(
                turn_id=_remote_running_turn(harness, index), after_sequence=0
            )
            waiting = asyncio.create_task(anext(subscription))
            await asyncio.sleep(0)
            waiting.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await waiting
            await subscription.aclose()
        return remote.condition_count, remote.notification_state_count

    assert asyncio.run(scenario()) == (0, 0)


def test_turn_publish_wakes_only_subscribers_for_that_turn() -> None:
    async def scenario() -> tuple[int, bool]:
        harness = Harness()
        other_turn_id = _remote_running_turn(harness, 100)
        coordinator = DetachedTurnCoordinator(
            transaction=harness.transaction,
            journal=harness.journal,
            jobs=harness.jobs,
            clock=lambda: NOW,
            persist_terminal=harness.persist_terminal,
            poll_seconds=10,
        )
        release_first = asyncio.Event()
        release_terminal = asyncio.Event()

        async def source():
            await release_first.wait()
            yield ChatStreamFrame("stream_start")
            await release_terminal.wait()
            yield ChatStreamFrame("done", {"finish_reason": "success"})

        stream = await coordinator.start(turn=harness.turn, source=source())
        first_subscription = coordinator.subscribe(
            turn_id=harness.turn.turn_id, after_sequence=0
        )
        other_subscription = coordinator.subscribe(
            turn_id=other_turn_id, after_sequence=0
        )
        first = asyncio.create_task(anext(first_subscription))
        other = asyncio.create_task(anext(other_subscription))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        baseline = harness.transaction_calls

        release_first.set()
        assert (await first).sequence == 1
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        transaction_delta = harness.transaction_calls - baseline
        other_still_waiting = not other.done()

        other.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await other
        await other_subscription.aclose()
        await first_subscription.aclose()
        release_terminal.set()
        await stream.source_task
        return transaction_delta, other_still_waiting

    assert asyncio.run(scenario()) == (2, True)


def test_coordinator_without_local_source_replays_and_tails_database_journal() -> None:
    async def scenario() -> list[int]:
        harness = Harness()
        remote = DetachedTurnCoordinator(
            transaction=harness.transaction,
            journal=harness.journal,
            jobs=harness.jobs,
            clock=lambda: NOW,
            persist_terminal=harness.persist_terminal,
            poll_seconds=0.01,
        )
        release = asyncio.Event()

        async def source():
            yield ChatStreamFrame("stream_start")
            await release.wait()
            yield ChatStreamFrame("done", {"finish_reason": "success"})

        stream = await harness.coordinator.start(turn=harness.turn, source=source())
        subscriber = asyncio.create_task(_sequences(remote, harness.turn.turn_id))
        while True:
            with harness.sessions() as db:
                if harness.journal.read_after(
                    db,
                    turn_id=harness.turn.turn_id,
                    after_sequence=0,
                    limit=10,
                ):
                    break
            await asyncio.sleep(0)
        release.set()
        await stream.source_task
        return await subscriber

    assert asyncio.run(scenario()) == [1, 2]


def test_start_rejects_stale_claim_without_consuming_source() -> None:
    async def scenario() -> bool:
        harness = Harness()
        consumed = False

        async def source():
            nonlocal consumed
            consumed = True
            yield ChatStreamFrame("done")

        stale = DetachedTurn(
            turn_id=harness.turn.turn_id,
            claim=TurnLeaseClaim(
                harness.turn.turn_id,
                harness.claim.worker_id,
                harness.claim.worker_generation,
                harness.claim.lease_generation + 1,
            ),
        )
        try:
            await harness.coordinator.start(turn=stale, source=source())
        except StaleTurnClaim:
            pass
        else:
            raise AssertionError("stale claim was accepted")
        return consumed

    assert asyncio.run(scenario()) is False


def test_second_start_is_rejected_without_consuming_replacement() -> None:
    async def scenario() -> tuple[bool, bool]:
        harness = Harness()
        release = asyncio.Event()
        replacement_consumed = False

        async def source():
            await release.wait()
            yield ChatStreamFrame("done", {"finish_reason": "success"})

        async def replacement():
            nonlocal replacement_consumed
            replacement_consumed = True
            yield ChatStreamFrame("done", {"finish_reason": "success"})

        first = await harness.coordinator.start(turn=harness.turn, source=source())
        try:
            await harness.coordinator.start(turn=harness.turn, source=replacement())
        except RuntimeError as error:
            assert str(error) == "Detached turn already has a local source"
        else:
            raise AssertionError("replacement source was accepted")
        release.set()
        await first.source_task
        return first.source_task.done(), replacement_consumed

    assert asyncio.run(scenario()) == (True, False)


def test_active_source_remains_strongly_owned() -> None:
    async def scenario() -> tuple[int, int]:
        harness = Harness()
        release = asyncio.Event()

        async def source():
            await release.wait()
            yield ChatStreamFrame("done", {"finish_reason": "success"})

        stream = await harness.coordinator.start(turn=harness.turn, source=source())
        retained = (
            harness.coordinator.active_turn_count,
            harness.coordinator.notification_state_count,
        )
        release.set()
        await stream.source_task
        return retained

    assert asyncio.run(scenario()) == (1, 1)


def test_confirmed_terminal_evicts_heavy_state_and_database_rejects_restart() -> None:
    async def scenario() -> tuple[int, int, int, bool]:
        harness = Harness()
        replacement_consumed = False

        async def source():
            yield ChatStreamFrame("done", {"finish_reason": "success"})

        async def replacement():
            nonlocal replacement_consumed
            replacement_consumed = True
            yield ChatStreamFrame("done", {"finish_reason": "success"})

        stream = await harness.coordinator.start(turn=harness.turn, source=source())
        await stream.source_task
        retained = (
            harness.coordinator.active_turn_count,
            harness.coordinator.condition_count,
            harness.coordinator.ambiguous_turn_count,
        )
        try:
            await harness.coordinator.start(turn=harness.turn, source=replacement())
        except StaleTurnClaim:
            pass
        else:
            raise AssertionError("terminal turn restarted")
        return (*retained, replacement_consumed)

    assert asyncio.run(scenario()) == (0, 0, 0, False)


def test_ambiguous_terminal_failure_keeps_only_bounded_restart_tombstone() -> None:
    async def scenario() -> tuple[int, int, int, int, bool]:
        harness = Harness()
        harness.terminal_error = RuntimeError("terminal commit outcome unknown")
        replacement_consumed = False

        async def source():
            yield ChatStreamFrame("done", {"finish_reason": "success"})

        async def replacement():
            nonlocal replacement_consumed
            replacement_consumed = True
            yield ChatStreamFrame("done", {"finish_reason": "success"})

        stream = await harness.coordinator.start(turn=harness.turn, source=source())
        try:
            await stream.source_task
        except RuntimeError as error:
            assert str(error) == "terminal commit outcome unknown"
        else:
            raise AssertionError("ambiguous terminal persistence was hidden")

        retained_before_expiry = (
            harness.coordinator.active_turn_count,
            harness.coordinator.condition_count,
            harness.coordinator.ambiguous_turn_count,
        )
        try:
            await harness.coordinator.start(turn=harness.turn, source=replacement())
        except StaleTurnClaim:
            pass
        else:
            raise AssertionError("ambiguous turn restarted before lease expiry")

        harness.now = NOW + timedelta(seconds=31)
        try:
            await harness.coordinator.start(turn=harness.turn, source=replacement())
        except StaleTurnClaim:
            pass
        else:
            raise AssertionError("expired ambiguous turn restarted")
        return (
            *retained_before_expiry,
            harness.coordinator.ambiguous_turn_count,
            replacement_consumed,
        )

    assert asyncio.run(scenario()) == (0, 0, 1, 0, False)


def test_ambiguous_tombstone_revalidates_heartbeat_extended_claim() -> None:
    async def scenario() -> tuple[int, int, bool]:
        harness = Harness()
        harness.terminal_error = RuntimeError("terminal commit outcome unknown")
        release = asyncio.Event()
        replacement_consumed = False

        async def source():
            await release.wait()
            yield ChatStreamFrame("done", {"finish_reason": "success"})

        async def replacement():
            nonlocal replacement_consumed
            replacement_consumed = True
            if False:
                yield ChatStreamFrame("done")

        stream = await harness.coordinator.start(turn=harness.turn, source=source())
        await harness.transaction(
            lambda db: harness.jobs.heartbeat(
                db,
                claim=harness.claim,
                now=NOW + timedelta(seconds=20),
                lease_seconds=30,
            )
        )
        release.set()
        with contextlib.suppress(RuntimeError):
            await stream.source_task

        harness.now = NOW + timedelta(seconds=31)
        try:
            await harness.coordinator.start(turn=harness.turn, source=replacement())
        except StaleTurnClaim:
            pass
        else:
            raise AssertionError("heartbeat-extended ambiguous claim restarted")
        retained_during_renewed_lease = harness.coordinator.ambiguous_turn_count

        harness.now = NOW + timedelta(seconds=51)
        try:
            await harness.coordinator.start(turn=harness.turn, source=replacement())
        except StaleTurnClaim:
            pass
        else:
            raise AssertionError("expired ambiguous claim restarted")
        return (
            retained_during_renewed_lease,
            harness.coordinator.ambiguous_turn_count,
            replacement_consumed,
        )

    assert asyncio.run(scenario()) == (1, 0, False)


def test_ambiguous_tombstone_fails_closed_when_revalidation_is_unavailable() -> None:
    async def scenario() -> tuple[int, bool]:
        harness = Harness()
        harness.terminal_error = RuntimeError("terminal commit outcome unknown")
        replacement_consumed = False

        async def source():
            yield ChatStreamFrame("done", {"finish_reason": "success"})

        async def replacement():
            nonlocal replacement_consumed
            replacement_consumed = True
            if False:
                yield ChatStreamFrame("done")

        stream = await harness.coordinator.start(turn=harness.turn, source=source())
        with contextlib.suppress(RuntimeError):
            await stream.source_task
        harness.transaction_error = OperationalError(
            "SELECT 1", {}, RuntimeError("database temporarily unavailable")
        )

        try:
            await harness.coordinator.start(turn=harness.turn, source=replacement())
        except StaleTurnClaim as error:
            assert str(error) == "Detached turn outcome remains ambiguous"
        else:
            raise AssertionError("unverifiable ambiguous turn restarted")
        await asyncio.sleep(0.03)
        return harness.coordinator.ambiguous_turn_count, replacement_consumed

    assert asyncio.run(scenario()) == (1, False)


def test_journal_overflow_persists_one_terminal_failure() -> None:
    async def scenario() -> tuple[list[tuple[str, str | None]], str, str | None]:
        harness = Harness()
        harness.journal.MAX_FRAME_BYTES = 1

        async def source():
            yield ChatStreamFrame("answer_delta", {"text": "too large"})

        stream = await harness.coordinator.start(turn=harness.turn, source=source())
        await stream.source_task
        with harness.sessions() as db:
            job = harness.jobs.load_by_turn(db, harness.turn.turn_id)
            assert job is not None
            return harness.terminal_calls, job.state, job.failure_code

    assert asyncio.run(scenario()) == (
        [("failed", "event_journal_exhausted")],
        "failed",
        "event_journal_exhausted",
    )


def test_terminal_projection_retains_journal_for_durable_replay_grace() -> None:
    async def scenario() -> tuple[list[str], int]:
        harness = Harness()
        ordering: list[str] = []
        original_persist = harness.coordinator._persist_terminal

        async def persist(claim, state, code):
            ordering.append("terminal")
            await original_persist(claim, state, code)

        harness.coordinator._persist_terminal = persist

        async def source():
            yield ChatStreamFrame("done", {"finish_reason": "success"})

        stream = await harness.coordinator.start(turn=harness.turn, source=source())
        await stream.source_task
        await asyncio.sleep(0.03)
        with harness.sessions() as db:
            remaining = db.query(ChatTurnEventChunk).count()
        return ordering, remaining

    assert asyncio.run(scenario()) == (["terminal"], 1)


def test_detached_lifecycle_observer_receives_only_bounded_labels_and_counts() -> None:
    async def scenario():
        harness = Harness()
        observations: list[tuple[str, str | None, int]] = []
        harness.coordinator._observe = lambda event, code, value: observations.append(
            (event, code, value)
        )

        async def source():
            yield ChatStreamFrame("done", {"finish_reason": "success"})

        stream = await harness.coordinator.start(turn=harness.turn, source=source())
        await stream.source_task
        await asyncio.sleep(0.03)
        return observations

    observations = asyncio.run(scenario())
    assert observations[:2] == [
        ("turn_state", "running", 1),
        ("journal_events", None, 1),
    ]
    assert observations[2][0:2] == ("journal_bytes", None)
    assert observations[2][2] > 0
    assert observations[3:] == [("turn_state", "completed", 1)]


def test_live_execution_loss_is_observed_after_terminal_persistence() -> None:
    async def scenario() -> list[tuple[str, str | None, int]]:
        harness = Harness()
        observations: list[tuple[str, str | None, int]] = []
        persisted = False
        original_persist = harness.coordinator._persist_terminal

        async def persist(claim, state, code):
            nonlocal persisted
            await original_persist(claim, state, code)
            persisted = True

        def observe(event, code, value):
            if (event, code) == ("typed_failure", "execution_lost"):
                assert persisted is True
            observations.append((event, code, value))

        harness.coordinator._persist_terminal = persist
        harness.coordinator._observe = observe

        async def source():
            yield ChatStreamFrame(
                "error",
                {
                    "message": "The sandbox execution could not be recovered.",
                    "code": "execution_lost",
                },
            )

        stream = await harness.coordinator.start(turn=harness.turn, source=source())
        await stream.source_task
        return observations

    assert asyncio.run(scenario())[-2:] == [
        ("turn_state", "failed", 1),
        ("typed_failure", "execution_lost", 1),
    ]


def test_expected_source_transport_error_appends_bounded_failure_before_terminal() -> (
    None
):
    async def scenario() -> tuple[list[str], list[tuple[str, str | None]]]:
        harness = Harness()

        async def source():
            yield ChatStreamFrame("stream_start")
            raise OSError("transport unavailable")

        stream = await harness.coordinator.start(turn=harness.turn, source=source())
        await stream.source_task
        frames = [
            frame
            async for frame in harness.coordinator.subscribe(
                turn_id=harness.turn.turn_id, after_sequence=0
            )
        ]
        assert frames[-1].payload == {
            "message": "The response could not be completed.",
            "code": "turn_failed",
        }
        assert harness.terminal_sequences == [[1, 2]]
        return [frame.event for frame in frames], harness.terminal_calls

    assert asyncio.run(scenario()) == (
        ["stream_start", "error"],
        [("failed", "turn_failed")],
    )


def test_programming_error_propagates_without_generic_turn_failed_terminal() -> None:
    async def scenario() -> tuple[list[tuple[str, str | None]], int]:
        harness = Harness()

        async def source():
            yield ChatStreamFrame("stream_start")
            raise RuntimeError("programming defect")

        stream = await harness.coordinator.start(turn=harness.turn, source=source())
        with pytest.raises(RuntimeError, match="programming defect"):
            await stream.source_task
        return harness.terminal_calls, harness.coordinator.ambiguous_turn_count

    assert asyncio.run(scenario()) == ([], 1)


def test_unleased_admission_becomes_dispatch_failed() -> None:
    async def scenario() -> tuple[bool, str, str | None, int]:
        harness = Harness()
        with harness.sessions.begin() as db:
            original = harness.jobs.load_by_turn(db, harness.turn.turn_id)
            assert original is not None
            session = db.get(ChatSession, original.chat_session_id)
            assert session is not None
            admitted = harness.jobs.admit(
                db,
                turn_id=uuid.uuid4(),
                chat_session_id=session.id,
                hf_user_id="other-owner",
                request_id=f"request-{uuid.uuid4()}",
                revision=1,
                dispatch_class="interactive",
                dispatch_route="external-pi",
                app_release_id="release-a",
                worker_contract_version="external-pi-v1",
                now=NOW - timedelta(seconds=2),
                emergency_capacity=8,
            ).job
        changed = await harness.coordinator.interrupt_dispatch_failed(
            admitted.turn_id,
            worker_id="dispatch-coordinator",
            worker_generation=1,
            lease_seconds=30,
            admitted_before=NOW - timedelta(seconds=1),
        )
        with harness.sessions() as db:
            job = harness.jobs.load_by_turn(db, admitted.turn_id)
            assert job is not None
            return (
                changed,
                job.state,
                job.failure_code,
                harness.coordinator.condition_count,
            )

    assert asyncio.run(scenario()) == (True, "interrupted", "dispatch_failed", 0)


@pytest.mark.parametrize(
    ("expired_state", "expected_code"),
    [
        ("leased", "dispatch_failed"),
        ("running", "external_worker_lost"),
        ("waiting_tool", "execution_lost"),
        ("cancelling", "cancel_control_missing"),
    ],
)
def test_expired_detached_reconciler_terminalizes_projection_and_retains_replay(
    expired_state, expected_code
) -> None:
    async def scenario():
        harness = Harness()
        ordering: list[str] = []
        observations: list[tuple[str, str | None, int]] = []
        with harness.sessions.begin() as db:
            job = harness.jobs.load_by_turn(db, harness.turn.turn_id, lock=True)
            assert job is not None
            session = db.get(ChatSession, job.chat_session_id)
            assert session is not None
            session.active_turn_id = job.turn_id
            session.active_turn_expires_at = NOW + timedelta(seconds=180)
            job.state = expired_state
            job.lease_expires_at = NOW - timedelta(seconds=1)
            db.add(
                ChatMessageRecord(
                    id=uuid.uuid4(),
                    session_id=session.id,
                    turn_id=job.turn_id,
                    sequence=1,
                    role="user",
                    content="content is irrelevant to reconciliation",
                    status="generating",
                )
            )
            db.add(
                ChatTurnEventChunk(
                    turn_id=job.turn_id,
                    first_sequence=1,
                    last_sequence=1,
                    events=[{"sequence": 1, "event": "stream_start", "payload": {}}],
                    payload_bytes=1,
                    created_at=NOW,
                )
            )

        async def transaction(operation):
            with harness.sessions.begin() as db:
                result = operation(db)
            ordering.append(operation.__name__)
            return result

        reconciler = ExpiredDetachedTurnReconciler(
            transaction=transaction,
            jobs=harness.jobs,
            journal=harness.journal,
            observe=lambda event, code, value: observations.append(
                (event, code, value)
            ),
        )
        result = await reconciler.reconcile(now=NOW, limit=10)

        with harness.sessions() as db:
            job = harness.jobs.load_by_turn(db, harness.turn.turn_id)
            session = db.get(ChatSession, job.chat_session_id)
            message = db.query(ChatMessageRecord).one()
            chunks = db.query(ChatTurnEventChunk).count()
            return result, ordering, observations, job, session, message, chunks

    result, ordering, observations, job, session, message, chunks = asyncio.run(
        scenario()
    )
    assert result == {expected_code: 1}
    assert ordering == ["<lambda>", "<lambda>"]
    assert observations == [
        ("expired_turn_lease", "expired", 1),
        ("typed_failure", expected_code, 1),
    ]
    assert (job.state, job.failure_code) == ("interrupted", expected_code)
    assert (message.status, message.error_code) == ("interrupted", expected_code)
    assert session.active_turn_id is None
    assert chunks == 1


def test_expired_reconciler_progresses_past_full_poison_window_across_restarts():
    async def scenario():
        harness = Harness()
        observations: list[tuple[str, str | None, int]] = []
        with harness.sessions.begin() as db:
            poison = harness.jobs.load_by_turn(db, harness.turn.turn_id, lock=True)
            poison_session = db.get(ChatSession, poison.chat_session_id)
            poison.state = "running"
            poison.lease_expires_at = NOW - timedelta(seconds=2)
            poison_session.active_turn_id = poison.turn_id

            for index in range(99):
                poison_session = ChatSession(
                    id=uuid.uuid4(),
                    hf_user_id=f"poison-{index}",
                    hf_username=f"poison-{index}",
                    selected_model="model",
                )
                poison_turn = uuid.uuid4()
                poison_session.active_turn_id = poison_turn
                db.add(poison_session)
                db.add(
                    ChatTurnJob(
                        turn_id=poison_turn,
                        chat_session_id=poison_session.id,
                        hf_user_id=poison_session.hf_user_id,
                        request_id=f"request-{uuid.uuid4()}",
                        revision=1,
                        dispatch_class="interactive",
                        dispatch_route="external-pi",
                        state="running",
                        worker_id=f"poison-worker-{index}",
                        worker_generation=8,
                        lease_generation=1,
                        app_release_id="release-a",
                        worker_contract_version="external-pi-v1",
                        admitted_at=NOW - timedelta(seconds=3),
                        heartbeat_at=NOW,
                        lease_expires_at=NOW - timedelta(seconds=2),
                    )
                )

            healthy_turn_ids = []
            for index in range(2):
                healthy_session = ChatSession(
                    id=uuid.uuid4(),
                    hf_user_id=f"healthy-owner-{index}",
                    hf_username=f"healthy-owner-{index}",
                    selected_model="model",
                )
                healthy_turn_id = uuid.uuid4()
                healthy_turn_ids.append(healthy_turn_id)
                healthy_session.active_turn_id = healthy_turn_id
                db.add(healthy_session)
                db.add(
                    ChatTurnJob(
                        turn_id=healthy_turn_id,
                        chat_session_id=healthy_session.id,
                        hf_user_id=healthy_session.hf_user_id,
                        request_id=f"request-{uuid.uuid4()}",
                        revision=1,
                        dispatch_class="interactive",
                        dispatch_route="external-pi",
                        state="running",
                        worker_id=f"worker-{index}",
                        worker_generation=8,
                        lease_generation=1,
                        app_release_id="release-a",
                        worker_contract_version="external-pi-v1",
                        admitted_at=NOW - timedelta(seconds=2),
                        heartbeat_at=NOW,
                        lease_expires_at=NOW - timedelta(seconds=1),
                    )
                )
                db.add(
                    ChatMessageRecord(
                        id=uuid.uuid4(),
                        session_id=healthy_session.id,
                        turn_id=healthy_turn_id,
                        sequence=1,
                        role="user",
                        content="irrelevant",
                        status="generating",
                    )
                )

        results = []
        for _restart in range(2):
            reconciler = ExpiredDetachedTurnReconciler(
                transaction=harness.transaction,
                jobs=harness.jobs,
                journal=harness.journal,
                observe=lambda event, code, value: observations.append(
                    (event, code, value)
                ),
            )
            results.append(await reconciler.reconcile(now=NOW, limit=1))
        with harness.sessions() as db:
            healthy_states = [
                harness.jobs.load_by_turn(db, turn_id).state
                for turn_id in healthy_turn_ids
            ]
            poison = harness.jobs.load_by_turn(db, harness.turn.turn_id)
            return results, observations, healthy_states, poison.state

    results, observations, healthy_states, poison_state = asyncio.run(scenario())
    assert results == [
        {"external_worker_lost": 1},
        {"external_worker_lost": 1},
    ]
    assert observations == [
        ("expired_turn_lease", "expired", 1),
        ("typed_failure", "external_worker_lost", 1),
        ("expired_turn_lease", "expired", 1),
        ("typed_failure", "external_worker_lost", 1),
    ]
    assert healthy_states == ["interrupted", "interrupted"]
    assert poison_state == "running"
