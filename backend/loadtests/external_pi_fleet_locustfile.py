"""Thin direct-loopback Locust adapter for external Pi fleet qualification."""

from __future__ import annotations

import itertools
import time
import warnings
from collections.abc import Callable
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Literal

import gevent
from gevent.event import Event
from gevent.lock import Semaphore
from gevent.monkey import MonkeyPatchWarning

with warnings.catch_warnings():
    warnings.simplefilter("ignore", MonkeyPatchWarning)
    from locust import HttpUser, between, events, task
    from locust.env import Environment
    from locust.exception import StopUser
    from locust.runners import LocalRunner

from requests.exceptions import RequestException

from backend.loadtests.external_pi_fleet_core import (
    EXPECTED_USERS,
    DurableTurnObservation,
    DurableWorkload,
    FleetReplica,
    FleetRunRefused,
    build_external_pi_fleet_request,
    classify_external_pi_fleet_response,
    route_ordinal,
    resolve_durable_profile,
)
from backend.loadtests.external_pi_shadow_core import BaselineObservation


@dataclass(frozen=True, slots=True)
class FleetRoundConfig:
    replicas: tuple[FleetReplica, ...]
    expected_users: int
    prompt: str = field(repr=False)
    token: str = field(repr=False)
    barrier_deadline: float
    abort_requested: Callable[[], bool] = field(repr=False)


@dataclass(frozen=True, slots=True)
class FleetRoundResult:
    observations: tuple[BaselineObservation, ...]
    protocol_errors: int
    transport_errors: int


@dataclass(frozen=True, slots=True)
class DurableUserSpec:
    ordinal: int
    workload: DurableWorkload
    arrival_delay_ms: Literal[0] = 0
    application_queue: Literal[False] = False


def build_durable_user_specs(profile_name: str) -> tuple[DurableUserSpec, ...]:
    """Build one immediate, deterministic user assignment without queue state."""
    profile = resolve_durable_profile(profile_name)
    return tuple(
        DurableUserSpec(ordinal=ordinal, workload=workload)
        for ordinal, workload in enumerate(profile.workloads)
    )


def build_durable_observation(**evidence) -> DurableTurnObservation:
    """Validate the bounded measurement schema; unknown/content fields fail."""
    return DurableTurnObservation.model_validate(evidence)


_ordinals = itertools.count()
_config: FleetRoundConfig | None = None
_observations: list[BaselineObservation] = []
_protocol_errors = 0
_transport_errors = 0
_arrival_gate = Event()
_arrival_lock = Semaphore()
_barrier_arrivals = 0
_barrier_failure: str | None = None


def configure_fleet_round(
    *,
    replicas: tuple[FleetReplica, ...],
    prompt: str,
    token: str,
    expected_users: int = EXPECTED_USERS,
    barrier_timeout_seconds: float = 5.0,
    abort_requested: Callable[[], bool] = lambda: False,
) -> None:
    """Set one bounded in-process round without serializing protected inputs."""
    global _arrival_gate, _arrival_lock, _barrier_arrivals, _barrier_failure
    global _config, _ordinals, _observations, _protocol_errors, _transport_errors
    route_ordinal(0, replicas)
    if type(expected_users) is not int or not 1 <= expected_users <= EXPECTED_USERS:
        raise FleetRunRefused("external Pi fleet expected users are invalid")
    if not prompt or not token:
        raise FleetRunRefused("external Pi fleet round inputs are incomplete")
    if not 0 < barrier_timeout_seconds <= 10:
        raise FleetRunRefused("external Pi fleet concurrency barrier is not bounded")
    _config = FleetRoundConfig(
        replicas=replicas,
        expected_users=expected_users,
        prompt=prompt,
        token=token,
        barrier_deadline=time.monotonic() + barrier_timeout_seconds,
        abort_requested=abort_requested,
    )
    _ordinals = itertools.count()
    _observations = []
    _protocol_errors = 0
    _transport_errors = 0
    _arrival_gate = Event()
    _arrival_lock = Semaphore()
    _barrier_arrivals = 0
    _barrier_failure = None


def fleet_round_result() -> FleetRoundResult:
    return FleetRoundResult(
        observations=tuple(_observations),
        protocol_errors=_protocol_errors,
        transport_errors=_transport_errors,
    )


