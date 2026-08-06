from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx

from backend.config import Settings
from backend.scripts import monitor_chat_operational_alerts as monitor
from backend.services.chat_operational_alert_service import (
    ProviderHealth,
    operational_alert_payload,
    provider_health,
    provider_transition,
    runtime_failure_counts,
)


def test_runtime_failure_counts_never_return_raw_journal_content():
    messages = [
        "chat stream persistence failed session_id=secret-session prompt=private",
        "chat transcript mirror failed session_id=another-private-id",
        "chat research producer failed error=ConnectionClosedError",
        "POST /api/internal/chat-gateway/session-store 403 Forbidden",
    ]

    assert runtime_failure_counts(messages) == {
        "stream_persistence_failure": 1,
        "transcript_mirror_failure": 1,
        "session_store_forbidden": 1,
    }


def test_provider_health_counts_only_content_free_aggregates():
    class FakeSession:
        values = iter((10, 5))

        def scalar(self, _statement):
            return next(self.values)

    now = datetime(2026, 8, 6, 12, tzinfo=UTC)
    settings = Settings(chat_provider_alert_window_seconds=300)

    assert provider_health(FakeSession(), settings, now) == ProviderHealth(
        total_turns=10,
        failed_turns=5,
        window_start=now - timedelta(minutes=5),
        window_end=now,
    )


def test_provider_transition_requires_sustained_failure_and_clean_recovery():
    now = datetime(2026, 8, 6, 12, tzinfo=UTC)
    settings = Settings(
        chat_provider_alert_min_failures=5,
        chat_provider_alert_failure_percent=50,
    )

    assert (
        provider_transition(
            active=False,
            health=ProviderHealth(10, 5, now - timedelta(minutes=5), now),
            settings=settings,
        )
        == "hf_provider_sustained_failure"
    )
    assert (
        provider_transition(
            active=True,
            health=ProviderHealth(10, 1, now - timedelta(minutes=5), now),
            settings=settings,
        )
        is None
    )
    assert (
        provider_transition(
            active=True,
            health=ProviderHealth(8, 0, now - timedelta(minutes=5), now),
            settings=settings,
        )
        == "hf_provider_recovered"
    )


def test_operational_payload_is_content_free():
    now = datetime(2026, 8, 6, 12, tzinfo=UTC)
    event = monitor.new_event(
        "chat_runtime_critical",
        now=now,
        classifications={"stream_persistence_failure": 2},
    )
    settings = Settings(
        environment="production",
        release_id="release-test",
        chat_sandbox_runbook_url="https://runbook.test/chat",
    )

    payload = operational_alert_payload(event, settings)["text"]

    assert "stream_persistence_failure" in payload
    assert "release-test" in payload
    assert "prompt" not in payload
    assert "answer" not in payload
    assert "credential" not in payload


def test_pending_runtime_events_are_bounded_by_coalescing():
    now = datetime(2026, 8, 6, 12, tzinfo=UTC)
    state = monitor.empty_state()
    first = monitor.new_event(
        "chat_runtime_critical",
        now=now,
        count=1,
        classifications={"turn_cleanup_failure": 1},
    )
    second = monitor.new_event(
        "chat_runtime_critical",
        now=now + timedelta(minutes=1),
        count=2,
        classifications={"turn_cleanup_failure": 1, "latency_phase_failure": 1},
    )

    monitor.append_event(state, first)
    monitor.append_event(state, second)

    assert len(state["events"]) == 1
    assert state["events"][0]["count"] == 3
    assert state["events"][0]["classifications"] == {
        "turn_cleanup_failure": 2,
        "latency_phase_failure": 1,
    }


def test_state_round_trip_is_private_and_atomic(tmp_path):
    path = tmp_path / "state.json"
    state = monitor.empty_state()
    state["journal_cursor"] = "content-free-cursor"

    monitor.write_state(path, state)

    assert monitor.load_state(path) == state
    assert path.stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob(".state.json.new-*"))


def test_journal_reader_advances_cursor_without_returning_records(monkeypatch):
    output = "\n".join(
        (
            json.dumps({"MESSAGE": "first", "__CURSOR": "cursor-1"}),
            json.dumps({"MESSAGE": "second", "__CURSOR": "cursor-2"}),
        )
    )
    observed = []

    def fake_run(command, **_kwargs):
        observed.append(command)
        return SimpleNamespace(stdout=output)

    monkeypatch.setattr(monitor.subprocess, "run", fake_run)

    messages, cursor, reset = monitor.read_journal(
        "previous-cursor", datetime(2026, 8, 6, 12, tzinfo=UTC)
    )

    assert messages == ["first", "second"]
    assert cursor == "cursor-2"
    assert reset is False
    assert "--after-cursor" in observed[0]
    assert "previous-cursor" in observed[0]


def test_journal_reader_recovers_from_a_vacuumed_cursor(monkeypatch):
    calls = 0

    def fake_run(_command, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise monitor.subprocess.CalledProcessError(1, "journalctl")
        return SimpleNamespace(
            stdout=json.dumps({"MESSAGE": "recent", "__CURSOR": "fresh-cursor"})
        )

    monkeypatch.setattr(monitor.subprocess, "run", fake_run)

    messages, cursor, reset = monitor.read_journal(
        "vacuumed-cursor", datetime(2026, 8, 6, 12, tzinfo=UTC)
    )

    assert messages == ["recent"]
    assert cursor == "fresh-cursor"
    assert reset is True


def test_delivery_uses_primary_then_fallback(monkeypatch):
    settings = Settings(
        environment="production",
        chat_sandbox_slack_webhook_url="https://primary.test/hook",
        chat_sandbox_alert_fallback_webhook_url="https://fallback.test/hook",
    )
    now = datetime(2026, 8, 6, 12, tzinfo=UTC)
    primary = monitor.new_event("hf_provider_sustained_failure", now=now)
    fallback = monitor.new_event("chat_runtime_critical", now=now)
    calls = []

    async def fake_post(url, event, _settings):
        calls.append((url, event["signal"]))
        if event["signal"] == "chat_runtime_critical" and "primary" in url:
            raise httpx.ConnectError("synthetic failure")

    monkeypatch.setattr(monitor, "post_operational_alert", fake_post)
    state = {"events": [primary, fallback]}

    assert asyncio.run(monitor.deliver_pending(state, settings)) == 2
    assert primary["primary_delivery_state"] == "delivered"
    assert primary["fallback_delivery_state"] == "not_needed"
    assert fallback["primary_delivery_state"] == "failed"
    assert fallback["fallback_delivery_state"] == "delivered"
    assert calls == [
        ("https://primary.test/hook", "hf_provider_sustained_failure"),
        ("https://primary.test/hook", "chat_runtime_critical"),
        ("https://fallback.test/hook", "chat_runtime_critical"),
    ]
