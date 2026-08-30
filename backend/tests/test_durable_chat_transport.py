from __future__ import annotations

import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

from backend.loadtests.external_pi_fleet_core import FleetRunRefused


def test_transport_contract_import_does_not_preload_requests_before_locust():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import backend.loadtests.durable_chat_transport; "
                "raise SystemExit('requests' in sys.modules)"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def _spec(ordinal: int, workload: str):
    return SimpleNamespace(ordinal=ordinal, workload=workload)


class _Response:
    def __init__(self, status_code, chunks=(), payload=None):
        self.status_code = status_code
        self._chunks = chunks
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def iter_content(self, **_kwargs):
        yield from self._chunks

    def json(self):
        if self._payload is None:
            raise ValueError
        return self._payload


class _Session:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []
        self.cookies = SimpleNamespace(
            set=lambda *args, **kwargs: self.calls.append(("cookie", args, kwargs))
        )
        self.trust_env = True
        self.proxies = {"https": "https://proxy.invalid"}

    def post(self, url, **kwargs):
        self.calls.append(("post", url, kwargs))
        return next(self.responses)

    def get(self, url, **kwargs):
        self.calls.append(("get", url, kwargs))
        return next(self.responses)


def _frame(sequence: int, event: str, payload: dict) -> bytes:
    return (
        f"id: {sequence}\nevent: {event}\ndata: "
        + json.dumps({"type": event, **payload}, separators=(",", ":"))
        + "\n\n"
    ).encode()


def test_real_transport_posts_chat_stream_and_resumes_same_turn_without_leaking_content():
    from backend.loadtests.durable_chat_transport import (
        DurableChatTransportConfig,
        HttpSSEDurableChatTransport,
    )

    session_id = "00000000-0000-0000-0000-000000000001"
    request_id = "00000000-0000-0000-0000-000000000002"
    operation_id = "op-0001"
    session = _Session(
        (
            _Response(
                200,
                (
                    _frame(
                        1,
                        "stream_start",
                        {
                            "request_id": request_id,
                            "session_id": session_id,
                            "provider_execution": True,
                        },
                    ),
                ),
            ),
            _Response(
                200,
                (
                    _frame(2, "answer_delta", {"text": "TOP_SECRET_OUTPUT"}),
                    _frame(
                        3,
                        "tool_call",
                        {
                            "id": operation_id,
                            "name": "Bash",
                            "input": {"command": "TOP_SECRET_COMMAND"},
                        },
                    ),
                    _frame(4, "done", {"finish_reason": "success", "followups": []}),
                ),
            ),
        )
    )
    transport = HttpSSEDurableChatTransport(
        DurableChatTransportConfig(
            base_url="https://staging.paperswithcode.co",
            synthetic_cookies=("signed-cookie",),
            initial_model="gpt-5.6-luna@openai",
        ),
        session_factory=lambda: session,
    )

    evidence = transport.open_durable_stream(_spec(0, "bash"))

    posts = [call for call in session.calls if call[0] == "post"]
    assert len(posts) == 2
    assert {call[1] for call in posts} == {
        "https://staging.paperswithcode.co/api/v1/chat/stream"
    }
    first_body = posts[0][2]["json"]
    second_body = posts[1][2]["json"]
    assert first_body["session_id"] is None
    assert second_body["session_id"] == session_id
    assert first_body["client_message_id"] == second_body["client_message_id"]
    assert posts[0][2]["headers"] == {
        "Accept": "text/event-stream",
        "Origin": "https://staging.paperswithcode.co",
    }
    assert posts[1][2]["headers"] == {
        "Accept": "text/event-stream",
        "Origin": "https://staging.paperswithcode.co",
        "Last-Event-ID": "1",
    }
    assert session.trust_env is False
    assert session.proxies == {}
    assert evidence["outcome"] == "completed"
    assert evidence["model_starts"] == 1
    assert "operation_start_ids" not in evidence
    assert evidence["reconnects"] == evidence["reconnect_successes"] == 1
    assert "TOP_SECRET" not in repr(evidence)
    assert "/v1/shadow" not in repr(session.calls)


