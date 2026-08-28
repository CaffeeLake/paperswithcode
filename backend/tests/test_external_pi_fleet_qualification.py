from __future__ import annotations

import json
from collections import Counter
from dataclasses import FrozenInstanceError
from pathlib import Path

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
