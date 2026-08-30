"""Pure guarded controller for staging durable external-turn qualification.

Task 11 defines the transaction and evidence contracts only. A live system adapter is
intentionally supplied by the separately authorized staging operation in Task 12.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from backend.loadtests.external_pi_fleet_core import (
    DurableProfileReport,
    DurableQualificationReport,
    DurableQualificationProfile,
    HostResourceSnapshot,
    resolve_durable_profile,
    load_modal_rate_evidence,
)
from backend.loadtests.durable_chat_transport import DurableChatTransportConfig

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

    def teardown_profile(
        self, profile: DurableQualificationProfile, scope_id: uuid.UUID | None
    ) -> None: ...

    def restore_flags(self, flags: Mapping[str, bool]) -> Mapping[str, bool]: ...

    def cleanup_transient_workers(self) -> CleanupProof: ...


class LiveQualificationControlPlane(Protocol):
    """Protected mutations and runtime evidence supplied by the live operation."""

    def environment(self) -> QualificationEnvironment: ...

    def snapshot_flags(self) -> Mapping[str, bool]: ...

    def resource_snapshot(
        self, profile: DurableQualificationProfile
    ) -> HostResourceSnapshot: ...

    def run_resources(self, profile: DurableQualificationProfile) -> object: ...

    def setup_profile(self, profile: DurableQualificationProfile) -> None: ...

    def restore_flags(self, flags: Mapping[str, bool]) -> Mapping[str, bool]: ...

    def cleanup_transient_workers(self) -> CleanupProof: ...

    def protected_runtime_evidence(
        self, profile: DurableQualificationProfile
    ) -> Mapping[str, str]: ...


class GuardedLiveDurableOperator:
    """Bind the controller to the concrete chat transport and exact Locust profile."""

    def __init__(
        self,
        *,
        control_plane: LiveQualificationControlPlane,
        transport_config: DurableChatTransportConfig,
    ) -> None:
        self.control_plane = control_plane
        self.transport_config = transport_config
        from backend.loadtests.durable_chat_transport import (
            HttpDurableQualificationEvidenceSource,
        )

        self.evidence_source = HttpDurableQualificationEvidenceSource(transport_config)
        self._scopes: dict[str, uuid.UUID] = {}

    def environment(self) -> QualificationEnvironment:
        return self.control_plane.environment()

    def snapshot_flags(self) -> Mapping[str, bool]:
        return self.control_plane.snapshot_flags()

    def resource_snapshot(
        self, profile: DurableQualificationProfile
    ) -> HostResourceSnapshot:
        return self.control_plane.resource_snapshot(profile)

    def setup_profile(self, profile: DurableQualificationProfile) -> None:
        self.control_plane.setup_profile(profile)

    def run_profile(self, profile: DurableQualificationProfile):
        from backend.loadtests.external_pi_fleet_locustfile import (
            run_live_durable_profile,
        )

        scope = self.evidence_source.begin_scope(profile.name)
        scope_id = scope["scope_id"]
        if not isinstance(scope_id, uuid.UUID):
            raise QualificationRefused("qualification_scope_invalid")
        self._scopes[profile.name] = scope_id
        if scope.get("app_release_id") != self.environment().target_release:
            raise QualificationRefused("exact_staging_release_required")
        return run_live_durable_profile(
            profile_name=profile.name,
            transport_config=self.transport_config,
            resources=self.control_plane.run_resources(profile),
            qualification_scope_id=scope_id,
        )

    def finalize_profile(self, profile: DurableQualificationProfile, measurement):
        from datetime import UTC, datetime
        from backend.loadtests.external_pi_fleet_locustfile import (
            finalize_live_durable_profile,
        )

        environment = self.environment()
        evidence = self.evidence_source.collect(measurement.qualification_scope_id)
        rate = load_modal_rate_evidence(
            self.control_plane.protected_runtime_evidence(profile),
            expected_release=environment.target_release,
            window_started_at_ms=evidence.window_started_at_ms,
            window_ended_at_ms=evidence.window_ended_at_ms,
            now_ms=round(datetime.now(UTC).timestamp() * 1_000),
        )
        return finalize_live_durable_profile(
            measurement,
            qualification_evidence=evidence,
            modal_rate=rate,
        )

    def cleanup_profile_evidence(self, profile: DurableQualificationProfile) -> None:
        scope_id = self._scopes.pop(profile.name, None)
        if scope_id is not None:
            self.evidence_source.cleanup(scope_id)

    def qualification_scope_id(
        self, profile: DurableQualificationProfile
    ) -> uuid.UUID | None:
        return self._scopes.get(profile.name)

    def teardown_profile(
        self, profile: DurableQualificationProfile, scope_id: uuid.UUID | None
    ) -> None:
        expected_scope_id = self._scopes.get(profile.name)
        if scope_id is None or scope_id != expected_scope_id:
            raise QualificationRefused("qualification_scope_invalid")
        self.evidence_source.teardown(scope_id)

    def restore_flags(self, flags: Mapping[str, bool]) -> Mapping[str, bool]:
        return self.control_plane.restore_flags(flags)

    def cleanup_transient_workers(self) -> CleanupProof:
        return self.control_plane.cleanup_transient_workers()


def run_live_durable_qualification(
    *,
    control_plane: LiveQualificationControlPlane,
    transport_config: DurableChatTransportConfig,
) -> DurableQualificationReport:
    return run_durable_qualification(
        GuardedLiveDurableOperator(
            control_plane=control_plane,
            transport_config=transport_config,
        )
    )


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
            result = None
            primary_error: BaseException | None = None
            profile_cleanup_failed = False
            try:
                operator.setup_profile(profile)
                result = operator.run_profile(profile)
            except BaseException as error:
                primary_error = error
            try:
                scope_id = getattr(result, "qualification_scope_id", None)
                scope_source = getattr(operator, "qualification_scope_id", None)
                if scope_id is None:
                    if callable(scope_source):
                        scope_id = scope_source(profile)
                if scope_id is not None or not callable(scope_source):
                    operator.teardown_profile(profile, scope_id)
            except BaseException:
                profile_cleanup_failed = True

            report = None
            if primary_error is None and not profile_cleanup_failed:
                try:
                    finalize = getattr(operator, "finalize_profile", None)
                    report = finalize(profile, result) if callable(finalize) else result
                except BaseException as error:
                    primary_error = error
            cleanup_evidence = getattr(operator, "cleanup_profile_evidence", None)
            if callable(cleanup_evidence):
                try:
                    cleanup_evidence(profile)
                except BaseException:
                    profile_cleanup_failed = True
            if profile_cleanup_failed:
                raise QualificationRefused("cleanup_failed")
            if primary_error is not None:
                raise primary_error
            if report.profile != profile.name or not report.passed:
                raise QualificationRefused("durable_profile_failed")
            reports.append(report)
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
    if not cleanup.passed or (previous_flags is not None and not flags_restored):
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
    "GuardedLiveDurableOperator",
    "LiveQualificationControlPlane",
    "CleanupProof",
    "ImmutableFlagSnapshot",
    "QualificationEnvironment",
    "QualificationRefused",
    "QualificationResult",
    "run_durable_qualification",
    "run_live_durable_qualification",
    "validate_qualification_environment",
)
