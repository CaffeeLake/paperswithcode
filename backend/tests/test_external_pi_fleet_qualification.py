from __future__ import annotations

import importlib
import importlib.util
import json
import signal
import subprocess
import threading
import time
from collections import Counter
from dataclasses import FrozenInstanceError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.loadtests.external_pi_fleet_core import (
    MIN_PROJECTED_MEM_AVAILABLE_BYTES,
    CleanupEvidence,
    FleetReplica,
    FleetRoundReport,
    FleetRunRefused,
    FleetSafetyConfig,
    FleetShape,
    ForbiddenActivity,
    HostResourceSnapshot,
    PortState,
    ResourceEvidence,
    ResourcePreflight,
    UnitResourceEvidence,
    WorkerEvidence,
    aggregate_round,
    build_completed_shape_report,
    build_external_pi_fleet_request,
    build_final_report,
    build_resource_refused_shape_report,
    classify_external_pi_fleet_response,
    evaluate_resource_preflight,
    publish_fleet_report,
    qualification_unit_names,
    resolve_fleet_shape,
    route_ordinal,
    validate_fleet_preflight,
)
from backend.loadtests.external_pi_shadow_core import (
    BaselineObservation,
    build_external_pi_baseline_request,
    classify_external_pi_baseline_response,
)
from deploy.external_pi_qualification_contract import (
    QUALIFICATION_PORTS,
    QUALIFICATION_SUPERVISOR_UNITS,
    QUALIFICATION_WORKER_IDS,
    QUALIFICATION_WORKER_UNITS,
)


def test_fleet_shapes_have_exact_allowlisted_topology_and_capacity():
    expected = {
        "5x32": (5, 32, 160, 128),
        "8x16": (8, 16, 128, 112),
        "16x8": (16, 8, 128, 120),
    }

    for name, capacities in expected.items():
        shape = resolve_fleet_shape(name)
        workers, sessions, aggregate, survivor = capacities
        assert shape.worker_count == workers
        assert shape.sessions_per_worker == sessions
        assert shape.aggregate_capacity == aggregate
        assert shape.post_loss_capacity == survivor
        assert [replica.worker_id for replica in shape.replicas] == [
            f"staging-qualification-{index:02d}" for index in range(workers)
        ]
        assert [replica.port for replica in shape.replicas] == list(
            range(8780, 8780 + workers)
        )

    with pytest.raises(FleetRunRefused, match="allowlisted fleet shape"):
        resolve_fleet_shape("10x10")

    with pytest.raises(FrozenInstanceError):
        resolve_fleet_shape("5x32").worker_count = 6


def test_ordinal_routing_is_deterministic_and_balanced_after_loss():
    healthy = resolve_fleet_shape("8x16").replicas
    survivor = healthy[1:]

    assert route_ordinal(0, healthy) == healthy[0]
    assert route_ordinal(8, healthy) == healthy[0]
    assert route_ordinal(99, healthy) == healthy[3]
    assert route_ordinal(0, survivor) == survivor[0]

    counts = Counter(route_ordinal(ordinal, survivor) for ordinal in range(100))
    assert max(counts.values()) - min(counts.values()) == 1

    with pytest.raises(ValueError, match="ordinal"):
        route_ordinal(100, healthy)
    with pytest.raises(FleetRunRefused, match="allowlisted replicas"):
        route_ordinal(0, (FleetReplica(healthy[0].worker_id, healthy[1].port),))
    with pytest.raises(FleetRunRefused, match="allowlisted replicas"):
        route_ordinal(0, (healthy[0], healthy[0]))


def _safety_config(**updates) -> FleetSafetyConfig:
    values = {
        "environment": "staging",
        "requested_release": "0123456789ab-staging",
        "active_release": "0123456789ab-staging",
        "external_admission_enabled": False,
        "executor_routing_enabled": False,
        "remote_execution_enabled": False,
        "active_worker_id": "staging-blue",
        "active_worker_healthy": True,
        "worker_token": "protected-worker-token",
    }
    values.update(updates)
    return FleetSafetyConfig(**values)


def test_preflight_requires_exact_staging_release_and_disabled_flags():
    shape = resolve_fleet_shape("5x32")
    ports = tuple(
        PortState(replica.port, "127.0.0.1", True) for replica in shape.replicas
    )

    validate_fleet_preflight(_safety_config(), shape, ports)
    assert "protected-worker-token" not in repr(_safety_config())

    unsafe = (
        {"environment": "production"},
        {"requested_release": "fedcba987654-staging"},
        {"external_admission_enabled": True},
        {"executor_routing_enabled": True},
        {"remote_execution_enabled": True},
        {"active_worker_id": "staging-qualification-00"},
        {"active_worker_healthy": False},
    )
    for updates in unsafe:
        with pytest.raises(FleetRunRefused, match="staging|release|disabled"):
            validate_fleet_preflight(_safety_config(**updates), shape, ports)


def test_preflight_requires_every_allowlisted_port_free_on_loopback():
    shape = resolve_fleet_shape("5x32")
    ports = [PortState(replica.port, "127.0.0.1", True) for replica in shape.replicas]

    ports[2] = PortState(ports[2].port, "0.0.0.0", True)
    with pytest.raises(FleetRunRefused, match="free loopback ports"):
        validate_fleet_preflight(_safety_config(), shape, tuple(ports))

    ports[2] = PortState(ports[2].port, "127.0.0.1", False)
    with pytest.raises(FleetRunRefused, match="free loopback ports"):
        validate_fleet_preflight(_safety_config(), shape, tuple(ports))


def test_preflight_rejects_forged_topology_even_with_free_loopback_ports():
    forged = FleetShape(
        name="10x10",
        worker_count=1,
        sessions_per_worker=100,
        replicas=(FleetReplica("staging-qualification-00", 8780),),
    )
    ports = (PortState(8780, "127.0.0.1", True),)

    with pytest.raises(FleetRunRefused, match="allowlisted fleet shape"):
        validate_fleet_preflight(_safety_config(), forged, ports)


def test_resource_preflight_preserves_1_5_gib_and_guards_cpu():
    one_gib = 1024**3
    accepted = evaluate_resource_preflight(
        HostResourceSnapshot(
            mem_available_bytes=3 * one_gib,
            projected_additional_bytes=MIN_PROJECTED_MEM_AVAILABLE_BYTES,
            cpu_percent=79.9,
            cpu_guard_percent=80.0,
        )
    )
    assert accepted.status == "passed"
    assert accepted.projected_mem_available_bytes == MIN_PROJECTED_MEM_AVAILABLE_BYTES

    low_memory = evaluate_resource_preflight(
        HostResourceSnapshot(
            mem_available_bytes=3 * one_gib - 1,
            projected_additional_bytes=MIN_PROJECTED_MEM_AVAILABLE_BYTES,
            cpu_percent=20.0,
            cpu_guard_percent=80.0,
        )
    )
    saturated = evaluate_resource_preflight(
        HostResourceSnapshot(
            mem_available_bytes=4 * one_gib,
            projected_additional_bytes=one_gib,
            cpu_percent=80.0,
            cpu_guard_percent=80.0,
        )
    )
    assert low_memory.status == "resource_refused"
    assert saturated.status == "resource_refused"

    with pytest.raises(ValueError, match="resource preflight evidence"):
        ResourcePreflight("passed", -1, 20.0, 80.0)

    with pytest.raises(ValueError, match="resource inputs"):
        HostResourceSnapshot(2**63, 0, 20.0, 80.0)
    with pytest.raises(ValueError, match="resource inputs"):
        HostResourceSnapshot(2**63 - 1, 2**63, 20.0, 80.0)
    with pytest.raises(ValueError, match="resource preflight evidence"):
        ResourcePreflight("passed", 2**63, 20.0, 80.0)


