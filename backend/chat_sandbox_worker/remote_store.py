"""Agent SDK SessionStore adapter scoped through the localhost broker."""

from __future__ import annotations

import asyncio
import json
import logging
import random
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)
TRANSIENT_HTTP_STATUSES = {408, 429, 502, 503, 504}


class TransientResponseError(ConnectionError):
    pass


@dataclass(frozen=True)
class RetryPolicy:
    total_deadline_seconds: float = 20
    initial_delay_seconds: float = 0.1
    maximum_delay_seconds: float = 2
    maximum_retry_after_seconds: float = 5


class RemoteSessionStore:
    def __init__(
        self,
        origin: str = "http://127.0.0.1:8765",
        *,
        retry_policy: RetryPolicy | None = None,
    ):
        self.origin = origin.rstrip("/")
        self.retry_policy = retry_policy or RetryPolicy()

    def _request_once(self, payload: dict[str, Any]) -> Any:
        raw = json.dumps(payload, separators=(",", ":")).encode()
        request = urllib.request.Request(
            f"{self.origin}/session-store",
            data=raw,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(
            request,
            timeout=min(10, self.retry_policy.total_deadline_seconds),
        ) as response:
            body = response.read(2 * 1024 * 1024)
            content_length = response.headers.get("Content-Length")
        if content_length is not None and int(content_length) != len(body):
            raise TransientResponseError("session-store response was truncated")
        try:
            value = json.loads(body)
        except json.JSONDecodeError as error:
            if not body or body.rstrip()[-1:] not in {b"}", b"]"}:
                raise TransientResponseError(
                    "session-store response was truncated"
                ) from error
            raise
        return value.get("result")

    @staticmethod
    def _transient(error: BaseException) -> bool:
        if isinstance(error, urllib.error.HTTPError):
            return error.code in TRANSIENT_HTTP_STATUSES
        if isinstance(
            error,
            (
                urllib.error.URLError,
                TimeoutError,
                ConnectionError,
                ConnectionResetError,
                socket.timeout,
                TransientResponseError,
            ),
        ):
            return True
        return isinstance(error, OSError)

    def _retry_after(self, error: BaseException) -> float | None:
        if not isinstance(error, urllib.error.HTTPError):
            return None
        raw = error.headers.get("Retry-After") if error.headers else None
        if raw is None:
            return None
        try:
            return min(
                self.retry_policy.maximum_retry_after_seconds,
                max(0.0, float(raw)),
            )
        except ValueError:
            return None

    def _request(self, payload: dict[str, Any]) -> Any:
        deadline = time.monotonic() + self.retry_policy.total_deadline_seconds
        attempt = 0
        while True:
            try:
                result = self._request_once(payload)
                if attempt:
                    logger.info(
                        "chat transcript-store retry outcome=success attempts=%d",
                        attempt + 1,
                    )
                return result
            except BaseException as error:
                if not self._transient(error):
                    raise
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    logger.warning(
                        "chat transcript-store retry outcome=deadline attempts=%d "
                        "status=%s",
                        attempt + 1,
                        getattr(error, "code", "connection"),
                    )
                    raise
                exponential = min(
                    self.retry_policy.maximum_delay_seconds,
                    self.retry_policy.initial_delay_seconds * (2**attempt),
                )
                retry_after = self._retry_after(error)
                delay = (
                    retry_after
                    if retry_after is not None
                    else random.uniform(0, exponential)
                )
                if delay >= remaining:
                    logger.warning(
                        "chat transcript-store retry outcome=deadline attempts=%d "
                        "status=%s",
                        attempt + 1,
                        getattr(error, "code", "connection"),
                    )
                    raise
                attempt += 1
                logger.info(
                    "chat transcript-store retry outcome=retry attempt=%d status=%s",
                    attempt,
                    getattr(error, "code", "connection"),
                )
                time.sleep(delay)

    async def append(self, key: dict, entries: list[dict]) -> None:
        await asyncio.to_thread(
            self._request, {"action": "append", "key": key, "entries": entries}
        )

    async def load(self, key: dict) -> list[dict] | None:
        return await asyncio.to_thread(self._request, {"action": "load", "key": key})

    async def list_sessions(self, project_key: str) -> list[dict]:
        return await asyncio.to_thread(
            self._request, {"action": "list_sessions", "project_key": project_key}
        )

    async def list_session_summaries(self, project_key: str) -> list[dict]:
        return await asyncio.to_thread(
            self._request,
            {"action": "list_session_summaries", "project_key": project_key},
        )

    async def list_subkeys(self, key: dict) -> list[str]:
        return await asyncio.to_thread(
            self._request, {"action": "list_subkeys", "key": key}
        )

    async def delete(self, key: dict) -> None:
        await asyncio.to_thread(self._request, {"action": "delete", "key": key})
