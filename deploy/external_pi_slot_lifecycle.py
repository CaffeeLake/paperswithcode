#!/usr/bin/env python3
"""Release-managed lifecycle for the staging external Pi shadow worker."""

from __future__ import annotations

import json
import math
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

try:
    from deploy.external_pi_runtime import external_pi_runtime_manifest
except ModuleNotFoundError:
    from external_pi_runtime import external_pi_runtime_manifest  # type: ignore[no-redef]

APP_ROOT = Path(os.environ.get("PWC_DEPLOY_APP_ROOT", "/srv/paperswithcode"))
CONFIG_ROOT = Path(os.environ.get("PWC_DEPLOY_CONFIG_ROOT", "/etc/paperswithcode"))
STATUS_ROOT = Path(
    os.environ.get("PWC_EXTERNAL_PI_STATUS_ROOT", "/run/paperswithcode/external-pi")
)
SLOT_PORTS = {"blue": 8766, "green": 8767}
MAXIMUM_SESSIONS = 8
CONTRACT_VERSION = "external-pi-v1"
DRAIN_SECONDS_MINIMUM = 5
DRAIN_SECONDS_MAXIMUM = 300
DRAIN_POLL_SECONDS_MINIMUM = 0.1
DRAIN_POLL_SECONDS_MAXIMUM = 5.0
NODE_TERMINATION_OVERHEAD_SECONDS = 5
SYSTEMCTL_COMPLETION_OVERHEAD_SECONDS = 5
MAXIMUM_DRAIN_STOP_TIMEOUT_SECONDS = (
    DRAIN_SECONDS_MAXIMUM
    + DRAIN_POLL_SECONDS_MAXIMUM
    + NODE_TERMINATION_OVERHEAD_SECONDS
    + SYSTEMCTL_COMPLETION_OVERHEAD_SECONDS
)

_SUPERVISOR_PROTECTED_KEYS = (
    "PWC_DB_HOST",
    "PWC_DB_PORT",
    "PWC_DB_NAME",
    "PWC_DB_USER",
    "PWC_DB_PASSWORD",
    "PWC_DB_SEARCH_PATH",
    "PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN",
    "PWC_CHAT_EXTERNAL_PI_HEARTBEAT_SECONDS",
    "PWC_CHAT_EXTERNAL_PI_LEASE_SECONDS",
    "PWC_CHAT_EXTERNAL_PI_STARTUP_TIMEOUT_SECONDS",
    "PWC_CHAT_EXTERNAL_PI_DRAIN_SECONDS",
    "PWC_CHAT_EXTERNAL_PI_DRAIN_POLL_SECONDS",
)


class ExternalPiSlotError(RuntimeError):
    """One shadow slot failed its bounded lifecycle transition."""


@dataclass(frozen=True, slots=True)
class ExternalPiSlot:
    slot: str
    port: int
    worker_id: str
    release: Path
    release_id: str
    runtime: Path
    node: Path
    entry_point: Path
    prompt: Path
    status_path: Path


def resolve_external_pi_slot(environment: str, slot: str) -> ExternalPiSlot:
    if environment != "staging":
        raise ValueError("external Pi slot lifecycle is staging-only")
    if slot not in SLOT_PORTS:
        raise ValueError("external Pi deployment slot is invalid")
    release_link = APP_ROOT / "environments/staging/slots" / slot / "release"
    if not release_link.is_symlink():
        raise ValueError("external Pi slot release pointer is missing")
    release = release_link.resolve(strict=True)
    manifest = json.loads((release / "release.json").read_text(encoding="utf-8"))
    descriptor = manifest.get("external_pi_runtime")
    if not isinstance(descriptor, dict):
        raise ValueError("release has no recorded external Pi runtime")
    identifier = descriptor.get("runtime_id")
    contract = descriptor.get("contract")
    if not isinstance(identifier, str) or not isinstance(contract, str):
        raise ValueError("release recorded external Pi runtime is invalid")
    runtime = APP_ROOT / "runtimes/external-pi" / identifier
    runtime_value = external_pi_runtime_manifest(
        runtime,
        expected_id=identifier,
        expected_contract=contract,
    )
    entry_point = runtime / str(runtime_value["entry_point"])
    return ExternalPiSlot(
        slot=slot,
        port=SLOT_PORTS[slot],
        worker_id=f"staging-{slot}",
        release=release,
        release_id=str(manifest["release_id"]),
        runtime=runtime,
        node=runtime / "node/bin/node",
        entry_point=entry_point,
        prompt=runtime / "assets/pi-system-prompt.txt",
        status_path=STATUS_ROOT / f"staging-{slot}.json",
    )