def run_local_fleet_round(
    *,
    replicas: tuple[FleetReplica, ...],
    prompt: str,
    token: str,
    expected_users: int = EXPECTED_USERS,
    timeout_seconds: float = 30.0,
    abort_requested: Callable[[], bool] = lambda: False,
    monotonic: Callable[[], float] = time.monotonic,
    barrier_timeout_seconds: float = 5.0,
) -> FleetRoundResult:
    """Run one exact bounded profile in one process and return its evidence."""
    if not 0 < timeout_seconds <= 60:
        raise FleetRunRefused("external Pi fleet Locust timeout is not bounded")
    if barrier_timeout_seconds > timeout_seconds:
        raise FleetRunRefused("external Pi fleet concurrency barrier exceeds timeout")
    configure_fleet_round(
        replicas=replicas,
        prompt=prompt,
        token=token,
        expected_users=expected_users,
        barrier_timeout_seconds=barrier_timeout_seconds,
        abort_requested=abort_requested,
    )
    environment = Environment(
        user_classes=[ExternalPiFleetUser],
        host=None,
        parsed_options=SimpleNamespace(
            num_users=expected_users, spawn_rate=float(expected_users)
        ),
    )
    runner = environment.create_local_runner()
    _validate_runner(environment)
    deadline = monotonic() + timeout_seconds
    try:
        runner.start(user_count=expected_users, spawn_rate=float(expected_users))
        while monotonic() < deadline:
            if _barrier_failure is not None:
                raise FleetRunRefused(_barrier_failure)
            if abort_requested():
                _fail_barrier("external Pi fleet concurrency barrier aborted")
                raise FleetRunRefused("external Pi fleet round aborted by safety guard")
            if runner.user_count == 0 and len(_observations) == expected_users:
                break
            gevent.sleep(0.05)
        else:
            _fail_barrier("external Pi fleet round timed out")
    finally:
        _arrival_gate.set()
        runner.quit()
    if _barrier_failure is not None:
        raise FleetRunRefused(_barrier_failure)
    result = fleet_round_result()
    if len(result.observations) != expected_users:
        raise FleetRunRefused(
            "external Pi fleet Locust round requires the exact expected observations"
        )
    return result


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1_000))


def _fail_barrier(reason: str) -> None:
    global _barrier_failure
    with _arrival_lock:
        if _barrier_failure is None:
            _barrier_failure = reason
        _arrival_gate.set()


def _await_concurrency_barrier(config: FleetRoundConfig) -> bool:
    global _barrier_arrivals, _barrier_failure
    with _arrival_lock:
        if _barrier_failure is not None:
            return False
        _barrier_arrivals += 1
        if _barrier_arrivals == config.expected_users:
            if config.abort_requested():
                _barrier_failure = "external Pi fleet concurrency barrier aborted"
                _arrival_gate.set()
            elif time.monotonic() >= config.barrier_deadline:
                _barrier_failure = "external Pi fleet concurrency barrier timed out"
                _arrival_gate.set()
            else:
                _arrival_gate.set()
    while not _arrival_gate.wait(timeout=0.01):
        if config.abort_requested():
            _fail_barrier("external Pi fleet concurrency barrier aborted")
        elif time.monotonic() >= config.barrier_deadline:
            _fail_barrier("external Pi fleet concurrency barrier timed out")
    return _barrier_failure is None and not config.abort_requested()


@events.test_start.add_listener
def _start(environment, **_kwargs) -> None:
    _validate_runner(environment)


def _validate_runner(environment: Environment) -> None:
    """Reject an unsafe runner synchronously before Locust starts users."""
    if not isinstance(environment.runner, LocalRunner):
        raise FleetRunRefused("external Pi fleet requires one local Locust runner")
    if _config is None:
        raise FleetRunRefused("external Pi fleet round is not configured")
    options = environment.parsed_options
    if getattr(options, "num_users", None) != _config.expected_users or getattr(
        options, "spawn_rate", None
    ) != float(_config.expected_users):
        raise FleetRunRefused(
            "external Pi fleet requires the exact configured users and spawn rate"
        )
    if environment.host is not None:
        raise FleetRunRefused("external Pi fleet must not accept a Locust host")


class ExternalPiFleetUser(HttpUser):
    host = "http://127.0.0.1"
    wait_time = between(0, 0)

    def on_start(self) -> None:
        self.client.trust_env = False
        self.client.proxies.clear()

    @task
    def run_once(self) -> None:
        global _protocol_errors, _transport_errors
        if getattr(self, "_fleet_request_started", False):
            raise StopUser()
        self._fleet_request_started = True
        config = _config
        if config is None:
            raise StopUser()
        if not _await_concurrency_barrier(config):
            raise StopUser()
        ordinal = next(_ordinals)
        if ordinal >= config.expected_users:
            raise StopUser()
        replica = route_ordinal(
            ordinal, config.replicas, expected_users=config.expected_users
        )
        request = build_external_pi_fleet_request(ordinal, config.prompt)
        started = time.perf_counter()
        observation = BaselineObservation("error", 0)
        try:
            with self.client.post(
                f"{replica.worker_url}/v1/shadow",
                headers={"Authorization": f"Bearer {config.token}"},
                json=request.wire_payload(),
                name="external_pi.error",
                catch_response=True,
                timeout=10.0,
                allow_redirects=False,
            ) as response:
                try:
                    payload = response.json()
                except ValueError:
                    payload = None
                observation = classify_external_pi_fleet_response(
                    request=request,
                    status_code=response.status_code,
                    payload=payload,
                    latency_ms=_elapsed_ms(started),
                )
                response.request_meta["name"] = (
                    f"external_pi.{observation.classification}"
                )
                if observation.classification == "error":
                    _protocol_errors += 1
                    response.failure("external_pi.error")
                else:
                    response.success()
        except RequestException:
            _transport_errors += 1
            observation = BaselineObservation("error", _elapsed_ms(started))
        _observations.append(observation)
        raise StopUser()
