"""Thin Locust adapter for the operator-only staging chat profiles.

Run only through the documented ephemeral ``uv --with`` command. Importing this
module fails closed unless the complete staging envelope is present.
"""

from __future__ import annotations

import itertools
import os
import time
import uuid
from urllib.parse import quote

from locust import HttpUser, between, events, task
from locust.exception import StopUser

from backend.loadtests.chat_core import (
    Metric,
    RunRefused,
    SSEParseError,
    SSEParser,
    StreamMetricTracker,
    build_turn_request,
    classify_refusal_bytes,
    load_run_config,
)

CONFIG = load_run_config(os.environ)
_credential_counter = itertools.count()


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def _record(user: HttpUser, metric: Metric) -> None:
    user.environment.events.request.fire(
        request_type="CHAT",
        name=metric.name,
        response_time=metric.elapsed_ms,
        response_length=0,
        exception=None if metric.success else RuntimeError(metric.name),
    )


def _record_refusal(user: HttpUser, label: str, started: float) -> None:
    _record(user, Metric(f"chat.{label}", _elapsed_ms(started), False))


@events.test_start.add_listener
def _validate_runtime(environment, **_kwargs) -> None:
    if environment.host != CONFIG.host:
        raise RunRefused("Locust host changed after the exact staging-origin gate")
    requested_users = getattr(environment.parsed_options, "num_users", None)
    if requested_users != CONFIG.profile.users:
        raise RunRefused(f"Locust users must equal profile size {CONFIG.profile.users}")


class StagingChatUser(HttpUser):
    host = CONFIG.host
    wait_time = between(1, 2)

    def on_start(self) -> None:
        index = next(_credential_counter)
        cookie_index = 0 if CONFIG.profile.same_account else index
        self.client.cookies.set(
            "pwc_staging_session",
            CONFIG.synthetic_cookies[cookie_index % len(CONFIG.synthetic_cookies)],
            domain="staging.paperswithcode.co",
            secure=True,
        )

    @task
    def run_profile_once(self) -> None:
        if CONFIG.profile.cohort == "connection-only":
            self._connection_only()
        else:
            self._stream_turn()
        raise StopUser()

    def _connection_only(self) -> None:
        with self.client.get(
            "/api/v1/chat/availability",
            name=f"{CONFIG.profile.metric_label}/connection",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure("connection check failed")

    def _stream_turn(self) -> None:
        started = time.perf_counter()
        body = build_turn_request(
            CONFIG.profile,
            client_message_id=f"load-{uuid.uuid4()}",
            max_prompt_chars=CONFIG.max_prompt_chars,
        )
        with self.client.post(
            "/api/v1/chat/stream",
            json=body,
            headers={"Accept": "text/event-stream"},
            stream=True,
            name=f"{CONFIG.profile.metric_label}/response_headers",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                label = classify_refusal_bytes(response.raw.read(4097))
                _record_refusal(self, label, started)
                response.failure(f"typed refusal: {label}")
                return
            response.success()
            self._consume_stream(response, started)

    def _consume_stream(self, response, started: float) -> None:
        parser = SSEParser(max_event_bytes=max(4096, CONFIG.max_output_chars * 2))
        tracker = StreamMetricTracker()
        output_chars = 0
        terminal = False
        session_id: str | None = None
        try:
            for chunk in response.iter_content(chunk_size=4096):
                for event in parser.feed(chunk):
                    for metric in tracker.observe(
                        event, elapsed_ms=_elapsed_ms(started)
                    ):
                        _record(self, metric)
                    event_type = event.get("type")
                    if event_type == "stream_start":
                        raw_session_id = event.get("session_id")
                        session_id = (
                            raw_session_id if isinstance(raw_session_id, str) else None
                        )
                        if CONFIG.profile.cohort == "reconnect":
                            response.close()
                            self._resume(session_id)
                            return
                    if event_type in {"answer_delta", "reasoning_delta"}:
                        text = event.get("text")
                        output_chars += len(text) if isinstance(text, str) else 0
                        if output_chars > CONFIG.max_output_chars:
                            raise SSEParseError(
                                "stream output exceeded configured bound"
                            )
                    if event_type in {"done", "error"}:
                        terminal = True
                        return
            for event in parser.close():
                for metric in tracker.observe(event, elapsed_ms=_elapsed_ms(started)):
                    _record(self, metric)
                terminal = event.get("type") in {"done", "error"}
        except SSEParseError:
            _record_refusal(self, "stream_error", started)
            return
        if not terminal:
            _record_refusal(self, "stream_error", started)

    def _resume(self, session_id: str | None) -> None:
        if not session_id:
            _record(self, Metric("chat.reconnect", 0, False))
            return
        started = time.perf_counter()
        parser = SSEParser(max_event_bytes=max(4096, CONFIG.max_output_chars * 2))
        with self.client.get(
            f"/api/v1/chat/sessions/{quote(session_id, safe='')}/stream",
            headers={"Accept": "text/event-stream"},
            stream=True,
            name=f"{CONFIG.profile.metric_label}/reconnect_headers",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure("reconnect failed")
                _record(self, Metric("chat.reconnect", _elapsed_ms(started), False))
                return
            response.success()
            for chunk in response.iter_content(chunk_size=4096):
                events_seen = parser.feed(chunk)
                if events_seen:
                    _record(
                        self,
                        StreamMetricTracker.reconnect(
                            elapsed_ms=_elapsed_ms(started), replayed=True
                        ),
                    )
                    return
            _record(self, Metric("chat.reconnect", _elapsed_ms(started), False))
