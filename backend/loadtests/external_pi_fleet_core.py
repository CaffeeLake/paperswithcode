"""Pure, content-free contracts for staging external Pi fleet qualification."""

from __future__ import annotations

import math
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from backend.loadtests.external_pi_shadow_core import (
    BaselineObservation,
    build_external_pi_baseline_request,
    classify_external_pi_baseline_response,
)


EXPECTED_USERS = 100
MIN_PROJECTED_MEM_AVAILABLE_BYTES = 1536 * 1024**2
MAX_REPORT_COUNTER = 1_000_000
MAX_REPORT_DURATION_MS = 60_000
MAX_REPORT_BYTES = 2**63 - 1
FleetShapeName = Literal["5x32", "8x16", "16x8"]
QUALIFICATION_PORTS = tuple(range(8780, 8796))
QUALIFICATION_WORKER_IDS = tuple(
    f"staging-qualification-{index:02d}" for index in range(16)
)
QUALIFICATION_SUPERVISOR_UNITS = tuple(
    f"paperswithcode-staging-external-pi-qualification@{index:02d}.service"
    for index in range(16)
)
QUALIFICATION_WORKER_UNITS = tuple(
    f"paperswithcode-staging-external-pi-qualification-worker@{index:02d}.service"
    for index in range(16)
)


class FleetRunRefused(RuntimeError):
    """The requested fleet qualification violates a fail-closed contract."""


_STAGING_RELEASE = re.compile(r"^[0-9a-f]{12}-staging$")


@dataclass(frozen=True, slots=True)
class FleetSafetyConfig:
    environment: str
    requested_release: str
    active_release: str
    external_admission_enabled: bool
    executor_routing_enabled: bool
    remote_execution_enabled: bool
    active_worker_id: str
    active_worker_healthy: bool
    worker_token: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class PortState:
    port: int
    bind_host: str
    is_free: bool


@dataclass(frozen=True, slots=True)
class HostResourceSnapshot:
    mem_available_bytes: int
    projected_additional_bytes: int
    cpu_percent: float
    cpu_guard_percent: float

    def __post_init__(self) -> None:
        if (
            type(self.mem_available_bytes) is not int
            or self.mem_available_bytes < 0
            or self.mem_available_bytes > MAX_REPORT_BYTES
            or type(self.projected_additional_bytes) is not int
            or self.projected_additional_bytes < 0
            or self.projected_additional_bytes > MAX_REPORT_BYTES
            or not 0 <= self.cpu_percent <= 100
            or not 0 < self.cpu_guard_percent <= 100
        ):
            raise ValueError("external Pi qualification resource inputs are invalid")


@dataclass(frozen=True, slots=True)
class ResourcePreflight:
    status: Literal["passed", "resource_refused"]
    projected_mem_available_bytes: int
    observed_cpu_percent: float
    cpu_guard_percent: float

    def __post_init__(self) -> None:
        if (
            self.status not in {"passed", "resource_refused"}
            or type(self.projected_mem_available_bytes) is not int
            or self.projected_mem_available_bytes < 0
            or self.projected_mem_available_bytes > MAX_REPORT_BYTES
            or not 0 <= self.observed_cpu_percent <= 100
            or not 0 < self.cpu_guard_percent <= 100
        ):
            raise ValueError(
                "external Pi qualification resource preflight evidence is invalid"
            )


class ForbiddenActivity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    model_calls: int = Field(default=0, ge=0, le=MAX_REPORT_COUNTER)
    tool_calls: int = Field(default=0, ge=0, le=MAX_REPORT_COUNTER)
    provider_calls: int = Field(default=0, ge=0, le=MAX_REPORT_COUNTER)
    modal_calls: int = Field(default=0, ge=0, le=MAX_REPORT_COUNTER)
    billing_events: int = Field(default=0, ge=0, le=MAX_REPORT_COUNTER)

    @property
    def detected(self) -> bool:
        return any(self.model_dump().values())


class FleetRoundReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    name: Literal["healthy", "survivor"]
    observations: int = Field(ge=0, le=EXPECTED_USERS)
    compatible: int = Field(ge=0, le=EXPECTED_USERS)
    capacity_rejections: int = Field(ge=0, le=EXPECTED_USERS)
    protocol_errors: int = Field(ge=0, le=EXPECTED_USERS)
    transport_errors: int = Field(ge=0, le=EXPECTED_USERS)
    p95_ms: int = Field(ge=0, le=MAX_REPORT_DURATION_MS)
    p99_ms: int = Field(ge=0, le=MAX_REPORT_DURATION_MS)
    forbidden_activity: ForbiddenActivity

    @model_validator(mode="after")
    def validate_counts(self) -> FleetRoundReport:
        outcomes = (
            self.compatible
            + self.capacity_rejections
            + self.protocol_errors
            + self.transport_errors
        )
        if self.observations != outcomes:
            raise ValueError("external Pi fleet round counts are inconsistent")
        if self.p95_ms > self.p99_ms:
            raise ValueError("external Pi fleet round percentiles are inconsistent")
        return self

    @computed_field
    @property
    def passed(self) -> bool:
        return (
            self.observations == EXPECTED_USERS
            and self.compatible == EXPECTED_USERS
            and self.capacity_rejections == 0
            and self.protocol_errors == 0
            and self.transport_errors == 0
            and not self.forbidden_activity.detected
            and self.p95_ms <= 3_000
            and self.p99_ms <= 5_000
        )


class WorkerEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    worker_id: str = Field(pattern=r"^staging-qualification-(0[0-9]|1[0-5])$")
    port: int = Field(ge=8780, le=8795)
    generation: int = Field(ge=1, le=MAX_REPORT_COUNTER)
    maximum_sessions: Literal[8, 16, 32]


class UnitResourceEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    unit_name: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9@_.-]+\.service$",
    )
    peak_memory_bytes: int = Field(ge=0, le=MAX_REPORT_BYTES)
    peak_cpu_percent: float = Field(ge=0, le=100)
    peak_tasks: int = Field(ge=0, le=MAX_REPORT_COUNTER)


class ResourceEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    peak_memory_bytes: int = Field(ge=0, le=MAX_REPORT_BYTES)
    peak_cpu_percent: float = Field(ge=0, le=100)
    peak_tasks: int = Field(ge=0, le=MAX_REPORT_COUNTER)
    minimum_host_mem_available_bytes: int = Field(ge=0, le=MAX_REPORT_BYTES)
    unit_peaks: tuple[UnitResourceEvidence, ...] = Field(max_length=32)


class CleanupEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    drain_proven: bool
    registry_offline: bool
    supervisors_stopped_before_workers: bool
    units_removed: bool
    status_files_removed: bool
    ports_free: bool
    processes_gone: bool

    @property
    def passed(self) -> bool:
        return all(self.model_dump().values())


class FleetShapeReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    shape: FleetShapeName
    status: Literal["completed", "resource_refused"]
    worker_count: int = Field(ge=5, le=16)
    sessions_per_worker: Literal[8, 16, 32]
    aggregate_capacity: int = Field(ge=0, le=160)
    post_loss_capacity: int = Field(ge=0, le=160)
    healthy: FleetRoundReport | None
    survivor: FleetRoundReport | None
    workers: tuple[WorkerEvidence, ...] = Field(max_length=16)
    removed_worker_id: str | None = Field(
        pattern=r"^staging-qualification-(0[0-9]|1[0-5])$"
    )
    resources: ResourceEvidence | None
    resource_preflight: ResourcePreflight | None
    cleanup: CleanupEvidence

    @computed_field
    @property
    def safety_passed(self) -> bool:
        return (
            self.status == "completed"
            and self.healthy is not None
            and self.survivor is not None
            and self.healthy.passed
            and self.survivor.passed
        )

    @computed_field
    @property
    def capacity_passed(self) -> bool:
        return self.aggregate_capacity >= EXPECTED_USERS

    @computed_field
    @property
    def failure_resilience_passed(self) -> bool:
        return (
            self.status == "completed"
            and self.survivor is not None
            and self.post_loss_capacity >= EXPECTED_USERS
            and self.survivor.passed
        )

    @computed_field
    @property
    def resource_passed(self) -> bool:
        return (
            self.status == "completed"
            and self.resources is not None
            and self.resource_preflight is not None
            and self.resource_preflight.status == "passed"
        )

    @computed_field
    @property
    def cleanup_passed(self) -> bool:
        return self.cleanup.passed

    @computed_field
    @property
    def overall_passed(self) -> bool:
        return (
            self.safety_passed
            and self.capacity_passed
            and self.failure_resilience_passed
            and self.resource_passed
            and self.cleanup_passed
        )


class FleetQualificationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    release_id: str = Field(pattern=r"^[0-9a-f]{12}-staging$")
    runtime_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._-]+$")
    shapes: tuple[FleetShapeReport, ...] = Field(min_length=1, max_length=3)
    preferred_shape: FleetShapeName | None


@dataclass(frozen=True, slots=True)
class FleetReplica:
    worker_id: str
    port: int

    @property
    def worker_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