def node_environment(
    resolved: ExternalPiSlot,
    protected: dict[str, str],
    *,
    instance_id: str,
) -> dict[str, str]:
    token = protected.get("PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN", "")
    if len(token) < 32:
        raise ValueError("external Pi worker token is missing or too short")
    return {
        "PWC_EXTERNAL_PI_HOST": "127.0.0.1",
        "PWC_EXTERNAL_PI_PORT": str(resolved.port),
        "PWC_EXTERNAL_PI_TOKEN": token,
        "PWC_EXTERNAL_PI_MAX_SESSIONS": str(MAXIMUM_SESSIONS),
        "PWC_EXTERNAL_PI_WORKER_ID": resolved.worker_id,
        "PWC_EXTERNAL_PI_INSTANCE_ID": instance_id,
        "PWC_EXTERNAL_PI_RELEASE_ID": resolved.release_id,
        "PWC_EXTERNAL_PI_PROMPT_PATH": str(resolved.prompt),
        "PWC_EXTERNAL_PI_TOOL_NAMES": "[]",
    }


def supervisor_environment(
    resolved: ExternalPiSlot, protected: dict[str, str]
) -> dict[str, str]:
    values = {
        key: protected[key] for key in _SUPERVISOR_PROTECTED_KEYS if key in protected
    }
    values.update(
        {
            "PWC_ENVIRONMENT": "staging",
            "PWC_RELEASE_ID": resolved.release_id,
            "PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED": "true",
            "PWC_CHAT_EXTERNAL_PI_WORKER_URL": f"http://127.0.0.1:{resolved.port}",
            "PWC_CHAT_EXTERNAL_PI_WORKER_CONTRACT_VERSION": CONTRACT_VERSION,
            "PWC_CHAT_EXTERNAL_PI_WORKER_MAX_SESSIONS": str(MAXIMUM_SESSIONS),
            "PWC_CHAT_EXTERNAL_PI_HEARTBEAT_SECONDS": protected.get(
                "PWC_CHAT_EXTERNAL_PI_HEARTBEAT_SECONDS", "10"
            ),
            "PWC_CHAT_EXTERNAL_PI_LEASE_SECONDS": protected.get(
                "PWC_CHAT_EXTERNAL_PI_LEASE_SECONDS", "30"
            ),
            "PWC_CHAT_EXTERNAL_PI_STARTUP_TIMEOUT_SECONDS": protected.get(
                "PWC_CHAT_EXTERNAL_PI_STARTUP_TIMEOUT_SECONDS", "60"
            ),
            "PWC_CHAT_EXTERNAL_PI_DRAIN_SECONDS": protected.get(
                "PWC_CHAT_EXTERNAL_PI_DRAIN_SECONDS", "60"
            ),
            "PWC_CHAT_EXTERNAL_PI_DRAIN_POLL_SECONDS": protected.get(
                "PWC_CHAT_EXTERNAL_PI_DRAIN_POLL_SECONDS", "1"
            ),
            "PWC_EXTERNAL_PI_STATUS_PATH": str(resolved.status_path),
        }
    )
    return values


def _unit(environment: str, slot: str) -> str:
    if environment != "staging" or slot not in SLOT_PORTS:
        raise ValueError("external Pi slot lifecycle is staging-only")
    return f"paperswithcode-staging-external-pi@{slot}.service"


def _status_path(environment: str, slot: str) -> Path:
    if environment != "staging" or slot not in SLOT_PORTS:
        raise ValueError("external Pi slot lifecycle is staging-only")
    return STATUS_ROOT / f"staging-{slot}.json"


def _read_status(environment: str, slot: str) -> dict:
    path = _status_path(environment, slot)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def slot_status(environment: str, slot: str) -> dict:
    """Return the release-managed lifecycle evidence for one staging slot."""
    return _read_status(environment, slot)


def _protected_staging_values() -> dict[str, str]:
    path = CONFIG_ROOT / "staging.env"
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, raw = line.partition("=")
        if separator:
            values[key] = raw.strip().strip("\"'")
    return values