def test_fleet_workload_reuses_shadow_payload_and_classifier_contracts():
    assert build_external_pi_fleet_request is build_external_pi_baseline_request
    assert classify_external_pi_fleet_response is classify_external_pi_baseline_response

    request = build_external_pi_fleet_request(0, "canonical-runtime-prompt")
    assert len(request.transcript_entries) == 2_000
    assert request.tool_names == ()


def _round(name: str, *, latency_ms: int = 100, activity=None):
    return aggregate_round(
        name=name,
        observations=tuple(
            BaselineObservation("compatible", latency_ms) for _ in range(100)
        ),
        protocol_errors=0,
        transport_errors=0,
        forbidden_activity=activity or ForbiddenActivity(),
    )


def _cleanup(**updates) -> CleanupEvidence:
    values = {
        "drain_proven": True,
        "registry_offline": True,
        "supervisors_stopped_before_workers": True,
        "units_removed": True,
        "status_files_removed": True,
        "ports_free": True,
        "processes_gone": True,
    }
    values.update(updates)
    return CleanupEvidence(**values)


def _unit_resources(shape_name: str) -> tuple[UnitResourceEvidence, ...]:
    return tuple(
        UnitResourceEvidence(
            unit_name=unit_name,
            peak_memory_bytes=100_000_000,
            peak_cpu_percent=10.0,
            peak_tasks=4,
        )
        for unit_name in qualification_unit_names(resolve_fleet_shape(shape_name))
    )


def _resources(shape_name: str = "5x32", **updates) -> ResourceEvidence:
    values = {
        "peak_memory_bytes": 300_000_000,
        "peak_cpu_percent": 40.0,
        "peak_tasks": 20,
        "minimum_host_mem_available_bytes": 2 * 1024**3,
        "unit_peaks": _unit_resources(shape_name),
    }
    values.update(updates)
    return ResourceEvidence(**values)


def _passed_resource_preflight():
    return evaluate_resource_preflight(
        HostResourceSnapshot(
            mem_available_bytes=3 * 1024**3,
            projected_additional_bytes=1024**3,
            cpu_percent=20.0,
            cpu_guard_percent=80.0,
        )
    )


def _workers(shape_name: str) -> tuple[WorkerEvidence, ...]:
    shape = resolve_fleet_shape(shape_name)
    return tuple(
        WorkerEvidence(
            worker_id=replica.worker_id,
            port=replica.port,
            generation=index + 1,
            maximum_sessions=shape.sessions_per_worker,
        )
        for index, replica in enumerate(shape.replicas)
    )


def test_round_aggregation_requires_100_compatible_fast_content_free_observations():
    passing = _round("healthy", latency_ms=3_000)
    assert passing.observations == passing.compatible == 100
    assert passing.p95_ms == passing.p99_ms == 3_000
    assert passing.passed is True

    capacity = aggregate_round(
        name="survivor",
        observations=(BaselineObservation("compatible", 50),) * 99
        + (BaselineObservation("capacity", 50),),
        protocol_errors=0,
        transport_errors=0,
        forbidden_activity=ForbiddenActivity(),
    )
    slow_p95 = aggregate_round(
        name="healthy",
        observations=(BaselineObservation("compatible", 10),) * 94
        + (BaselineObservation("compatible", 3_001),) * 6,
        protocol_errors=0,
        transport_errors=0,
        forbidden_activity=ForbiddenActivity(),
    )
    slow_p99 = aggregate_round(
        name="healthy",
        observations=(BaselineObservation("compatible", 10),) * 98
        + (BaselineObservation("compatible", 5_001),) * 2,
        protocol_errors=0,
        transport_errors=0,
        forbidden_activity=ForbiddenActivity(),
    )
    forbidden = _round("healthy", activity=ForbiddenActivity(model_calls=1))
    assert capacity.passed is False
    assert slow_p95.passed is False
    assert slow_p99.p95_ms == 10 and slow_p99.p99_ms == 5_001
    assert slow_p99.passed is False
    assert forbidden.passed is False


def test_round_aggregation_accounts_for_protocol_and_transport_errors():
    observations = (BaselineObservation("compatible", 10),) * 98 + (
        BaselineObservation("error", 10),
        BaselineObservation("error", 10),
    )
    report = aggregate_round(
        name="healthy",
        observations=observations,
        protocol_errors=1,
        transport_errors=1,
        forbidden_activity=ForbiddenActivity(),
    )
    assert report.protocol_errors == 1
    assert report.transport_errors == 1
    assert report.passed is False


def test_round_report_rejects_forged_pass_with_contradictory_counts():
    with pytest.raises(ValidationError, match="round counts are inconsistent"):
        FleetRoundReport(
            name="healthy",
            observations=1,
            compatible=100,
            capacity_rejections=0,
            protocol_errors=0,
            transport_errors=0,
            p95_ms=10,
            p99_ms=10,
            forbidden_activity=ForbiddenActivity(),
        )

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        FleetRoundReport(
            name="healthy",
            observations=100,
            compatible=100,
            capacity_rejections=0,
            protocol_errors=0,
            transport_errors=0,
            p95_ms=10,
            p99_ms=10,
            forbidden_activity=ForbiddenActivity(),
            passed=True,
        )


def test_shape_reports_require_both_rounds_survivor_capacity_and_cleanup():
    shape = resolve_fleet_shape("5x32")
    report = build_completed_shape_report(
        shape=shape,
        healthy=_round("healthy"),
        survivor=_round("survivor"),
        workers=_workers(shape.name),
        removed_worker_id=shape.replicas[0].worker_id,
        resources=_resources(),
        resource_preflight=_passed_resource_preflight(),
        cleanup=_cleanup(),
    )
    assert report.aggregate_capacity == 160
    assert report.post_loss_capacity == 128
    assert [worker.port for worker in report.workers] == list(range(8780, 8785))
    assert report.overall_passed is True

    failed_cleanup = build_completed_shape_report(
        shape=shape,
        healthy=_round("healthy"),
        survivor=_round("survivor"),
        workers=_workers(shape.name),
        removed_worker_id=shape.replicas[0].worker_id,
        resources=_resources(),
        resource_preflight=_passed_resource_preflight(),
        cleanup=_cleanup(ports_free=False),
    )
    assert failed_cleanup.cleanup_passed is False
    assert failed_cleanup.overall_passed is False

    forged_summary = failed_cleanup.model_copy(
        update={"cleanup_passed": True, "overall_passed": True}
    )
    forged_final = build_final_report(
        release_id="0123456789ab-staging",
        runtime_id="external-pi-runtime-1",
        shapes=(forged_summary,),
    )
    assert forged_final.preferred_shape is None

    contradictory_evidence = report.model_copy(update={"worker_count": 16})
    with pytest.raises(FleetRunRefused, match="shape report evidence"):
        build_final_report(
            release_id="0123456789ab-staging",
            runtime_id="external-pi-runtime-1",
            shapes=(contradictory_evidence,),
        )

    with pytest.raises(FleetRunRefused, match="resource preflight"):
        build_completed_shape_report(
            shape=shape,
            healthy=_round("healthy"),
            survivor=_round("survivor"),
            workers=_workers(shape.name),
            removed_worker_id=shape.replicas[0].worker_id,
            resources=_resources(),
            resource_preflight=evaluate_resource_preflight(
                HostResourceSnapshot(
                    mem_available_bytes=2 * 1024**3,
                    projected_additional_bytes=1024**3,
                    cpu_percent=20.0,
                    cpu_guard_percent=80.0,
                )
            ),
            cleanup=_cleanup(),
        )

    with pytest.raises(FleetRunRefused, match="per-unit resource evidence"):
        build_completed_shape_report(
            shape=shape,
            healthy=_round("healthy"),
            survivor=_round("survivor"),
            workers=_workers(shape.name),
            removed_worker_id=shape.replicas[0].worker_id,
            resources=_resources(unit_peaks=_unit_resources(shape.name)[:-1]),
            resource_preflight=_passed_resource_preflight(),
            cleanup=_cleanup(),
        )