@dataclass(frozen=True, slots=True)
class FleetShape:
    name: FleetShapeName
    worker_count: int
    sessions_per_worker: int
    replicas: tuple[FleetReplica, ...]

    @property
    def aggregate_capacity(self) -> int:
        return self.worker_count * self.sessions_per_worker

    @property
    def post_loss_capacity(self) -> int:
        return (self.worker_count - 1) * self.sessions_per_worker


def _shape(name: FleetShapeName, worker_count: int, sessions: int) -> FleetShape:
    return FleetShape(
        name=name,
        worker_count=worker_count,
        sessions_per_worker=sessions,
        replicas=tuple(
            FleetReplica(QUALIFICATION_WORKER_IDS[index], QUALIFICATION_PORTS[index])
            for index in range(worker_count)
        ),
    )


_FLEET_SHAPES: dict[FleetShapeName, FleetShape] = {
    "5x32": _shape("5x32", 5, 32),
    "8x16": _shape("8x16", 8, 16),
    "16x8": _shape("16x8", 16, 8),
}


def resolve_fleet_shape(name: str) -> FleetShape:
    try:
        return _FLEET_SHAPES[name]
    except KeyError:
        raise FleetRunRefused(
            "external Pi qualification requires an allowlisted fleet shape"
        ) from None


def route_ordinal(ordinal: int, replicas: tuple[FleetReplica, ...]) -> FleetReplica:
    if type(ordinal) is not int or not 0 <= ordinal < EXPECTED_USERS:
        raise ValueError("external Pi qualification ordinal is out of range")
    if not replicas:
        raise FleetRunRefused("external Pi qualification requires at least one replica")
    allowed_pairs = {
        worker_id: QUALIFICATION_PORTS[index]
        for index, worker_id in enumerate(QUALIFICATION_WORKER_IDS)
    }
    indices = [
        QUALIFICATION_WORKER_IDS.index(replica.worker_id)
        for replica in replicas
        if replica.worker_id in allowed_pairs
    ]
    if (
        len(indices) != len(replicas)
        or len(set(indices)) != len(indices)
        or indices != sorted(indices)
        or any(
            allowed_pairs.get(replica.worker_id) != replica.port for replica in replicas
        )
    ):
        raise FleetRunRefused(
            "external Pi qualification routing requires allowlisted replicas"
        )
    return replicas[ordinal % len(replicas)]


def validate_fleet_preflight(
    config: FleetSafetyConfig,
    shape: FleetShape,
    ports: tuple[PortState, ...],
) -> None:
    """Validate pure staging, release, disabled-route, and port safety gates."""

    shape = _require_allowlisted_shape(shape)
    if config.environment != "staging":
        raise FleetRunRefused("external Pi qualification is staging only")
    if (
        config.requested_release != config.active_release
        or not _STAGING_RELEASE.fullmatch(config.active_release)
    ):
        raise FleetRunRefused(
            "external Pi qualification requires the exact active staging release"
        )
    flags = (
        config.external_admission_enabled,
        config.executor_routing_enabled,
        config.remote_execution_enabled,
    )
    if any(type(flag) is not bool or flag for flag in flags):
        raise FleetRunRefused(
            "external Pi qualification routing flags must remain disabled"
        )
    if (
        config.active_worker_id not in {"staging-blue", "staging-green"}
        or type(config.active_worker_healthy) is not bool
        or not config.active_worker_healthy
    ):
        raise FleetRunRefused(
            "external Pi qualification requires the healthy active staging worker"
        )
    if not config.worker_token:
        raise FleetRunRefused(
            "external Pi qualification requires a protected worker token"
        )

    expected_ports = tuple(replica.port for replica in shape.replicas)
    if (
        len(ports) != len(expected_ports)
        or tuple(item.port for item in ports) != expected_ports
        or any(
            item.bind_host != "127.0.0.1"
            or type(item.is_free) is not bool
            or not item.is_free
            for item in ports
        )
    ):
        raise FleetRunRefused(
            "external Pi qualification requires exact free loopback ports"
        )


def evaluate_resource_preflight(snapshot: HostResourceSnapshot) -> ResourcePreflight:
    projected = max(
        0, snapshot.mem_available_bytes - snapshot.projected_additional_bytes
    )
    passed = (
        snapshot.mem_available_bytes >= snapshot.projected_additional_bytes
        and projected >= MIN_PROJECTED_MEM_AVAILABLE_BYTES
        and snapshot.cpu_percent < snapshot.cpu_guard_percent
    )
    return ResourcePreflight(
        status="passed" if passed else "resource_refused",
        projected_mem_available_bytes=projected,
        observed_cpu_percent=snapshot.cpu_percent,
        cpu_guard_percent=snapshot.cpu_guard_percent,
    )