def test_real_transport_preserves_typed_immediate_429_without_queueing():
    from backend.loadtests.durable_chat_transport import (
        DurableChatTransportConfig,
        HttpSSEDurableChatTransport,
    )

    session = _Session((_Response(429, payload={"detail": {"code": "chat_overload"}}),))
    transport = HttpSSEDurableChatTransport(
        DurableChatTransportConfig(
            base_url="https://staging.paperswithcode.co",
            synthetic_cookies=("signed-cookie",),
            initial_model="gpt-5.6-luna@openai",
        ),
        session_factory=lambda: session,
    )

    evidence = transport.open_durable_stream(_spec(0, "admission_stream"))

    assert evidence["outcome"] == "refused"
    assert evidence["failure_code"] == "chat_overload"
    assert "queued_states" not in evidence


@pytest.mark.parametrize(
    "response",
    (
        _Response(429, payload={"detail": {"code": "unknown"}}),
        _Response(503, payload={"detail": {"code": "chat_overload"}}),
        _Response(200, (_frame(1, "queued", {"position": 1}),)),
        _Response(200, (b'event: done\ndata: {"type":"done"}\n\n',)),
    ),
)
def test_real_transport_rejects_untyped_queue_and_invalid_sse(response):
    from backend.loadtests.durable_chat_transport import (
        DurableChatTransportConfig,
        HttpSSEDurableChatTransport,
    )

    transport = HttpSSEDurableChatTransport(
        DurableChatTransportConfig(
            base_url="https://staging.paperswithcode.co",
            synthetic_cookies=("signed-cookie",),
            initial_model="gpt-5.6-luna@openai",
        ),
        session_factory=lambda: _Session((response,)),
    )

    with pytest.raises(FleetRunRefused):
        transport.open_durable_stream(_spec(0, "no_tool"))


def test_real_transport_rejects_a_truncated_sse_tail():
    from backend.loadtests.durable_chat_transport import (
        DurableChatTransportConfig,
        HttpSSEDurableChatTransport,
    )

    session = _Session(
        (
            _Response(
                200,
                (
                    _frame(
                        1,
                        "stream_start",
                        {
                            "request_id": "00000000-0000-0000-0000-000000000002",
                            "session_id": "00000000-0000-0000-0000-000000000001",
                            "provider_execution": True,
                        },
                    ),
                ),
            ),
            _Response(200, (b"id: 2\nevent: answer_delta\ndata: {",)),
        )
    )
    transport = HttpSSEDurableChatTransport(
        DurableChatTransportConfig(
            base_url="https://staging.paperswithcode.co",
            synthetic_cookies=("signed-cookie",),
            initial_model="gpt-5.6-luna@openai",
        ),
        session_factory=lambda: session,
    )

    with pytest.raises(FleetRunRefused, match="mid-event"):
        transport.open_durable_stream(_spec(0, "no_tool"))


def test_live_constructor_refuses_non_staging_hosts_and_injected_fakes():
    from backend.loadtests.durable_chat_transport import (
        DurableChatTransportConfig,
        create_live_durable_transport,
    )

    with pytest.raises(FleetRunRefused, match="exact staging origin"):
        DurableChatTransportConfig(
            base_url="https://paperswithcode.co",
            synthetic_cookies=("signed-cookie",),
            initial_model="gpt-5.6-luna@openai",
        )
    live = create_live_durable_transport(
        DurableChatTransportConfig(
            base_url="https://staging.paperswithcode.co",
            synthetic_cookies=("signed-cookie",),
            initial_model="gpt-5.6-luna@openai",
            qualification_run_id="run",
            admin_token="a" * 32,
        ),
        "32-functional-turns",
    )
    assert type(live).__name__ == "HttpSSEDurableChatTransport"


def test_modal_lifecycle_delta_and_protected_rate_are_window_bound_not_chat_latency():
    from backend.loadtests.external_pi_fleet_core import (
        ModalLifecycleSnapshot,
        ModalRateEvidence,
        aggregate_durable_profile,
        modal_lifecycle_delta,
        resolve_durable_profile,
        DurableTurnObservation,
    )

    before = ModalLifecycleSnapshot(
        captured_at_ms=1_000,
        creates=10,
        reuses=20,
        evictions=3,
        active_duration_ms=50_000,
        source="application_modal_lifecycle",
    )
    after = before.model_copy(
        update={
            "captured_at_ms": 2_000,
            "creates": 11,
            "reuses": 35,
            "evictions": 4,
            "active_duration_ms": 62_345,
        }
    )
    profile = resolve_durable_profile("32-functional-turns")
    observations = tuple(
        DurableTurnObservation(
            outcome="completed",
            ttft_ms=10,
            completion_ms=999,
            model_starts=1,
            terminal_cause="completed",
        )
        for _ in profile.workloads
    )

    report = aggregate_durable_profile(
        profile=profile,
        observations=observations,
        peak_memory_bytes=1,
        minimum_host_mem_available_bytes=2 * 1024**3,
        peak_cpu_percent=1.0,
        peak_active_backend_turns=32,
        peak_active_external_workers=4,
        peak_active_sandboxes=16,
        modal_lifecycle=modal_lifecycle_delta(before, after),
        modal_rate=ModalRateEvidence(
            microusd_per_second=25,
            source="protected_runtime",
            source_id="modal-staging-price-v1",
            release_id="0123456789ab-staging",
            attested_at_ms=1,
        ),
    )

    assert report.modal_creates == 1
    assert report.modal_reuses == 15
    assert report.modal_evictions == 1
    assert report.modal_active_ms == 12_345
    assert report.modal_active_ms != sum(item.completion_ms for item in observations)
    assert report.modal_rate_source == "protected_runtime"
    assert report.modal_estimated_cost_microusd == 309