def test_resource_refusal_is_bounded_evidence_and_never_a_pass():
    shape = resolve_fleet_shape("16x8")
    refusal = evaluate_resource_preflight(
        HostResourceSnapshot(
            mem_available_bytes=2 * 1024**3,
            projected_additional_bytes=1024**3,
            cpu_percent=20.0,
            cpu_guard_percent=80.0,
        )
    )
    report = build_resource_refused_shape_report(shape, refusal, _cleanup())
    assert report.status == "resource_refused"
    assert report.healthy is None and report.survivor is None
    assert report.overall_passed is False


def _completed_shape(name: str, *, memory: int, cpu: float, latency: int):
    shape = resolve_fleet_shape(name)
    return build_completed_shape_report(
        shape=shape,
        healthy=_round("healthy", latency_ms=latency),
        survivor=_round("survivor", latency_ms=latency),
        workers=_workers(name),
        removed_worker_id=shape.replicas[0].worker_id,
        resources=_resources(
            name,
            peak_memory_bytes=memory,
            peak_cpu_percent=cpu,
        ),
        resource_preflight=_passed_resource_preflight(),
        cleanup=_cleanup(),
    )


def _preferred(*reports) -> str | None:
    return build_final_report(
        release_id="0123456789ab-staging",
        runtime_id="external-pi-runtime-1",
        shapes=reports,
    ).preferred_shape


def test_final_selection_prefers_lower_measured_memory_first():
    assert (
        _preferred(
            _completed_shape("5x32", memory=200, cpu=10.0, latency=10),
            _completed_shape("8x16", memory=100, cpu=90.0, latency=1_000),
        )
        == "8x16"
    )


def test_final_selection_uses_cpu_when_memory_ties():
    assert (
        _preferred(
            _completed_shape("5x32", memory=100, cpu=20.0, latency=10),
            _completed_shape("8x16", memory=100, cpu=10.0, latency=1_000),
        )
        == "8x16"
    )


def test_final_selection_uses_latency_when_memory_and_cpu_tie():
    assert (
        _preferred(
            _completed_shape("5x32", memory=100, cpu=10.0, latency=20),
            _completed_shape("8x16", memory=100, cpu=10.0, latency=10),
        )
        == "8x16"
    )


def test_final_selection_uses_worker_count_as_last_tiebreaker():
    assert (
        _preferred(
            _completed_shape("16x8", memory=100, cpu=10.0, latency=10),
            _completed_shape("5x32", memory=100, cpu=10.0, latency=10),
            _completed_shape("8x16", memory=100, cpu=10.0, latency=10),
        )
        == "5x32"
    )


def test_final_report_is_content_free_atomic_and_mode_0600(tmp_path: Path, monkeypatch):
    shape = resolve_fleet_shape("5x32")
    shape_report = build_completed_shape_report(
        shape=shape,
        healthy=_round("healthy"),
        survivor=_round("survivor"),
        workers=_workers(shape.name),
        removed_worker_id=shape.replicas[0].worker_id,
        resources=_resources(),
        resource_preflight=_passed_resource_preflight(),
        cleanup=_cleanup(),
    )
    final = build_final_report(
        release_id="0123456789ab-staging",
        runtime_id="external-pi-runtime-1",
        shapes=(shape_report,),
    )
    destination = tmp_path / "fleet.json"
    destination.write_text('{"previous":true}\n', encoding="utf-8")
    publish_fleet_report(final, destination, tmp_path)

    payload = destination.read_text(encoding="utf-8")
    assert json.loads(payload)["preferred_shape"] == "5x32"
    assert destination.stat().st_mode & 0o777 == 0o600
    for protected in (
        "protected-worker-token",
        "canonical-runtime-prompt",
        "request-body",
        "response-body",
        "exception-text",
    ):
        assert protected not in payload


def test_atomic_publication_failure_preserves_previous_report(
    tmp_path: Path, monkeypatch
):
    shape = resolve_fleet_shape("5x32")
    report = build_final_report(
        release_id="0123456789ab-staging",
        runtime_id="external-pi-runtime-1",
        shapes=(
            build_completed_shape_report(
                shape=shape,
                healthy=_round("healthy"),
                survivor=_round("survivor"),
                workers=_workers(shape.name),
                removed_worker_id=shape.replicas[0].worker_id,
                resources=_resources(),
                resource_preflight=_passed_resource_preflight(),
                cleanup=_cleanup(),
            ),
        ),
    )
    destination = tmp_path / "fleet.json"
    previous = '{"previous":true}\n'
    destination.write_text(previous, encoding="utf-8")

    def fail_replace(_source, _destination):
        raise OSError("replace failed")

    monkeypatch.setattr(
        "backend.loadtests.external_pi_fleet_core.os.replace", fail_replace
    )
    with pytest.raises(OSError, match="replace failed"):
        publish_fleet_report(report, destination, tmp_path)
    assert destination.read_text(encoding="utf-8") == previous


def test_fleet_locust_adapter_import_is_quiet(capsys, recwarn):
    if importlib.util.find_spec("locust") is None:
        return

    importlib.import_module("backend.loadtests.external_pi_fleet_locustfile")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert not recwarn, [str(warning.message) for warning in recwarn]


def test_fleet_locust_requires_one_local_exact_hundred_user_runner(monkeypatch):
    if importlib.util.find_spec("locust") is None:
        return
    adapter = importlib.import_module("backend.loadtests.external_pi_fleet_locustfile")
    shape = resolve_fleet_shape("5x32")
    adapter.configure_fleet_round(
        replicas=shape.replicas,
        prompt="canonical-runtime-prompt",
        token="protected-worker-token",
    )

    environment = SimpleNamespace(
        runner=object(),
        parsed_options=SimpleNamespace(num_users=100, spawn_rate=100.0),
        host=None,
    )
    with pytest.raises(FleetRunRefused, match="one local Locust runner"):
        adapter._start(environment)

    environment.runner = object.__new__(adapter.LocalRunner)
    environment.runner.greenlet = None
    for users, spawn_rate, host in (
        (99, 100.0, None),
        (100, 99.0, None),
        (100, 100.0, "https://staging.paperswithcode.co"),
    ):
        environment.parsed_options = SimpleNamespace(
            num_users=users, spawn_rate=spawn_rate
        )
        environment.host = host
        with pytest.raises(FleetRunRefused, match="exactly 100|must not accept"):
            adapter._start(environment)


