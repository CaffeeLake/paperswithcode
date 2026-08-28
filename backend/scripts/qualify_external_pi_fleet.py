"""Root-operated staging controller for transient external Pi qualification."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import signal
import socket
import subprocess
import threading
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Protocol

import httpx

from backend.loadtests.external_pi_fleet_core import (
    CleanupEvidence,
    FleetQualificationReport,
    FleetReplica,
    FleetRoundReport,
    FleetRunRefused,
    FleetSafetyConfig,
    FleetShape,
    FleetShapeName,
    ForbiddenActivity,
    HostResourceSnapshot,
    PortState,
    ResourceEvidence,
    ResourcePreflight,
    UnitResourceEvidence,
    WorkerEvidence,
    aggregate_round,
    build_completed_shape_report,
    build_final_report,
    build_resource_refused_shape_report,
    publish_fleet_report,
    qualification_unit_names,
    resolve_fleet_shape,
    route_ordinal,
    validate_fleet_preflight,
)
from backend.services.chat_external_pi_shadow import ExternalPiWorkerStatus
from deploy import external_pi_qualification_lifecycle as lifecycle


class FleetOperator(Protocol):
    runtime_id: str

    def revalidate(self, shape: FleetShape, active: Sequence[object]) -> None: ...

    def resource_preflight(self, shape: FleetShape) -> ResourcePreflight: ...

    def resolve(self, shape: FleetShape, index: int): ...

    def start(self, resolved) -> None: ...

    def wait_ready(self, resolved) -> int: ...

    def run_round(
        self, name: str, workers: tuple[WorkerEvidence, ...]
    ) -> FleetRoundReport: ...

    def sample_resources(self, shape: FleetShape) -> ResourceEvidence: ...

    def cleanup(self, resolved, generation: int | None): ...


class FleetQualificationInterrupted(FleetRunRefused):
    """A normal operator signal interrupted the qualification transaction."""

    def __init__(self, signal_number: int):
        super().__init__(
            f"external Pi fleet qualification interrupted by signal {signal_number}"
        )
        self.signal_number = signal_number


@contextlib.contextmanager
def qualification_signal_context():
    """Convert normal termination into cleanup-preserving exceptions."""
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("qualification signal handlers require the main thread")
    watched = (signal.SIGTERM, signal.SIGINT)
    previous = {number: signal.getsignal(number) for number in watched}
    original_mask = signal.pthread_sigmask(signal.SIG_BLOCK, set())
    interrupted = False

    def interrupt(signal_number, _frame):
        nonlocal interrupted
        if interrupted:
            return
        interrupted = True
        signal.pthread_sigmask(signal.SIG_BLOCK, watched)
        raise FleetQualificationInterrupted(signal_number)

    try:
        for number in watched:
            signal.signal(number, interrupt)
        yield
    finally:
        signal.pthread_sigmask(signal.SIG_BLOCK, watched)
        try:
            for number, handler in previous.items():
                signal.signal(number, handler)
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, original_mask)


def _listener_hosts(port: int) -> tuple[str, ...]:
    hosts: set[str] = set()
    for path, family in (
        (Path("/proc/net/tcp"), socket.AF_INET),
        (Path("/proc/net/tcp6"), socket.AF_INET6),
    ):
        for line in path.read_text(encoding="ascii").splitlines()[1:]:
            fields = line.split()
            if len(fields) < 4 or fields[3] != "0A":
                continue
            address, encoded_port = fields[1].split(":")
            if int(encoded_port, 16) != port:
                continue
            packed = bytes.fromhex(address)
            if family == socket.AF_INET:
                packed = packed[::-1]
            else:
                packed = b"".join(
                    packed[index : index + 4][::-1]
                    for index in range(0, len(packed), 4)
                )
            hosts.add(socket.inet_ntop(family, packed))
    return tuple(sorted(hosts))


class SystemFleetOperator:
    """Fresh host-state adapter for the root qualification controller."""

    _REMOTE_FLAGS = (
        "PWC_CHAT_REMOTE_WORKSPACE_TOOLS_ENABLED",
        "PWC_CHAT_REMOTE_BASH_ENABLED",
        "PWC_CHAT_REMOTE_READ_ENABLED",
        "PWC_CHAT_LAZY_WORKSPACE_ENABLED",
    )

    def __init__(
        self,
        *,
        release_id: str,
        app_root: Path = Path("/srv/paperswithcode"),
        status_root: Path = Path("/run/paperswithcode/external-pi"),
        environ: Mapping[str, str] = os.environ,
        listener_hosts: Callable[[int], tuple[str, ...]] = _listener_hosts,
        runner: Callable = subprocess.run,
        http_get: Callable = httpx.get,
    ) -> None:
        self.release_id = release_id
        self.app_root = app_root
        self.status_root = status_root
        self.environ = environ
        self.listener_hosts = listener_hosts
        self.runner = runner
        self.http_get = http_get
        self.owner_id = str(uuid.uuid4())
        self._prompt_path: Path | None = None
        self._host_cpu_state: tuple[int, int] | None = None
        self._unit_cpu_state: dict[str, tuple[int, float]] = {}
        self.runtime_id = self._manifest()["external_pi_runtime"]["runtime_id"]

    def _manifest(self) -> dict:
        current = self.app_root / "environments/staging/current"
        if not current.is_symlink():
            raise FleetRunRefused("external Pi fleet active release is unavailable")
        release = current.resolve(strict=True)
        if (
            release.parent != self.app_root / "releases"
            or release.name != self.release_id
        ):
            raise FleetRunRefused(
                "external Pi fleet requires the exact active staging release"
            )
        manifest = json.loads(
            release.joinpath("release.json").read_text(encoding="utf-8")
        )
        descriptor = manifest.get("external_pi_runtime")
        if (
            manifest.get("release_id") != self.release_id
            or not isinstance(descriptor, dict)
            or not isinstance(descriptor.get("runtime_id"), str)
        ):
            raise FleetRunRefused("external Pi fleet release manifest is invalid")
        return manifest

    def _active_worker(self) -> tuple[str, bool]:
        staging = self.app_root / "environments/staging"
        active = staging / "active"
        if not active.is_symlink():
            raise FleetRunRefused("external Pi fleet active worker is unavailable")
        target = active.resolve(strict=True)
        slot = next(
            (
                name
                for name in ("blue", "green")
                if target == (staging / "slots" / name).resolve(strict=True)
            ),
            None,
        )
        if slot is None:
            raise FleetRunRefused("external Pi fleet active worker is invalid")
        slot_release = target.joinpath("release").resolve(strict=True)
        current_release = staging.joinpath("current").resolve(strict=True)
        status = json.loads(
            self.status_root.joinpath(f"staging-{slot}.json").read_text(
                encoding="utf-8"
            )
        )

        def unit_active(unit: str) -> bool:
            result = self.runner(
                [
                    "systemctl",
                    "show",
                    "--property=ActiveState",
                    "--value",
                    unit,
                ],
                check=False,
                text=True,
                capture_output=True,
                timeout=10,
            )
            return result.returncode == 0 and result.stdout.strip() == "active"

        units_active = all(
            unit_active(unit)
            for unit in (
                f"paperswithcode-staging-external-pi@{slot}.service",
                f"paperswithcode-staging-external-pi-worker@{slot}.service",
            )
        )
        healthy = (
            units_active
            and slot_release == current_release
            and status.get("release_id") == self.release_id
            and status.get("worker_id") == f"staging-{slot}"
            and status.get("state") == "ready"
            and status.get("authenticated") is True
            and status.get("registered") is True
            and type(status.get("generation")) is int
            and status["generation"] >= 1
        )
        try:
            response = self.http_get(
                f"http://127.0.0.1:{8766 if slot == 'blue' else 8767}/v1/status",
                headers={
                    "Authorization": "Bearer "
                    + self.environ.get("PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN", "")
                },
                timeout=5.0,
                follow_redirects=False,
                trust_env=False,
            )
            response.raise_for_status()
            live = ExternalPiWorkerStatus.model_validate(response.json())
        except (httpx.HTTPError, ValueError):
            raise FleetRunRefused(
                "external Pi fleet active worker health is invalid"
            ) from None
        counters = live.operation_counters
        healthy = healthy and (
            live.worker_id == f"staging-{slot}"
            and live.release_id == self.release_id
            and live.state == "ready"
            and live.active_sessions == 0
            and live.maximum_sessions == 8
            and live.worker_generation == status.get("generation")
            and not live.capability_evidence.provider_credentials_present
            and not live.capability_evidence.modal_credentials_present
            and live.capability_evidence.registered_tool_count == 0
            and not any(
                (
                    counters.model_calls,
                    counters.tool_calls,
                    counters.provider_calls,
                    counters.modal_calls,
                    counters.billing_events,
                )
            )
        )
        if not healthy:
            raise FleetRunRefused("external Pi fleet active worker health is invalid")
        return f"staging-{slot}", healthy

    def revalidate(self, shape: FleetShape, active: Sequence[object]) -> None:
        self._manifest()
        active_worker_id, active_worker_healthy = self._active_worker()
        admission = (
            self.environ.get("PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED") != "false"
        )
        executor = self.environ.get("PWC_CHAT_SANDBOX_EXECUTOR_ENABLED") != "false"
        remote = any(self.environ.get(name) != "false" for name in self._REMOTE_FLAGS)
        config = FleetSafetyConfig(
            environment="staging",
            requested_release=self.release_id,
            active_release=self.release_id,
            external_admission_enabled=admission,
            executor_routing_enabled=executor,
            remote_execution_enabled=remote,
            active_worker_id=active_worker_id,
            active_worker_healthy=active_worker_healthy,
            worker_token=self.environ.get("PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN", ""),
        )
        validate_fleet_preflight(
            config,
            shape,
            tuple(
                PortState(replica.port, "127.0.0.1", True) for replica in shape.replicas
            ),
        )
        active_replicas = tuple(
            FleetReplica(item.worker_id, item.port) for item in active
        )
        if active_replicas:
            route_ordinal(0, active_replicas)
        active_by_port = {
            item.port: evidence
            for item, evidence in zip(active_replicas, active, strict=True)
        }
        for replica in shape.replicas:
            hosts = self.listener_hosts(replica.port)
            active_evidence = active_by_port.get(replica.port)
            if active_evidence is not None:
                ready_observed = hasattr(active_evidence, "generation")
                if hosts not in (
                    (("127.0.0.1",),) if ready_observed else ((), ("127.0.0.1",))
                ):
                    raise FleetRunRefused(
                        "external Pi fleet active ports must remain loopback-only"
                    )
            elif hosts:
                raise FleetRunRefused(
                    "external Pi fleet inactive qualification ports must remain free"
                )

    def _systemctl_properties(self, unit: str, *names: str) -> dict[str, int]:
        result = self.runner(
            ["systemctl", "show", *(f"--property={name}" for name in names), unit],
            check=False,
            text=True,
            capture_output=True,
            timeout=10,
        )
        if result.returncode != 0:
            return {name: 0 for name in names}
        values: dict[str, int] = {}
        for line in result.stdout.splitlines():
            key, separator, raw = line.partition("=")
            if separator and key in names:
                try:
                    values[key] = int(raw)
                except ValueError:
                    values[key] = 0
        return {name: max(0, values.get(name, 0)) for name in names}

    @staticmethod
    def _mem_available_bytes() -> int:
        for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
            if line.startswith("MemAvailable:"):
                value = int(line.split()[1]) * 1024
                return min(value, 2**63 - 1)
        raise FleetRunRefused("external Pi fleet host memory evidence is unavailable")

    def _host_cpu_percent(self) -> float:
        fields = Path("/proc/stat").read_text(encoding="ascii").splitlines()[0].split()
        if fields[0] != "cpu" or len(fields) < 6:
            raise FleetRunRefused("external Pi fleet host CPU evidence is unavailable")
        counters = tuple(int(value) for value in fields[1:])
        total = sum(counters)
        idle = counters[3] + counters[4]
        previous = self._host_cpu_state
        self._host_cpu_state = (total, idle)
        if previous is None or total <= previous[0]:
            return 0.0
        busy_delta = (total - previous[0]) - (idle - previous[1])
        return max(0.0, min(100.0, busy_delta * 100 / (total - previous[0])))

    def resource_preflight(self, shape: FleetShape) -> ResourcePreflight:
        staging = self.app_root / "environments/staging"
        active = staging.joinpath("active").resolve(strict=True)
        slot = active.name
        if slot not in {"blue", "green"}:
            raise FleetRunRefused("external Pi fleet active worker is invalid")
        memory = sum(
            self._systemctl_properties(unit, "MemoryCurrent")["MemoryCurrent"]
            for unit in (
                f"paperswithcode-staging-external-pi@{slot}.service",
                f"paperswithcode-staging-external-pi-worker@{slot}.service",
            )
        )
        if memory <= 0:
            return ResourcePreflight(
                "resource_refused", 0, self._host_cpu_percent(), 80.0
            )
        snapshot = HostResourceSnapshot(
            mem_available_bytes=self._mem_available_bytes(),
            projected_additional_bytes=min(memory * shape.worker_count, 2**63 - 1),
            cpu_percent=self._host_cpu_percent(),
            cpu_guard_percent=80.0,
        )
        from backend.loadtests.external_pi_fleet_core import evaluate_resource_preflight

        return evaluate_resource_preflight(snapshot)

    def resolve(self, shape: FleetShape, index: int):
        replica = shape.replicas[index]
        resolved = lifecycle.resolve_qualification_replica(
            "staging",
            self.release_id,
            index,
            replica.port,
            shape.sessions_per_worker,
        )
        if self._prompt_path is None:
            self._prompt_path = resolved.prompt
        elif self._prompt_path != resolved.prompt:
            raise FleetRunRefused("external Pi fleet runtime prompt changed")
        return resolved

    def start(self, resolved) -> None:
        lifecycle.start_replica(resolved, runner=self.runner, owner_id=self.owner_id)

    def wait_ready(self, resolved) -> int:
        return lifecycle.wait_ready(resolved)

    def _worker_status(self, worker: WorkerEvidence) -> ExternalPiWorkerStatus:
        token = self.environ.get("PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN", "")
        try:
            response = self.http_get(
                f"http://127.0.0.1:{worker.port}/v1/status",
                headers={"Authorization": f"Bearer {token}"},
                timeout=5.0,
                follow_redirects=False,
                trust_env=False,
            )
            response.raise_for_status()
            return ExternalPiWorkerStatus.model_validate(response.json())
        except (httpx.HTTPError, ValueError):
            raise FleetRunRefused(
                "external Pi fleet worker status is invalid"
            ) from None

    def _validate_worker_status(
        self, worker: WorkerEvidence, status: ExternalPiWorkerStatus
    ) -> None:
        counters = status.operation_counters
        if (
            status.worker_id != worker.worker_id
            or status.release_id != self.release_id
            or status.state != "ready"
            or status.active_sessions != 0
            or status.maximum_sessions != worker.maximum_sessions
            or status.worker_generation != worker.generation
            or status.capability_evidence.provider_credentials_present
            or status.capability_evidence.modal_credentials_present
            or status.capability_evidence.registered_tool_count != 0
            or any(
                (
                    counters.model_calls,
                    counters.tool_calls,
                    counters.provider_calls,
                    counters.modal_calls,
                    counters.billing_events,
                )
            )
        ):
            raise FleetRunRefused("external Pi fleet worker evidence is unsafe")

    def run_round(
        self, name: str, workers: tuple[WorkerEvidence, ...]
    ) -> FleetRoundReport:
        if self._prompt_path is None:
            raise FleetRunRefused("external Pi fleet runtime prompt is unavailable")
        before = tuple(self._worker_status(worker) for worker in workers)
        for worker, status in zip(workers, before, strict=True):
            self._validate_worker_status(worker, status)
        from backend.loadtests.external_pi_fleet_locustfile import run_local_fleet_round

        result = run_local_fleet_round(
            replicas=tuple(
                FleetReplica(worker.worker_id, worker.port) for worker in workers
            ),
            prompt=self._prompt_path.read_text(encoding="utf-8"),
            token=self.environ["PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN"],
        )
        after = tuple(self._worker_status(worker) for worker in workers)
        for worker, status in zip(workers, after, strict=True):
            self._validate_worker_status(worker, status)
        shadow_delta = sum(
            final.operation_counters.shadow_requests
            - initial.operation_counters.shadow_requests
            for initial, final in zip(before, after, strict=True)
        )
        if shadow_delta != 100:
            raise FleetRunRefused("external Pi fleet shadow counter is inconsistent")
        return aggregate_round(
            name=name,
            observations=result.observations,
            protocol_errors=result.protocol_errors,
            transport_errors=result.transport_errors,
            forbidden_activity=ForbiddenActivity(),
        )

    def sample_resources(self, shape: FleetShape) -> ResourceEvidence:
        now = time.monotonic()
        unit_peaks = []
        for unit in qualification_unit_names(shape):
            values = self._systemctl_properties(
                unit, "MemoryPeak", "CPUUsageNSec", "TasksCurrent"
            )
            previous = self._unit_cpu_state.get(unit)
            self._unit_cpu_state[unit] = (values["CPUUsageNSec"], now)
            cpu_percent = 0.0
            if previous is not None and now > previous[1]:
                cpu_percent = max(
                    0.0,
                    min(
                        100.0,
                        (values["CPUUsageNSec"] - previous[0])
                        / ((now - previous[1]) * 1_000_000_000)
                        * 100,
                    ),
                )
            unit_peaks.append(
                UnitResourceEvidence(
                    unit_name=unit,
                    peak_memory_bytes=values["MemoryPeak"],
                    peak_cpu_percent=cpu_percent,
                    peak_tasks=values["TasksCurrent"],
                )
            )
        return ResourceEvidence(
            peak_memory_bytes=sum(item.peak_memory_bytes for item in unit_peaks),
            peak_cpu_percent=self._host_cpu_percent(),
            peak_tasks=sum(item.peak_tasks for item in unit_peaks),
            minimum_host_mem_available_bytes=self._mem_available_bytes(),
            unit_peaks=tuple(unit_peaks),
        )

    def cleanup(self, resolved, generation: int | None):
        return lifecycle.cleanup_replica(
            resolved, generation=generation, runner=self.runner
        )


def _clean() -> CleanupEvidence:
    return CleanupEvidence(
        drain_proven=True,
        registry_offline=True,
        supervisors_stopped_before_workers=True,
        units_removed=True,
        status_files_removed=True,
        ports_free=True,
        processes_gone=True,
    )


def _cleanup_evidence(results: Sequence[object]) -> CleanupEvidence:
    return CleanupEvidence(
        drain_proven=all(item.registry_offline for item in results),
        registry_offline=all(item.registry_offline for item in results),
        supervisors_stopped_before_workers=all(
            item.supervisors_stopped_before_workers for item in results
        ),
        units_removed=all(item.units_removed for item in results),
        status_files_removed=all(item.status_files_removed for item in results),
        ports_free=all(item.ports_free for item in results),
        processes_gone=all(item.processes_gone for item in results),
    )


def _merge_resources(samples: Sequence[ResourceEvidence]) -> ResourceEvidence:
    if not samples:
        raise FleetRunRefused("external Pi fleet resource evidence is missing")
    unit_names = tuple(item.unit_name for item in samples[0].unit_peaks)
    if any(
        tuple(item.unit_name for item in sample.unit_peaks) != unit_names
        for sample in samples
    ):
        raise FleetRunRefused("external Pi fleet resource evidence is inconsistent")
    unit_peaks = tuple(
        UnitResourceEvidence(
            unit_name=name,
            peak_memory_bytes=max(
                sample.unit_peaks[index].peak_memory_bytes for sample in samples
            ),
            peak_cpu_percent=max(
                sample.unit_peaks[index].peak_cpu_percent for sample in samples
            ),
            peak_tasks=max(sample.unit_peaks[index].peak_tasks for sample in samples),
        )
        for index, name in enumerate(unit_names)
    )
    return ResourceEvidence(
        peak_memory_bytes=max(item.peak_memory_bytes for item in samples),
        peak_cpu_percent=max(item.peak_cpu_percent for item in samples),
        peak_tasks=max(item.peak_tasks for item in samples),
        minimum_host_mem_available_bytes=min(
            item.minimum_host_mem_available_bytes for item in samples
        ),
        unit_peaks=unit_peaks,
    )


def _run_shape(operator: FleetOperator, shape: FleetShape):
    active: list[object] = []
    generations: dict[str, int] = {}
    workers: list[WorkerEvidence] = []
    cleanup_results: list[object] = []
    samples: list[ResourceEvidence] = []
    error: BaseException | None = None

    def checkpoint() -> None:
        evidence = tuple(
            WorkerEvidence(
                worker_id=resolved.worker_id,
                port=resolved.port,
                generation=generations[resolved.worker_id],
                maximum_sessions=shape.sessions_per_worker,
            )
            if resolved.worker_id in generations
            else resolved
            for resolved in active
        )
        operator.revalidate(shape, evidence)
        samples.append(operator.sample_resources(shape))

    checkpoint()
    preflight = operator.resource_preflight(shape)
    checkpoint()
    if preflight.status == "resource_refused":
        return build_resource_refused_shape_report(shape, preflight, _clean())

    healthy: FleetRoundReport | None = None
    survivor: FleetRoundReport | None = None
    removed_worker_id: str | None = None
    resolved_by_id: dict[str, object] = {}
    try:
        for index, replica in enumerate(shape.replicas):
            checkpoint()
            resolved = operator.resolve(shape, index)
            operator.start(resolved)
            active.append(resolved)
            resolved_by_id[replica.worker_id] = resolved
            checkpoint()
            checkpoint()
            generation = operator.wait_ready(resolved)
            generations[replica.worker_id] = generation
            workers.append(
                WorkerEvidence(
                    worker_id=replica.worker_id,
                    port=replica.port,
                    generation=generation,
                    maximum_sessions=shape.sessions_per_worker,
                )
            )
            checkpoint()

        checkpoint()
        healthy = operator.run_round("healthy", tuple(workers))
        checkpoint()

        removed = workers[0]
        removed_worker_id = removed.worker_id
        removed_resolved = resolved_by_id[removed.worker_id]
        checkpoint()
        cleanup_results.append(operator.cleanup(removed_resolved, removed.generation))
        active.remove(removed_resolved)
        checkpoint()

        survivor_workers = tuple(worker for worker in workers if worker != removed)
        checkpoint()
        survivor = operator.run_round("survivor", survivor_workers)
        checkpoint()
    except BaseException as exc:  # noqa: BLE001 - signals must enter cleanup
        error = exc
    finally:
        for resolved in tuple(active):
            worker_id = resolved.worker_id
            generation = generations.get(worker_id)
            try:
                checkpoint()
            except BaseException as checkpoint_error:  # noqa: BLE001
                if error is None:
                    error = checkpoint_error
            try:
                cleanup_results.append(operator.cleanup(resolved, generation))
                active.remove(resolved)
            except BaseException as cleanup_error:  # noqa: BLE001 - keep cleaning
                if error is None:
                    error = cleanup_error
                continue
            try:
                checkpoint()
            except BaseException as checkpoint_error:  # noqa: BLE001
                if error is None:
                    error = checkpoint_error

    if error is not None:
        raise error
    if healthy is None or survivor is None or removed_worker_id is None:
        raise FleetRunRefused("external Pi fleet shape evidence is incomplete")
    return build_completed_shape_report(
        shape=shape,
        healthy=healthy,
        survivor=survivor,
        workers=tuple(workers),
        removed_worker_id=removed_worker_id,
        resources=_merge_resources(samples),
        resource_preflight=preflight,
        cleanup=_cleanup_evidence(cleanup_results),
    )


def run_fleet_controller(
    operator: FleetOperator,
    *,
    release_id: str,
    report_path: Path,
    report_root: Path,
    shape_names: tuple[FleetShapeName, ...] = ("5x32", "8x16", "16x8"),
    geteuid: Callable[[], int] = os.geteuid,
) -> FleetQualificationReport:
    """Run allowlisted shapes sequentially and atomically retain final evidence."""
    if geteuid() != 0:
        raise FleetRunRefused("external Pi fleet controller requires a root operator")
    with qualification_signal_context():
        reports = tuple(
            _run_shape(operator, resolve_fleet_shape(name)) for name in shape_names
        )
        final = build_final_report(
            release_id=release_id,
            runtime_id=operator.runtime_id,
            shapes=reports,
        )
        publish_fleet_report(final, report_path, report_root)
    return final


REPORT_ROOT = Path("/var/lib/paperswithcode/staging")
REPORT_PATH = REPORT_ROOT / "external-pi-fleet-qualification.json"
CONFIRMATION = "RUN_EXTERNAL_PI_FLEET_QUALIFICATION"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", choices=("staging",), required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("run through sudo as the root operator")
    if args.confirm != CONFIRMATION:
        parser.error("exact fleet qualification confirmation is required")
    try:
        operator = SystemFleetOperator(release_id=args.release_id)
        report = run_fleet_controller(
            operator,
            release_id=args.release_id,
            report_path=args.report,
            report_root=REPORT_ROOT,
        )
    except Exception:  # noqa: BLE001 - CLI must never emit protected details
        print("external Pi fleet qualification failed closed", file=os.sys.stderr)
        return 1
    return 0 if report.preferred_shape is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