def test_modal_lifecycle_refuses_missing_or_contradictory_snapshot_evidence():
    from backend.loadtests.external_pi_fleet_core import (
        ModalLifecycleSnapshot,
        modal_lifecycle_delta,
    )

    before = ModalLifecycleSnapshot(
        captured_at_ms=1_000,
        creates=2,
        reuses=2,
        evictions=2,
        active_duration_ms=2,
        source="application_modal_lifecycle",
    )
    for changes in (
        {"captured_at_ms": 1_000},
        {"captured_at_ms": 2_000, "creates": 1},
        {"captured_at_ms": 2_000, "active_duration_ms": 1},
    ):
        with pytest.raises(FleetRunRefused):
            modal_lifecycle_delta(before, before.model_copy(update=changes))


def test_http_durable_evidence_source_reads_exact_scoped_content_free_seam():
    from backend.loadtests.durable_chat_transport import (
        DurableChatTransportConfig,
        HttpDurableQualificationEvidenceSource,
    )

    session = _Session(
        (
            _Response(
                200,
                payload={
                    "expected_users": 32,
                    "admitted_turns": 32,
                    "terminal_turns": 32,
                    "queued_states": 0,
                    "stale_fences": 0,
                    "executor_starts": 16,
                    "duplicate_executor_starts": 0,
                    "workspace_creates": 1,
                    "workspace_reuses": 15,
                    "workspace_evictions": 0,
                    "billed_duration_ms": 4,
                    "source": "durable_qualification_records",
                },
            ),
        )
    )
    source = HttpDurableQualificationEvidenceSource(
        DurableChatTransportConfig(
            base_url="https://staging.paperswithcode.co",
            synthetic_cookies=("signed-cookie",),
            initial_model="gpt-5.6-luna@openai",
            qualification_run_id="run",
            admin_token="a" * 32,
        ),
        session_factory=lambda: session,
    )

    from datetime import UTC, datetime, timedelta

    started = datetime.now(UTC)
    snapshot = source.collect(
        "32-functional-turns",
        window_started_at=started,
        window_ended_at=started + timedelta(seconds=1),
    )

    post = next(call for call in session.calls if call[0] == "post")
    assert post[1] == (
        "https://staging.paperswithcode.co/api/v1/chat/admin/qualification-evidence"
    )
    assert post[2]["json"]["run_id"] == "run-f32"
    assert post[2]["headers"]["Origin"] == "https://staging.paperswithcode.co"
    assert snapshot.billed_duration_ms == 4
    assert "signed-cookie" not in repr(snapshot)


def test_modal_rate_has_no_code_default_and_requires_explicit_protected_input():
    from backend.loadtests.external_pi_fleet_core import load_modal_rate_evidence

    with pytest.raises(FleetRunRefused, match="explicit protected Modal rate"):
        load_modal_rate_evidence({}, expected_release="0123456789ab-staging")

    rate = load_modal_rate_evidence(
        {
            "PWC_MODAL_EXECUTOR_RATE_MICROUSD_PER_SECOND": "25",
            "PWC_MODAL_EXECUTOR_RATE_SOURCE_ID": "modal-staging-price-v1",
            "PWC_MODAL_EXECUTOR_RATE_ATTESTED_AT_MS": "1",
            "PWC_RELEASE_ID": "0123456789ab-staging",
        },
        expected_release="0123456789ab-staging",
    )

    assert rate.microusd_per_second == 25
    assert rate.source == "protected_runtime"
