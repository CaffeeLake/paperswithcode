from __future__ import annotations

import asyncio
import uuid

from backend.services.chat_live_stream_service import LiveChatStreamRegistry
from backend.services.chat_stream_service import ChatStreamFrame


def test_stream_survives_subscriber_disconnect_and_replays_to_reconnect() -> None:
    async def scenario() -> list[str | None]:
        release_second = asyncio.Event()

        async def source():
            yield ChatStreamFrame("stream_start", {"request_id": "r1"})
            await release_second.wait()
            yield ChatStreamFrame("answer_delta", {"text": "Recovered"})
            yield ChatStreamFrame("done", {"finish_reason": "success"})

        session_id = uuid.uuid4()
        turn_id = uuid.uuid4()
        registry = LiveChatStreamRegistry()
        stream = registry.start(
            session_id=session_id,
            turn_id=turn_id,
            owner_id="owner-1",
            source=source(),
        )

        first_subscription = stream.subscribe()
        first = await anext(first_subscription)
        await first_subscription.aclose()
        assert first.event == "stream_start"
        assert not stream.task.done()

        release_second.set()
        recovered = [frame.event async for frame in stream.subscribe()]
        await stream.task
        return recovered

    assert asyncio.run(scenario()) == ["stream_start", "answer_delta", "done"]


def test_registry_requires_matching_owner_and_turn() -> None:
    async def scenario() -> None:
        async def source():
            if False:
                yield ChatStreamFrame.heartbeat()

        session_id = uuid.uuid4()
        turn_id = uuid.uuid4()
        registry = LiveChatStreamRegistry()
        stream = registry.start(
            session_id=session_id,
            turn_id=turn_id,
            owner_id="owner-1",
            source=source(),
        )
        assert registry.get(session_id, turn_id, "owner-1") is stream
        assert registry.get(session_id, uuid.uuid4(), "owner-1") is None
        assert registry.get(session_id, turn_id, "owner-2") is None
        await stream.task

    asyncio.run(scenario())
