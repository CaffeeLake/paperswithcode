"""Pure guarded controller for staging durable external-turn qualification.

Task 11 defines the transaction and evidence contracts only. A live system adapter is
intentionally supplied by the separately authorized staging operation in Task 12.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from backend.loadtests.external_pi_fleet_core import (
    DurableProfileReport,
    DurableQualificationProfile,
    HostResourceSnapshot,
    evaluate_resource_preflight,
    resolve_durable_profile,
)

_STAGING_RELEASE = re.compile(r"^[0-9a-f]{12}-staging$")
_MIN_APPROVED_HOST_MEMORY_BYTES = 7 * 1024**3
_MAX_APPROVED_HOST_MEMORY_BYTES = 9 * 1024**3


class QualificationRefused(RuntimeError):
    """The durable-turn qualification would violate an operator gate."""


@dataclass(frozen=True, slots=True)
class QualificationEnvironment:
    name: str
    target_release: str
    staging_release: str
    production_release: str
    host_mem_total_bytes: int
    public_external_admission_flags: tuple[bool, ...]


@dataclass(frozen=True, slots=True)
class QualificationResult:
    status: Literal["completed", "resource_refused"]
    reason: Literal["memory_headroom"] | None
    profiles: tuple[DurableProfileReport, ...]


class DurableQualificationOperator(Protocol):
    def environment(self) -> QualificationEnvironment: ...

    def snapshot_flags(self) -> Mapping[str, bool]: ...

    def resource_snapshot(
        self, profile: DurableQualificationProfile
    ) -> HostResourceSnapshot: ...

    def setup_profile(self, profile: DurableQualificationProfile) -> None: ...

    def run_profile(
        self, profile: DurableQualificationProfile
    ) -> DurableProfileReport: ...

    def teardown_profile(self, profile: DurableQualificationProfile) -> None: ...

    def restore_flags(self, flags: Mapping[str, bool]) -> None: ...

    def cleanup_transient_workers(self) -> None: ...


def validate_qualification_environment(environment: QualificationEnvironment) -> None:
    """Require an isolated exact staging release on the approved 8 GiB class."""
    if (
        environment.name != "staging"
        or environment.production_release == environment.target_release
    ):
        raise QualificationRefused("staging_isolation_required")
    if (
        environment.target_release != environment.staging_release
        or not _STAGING_RELEASE.fullmatch(environment.target_release)
    ):
        raise QualificationRefused("exact_staging_release_required")
    if (
        type(environment.host_mem_total_bytes) is not int
        or not _MIN_APPROVED_HOST_MEMORY_BYTES
        <= environment.host_mem_total_bytes
        <= _MAX_APPROVED_HOST_MEMORY_BYTES
    ):
        raise QualificationRefused("approved_8_gib_host_required")
    if not environment.public_external_admission_flags or any(
        type(flag) is not bool or flag
        for flag in environment.public_external_admission_flags
    ):
        raise QualificationRefused("public_external_admission_flags_must_be_off")


def _resource_refused(
    profile: DurableQualificationProfile, snapshot: HostResourceSnapshot
) -> bool:
    preflight = evaluate_resource_preflight(snapshot)
    return (
        preflight.status == "resource_refused"
        or preflight.projected_mem_available_bytes < profile.minimum_available_bytes
    )


def _run_durable_qualification(
    operator: DurableQualificationOperator,
    *,
    profiles: Sequence[str] = (
        "32-functional-turns",
        "100-immediate-admission",
    ),
) -> QualificationResult:
    """Run profiles in order with fail-closed restoration around every outcome."""
    previous_flags = operator.snapshot_flags()
    reports: list[DurableProfileReport] = []
    try:
        profile_names = tuple(profiles)
        if profile_names != (
            "32-functional-turns",
            "100-immediate-admission",
        ):
            raise QualificationRefused("binding_profile_order_required")
        if not previous_flags or any(
            type(flag) is not bool or flag for flag in previous_flags.values()
        ):
            raise QualificationRefused("public_external_admission_flags_must_be_off")
        for profile_name in profile_names:
            profile = resolve_durable_profile(profile_name)
            validate_qualification_environment(operator.environment())
            snapshot = operator.resource_snapshot(profile)
            if _resource_refused(profile, snapshot):
                return QualificationResult(
                    status="resource_refused",
                    reason="memory_headroom",
                    profiles=tuple(reports),
                )
            try:
                operator.setup_profile(profile)
                report = operator.run_profile(profile)
                if report.profile != profile.name or not report.passed:
                    raise QualificationRefused("durable_profile_failed")
                reports.append(report)
            finally:
                operator.teardown_profile(profile)
        return QualificationResult(
            status="completed", reason=None, profiles=tuple(reports)
        )
    finally:
        try:
            operator.restore_flags(previous_flags)
        finally:
            operator.cleanup_transient_workers()


def run_durable_qualification(
    operator: DurableQualificationOperator,
    *,
    profiles: Sequence[str] = (
        "32-functional-turns",
        "100-immediate-admission",
    ),
) -> QualificationResult:
    """Expose only typed, content-free failures from the guarded transaction."""
    try:
        return _run_durable_qualification(operator, profiles=profiles)
    except QualificationRefused:
        raise
    except BaseException:
        raise QualificationRefused("durable_qualification_failed") from None


__all__ = (
    "DurableQualificationOperator",
    "QualificationEnvironment",
    "QualificationRefused",
    "QualificationResult",
    "run_durable_qualification",
    "validate_qualification_environment",
)