def drain_stop_timeout_seconds(environment: str) -> float:
    """Bound systemctl by the protected drain contract plus fixed teardown time."""
    if environment != "staging":
        raise ValueError("external Pi drain lifecycle is staging-only")
    values = _protected_staging_values()
    raw_drain = values.get("PWC_CHAT_EXTERNAL_PI_DRAIN_SECONDS", "60")
    raw_poll = values.get("PWC_CHAT_EXTERNAL_PI_DRAIN_POLL_SECONDS", "1")
    try:
        drain_seconds = int(raw_drain)
        poll_seconds = float(raw_poll)
    except ValueError as error:
        raise ValueError("external Pi drain configuration must be numeric") from error
    if not DRAIN_SECONDS_MINIMUM <= drain_seconds <= DRAIN_SECONDS_MAXIMUM:
        raise ValueError("external Pi drain seconds are outside protected bounds")
    if (
        not math.isfinite(poll_seconds)
        or not DRAIN_POLL_SECONDS_MINIMUM <= poll_seconds <= DRAIN_POLL_SECONDS_MAXIMUM
    ):
        raise ValueError("external Pi drain polling is outside protected bounds")
    return (
        drain_seconds
        + poll_seconds
        + NODE_TERMINATION_OVERHEAD_SECONDS
        + SYSTEMCTL_COMPLETION_OVERHEAD_SECONDS
    )


def start_slot(environment: str, slot: str) -> None:
    _status_path(environment, slot).unlink(missing_ok=True)
    subprocess.run(["systemctl", "start", _unit(environment, slot)], check=True)


def qualify_candidate(
    environment: str,
    slot: str,
    release_id: str,
    *,
    timeout_seconds: float = 65,
) -> int:
    deadline = time.monotonic() + timeout_seconds
    last: dict = {}
    while time.monotonic() < deadline:
        last = _read_status(environment, slot)
        generation = last.get("generation")
        if (
            last.get("release_id") == release_id
            and last.get("worker_id") == f"staging-{slot}"
            and last.get("state") == "ready"
            and last.get("authenticated") is True
            and last.get("registered") is True
            and isinstance(generation, int)
            and generation >= 1
            and isinstance(last.get("heartbeats"), int)
            and last["heartbeats"] >= 1
        ):
            return generation
        time.sleep(0.25)
    raise ExternalPiSlotError(f"external Pi candidate qualification failed: {last!r}")


def stop_slot(
    environment: str,
    slot: str,
    release_id: str,
) -> None:
    timeout_seconds = drain_stop_timeout_seconds(environment)
    previous = _read_status(environment, slot)
    try:
        subprocess.run(
            ["systemctl", "stop", _unit(environment, slot)],
            check=True,
            timeout=timeout_seconds,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise ExternalPiSlotError("external Pi worker drain timed out") from error
    if not previous:
        return
    if previous.get("release_id") != release_id:
        if previous.get("state") == "offline" and previous.get("drained") is True:
            return
        value = _read_status(environment, slot)
        if value.get("state") == "offline" and value.get("drained") is True:
            return
        raise ExternalPiSlotError(
            f"external Pi stale worker did not prove graceful drain: {value!r}"
        )
    value = _read_status(environment, slot)
    if not (
        value.get("release_id") == release_id
        and value.get("state") == "offline"
        and value.get("drained") is True
    ):
        raise ExternalPiSlotError(
            f"external Pi worker did not prove graceful drain: {value!r}"
        )


def prepare_candidate(environment: str, slot: str, release_id: str) -> int:
    stop_timeout_seconds = drain_stop_timeout_seconds(environment)
    try:
        start_slot(environment, slot)
        first_generation = qualify_candidate(environment, slot, release_id)
        stop_slot(environment, slot, release_id)
        start_slot(environment, slot)
        restarted_generation = qualify_candidate(environment, slot, release_id)
        if restarted_generation <= first_generation:
            raise ExternalPiSlotError(
                "external Pi restart did not advance fencing generation"
            )
        return restarted_generation
    except (
        ExternalPiSlotError,
        OSError,
        ValueError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ):
        subprocess.run(
            ["systemctl", "stop", _unit(environment, slot)],
            check=False,
            timeout=stop_timeout_seconds,
        )
        raise


def _configured_enabled(environment: str) -> bool:
    if environment != "staging":
        return False
    return (
        _protected_staging_values()
        .get("PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED", "false")
        .lower()
        == "true"
    )


def prepare_candidate_if_enabled(environment: str, slot: str, release_id: str) -> bool:
    if not _configured_enabled(environment):
        return False
    prepare_candidate(environment, slot, release_id)
    return True


def stop_slot_if_enabled(environment: str, slot: str, release_id: str) -> bool:
    if not _configured_enabled(environment):
        return False
    stop_slot(environment, slot, release_id)
    return True
