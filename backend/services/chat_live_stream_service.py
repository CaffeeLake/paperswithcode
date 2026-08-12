"""In-process fan-out and replay for active research chat streams."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator

from backend.services.chat_stream_service import ChatStreamFrame


class LiveChatStream:
    """Keep one turn running independently of any individual HTTP response."""

    def __init__(
        self,
        *,
        session_id: uuid.UUID,
        turn_id: uuid.UUID,
        owner_id: str,
        source: AsyncIterator[ChatStreamFrame],
    ) -> None:
        self.session_id = session_id
        self.turn_id = turn_id
        self.owner_id = owner_id
        self._source = source
        self._frames: list[ChatStreamFrame] = []
        self._condition = asyncio.Condition()
        self._finished = False
        self.task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        try:
            async for frame in self._source:
                async with self._condition:
                    self._frames.append(frame)
                    self._condition.notify_all()
        finally:
            async with self._condition:
                self._finished = True
                self._condition.notify_all()

    async def subscribe(self) -> AsyncIterator[ChatStreamFrame]:
        """Replay the turn from its first frame, then follow new frames live."""

        index = 0
        while True:
            async with self._condition:
                await self._condition.wait_for(
                    lambda: index < len(self._frames) or self._finished
                )
                if index >= len(self._frames):
                    return
                frame = self._frames[index]
                index += 1
            yield frame


class LiveChatStreamRegistry:
    """Own active turn tasks and make them reconnectable by session."""

    def __init__(self) -> None:
        self._streams: dict[uuid.UUID, LiveChatStream] = {}

    def start(
        self,
        *,
        session_id: uuid.UUID,
        turn_id: uuid.UUID,
        owner_id: str,
        source: AsyncIterator[ChatStreamFrame],
    ) -> LiveChatStream:
        existing = self._streams.get(session_id)
        if existing is not None and not existing.task.done():
            raise RuntimeError("Chat session already has a live stream")
        stream = LiveChatStream(
            session_id=session_id,
            turn_id=turn_id,
            owner_id=owner_id,
            source=source,
        )
        self._streams[session_id] = stream
        stream.task.add_done_callback(
            lambda _task: asyncio.create_task(self._expire(session_id, stream))
        )
        return stream

    def get(
        self, session_id: uuid.UUID, turn_id: uuid.UUID, owner_id: str
    ) -> LiveChatStream | None:
        stream = self._streams.get(session_id)
        if stream is None or stream.turn_id != turn_id or stream.owner_id != owner_id:
            return None
        return stream

    async def _expire(self, session_id: uuid.UUID, stream: LiveChatStream) -> None:
        # A short grace period covers the race between the terminal SSE frame
        # and the browser's canonical session reload.
        await asyncio.sleep(30)
        if self._streams.get(session_id) is stream:
            self._streams.pop(session_id, None)


_registry = LiveChatStreamRegistry()


def live_chat_stream_registry() -> LiveChatStreamRegistry:
    return _registry
