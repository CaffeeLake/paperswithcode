from __future__ import annotations

import json

import pytest

from backend.loadtests.chat_core import (
    CONFIRMATION,
    PROFILES,
    BoundedSSEStream,
    RunRefused,
    SSEParseError,
    SSEParser,
    StreamMetricTracker,
    build_turn_request,
    classify_event,
    classify_refusal,
    classify_refusal_bytes,
    load_run_config,
)


def test_sse_parser_reassembles_chunked_crlf_and_multiline_data() -> None:
    parser = SSEParser(max_event_bytes=256)

    assert parser.feed(b": keepalive\r\nda") == []
    assert parser.feed(b'ta: {"type":"answer_delta",\r\n') == []
    assert parser.feed(b'data: "text":"bounded"}\r\n\r\n') == [
        {"type": "answer_delta", "text": "bounded"}
    ]
    assert parser.close() == []


def test_sse_parser_ignores_done_sentinel_and_rejects_oversized_event() -> None:
    parser = SSEParser(max_event_bytes=20)

    assert parser.feed(b"data: [DONE]\n\n") == []
    with pytest.raises(SSEParseError, match="exceeds 20 bytes"):
        parser.feed(b"data: " + b"x" * 21)


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        ({"type": "stream_start"}, "admission"),
        ({"type": "done"}, "terminal"),
        ({"type": "error", "code": "provider_error"}, "stream_error"),
        ({"type": "error", "code": "account_busy"}, "account_busy"),
        ({"type": "error", "code": "chat_overload"}, "overload"),
    ],
)
def test_event_classification_uses_only_content_free_labels(event, expected) -> None:
    event["message"] = "operator payload must never become a label"

    assert classify_event(event) == expected


def test_sse_parser_rejects_non_object_json_without_echoing_content() -> None:
    secret = "synthetic-secret-content"
    parser = SSEParser()

    with pytest.raises(SSEParseError) as exc_info:
        parser.feed(f"data: {json.dumps(secret)}\n\n".encode())

    assert secret not in str(exc_info.value)


def _valid_environment(**overrides: str) -> dict[str, str]:
    environment = {
        "PWC_LOADTEST_HOST": "https://staging.paperswithcode.co",
        "PWC_LOADTEST_CONFIRM": CONFIRMATION,
        "PWC_LOADTEST_PROFILE": "bridge-smoke",
        "PWC_LOADTEST_SYNTHETIC_COOKIES": json.dumps(["cookie-a", "cookie-b"]),
        "PWC_LOADTEST_MAX_USERS": "2",
        "PWC_LOADTEST_MAX_SPEND_USD": "0",
        "PWC_LOADTEST_MAX_PROMPT_CHARS": "128",
        "PWC_LOADTEST_MAX_OUTPUT_CHARS": "4096",
    }
    environment.update(overrides)
    return environment


@pytest.mark.parametrize(
    "host",
    [
        "https://paperswithcode.co",
        "http://staging.paperswithcode.co",
        "https://staging.paperswithcode.co.evil.test",
        "https://staging.paperswithcode.co/chat",
        "https://user@staging.paperswithcode.co",
    ],
)
def test_run_config_refuses_every_non_exact_staging_origin(host: str) -> None:
    with pytest.raises(RunRefused, match="exact staging origin"):
        load_run_config(_valid_environment(PWC_LOADTEST_HOST=host))


def test_run_config_requires_explicit_confirmation_and_synthetic_cookies() -> None:
    with pytest.raises(RunRefused, match="confirmation"):
        load_run_config(_valid_environment(PWC_LOADTEST_CONFIRM=""))
    with pytest.raises(RunRefused, match="synthetic session cookies"):
        load_run_config(_valid_environment(PWC_LOADTEST_SYNTHETIC_COOKIES="[]"))


def test_independent_account_profile_refuses_duplicate_synthetic_cookies() -> None:
    duplicate = json.dumps(["cookie-a", "cookie-a"])

    with pytest.raises(RunRefused, match="distinct synthetic session cookies"):
        load_run_config(_valid_environment(PWC_LOADTEST_SYNTHETIC_COOKIES=duplicate))


def test_bridge_smoke_is_bounded_and_connection_only() -> None:
    config = load_run_config(_valid_environment())

    assert config.profile.name == "bridge-smoke"
    assert config.profile.users == 2
    assert config.profile.cohort == "connection-only"
    assert config.max_users == 2
    assert config.max_spend_usd == 0
    assert config.max_prompt_chars == 128
    assert config.max_output_chars == 4096
    assert config.protected_spend_cap_usd is None


