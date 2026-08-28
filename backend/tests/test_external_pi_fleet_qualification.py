from __future__ import annotations

import importlib
import importlib.util
import json
import signal
import subprocess
from collections import Counter
from dataclasses import FrozenInstanceError
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


class _FleetOperator:
    runtime_id = "external-pi-runtime-1"

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
        replica = shape.replicas[index]
        return SimpleNamespace(
            index=index,
            worker_id=replica.worker_id,
            port=replica.port,
            maximum_sessions=shape.sessions_per_worker,
        )

    def start(self, resolved):
        self.events.append(("start", resolved.worker_id))

    def wait_ready(self, resolved):
        generation = resolved.index + 10
        self.events.append(("ready", resolved.worker_id, generation))
        return generation

    def run_round(self, name, workers):
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
        def run_round(self, name, workers):
            super().run_round(name, workers)
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
    assert report_path.read_text(encoding="utf-8") == '{"previous":true}\n'


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

        def run_round(self, name, workers):
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

    def systemctl(command, **_kwargs):
        state = (
            unit_states["worker"]
            if "external-pi-worker" in command[-1]
            else unit_states["supervisor"]
        )
        return subprocess.CompletedProcess(command, 0, state + "\n")

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