# The fleet deliberately shares the proven content-free payload and classifier.
build_external_pi_fleet_request = build_external_pi_baseline_request
classify_external_pi_fleet_response = classify_external_pi_baseline_response


def _nearest_rank(values: tuple[int, ...], percentile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[math.ceil(percentile * len(ordered)) - 1]


def aggregate_round(
    *,
    name: Literal["healthy", "survivor"],
    observations: tuple[BaselineObservation, ...],
    protocol_errors: int,
    transport_errors: int,
    forbidden_activity: ForbiddenActivity,
) -> FleetRoundReport:
    """Reduce one fixed 100-user round to bounded content-free counters."""

    if len(observations) != EXPECTED_USERS:
        raise FleetRunRefused(
            "external Pi fleet round requires exactly 100 observations"
        )
    if (
        type(protocol_errors) is not int
        or type(transport_errors) is not int
        or protocol_errors < 0
        or transport_errors < 0
    ):
        raise FleetRunRefused("external Pi fleet round error counters are invalid")
    compatible = sum(item.classification == "compatible" for item in observations)
    capacity = sum(item.classification == "capacity" for item in observations)
    classified_errors = sum(item.classification == "error" for item in observations)
    if protocol_errors + transport_errors != classified_errors:
        raise FleetRunRefused("external Pi fleet round error evidence is inconsistent")
    latencies = tuple(item.latency_ms for item in observations)
    p95 = _nearest_rank(latencies, 0.95)
    p99 = _nearest_rank(latencies, 0.99)
    return FleetRoundReport(
        name=name,
        observations=len(observations),
        compatible=compatible,
        capacity_rejections=capacity,
        protocol_errors=protocol_errors,
        transport_errors=transport_errors,
        p95_ms=p95,
        p99_ms=p99,
        forbidden_activity=forbidden_activity,
    )


def _require_allowlisted_shape(shape: FleetShape) -> FleetShape:
    expected = resolve_fleet_shape(shape.name)
    if shape != expected:
        raise FleetRunRefused(
            "external Pi qualification requires an allowlisted fleet shape"
        )
    return expected


def qualification_unit_names(shape: FleetShape) -> tuple[str, ...]:
    """Return every exact transient supervisor and worker unit for a shape."""

    shape = _require_allowlisted_shape(shape)
    return (
        QUALIFICATION_SUPERVISOR_UNITS[: shape.worker_count]
        + QUALIFICATION_WORKER_UNITS[: shape.worker_count]
    )


def build_completed_shape_report(
    *,
    shape: FleetShape,
    healthy: FleetRoundReport,
    survivor: FleetRoundReport,
    workers: tuple[WorkerEvidence, ...],
    removed_worker_id: str,
    resources: ResourceEvidence,
    resource_preflight: ResourcePreflight,
    cleanup: CleanupEvidence,
) -> FleetShapeReport:
    shape = _require_allowlisted_shape(shape)
    expected_worker_ids = tuple(replica.worker_id for replica in shape.replicas)
    if (
        healthy.name != "healthy"
        or survivor.name != "survivor"
        or tuple(worker.worker_id for worker in workers) != expected_worker_ids
        or tuple(worker.port for worker in workers)
        != tuple(replica.port for replica in shape.replicas)
        or any(
            worker.maximum_sessions != shape.sessions_per_worker for worker in workers
        )
        or removed_worker_id not in expected_worker_ids
    ):
        raise FleetRunRefused(
            "external Pi fleet shape evidence does not match its topology"
        )
    if resource_preflight.status != "passed":
        raise FleetRunRefused(
            "external Pi completed shape requires a passed resource preflight"
        )
    if tuple(item.unit_name for item in resources.unit_peaks) != (
        qualification_unit_names(shape)
    ):
        raise FleetRunRefused(
            "external Pi shape requires exact per-unit resource evidence"
        )
    return FleetShapeReport(
        shape=shape.name,
        status="completed",
        worker_count=shape.worker_count,
        sessions_per_worker=shape.sessions_per_worker,
        aggregate_capacity=shape.aggregate_capacity,
        post_loss_capacity=shape.post_loss_capacity,
        healthy=healthy,
        survivor=survivor,
        workers=workers,
        removed_worker_id=removed_worker_id,
        resources=resources,
        resource_preflight=resource_preflight,
        cleanup=cleanup,
    )


def build_resource_refused_shape_report(
    shape: FleetShape,
    preflight: ResourcePreflight,
    cleanup: CleanupEvidence,
) -> FleetShapeReport:
    shape = _require_allowlisted_shape(shape)
    if preflight.status != "resource_refused":
        raise FleetRunRefused(
            "external Pi shape may be refused only by resource preflight"
        )
    return FleetShapeReport(
        shape=shape.name,
        status="resource_refused",
        worker_count=shape.worker_count,
        sessions_per_worker=shape.sessions_per_worker,
        aggregate_capacity=shape.aggregate_capacity,
        post_loss_capacity=shape.post_loss_capacity,
        healthy=None,
        survivor=None,
        workers=(),
        removed_worker_id=None,
        resources=None,
        resource_preflight=preflight,
        cleanup=cleanup,
    )


def _shape_evidence(report: FleetShapeReport) -> dict[str, object]:
    return report.model_dump(exclude_computed_fields=True)


def _revalidate_shape_report(report: FleetShapeReport) -> FleetShapeReport:
    """Rebuild a shape verdict exclusively from its bounded source evidence."""

    try:
        shape = resolve_fleet_shape(report.shape)
        if report.status == "completed":
            if (
                report.healthy is None
                or report.survivor is None
                or report.resources is None
                or report.resource_preflight is None
                or report.removed_worker_id is None
            ):
                raise FleetRunRefused(
                    "external Pi completed shape report evidence is incomplete"
                )
            healthy = FleetRoundReport.model_validate(
                report.healthy.model_dump(exclude_computed_fields=True)
            )
            survivor = FleetRoundReport.model_validate(
                report.survivor.model_dump(exclude_computed_fields=True)
            )
            rebuilt = build_completed_shape_report(
                shape=shape,
                healthy=healthy,
                survivor=survivor,
                workers=report.workers,
                removed_worker_id=report.removed_worker_id,
                resources=report.resources,
                resource_preflight=report.resource_preflight,
                cleanup=report.cleanup,
            )
        else:
            if report.resource_preflight is None:
                raise FleetRunRefused(
                    "external Pi refused shape report evidence is incomplete"
                )
            rebuilt = build_resource_refused_shape_report(
                shape, report.resource_preflight, report.cleanup
            )
    except (AttributeError, TypeError, ValueError) as exc:
        raise FleetRunRefused("external Pi shape report evidence is invalid") from exc
    if _shape_evidence(report) != _shape_evidence(rebuilt):
        raise FleetRunRefused("external Pi shape report evidence is contradictory")
    return rebuilt


def build_final_report(
    *,
    release_id: str,
    runtime_id: str,
    shapes: tuple[FleetShapeReport, ...],
) -> FleetQualificationReport:
    validated_shapes = tuple(_revalidate_shape_report(report) for report in shapes)
    names = tuple(report.shape for report in validated_shapes)
    if len(set(names)) != len(names):
        raise FleetRunRefused("external Pi final report requires unique fleet shapes")
    passing = [report for report in validated_shapes if report.overall_passed]
    passing.sort(
        key=lambda report: (
            report.resources.peak_memory_bytes
            if report.resources
            else MAX_REPORT_BYTES,
            report.resources.peak_cpu_percent if report.resources else 101.0,
            max(report.healthy.p99_ms, report.survivor.p99_ms)
            if report.healthy and report.survivor
            else MAX_REPORT_DURATION_MS + 1,
            report.worker_count,
        )
    )
    return FleetQualificationReport(
        release_id=release_id,
        runtime_id=runtime_id,
        shapes=validated_shapes,
        preferred_shape=passing[0].shape if passing else None,
    )


def _path_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def publish_fleet_report(
    report: FleetQualificationReport,
    destination: Path,
    report_root: Path,
) -> None:
    """Atomically publish only the bounded report schema with mode 0600."""

    try:
        root = report_root.resolve(strict=True)
        parent = destination.parent.resolve(strict=True)
    except OSError as exc:
        raise FleetRunRefused(
            "external Pi fleet report directory is unavailable"
        ) from exc
    if not destination.is_absolute() or not _path_within(parent, root):
        raise FleetRunRefused(
            "external Pi fleet report must remain under its report root"
        )
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=parent
    )
    temporary = Path(temporary_name)
    try:
        os.chmod(temporary, 0o600)
        payload = report.model_dump_json(indent=2).encode("utf-8") + b"\n"
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        os.chmod(destination, 0o600)
        directory_descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary.exists():
            temporary.unlink()
