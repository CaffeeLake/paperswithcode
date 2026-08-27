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
from requests.exceptions import RequestException

from backend.loadtests.chat_core import (
    STAGING_RUNTIME_ENV_PATH,
    BoundedSSEStream,
    Metric,
    RunRefused,
    SSEParseError,
    build_turn_request,
    classify_refusal_bytes,
    load_run_config,
)

CONFIG = load_run_config(
    os.environ,
    budget_path=STAGING_RUNTIME_ENV_PATH,
    expected_budget_path=STAGING_RUNTIME_ENV_PATH,
    expected_budget_owner_uid=0,
)
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
            initial_model=CONFIG.initial_model,
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
        stream = BoundedSSEStream(max_output_chars=CONFIG.max_output_chars)
        session_id: str | None = None
        try:
            chunk_size = 1 if CONFIG.profile.cohort == "reconnect" else 4096
            for chunk in response.iter_content(chunk_size=chunk_size):
                batch = stream.feed(chunk, elapsed_ms=_elapsed_ms(started))
                for metric in batch.metrics:
                    _record(self, metric)
                for event in batch.events:
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
                if stream.finished:
                    return
            batch = stream.close(elapsed_ms=_elapsed_ms(started))
            for metric in batch.metrics:
                _record(self, metric)
        except (SSEParseError, RequestException):
            _record_refusal(self, "stream_error", started)
            return
        if not stream.finished:
            _record_refusal(self, "stream_error", started)

    def _resume(self, session_id: str | None) -> None:
        started = time.perf_counter()
        if not session_id:
            _record(self, Metric("chat.reconnect", 0, False))
            _record_refusal(self, "stream_error", started)
            return
        stream = BoundedSSEStream(
            max_output_chars=CONFIG.max_output_chars,
            replay=True,
        )
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
                _record_refusal(self, "stream_error", started)
                return
            response.success()
            _record(self, Metric("chat.reconnect", _elapsed_ms(started), True))
            try:
                for chunk in response.iter_content(chunk_size=4096):
                    batch = stream.feed(chunk, elapsed_ms=_elapsed_ms(started))
                    for metric in batch.metrics:
                        _record(self, metric)
                    if stream.finished:
                        return
                batch = stream.close(elapsed_ms=_elapsed_ms(started))
                for metric in batch.metrics:
                    _record(self, metric)
            except (SSEParseError, RequestException):
                _record_refusal(self, "stream_error", started)
                return
            if not stream.finished:
                _record_refusal(self, "stream_error", started)