def _provider_environment(**overrides: str) -> dict[str, str]:
    return _valid_environment(
        PWC_LOADTEST_PROFILE="safe-cli",
        PWC_LOADTEST_MAX_SPEND_USD="1.25",
        **overrides,
    )


def test_provider_profile_refuses_missing_protected_daily_spend_cap() -> None:
    with pytest.raises(RunRefused, match="protected daily spend cap is required"):
        load_run_config(_provider_environment())


@pytest.mark.parametrize("value", ["not-money", "nan", "0", "-1"])
def test_provider_profile_refuses_malformed_protected_daily_spend_cap(
    value: str,
) -> None:
    with pytest.raises(RunRefused, match="protected daily spend cap is invalid"):
        load_run_config(_provider_environment(PWC_CHAT_OPENAI_DAILY_BUDGET_USD=value))


def test_provider_profile_refuses_mismatched_protected_daily_spend_cap() -> None:
    with pytest.raises(RunRefused, match="does not match declared envelope"):
        load_run_config(_provider_environment(PWC_CHAT_OPENAI_DAILY_BUDGET_USD="2.50"))


def test_provider_profile_accepts_exact_protected_daily_spend_cap() -> None:
    config = load_run_config(
        _provider_environment(PWC_CHAT_OPENAI_DAILY_BUDGET_USD="1.25")
    )

    assert config.max_spend_usd == 1.25
    assert config.protected_spend_cap_usd == 1.25


def test_provider_profile_requires_all_loaded_provider_caps_to_align() -> None:
    with pytest.raises(RunRefused, match="does not match declared envelope"):
        load_run_config(
            _provider_environment(
                PWC_CHAT_OPENAI_DAILY_BUDGET_USD="1.25",
                PWC_CHAT_OPENROUTER_DAILY_BUDGET_USD="2.00",
            )
        )


def test_connection_only_profile_refuses_nonzero_spend_envelope() -> None:
    with pytest.raises(RunRefused, match="zero spend envelope"):
        load_run_config(_valid_environment(PWC_LOADTEST_MAX_SPEND_USD="0.01"))


def test_profiles_define_every_requested_content_free_cohort() -> None:
    assert set(PROFILES) == {
        "bridge-smoke",
        "steady-10",
        "steady-25",
        "steady-50",
        "steady-100",
        "burst",
        "same-account-contention",
        "reconnect",
        "safe-cli",
        "general-bash",
        "overload",
        "connection-only",
    }
    assert {
        PROFILES[name].users
        for name in ("steady-10", "steady-25", "steady-50", "steady-100")
    } == {
        10,
        25,
        50,
        100,
    }
    assert all(profile.metric_label.isascii() for profile in PROFILES.values())


def test_definition_only_scaled_profile_cannot_be_armed() -> None:
    with pytest.raises(RunRefused, match="definition-only"):
        load_run_config(
            _valid_environment(
                PWC_LOADTEST_PROFILE="steady-10",
                PWC_LOADTEST_MAX_USERS="10",
                PWC_LOADTEST_MAX_SPEND_USD="1",
            )
        )


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"PWC_LOADTEST_MAX_USERS": "1"}, "user envelope"),
        ({"PWC_LOADTEST_MAX_SPEND_USD": ""}, "spend envelope"),
        ({"PWC_LOADTEST_MAX_PROMPT_CHARS": "1000000"}, "prompt bound"),
        ({"PWC_LOADTEST_MAX_OUTPUT_CHARS": "1000000"}, "output bound"),
    ],
)
def test_run_config_refuses_missing_or_excessive_envelopes(override, message) -> None:
    with pytest.raises(RunRefused, match=message):
        load_run_config(_valid_environment(**override))


@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_run_config_refuses_non_finite_spend_envelope(value: str) -> None:
    with pytest.raises(RunRefused, match="finite"):
        load_run_config(_valid_environment(PWC_LOADTEST_MAX_SPEND_USD=value))