def test_fleet_locust_routes_each_one_shot_user_directly_without_proxy_or_redirect(
    monkeypatch,
):
    if importlib.util.find_spec("locust") is None:
        return
    adapter = importlib.import_module("backend.loadtests.external_pi_fleet_locustfile")
    shape = resolve_fleet_shape("5x32")

    class Response:
        status_code = 503

        def __init__(self):
            self.request_meta = {"name": "external_pi.error"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def json(self):
            return {"code": "shadow_capacity"}

        def success(self):
            return None

        def failure(self, _message):
            return None

    class Client:
        def __init__(self):
            self.trust_env = True
            self.proxies = {"http": "http://proxy.invalid"}
            self.calls = []

        def post(self, url, **kwargs):
            self.calls.append({"url": url, **kwargs})
            return Response()

    adapter.configure_fleet_round(
        replicas=shape.replicas,
        prompt="canonical-runtime-prompt",
        token="protected-worker-token",
    )
    monkeypatch.setattr(adapter, "_ordinals", iter((0, 5)))
    client = Client()
    user = object.__new__(adapter.ExternalPiFleetUser)
    user.client = client
    user.on_start()
    with pytest.raises(adapter.StopUser):
        user.run_once()
    with pytest.raises(adapter.StopUser):
        user.run_once()

    assert client.trust_env is False
    assert client.proxies == {}
    assert [call["url"] for call in client.calls] == [
        "http://127.0.0.1:8780/v1/shadow",
        "http://127.0.0.1:8780/v1/shadow",
    ]
    assert all(call["allow_redirects"] is False for call in client.calls)
    assert all("response" not in call and "body" not in call for call in client.calls)
    assert len(adapter.fleet_round_result().observations) == 2


def test_fleet_local_runner_completes_exact_balanced_hundred_over_loopback():
    if importlib.util.find_spec("locust") is None:
        return
    adapter = importlib.import_module("backend.loadtests.external_pi_fleet_locustfile")
    counts = Counter()
    servers = []
    threads = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers["Content-Length"])
            request = json.loads(self.rfile.read(length))
            counts[self.server.server_port] += 1
            response = {
                "type": "shadow_projection",
                "protocol_version": 1,
                "request_id": request["request_id"],
                "chat_session_id": request["chat_session_id"],
                "agent_session_id": request["agent_session_id"],
                "current_leaf_id": request["current_leaf_id"],
                "entry_count": len(request["transcript_entries"]),
                "transcript_sha256": request["expected_transcript_sha256"],
                "prompt_sha256": request["expected_prompt_sha256"],
                "tool_names_sha256": request["expected_tool_names_sha256"],
            }
            body = json.dumps(response).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            return None

    try:
        for port in range(8780, 8785):
            server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            servers.append(server)
            threads.append(thread)
        result = adapter.run_local_fleet_round(
            replicas=resolve_fleet_shape("5x32").replicas,
            prompt="canonical-runtime-prompt",
            token="protected-worker-token",
            timeout_seconds=20,
        )
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=2)

    assert len(result.observations) == 100
    assert all(item.classification == "compatible" for item in result.observations)
    assert result.protocol_errors == result.transport_errors == 0
    assert counts == Counter({port: 20 for port in range(8780, 8785)})


def test_fleet_local_runner_validates_before_start(monkeypatch):
    if importlib.util.find_spec("locust") is None:
        return
    adapter = importlib.import_module("backend.loadtests.external_pi_fleet_locustfile")
    started = False

    def reject(_environment):
        raise FleetRunRefused("runner invariant")

    def start(*_args, **_kwargs):
        nonlocal started
        started = True

    monkeypatch.setattr(adapter, "_validate_runner", reject)
    monkeypatch.setattr(adapter.LocalRunner, "start", start)
    with pytest.raises(FleetRunRefused, match="runner invariant"):
        adapter.run_local_fleet_round(
            replicas=resolve_fleet_shape("5x32").replicas,
            prompt="canonical-runtime-prompt",
            token="protected-worker-token",
        )
    assert started is False


def test_fleet_local_runner_timeout_refuses_incomplete_real_round():
    if importlib.util.find_spec("locust") is None:
        return
    adapter = importlib.import_module("backend.loadtests.external_pi_fleet_locustfile")
    timestamps = iter((0.0, 31.0))

    with pytest.raises(FleetRunRefused, match="exactly 100 observations"):
        adapter.run_local_fleet_round(
            replicas=resolve_fleet_shape("5x32").replicas,
            prompt="canonical-runtime-prompt",
            token="protected-worker-token",
            timeout_seconds=30,
            monotonic=lambda: next(timestamps),
        )


class _FleetOperator:
    runtime_id = "external-pi-runtime-1"
    owner_id = "test-owner"

    def __init__(self, *, refuse=()):
        self.refuse = set(refuse)
        self.events = []

    def revalidate(self, shape, active):
        self.events.append(
            ("revalidate", shape.name, tuple(item.worker_id for item in active))
        )

    def resource_preflight(self, shape):
        self.events.append(("resource_preflight", shape.name))
        if shape.name in self.refuse:
            return ResourcePreflight("resource_refused", 1024**3, 20.0, 80.0)
        return _passed_resource_preflight()

    def resolve(self, shape, index):
        replica = FleetReplica(
            QUALIFICATION_WORKER_IDS[index], QUALIFICATION_PORTS[index]
        )
        return SimpleNamespace(
            index=index,
            worker_id=replica.worker_id,
            port=replica.port,
            maximum_sessions=shape.sessions_per_worker,
            supervisor_unit=QUALIFICATION_SUPERVISOR_UNITS[index],
            worker_unit=QUALIFICATION_WORKER_UNITS[index],
            status_path=Path(f"/tmp/{replica.worker_id}.json"),
        )

    def start(self, resolved):
        self.events.append(("start", resolved.worker_id))

    def wait_ready(self, resolved):
        generation = resolved.index + 10
        self.events.append(("ready", resolved.worker_id, generation))
        return generation

    def run_round(self, name, workers, *, abort_requested=lambda: False):
        self.events.append(
            ("round", name, tuple(worker.worker_id for worker in workers))
        )
        return _round(name)

    def sample_resources(self, shape):
        self.events.append(("resources", shape.name))
        return _resources(shape.name)

    def cleanup(self, resolved, generation):
        self.events.append(("cleanup", resolved.worker_id, generation))
        return SimpleNamespace(
            registry_offline=True,
            supervisors_stopped_before_workers=True,
            units_removed=True,
            status_files_removed=True,
            ports_free=True,
            processes_gone=True,
        )

    def cleanup_postconditions(self, _shape):
        return _cleanup()

    def set_owner(self, owner_id):
        self.owner_id = owner_id

    def owned_units(self, _resolved):
        return ()

    def recovery_postconditions(self, resolved, owned_units):
        cleaned = any(
            event[0] == "cleanup" and event[1] == resolved.worker_id
            for event in self.events
        )
        cleanup = (
            _cleanup()
            if cleaned or not owned_units
            else _cleanup(units_removed=False, processes_gone=False)
        )
        return cleanup, (() if cleanup.passed else owned_units)


