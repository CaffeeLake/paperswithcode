"""Pure guarded controller for staging durable external-turn qualification.

Task 11 defines the transaction and evidence contracts only. A live system adapter is
intentionally supplied by the separately authorized staging operation in Task 12.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from backend.loadtests.external_pi_fleet_core import (
    DurableProfileReport,
    DurableQualificationReport,
    DurableQualificationProfile,
    HostResourceSnapshot,
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
class ImmutableFlagSnapshot:
    entries: tuple[tuple[str, bool], ...]

    @classmethod
    def capture(cls, value: Mapping[str, bool]) -> ImmutableFlagSnapshot:
        if not isinstance(value, Mapping) or not 1 <= len(value) <= 32:
            raise QualificationRefused("public_external_admission_flags_are_invalid")
        entries = tuple(sorted(value.items()))
        if any(
            not isinstance(name, str)
            or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", name)
            or type(enabled) is not bool
            for name, enabled in entries
        ):
            raise QualificationRefused("public_external_admission_flags_are_invalid")
        return cls(entries)

    @property
    def any_enabled(self) -> bool:
        return any(enabled for _, enabled in self.entries)

    def as_dict(self) -> dict[str, bool]:
        return dict(self.entries)


@dataclass(frozen=True, slots=True)
class CleanupProof:
    exact_workers_drained: bool
    transient_workers_removed: bool
    listeners_gone: bool
    status_files_gone: bool
    processes_gone: bool
    final_active_backend_turns: int
    final_active_external_workers: int
    final_active_sandboxes: int

    def __post_init__(self) -> None:
        values = (
            self.exact_workers_drained,
            self.transient_workers_removed,
            self.listeners_gone,
            self.status_files_gone,
            self.processes_gone,
        )
        counts = (
            self.final_active_backend_turns,
            self.final_active_external_workers,
            self.final_active_sandboxes,
        )
        if any(type(value) is not bool for value in values) or any(
            type(count) is not int or count < 0 or count > 1_000_000 for count in counts
        ):
            raise ValueError("durable cleanup proof is invalid")

    @property
    def passed(self) -> bool:
        return (
            self.exact_workers_drained
            and self.transient_workers_removed
            and self.listeners_gone
            and self.status_files_gone
            and self.processes_gone
            and self.final_active_backend_turns == 0
            and self.final_active_external_workers == 0
            and self.final_active_sandboxes == 0
        )


_FAILED_CLEANUP = CleanupProof(False, False, False, False, False, 0, 0, 0)
QualificationResult = DurableQualificationReport


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

    def restore_flags(self, flags: Mapping[str, bool]) -> Mapping[str, bool]: ...

    def cleanup_transient_workers(self) -> CleanupProof: ...


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


def _resource_refusal(
    profile: DurableQualificationProfile, snapshot: HostResourceSnapshot
) -> str | None:
    projected = max(
        0, snapshot.mem_available_bytes - snapshot.projected_additional_bytes
    )
    if (
        snapshot.mem_available_bytes < snapshot.projected_additional_bytes
        or projected < profile.minimum_available_bytes
    ):
        return "memory_headroom"
    if snapshot.cpu_guard_percent != 80.0 or snapshot.cpu_percent >= 80.0:
        return "cpu_headroom"
    return None


def run_durable_qualification(
    operator: DurableQualificationOperator,
    *,
    profiles: Sequence[str] = (
        "32-functional-turns",
        "100-immediate-admission",
    ),
) -> DurableQualificationReport:
    """Run the fixed profiles and return directly publishable fail-closed evidence."""
    environment: QualificationEnvironment | None = None
    environment_valid = False
    previous_flags: ImmutableFlagSnapshot | None = None
    reports: list[DurableProfileReport] = []
    status = "failed"
    reason: str | None = "durable_qualification_failed"
    flags_restored = False
    cleanup = _FAILED_CLEANUP
    unreportable_refusal: str | None = None
    try:
        profile_names = tuple(profiles)
        if profile_names != (
            "32-functional-turns",
            "100-immediate-admission",
        ):
            raise QualificationRefused("binding_profile_order_required")
        environment = operator.environment()
        validate_qualification_environment(environment)
        environment_valid = True
        previous_flags = ImmutableFlagSnapshot.capture(operator.snapshot_flags())
        if previous_flags.any_enabled:
            raise QualificationRefused("public_external_admission_flags_must_be_off")
        for profile_name in profile_names:
            profile = resolve_durable_profile(profile_name)
            validate_qualification_environment(operator.environment())
            snapshot = operator.resource_snapshot(profile)
            refusal = _resource_refusal(profile, snapshot)
            if refusal is not None:
                status = "resource_refused"
                reason = refusal
                break
            try:
                operator.setup_profile(profile)
                report = operator.run_profile(profile)
                if report.profile != profile.name or not report.passed:
                    raise QualificationRefused("durable_profile_failed")
                reports.append(report)
            finally:
                operator.teardown_profile(profile)
        else:
            status = "completed"
            reason = None
    except QualificationRefused as error:
        reason = str(error)
        if not environment_valid:
            unreportable_refusal = reason
    except BaseException:
        reason = "durable_qualification_failed"
    finally:
        if previous_flags is not None:
            try:
                restored = ImmutableFlagSnapshot.capture(
                    operator.restore_flags(previous_flags.as_dict())
                )
                flags_restored = restored == previous_flags
            except BaseException:
                flags_restored = False
        try:
            candidate = operator.cleanup_transient_workers()
            if isinstance(candidate, CleanupProof):
                cleanup = candidate
        except BaseException:
            cleanup = _FAILED_CLEANUP

    if unreportable_refusal is not None or environment is None:
        raise QualificationRefused(
            unreportable_refusal or "durable_qualification_failed"
        ) from None
    if status in {"completed", "resource_refused"} and not (
        flags_restored and cleanup.passed
    ):
        status = "failed"
        reason = "cleanup_failed"
    return DurableQualificationReport(
        release_id=environment.target_release,
        status=status,
        reason=reason,
        profiles=tuple(reports),
        flags_restored=flags_restored,
        exact_workers_drained=cleanup.exact_workers_drained,
        transient_workers_removed=cleanup.transient_workers_removed,
        listeners_gone=cleanup.listeners_gone,
        status_files_gone=cleanup.status_files_gone,
        processes_gone=cleanup.processes_gone,
        final_active_backend_turns=cleanup.final_active_backend_turns,
        final_active_external_workers=cleanup.final_active_external_workers,
        final_active_sandboxes=cleanup.final_active_sandboxes,
    )


__all__ = (
    "DurableQualificationOperator",
    "CleanupProof",
    "ImmutableFlagSnapshot",
    "QualificationEnvironment",
    "QualificationRefused",
    "QualificationResult",
    "run_durable_qualification",
    "validate_qualification_environment",
)