def test_stream_tracker_keeps_first_event_and_terminal_latency_separate() -> None:
    tracker = StreamMetricTracker()

    first = tracker.observe({"type": "stream_start"}, elapsed_ms=17)
    middle = tracker.observe(
        {"type": "answer_delta", "text": "never a metric label"}, elapsed_ms=23
    )
    terminal = tracker.observe({"type": "done"}, elapsed_ms=91)

    assert [(metric.name, metric.elapsed_ms) for metric in first] == [
        ("chat.first_event", 17),
        ("chat.admission", 17),
    ]
    assert middle == []
    assert [(metric.name, metric.elapsed_ms) for metric in terminal] == [
        ("chat.terminal", 91)
    ]


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"detail": {"code": "account_busy", "message": "busy"}}, "account_busy"),
        ({"detail": {"code": "chat_overload", "message": "full"}}, "overload"),
        ({"detail": {"code": "chat_capacity", "message": "legacy"}}, "overload"),
        ({"detail": "Unauthorized"}, "stream_error"),
    ],
)
def test_http_refusal_classification_preserves_typed_capacity(
    payload, expected
) -> None:
    assert classify_refusal(payload) == expected


def test_http_refusal_bytes_are_bounded_and_content_free() -> None:
    overload = b'{"detail":{"code":"chat_overload","message":"full"}}'

    assert classify_refusal_bytes(overload, max_bytes=128) == "overload"
    assert classify_refusal_bytes(b"x" * 129, max_bytes=128) == "stream_error"
    assert classify_refusal_bytes(b"not-json", max_bytes=128) == "stream_error"


def test_tracker_records_stream_error_metric() -> None:
    tracker = StreamMetricTracker()

    assert [
        metric.name
        for metric in tracker.observe(
            {"type": "error", "code": "provider_error"}, elapsed_ms=50
        )
    ] == ["chat.first_event", "chat.stream_error"]


def test_replayed_stream_start_followed_by_parse_failure_cannot_pass() -> None:
    stream = BoundedSSEStream(max_output_chars=128, replay=True)

    batch = stream.feed(
        b'data: {"type":"stream_start","session_id":"synthetic"}\n\n',
        elapsed_ms=11,
    )
    assert [metric.name for metric in batch.metrics] == ["chat.first_replay"]

    with pytest.raises(SSEParseError, match="valid JSON"):
        stream.feed(b"data: not-json\n\n", elapsed_ms=19)

    assert stream.successful_terminal is False


def test_valid_replay_consumes_through_terminal_with_separate_metrics() -> None:
    stream = BoundedSSEStream(max_output_chars=128, replay=True)

    first = stream.feed(b'data: {"type":"stream_start"}\n\n', elapsed_ms=7)
    middle = stream.feed(b'data: {"type":"answer_delta","text":"RE', elapsed_ms=15)
    assert middle.metrics == []
    terminal = stream.feed(b'ADY"}\n\ndata: {"type":"done"}\n\n', elapsed_ms=31)
    tail = stream.close(elapsed_ms=31)

    assert [(metric.name, metric.elapsed_ms) for metric in first.metrics] == [
        ("chat.first_replay", 7)
    ]
    assert [(metric.name, metric.elapsed_ms) for metric in terminal.metrics] == [
        ("chat.terminal", 31)
    ]
    assert tail.metrics == []
    assert stream.successful_terminal is True


def test_replay_without_terminal_is_not_successful() -> None:
    stream = BoundedSSEStream(max_output_chars=128, replay=True)
    stream.feed(b'data: {"type":"stream_start"}\n\n', elapsed_ms=5)

    stream.close(elapsed_ms=8)

    assert stream.successful_terminal is False


def test_connection_only_profile_cannot_construct_an_admitted_turn() -> None:
    with pytest.raises(RunRefused, match="does not admit chat turns"):
        build_turn_request(
            PROFILES["bridge-smoke"],
            client_message_id="synthetic-request",
            max_prompt_chars=128,
        )


@pytest.mark.parametrize("profile_name", ["safe-cli", "general-bash", "reconnect"])
def test_executable_profile_request_is_bounded_and_disables_search(
    profile_name: str,
) -> None:
    body = build_turn_request(
        PROFILES[profile_name],
        client_message_id="synthetic-request",
        max_prompt_chars=128,
    )

    assert 0 < len(body["message"]) <= 128
    assert body["client_message_id"] == "synthetic-request"
    assert body["session_id"] is None
    assert body["web_search_enabled"] is False


def test_executable_profile_refuses_a_prompt_bound_below_its_fixture() -> None:
    with pytest.raises(RunRefused, match="prompt fixture exceeds"):
        build_turn_request(
            PROFILES["general-bash"],
            client_message_id="synthetic-request",
            max_prompt_chars=4,
        )