def test_controller_runs_shapes_sequentially_healthy_then_exact_generation_loss(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    operator = _FleetOperator(refuse={"16x8"})
    report_path = tmp_path / "fleet.json"
    report = run_fleet_controller(
        operator,
        release_id="0123456789ab-staging",
        report_path=report_path,
        report_root=tmp_path,
        geteuid=lambda: 0,
    )

    assert [shape.status for shape in report.shapes] == [
        "completed",
        "completed",
        "resource_refused",
    ]
    assert [shape.removed_worker_id for shape in report.shapes[:2]] == [
        "staging-qualification-00",
        "staging-qualification-00",
    ]
    assert [event[:2] for event in operator.events if event[0] == "round"] == [
        ("round", "healthy"),
        ("round", "survivor"),
        ("round", "healthy"),
        ("round", "survivor"),
    ]
    assert ("cleanup", "staging-qualification-00", 10) in operator.events
    second_shape_preflight = operator.events.index(("resource_preflight", "8x16"))
    first_shape_last_cleanup = max(
        index
        for index, event in enumerate(operator.events)
        if index < second_shape_preflight and event[0] == "cleanup"
    )
    assert first_shape_last_cleanup < second_shape_preflight
    assert any(event[0] == "resources" for event in operator.events)
    transition_indices = [
        index
        for index, event in enumerate(operator.events)
        if event[0] in {"start", "ready", "round", "cleanup"}
    ]
    revalidation_indices = [
        index for index, event in enumerate(operator.events) if event[0] == "revalidate"
    ]
    for index in transition_indices:
        assert any(candidate < index for candidate in revalidation_indices)
        assert any(candidate > index for candidate in revalidation_indices)
    assert report_path.stat().st_mode & 0o777 == 0o600


def test_controller_always_cleans_every_observed_generation_on_round_failure(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    class FailingOperator(_FleetOperator):
        def run_round(self, name, workers, *, abort_requested=lambda: False):
            super().run_round(name, workers, abort_requested=abort_requested)
            raise RuntimeError("protected response body")

    operator = FailingOperator()
    report_path = tmp_path / "fleet.json"
    report_path.write_text('{"previous":true}\n', encoding="utf-8")

    with pytest.raises(RuntimeError, match="protected response body"):
        run_fleet_controller(
            operator,
            release_id="0123456789ab-staging",
            report_path=report_path,
            report_root=tmp_path,
            shape_names=("5x32",),
            geteuid=lambda: 0,
        )

    assert [event for event in operator.events if event[0] == "cleanup"] == [
        ("cleanup", "staging-qualification-00", 10),
        ("cleanup", "staging-qualification-01", 11),
        ("cleanup", "staging-qualification-02", 12),
        ("cleanup", "staging-qualification-03", 13),
        ("cleanup", "staging-qualification-04", 14),
    ]
    retained = json.loads(report_path.read_text(encoding="utf-8"))
    assert retained["report_type"] == "recovery"
    assert retained["release_id"] == "0123456789ab-staging"
    assert len(retained["replicas"]) == 5
    assert [item["generation"] for item in retained["replicas"]] == [10, 11, 12, 13, 14]
    assert all(item["unresolved_units"] == [] for item in retained["replicas"])
    assert retained["cleanup_complete"] is True
    assert "protected response body" not in report_path.read_text(encoding="utf-8")
    assert report_path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    ("shape_names", "failure_round", "expected_workers"),
    (
        (("5x32", "8x16"), 2, 8),
        (("5x32", "8x16", "16x8"), 3, 16),
    ),
)
def test_later_shape_failure_publishes_only_unique_current_shape_recovery(
    tmp_path: Path,
    shape_names,
    failure_round,
    expected_workers,
):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    class SecondShapeFailure(_FleetOperator):
        healthy_rounds = 0

        def run_round(self, name, workers, *, abort_requested=lambda: False):
            if name == "healthy":
                self.healthy_rounds += 1
                if self.healthy_rounds == failure_round:
                    raise RuntimeError("later shape failed")
            return super().run_round(name, workers, abort_requested=abort_requested)

    report_path = tmp_path / "fleet.json"
    with pytest.raises(RuntimeError, match="later shape failed"):
        run_fleet_controller(
            SecondShapeFailure(),
            release_id="0123456789ab-staging",
            report_path=report_path,
            report_root=tmp_path,
            shape_names=shape_names,
            geteuid=lambda: 0,
        )

    retained = json.loads(report_path.read_text(encoding="utf-8"))
    assert retained["report_type"] == "recovery"
    assert [item["worker_id"] for item in retained["replicas"]] == list(
        QUALIFICATION_WORKER_IDS[:expected_workers]
    )
    assert len({item["worker_id"] for item in retained["replicas"]}) == expected_workers


def test_first_checkpoint_foreign_unit_and_port_are_retained_as_recovery(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    class ForeignPreflight(_FleetOperator):
        def revalidate(self, _shape, _active):
            raise FleetRunRefused("foreign reserved slot")

        def recovery_postconditions(self, resolved, _owned_units):
            if resolved.index == 6:
                return _cleanup(units_removed=False, processes_gone=False), (
                    resolved.supervisor_unit,
                )
            if resolved.index == 7:
                return _cleanup(ports_free=False, processes_gone=False), ()
            return _cleanup(), ()

    report_path = tmp_path / "fleet.json"
    with pytest.raises(FleetRunRefused, match="foreign reserved slot"):
        run_fleet_controller(
            ForeignPreflight(),
            release_id="0123456789ab-staging",
            report_path=report_path,
            report_root=tmp_path,
            shape_names=("5x32",),
            geteuid=lambda: 0,
        )

    retained = json.loads(report_path.read_text(encoding="utf-8"))
    assert retained["cleanup_complete"] is False
    assert [item["worker_id"] for item in retained["replicas"]] == [
        "staging-qualification-06",
        "staging-qualification-07",
    ]
    assert retained["replicas"][0]["unresolved_units"] == [
        QUALIFICATION_SUPERVISOR_UNITS[6]
    ]
    assert retained["replicas"][1]["cleanup"]["ports_free"] is False


@pytest.mark.parametrize("pointer_failure", ("current missing", "current changed"))
def test_partial_attempt_recovery_uses_cached_descriptors_after_pointer_drift(
    tmp_path: Path,
    pointer_failure: str,
):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    class PointerDrift(_FleetOperator):
        pointer_valid = True

        def resolve(self, shape, index):
            if not self.pointer_valid:
                raise FleetRunRefused(pointer_failure)
            return super().resolve(shape, index)

        def start(self, resolved):
            self.pointer_valid = False
            raise RuntimeError("protected partial-start detail")

        def owned_units(self, resolved):
            return (resolved.worker_unit,) if resolved.index == 0 else ()

    report_path = tmp_path / "fleet.json"
    report_path.write_text('{"previous":true}\n', encoding="utf-8")
    with pytest.raises(RuntimeError, match="protected partial-start detail"):
        run_fleet_controller(
            PointerDrift(),
            release_id="0123456789ab-staging",
            report_path=report_path,
            report_root=tmp_path,
            shape_names=("5x32",),
            geteuid=lambda: 0,
        )

    retained_text = report_path.read_text(encoding="utf-8")
    retained = json.loads(retained_text)
    assert retained["report_type"] == "recovery"
    assert retained["cleanup_complete"] is True
    assert len(retained["replicas"]) == 1
    assert retained["replicas"][0]["worker_id"] == "staging-qualification-00"
    assert retained["replicas"][0]["port"] == 8780
    assert retained["replicas"][0]["supervisor_unit"] == (
        "paperswithcode-staging-external-pi-qualification@00.service"
    )
    assert retained["replicas"][0]["worker_unit"] == (
        "paperswithcode-staging-external-pi-qualification-worker@00.service"
    )
    assert pointer_failure not in retained_text
    assert "protected partial-start detail" not in retained_text
    assert report_path.stat().st_mode & 0o777 == 0o600


def test_controller_retains_exact_unresolved_worker_only_partial_start(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    class PartialStartFailure(_FleetOperator):
        def start(self, resolved):
            raise RuntimeError("partial start")

        def owned_units(self, resolved):
            return (resolved.worker_unit,) if resolved.index == 0 else ()

        def cleanup(self, _resolved, _generation):
            raise RuntimeError("cleanup unavailable")

    operator = PartialStartFailure()
    report_path = tmp_path / "fleet.json"
    with pytest.raises(RuntimeError, match="partial start"):
        run_fleet_controller(
            operator,
            release_id="0123456789ab-staging",
            report_path=report_path,
            report_root=tmp_path,
            shape_names=("5x32",),
            geteuid=lambda: 0,
        )

    retained = json.loads(report_path.read_text(encoding="utf-8"))
    assert retained["cleanup_complete"] is False
    assert len(retained["replicas"]) == 1
    replica = retained["replicas"][0]
    assert replica["generation"] is None
    assert replica["owned_units"] == [
        "paperswithcode-staging-external-pi-qualification-worker@00.service"
    ]
    assert replica["unresolved_units"] == replica["owned_units"]


def test_controller_cleans_started_replica_when_readiness_has_no_generation(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    class ReadinessFailure(_FleetOperator):
        def wait_ready(self, resolved):
            if resolved.index == 1:
                raise RuntimeError("readiness failed")
            return super().wait_ready(resolved)

    operator = ReadinessFailure()
    with pytest.raises(RuntimeError, match="readiness failed"):
        run_fleet_controller(
            operator,
            release_id="0123456789ab-staging",
            report_path=tmp_path / "fleet.json",
            report_root=tmp_path,
            shape_names=("5x32",),
            geteuid=lambda: 0,
        )

    assert [event for event in operator.events if event[0] == "cleanup"] == [
        ("cleanup", "staging-qualification-00", 10),
        ("cleanup", "staging-qualification-01", None),
    ]


def test_controller_cleanup_continues_when_pre_cleanup_revalidation_fails(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    class SafetyFailure(_FleetOperator):
        unsafe = False

        def revalidate(self, shape, active):
            if self.unsafe:
                raise FleetRunRefused("safety changed")
            super().revalidate(shape, active)

        def run_round(self, name, workers, *, abort_requested=lambda: False):
            self.unsafe = True
            raise RuntimeError("round failed")

    operator = SafetyFailure()
    with pytest.raises(RuntimeError, match="round failed"):
        run_fleet_controller(
            operator,
            release_id="0123456789ab-staging",
            report_path=tmp_path / "fleet.json",
            report_root=tmp_path,
            shape_names=("5x32",),
            geteuid=lambda: 0,
        )

    assert [event for event in operator.events if event[0] == "cleanup"] == [
        ("cleanup", "staging-qualification-00", 10),
        ("cleanup", "staging-qualification-01", 11),
        ("cleanup", "staging-qualification-02", 12),
        ("cleanup", "staging-qualification-03", 13),
        ("cleanup", "staging-qualification-04", 14),
    ]


def test_controller_refuses_non_root_before_operator_actions(tmp_path: Path):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    operator = _FleetOperator()
    with pytest.raises(FleetRunRefused, match="root operator"):
        run_fleet_controller(
            operator,
            release_id="0123456789ab-staging",
            report_path=tmp_path / "fleet.json",
            report_root=tmp_path,
            geteuid=lambda: 1000,
        )
    assert operator.events == []


def test_controller_signal_context_converts_interrupt_and_restores_handlers():
    from backend.scripts.qualify_external_pi_fleet import (
        FleetQualificationInterrupted,
        qualification_signal_context,
    )

    previous = {
        number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)
    }
    with pytest.raises(FleetQualificationInterrupted), qualification_signal_context():
        signal.raise_signal(signal.SIGTERM)
    assert {
        number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)
    } == previous


def test_system_operator_revalidates_live_staging_and_exact_listener_state(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import SystemFleetOperator

    app_root = tmp_path / "srv/paperswithcode"
    release = app_root / "releases/0123456789ab-staging"
    release.mkdir(parents=True)
    release.joinpath("release.json").write_text(
        json.dumps(
            {
                "release_id": release.name,
                "external_pi_runtime": {"runtime_id": "runtime-1"},
            }
        ),
        encoding="utf-8",
    )
    staging = app_root / "environments/staging"
    staging.mkdir(parents=True)
    staging.joinpath("current").symlink_to(release)
    blue = staging / "slots/blue"
    blue.mkdir(parents=True)
    blue.joinpath("release").symlink_to(release)
    staging.joinpath("active").symlink_to(blue)
    status_root = tmp_path / "run/external-pi"
    status_root.mkdir(parents=True)
    status_root.joinpath("staging-blue.json").write_text(
        json.dumps(
            {
                "release_id": release.name,
                "worker_id": "staging-blue",
                "state": "ready",
                "authenticated": True,
                "registered": True,
                "generation": 7,
            }
        ),
        encoding="utf-8",
    )
    environ = {
        "PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN": "t" * 32,
        "PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED": "false",
        "PWC_CHAT_SANDBOX_EXECUTOR_ENABLED": "false",
        "PWC_CHAT_REMOTE_WORKSPACE_TOOLS_ENABLED": "false",
        "PWC_CHAT_REMOTE_BASH_ENABLED": "false",
        "PWC_CHAT_REMOTE_READ_ENABLED": "false",
        "PWC_CHAT_LAZY_WORKSPACE_ENABLED": "false",
    }
    listeners: dict[int, tuple[str, ...]] = {}
    live_status = {
        "protocol": "external-pi-v1",
        "worker_id": "staging-blue",
        "instance_id": "10000000-0000-4000-8000-000000000001",
        "release_id": release.name,
        "state": "ready",
        "active_sessions": 0,
        "maximum_sessions": 8,
        "worker_generation": 7,
        "operation_counters": {
            "shadow_requests": 0,
            "model_calls": 0,
            "tool_calls": 0,
            "provider_calls": 0,
            "modal_calls": 0,
            "billing_events": 0,
        },
        "capability_evidence": {
            "provider_credentials_present": False,
            "modal_credentials_present": False,
            "registered_tool_count": 0,
        },
    }

    class LiveResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return live_status

    unit_states = {"supervisor": "active", "worker": "active"}
    qualification_active = False

    def systemctl(command, **_kwargs):
        nonlocal qualification_active
        if "qualification" in command[-1]:
            if qualification_active and command[-1].endswith("@00.service"):
                role = (
                    "worker" if "qualification-worker" in command[-1] else "supervisor"
                )
                return subprocess.CompletedProcess(
                    command,
                    0,
                    "LoadState=loaded\nActiveState=active\n"
                    "Description=Papers With Code staging external Pi qualification "
                    f"{role} 00 owner {operator.owner_id}\n",
                )
            return subprocess.CompletedProcess(
                command,
                0,
                "LoadState=not-found\nActiveState=inactive\nDescription=\n",
            )
        state = (
            unit_states["worker"]
            if "external-pi-worker" in command[-1]
            else unit_states["supervisor"]
        )
        return subprocess.CompletedProcess(command, 0, state + "\n")

    listeners = {}
    operator = SystemFleetOperator(
        release_id=release.name,
        app_root=app_root,
        status_root=status_root,
        environ=environ,
        listener_hosts=lambda port: listeners.get(port, ()),
        http_get=lambda *_args, **_kwargs: LiveResponse(),
        runner=systemctl,
    )
    shape = resolve_fleet_shape("5x32")

    operator.revalidate(shape, ())
    listeners[8780] = ("127.0.0.1",)
    qualification_active = True
    active = (SimpleNamespace(worker_id=shape.replicas[0].worker_id, port=8780),)
    operator.revalidate(shape, active)

    live_status["operation_counters"]["provider_calls"] = 1
    with pytest.raises(FleetRunRefused, match="active worker"):
        operator.revalidate(shape, active)
    live_status["operation_counters"]["provider_calls"] = 0

    unit_states["supervisor"] = "failed"
    with pytest.raises(FleetRunRefused, match="active worker"):
        operator.revalidate(shape, active)
    unit_states["supervisor"] = "active"

    listeners[8780] = ("0.0.0.0",)
    with pytest.raises(FleetRunRefused, match="loopback"):
        operator.revalidate(shape, active)
    listeners[8780] = ("127.0.0.1",)
    environ["PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED"] = "true"
    with pytest.raises(FleetRunRefused, match="disabled"):
        operator.revalidate(shape, active)


def test_system_operator_rejects_stale_and_foreign_exact_qualification_units(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import SystemFleetOperator

    app_root = tmp_path / "srv/paperswithcode"
    release = app_root / "releases/0123456789ab-staging"
    release.mkdir(parents=True)
    release.joinpath("release.json").write_text(
        json.dumps(
            {
                "release_id": release.name,
                "external_pi_runtime": {"runtime_id": "runtime-1"},
            }
        ),
        encoding="utf-8",
    )
    staging = app_root / "environments/staging"
    blue = staging / "slots/blue"
    blue.mkdir(parents=True)
    staging.joinpath("current").symlink_to(release)
    staging.joinpath("active").symlink_to(blue)
    blue.joinpath("release").symlink_to(release)
    status_root = tmp_path / "status"
    status_root.mkdir()
    status_root.joinpath("staging-blue.json").write_text(
        json.dumps(
            {
                "release_id": release.name,
                "worker_id": "staging-blue",
                "state": "ready",
                "authenticated": True,
                "registered": True,
                "generation": 7,
            }
        ),
        encoding="utf-8",
    )
    live_status = {
        "protocol": "external-pi-v1",
        "worker_id": "staging-blue",
        "instance_id": "10000000-0000-4000-8000-000000000001",
        "release_id": release.name,
        "state": "ready",
        "active_sessions": 0,
        "maximum_sessions": 8,
        "worker_generation": 7,
        "operation_counters": {
            "shadow_requests": 0,
            "model_calls": 0,
            "tool_calls": 0,
            "provider_calls": 0,
            "modal_calls": 0,
            "billing_events": 0,
        },
        "capability_evidence": {
            "provider_credentials_present": False,
            "modal_credentials_present": False,
            "registered_tool_count": 0,
        },
    }

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return live_status

    qualification = {}

    def systemctl(command, **_kwargs):
        unit = command[-1]
        if "qualification" not in unit:
            values = {
                "LoadState": "loaded",
                "ActiveState": "active",
                "Description": "live",
            }
        else:
            values = qualification.get(
                unit,
                {
                    "LoadState": "not-found",
                    "ActiveState": "inactive",
                    "Description": "",
                },
            )
        if "--value" in command:
            return subprocess.CompletedProcess(command, 0, values["ActiveState"] + "\n")
        return subprocess.CompletedProcess(
            command,
            0,
            "\n".join(f"{name}={value}" for name, value in values.items()) + "\n",
        )

    environ = {
        "PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN": "t" * 32,
        "PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED": "false",
        "PWC_CHAT_SANDBOX_EXECUTOR_ENABLED": "false",
        "PWC_CHAT_REMOTE_WORKSPACE_TOOLS_ENABLED": "false",
        "PWC_CHAT_REMOTE_BASH_ENABLED": "false",
        "PWC_CHAT_REMOTE_READ_ENABLED": "false",
        "PWC_CHAT_LAZY_WORKSPACE_ENABLED": "false",
    }
    listeners = {}
    operator = SystemFleetOperator(
        release_id=release.name,
        app_root=app_root,
        status_root=status_root,
        environ=environ,
        listener_hosts=lambda port: listeners.get(port, ()),
        http_get=lambda *_args, **_kwargs: Response(),
        runner=systemctl,
    )
    operator.owner_id = "test-owner"
    shape = resolve_fleet_shape("5x32")
    supervisor = qualification_unit_names(shape)[0]
    worker = qualification_unit_names(shape)[shape.worker_count]

    qualification[QUALIFICATION_SUPERVISOR_UNITS[6]] = {
        "LoadState": "loaded",
        "ActiveState": "active",
        "Description": "foreign reserved slot",
    }
    with pytest.raises(FleetRunRefused, match="qualification unit"):
        operator.revalidate(shape, ())
    del qualification[QUALIFICATION_SUPERVISOR_UNITS[6]]

    listeners[QUALIFICATION_PORTS[6]] = ("127.0.0.1",)
    with pytest.raises(FleetRunRefused, match="inactive qualification ports"):
        operator.revalidate(shape, ())
    listeners.clear()

    qualification[supervisor] = {
        "LoadState": "loaded",
        "ActiveState": "failed",
        "Description": "foreign",
    }
    with pytest.raises(FleetRunRefused, match="qualification unit"):
        operator.revalidate(shape, ())

    qualification[supervisor] = {
        "LoadState": "loaded",
        "ActiveState": "active",
        "Description": (
            "Papers With Code staging external Pi qualification supervisor 00 "
            "owner test-owner"
        ),
    }
    qualification[worker] = {
        "LoadState": "loaded",
        "ActiveState": "active",
        "Description": (
            "Papers With Code staging external Pi qualification worker 00 "
            "owner test-owner"
        ),
    }
    active = (SimpleNamespace(worker_id=shape.replicas[0].worker_id, port=8780),)
    operator.revalidate(shape, active)

    qualification[worker]["Description"] = "foreign-owner"
    with pytest.raises(FleetRunRefused, match="qualification unit"):
        operator.revalidate(shape, active)


def test_resource_refused_shape_uses_observed_cleanup_postconditions(tmp_path: Path):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    class RefusedOperator(_FleetOperator):
        def cleanup_postconditions(self, _shape):
            return _cleanup(units_removed=False, processes_gone=False)

    operator = RefusedOperator(refuse={"16x8"})
    report = run_fleet_controller(
        operator,
        release_id="0123456789ab-staging",
        report_path=tmp_path / "fleet.json",
        report_root=tmp_path,
        shape_names=("16x8",),
        geteuid=lambda: 0,
    )

    assert report.shapes[0].status == "resource_refused"
    assert report.shapes[0].cleanup.units_removed is False
    assert report.shapes[0].cleanup.processes_gone is False


def test_system_recovery_does_not_report_foreign_exact_unit_as_removed(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import SystemFleetOperator

    operator = object.__new__(SystemFleetOperator)
    operator.listener_hosts = lambda _port: ()
    resolved = SimpleNamespace(
        supervisor_unit=("paperswithcode-staging-external-pi-qualification@00.service"),
        worker_unit=(
            "paperswithcode-staging-external-pi-qualification-worker@00.service"
        ),
        status_path=tmp_path / "missing.json",
        release_id="0123456789ab-staging",
        worker_id="staging-qualification-00",
        port=8780,
    )
    operator._unit_metadata = lambda unit: (
        ("loaded", "active", "foreign")
        if unit == resolved.supervisor_unit
        else ("not-found", "inactive", "")
    )

    cleanup, unresolved = operator.recovery_postconditions(resolved, ())

    assert unresolved == (resolved.supervisor_unit,)
    assert cleanup.units_removed is False
    assert cleanup.registry_offline is False
    assert cleanup.passed is False


def test_system_refusal_cleanup_postconditions_inspect_all_reserved_slots(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import SystemFleetOperator

    units = []
    ports = []
    operator = object.__new__(SystemFleetOperator)
    operator.qualification_status_root = tmp_path
    operator._unit_metadata = lambda unit: (
        units.append(unit) or ("not-found", "inactive", "")
    )
    operator.listener_hosts = lambda port: ports.append(port) or ()

    cleanup = operator.cleanup_postconditions(resolve_fleet_shape("5x32"))

    assert cleanup.passed is True
    assert units == list(QUALIFICATION_SUPERVISOR_UNITS + QUALIFICATION_WORKER_UNITS)
    assert ports == list(QUALIFICATION_PORTS)


def test_system_resource_preflight_scales_worker_memory_by_session_limit(monkeypatch):
    from backend.scripts.qualify_external_pi_fleet import SystemFleetOperator

    operator = object.__new__(SystemFleetOperator)
    operator.app_root = Path("/srv/paperswithcode")
    monkeypatch.setattr(
        Path,
        "resolve",
        lambda self, strict=False: Path(
            "/srv/paperswithcode/environments/staging/slots/blue"
        ),
    )

    def properties(unit, *_names):
        return {"MemoryCurrent": 100 * 1024**2 if "worker" in unit else 50 * 1024**2}

    operator._systemctl_properties = properties
    operator._mem_available_bytes = lambda: 4 * 1024**3
    slept = []
    cpu = iter(((100, 80), (200, 100)))
    operator._read_host_cpu = lambda: next(cpu)
    operator.sleep = lambda seconds: slept.append(seconds)

    preflight = operator.resource_preflight(resolve_fleet_shape("5x32"))

    assert slept == [0.1]
    assert preflight.observed_cpu_percent == 80.0
    assert preflight.status == "resource_refused"
    assert preflight.projected_mem_available_bytes == 4 * 1024**3 - 2250 * 1024**2


def test_system_resource_adapter_parses_only_requested_numeric_properties():
    from backend.scripts.qualify_external_pi_fleet import SystemFleetOperator

    commands = []

    def systemctl(command, **_kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            "MemoryPeak=1048576\nCPUUsageNSec=invalid\nTasksCurrent=7\nIgnored=9\n",
        )

    operator = object.__new__(SystemFleetOperator)
    operator.runner = systemctl
    values = operator._systemctl_properties(
        "qualification-worker@00.service",
        "MemoryPeak",
        "CPUUsageNSec",
        "TasksCurrent",
    )

    assert values == {
        "MemoryPeak": 1048576,
        "CPUUsageNSec": 0,
        "TasksCurrent": 7,
    }
    assert commands == [
        [
            "systemctl",
            "show",
            "--property=MemoryPeak",
            "--property=CPUUsageNSec",
            "--property=TasksCurrent",
            "qualification-worker@00.service",
        ]
    ]


def test_system_sample_resources_aggregates_injected_exact_unit_and_host_evidence(
    monkeypatch,
):
    import backend.scripts.qualify_external_pi_fleet as controller

    calls = Counter()

    def systemctl(command, **_kwargs):
        unit = command[-1]
        calls[unit] += 1
        worker = "qualification-worker" in unit
        return subprocess.CompletedProcess(
            command,
            0,
            "\n".join(
                (
                    f"MemoryPeak={(20 if worker else 10) * 1024**2}",
                    f"CPUUsageNSec={calls[unit] * 1_000_000_000}",
                    "TasksCurrent=3",
                )
            )
            + "\n",
        )

    operator = object.__new__(controller.SystemFleetOperator)
    operator.runner = systemctl
    operator._unit_cpu_state = {}
    operator._host_cpu_state = None
    host_cpu = iter(((100, 80), (200, 100)))
    operator._read_host_cpu = lambda: next(host_cpu)
    operator._mem_available_bytes = lambda: 2 * 1024**3
    monotonic = iter((10.0, 12.0))
    monkeypatch.setattr(controller.time, "monotonic", lambda: next(monotonic))
    shape = resolve_fleet_shape("5x32")

    first = operator.sample_resources(shape)
    second = operator.sample_resources(shape)

    assert first.peak_cpu_percent == 0.0
    assert second.peak_memory_bytes == 150 * 1024**2
    assert second.peak_cpu_percent == 80.0
    assert second.peak_tasks == 30
    assert second.minimum_host_mem_available_bytes == 2 * 1024**3
    assert len(second.unit_peaks) == 10
    assert {item.peak_cpu_percent for item in second.unit_peaks} == {50.0}
    assert set(calls.values()) == {2}


def test_controller_concurrently_aborts_round_when_live_resource_guard_crosses(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    class CrossingOperator(_FleetOperator):
        in_round = threading.Event()

        def sample_resources(self, shape):
            evidence = super().sample_resources(shape)
            if self.in_round.is_set():
                return evidence.model_copy(
                    update={"minimum_host_mem_available_bytes": 1536 * 1024**2 - 1}
                )
            return evidence

        def run_round(self, name, workers, *, abort_requested):
            self.in_round.set()
            deadline = time.monotonic() + 1
            while time.monotonic() < deadline and not abort_requested():
                time.sleep(0.01)
            if not abort_requested():
                raise RuntimeError("no concurrent resource guard")
            raise FleetRunRefused("resource guard crossed")

    operator = CrossingOperator()
    report_path = tmp_path / "fleet.json"
    with pytest.raises(FleetRunRefused, match="resource guard crossed"):
        run_fleet_controller(
            operator,
            release_id="0123456789ab-staging",
            report_path=report_path,
            report_root=tmp_path,
            shape_names=("5x32",),
            geteuid=lambda: 0,
        )

    retained = json.loads(report_path.read_text(encoding="utf-8"))
    assert retained["report_type"] == "recovery"
    assert retained["cleanup_complete"] is True


def test_controller_aborts_round_when_concurrent_resource_sampler_errors(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    class SamplingFailure(_FleetOperator):
        in_round = threading.Event()

        def sample_resources(self, shape):
            if self.in_round.is_set():
                raise RuntimeError("resource adapter failed")
            return super().sample_resources(shape)

        def run_round(self, name, workers, *, abort_requested):
            self.in_round.set()
            deadline = time.monotonic() + 1
            while time.monotonic() < deadline and not abort_requested():
                time.sleep(0.01)
            raise FleetRunRefused("round stopped")

    report_path = tmp_path / "fleet.json"
    with pytest.raises(FleetRunRefused, match="round stopped"):
        run_fleet_controller(
            SamplingFailure(),
            release_id="0123456789ab-staging",
            report_path=report_path,
            report_root=tmp_path,
            shape_names=("5x32",),
            geteuid=lambda: 0,
        )

    retained = json.loads(report_path.read_text(encoding="utf-8"))
    assert retained["report_type"] == "recovery"
    assert retained["cleanup_complete"] is True
