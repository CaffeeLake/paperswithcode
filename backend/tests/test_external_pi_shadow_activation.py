from __future__ import annotations

import json
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

from deploy.external_pi_shadow_activation import (
    QualificationEvidence,
    ShadowActivationError,
    _validate_report,
    activation_signal_context,
    apply_staging_shadow_activation,
    deactivate_external_pi_slots,
    refresh_command,
    run_temporary_shadow_qualification,
)


def _wait_for(path: Path) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.02)
    raise AssertionError(f"timed out waiting for {path}")


def _release(root: Path, release_id: str = "release-a") -> Path:
    release = root / "releases" / release_id
    release.mkdir(parents=True)
    (release / "release.json").write_text(
        json.dumps({"release_id": release_id, "git_sha": "a" * 40})
    )
    environment = root / "environments/staging"
    environment.mkdir(parents=True)
    (environment / "current").symlink_to(release)
    return release


def _evidence() -> QualificationEvidence:
    return QualificationEvidence("staging-blue", 4, 5, 6, True, True, "n" * 32)


def _report(
    path: Path,
    *,
    passed: bool = True,
    release_id: str = "release-a",
    evidence: QualificationEvidence | None = None,
):
    evidence = evidence or _evidence()
    case_names = (
        "linear_history",
        "branching_history",
        "tool_history",
        "eight_isolated_sessions",
        "capacity_no_queue",
        "restart_after_lease_expiry",
        "stale_generation_fencing",
        "drain_recovery",
        "zero_external_work",
    )
    path.write_text(
        json.dumps(
            {
                "release_id": release_id,
                "worker_id": evidence.worker_id,
                "worker_generation": evidence.recovery_generation,
                "qualification_nonce": evidence.nonce,
                "qualified_at_unix_ms": int(time.time() * 1000),
                "passed": passed,
                "case_count": 9,
                "duration_ms": 12,
                "external_work_counts": {
                    "shadow_requests": 20,
                    "model_calls": 0,
                    "tool_calls": 0,
                    "provider_calls": 0,
                    "modal_calls": 0,
                    "billing_events": 0,
                },
                "cases": [
                    {
                        "name": name,
                        "passed": passed,
                        "count": 1,
                        "duration_ms": 1,
                        "failure_code": None if passed else "failed",
                    }
                    for name in case_names
                ],
            }
        )
    )


def test_guard_enables_only_shadow_lifecycle_and_preserves_token(tmp_path: Path):
    _release(tmp_path)
    config = tmp_path / "config"
    config.mkdir()
    staging = config / "staging.env"
    staging.write_text(
        "PWC_DB_NAME=pwc\n"
        "PWC_CHAT_EXTERNAL_PI_SHADOW_ENABLED=false\n"
        "PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED=false\n"
        "PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED=true\n"
        "PWC_CHAT_SANDBOX_EXECUTOR_ENABLED=true\n"
    )
    worker = config / "external-pi-worker.env"
    worker.write_text(f"PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN={'t' * 32}\n")
    worker.chmod(0o640)
    report = tmp_path / "report.json"
    refreshed = []
    events = []
    units = {"worker": "inactive", "supervisor": "inactive"}

    def qualify(release_id, _git_sha, report_path):
        values = dict(
            line.split("=", 1)
            for line in staging.read_text().splitlines()
            if "=" in line
        )
        assert values["PWC_CHAT_EXTERNAL_PI_SHADOW_ENABLED"] == "false"
        assert values["PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED"] == "false"

        def start(*_args):
            assert units == {"worker": "inactive", "supervisor": "inactive"}
            units.update(worker="active", supervisor="active")
            events.append("temporary-start")

        generations = iter((4, 6))

        def authenticated(*_args):
            assert units == {"worker": "active", "supervisor": "active"}
            events.append("authenticated")
            return next(generations)

        def expire(*_args):
            events.append("lease-expiry-restart")
            return 5

        def stale(*_args):
            events.append("stale-fenced")
            return True

        def stop(*_args):
            units.update(worker="inactive", supervisor="inactive")
            events.append("temporary-stop")

        def write_report(evidence, destination):
            events.append("qualified")
            _report(destination, evidence=evidence)

        return run_temporary_shadow_qualification(
            environment="staging",
            slot="blue",
            release_id=release_id,
            report_path=report_path,
            start=start,
            authenticated=authenticated,
            expire_and_restart=expire,
            stale_probe=stale,
            qualify=write_report,
            stop=stop,
        )

    result = apply_staging_shadow_activation(
        environment="staging",
        expected_release_id="release-a",
        report_path=report,
        enabled=True,
        app_root=tmp_path,
        config_root=config,
        qualify=qualify,
        deactivate=None,
        refresh=lambda sha: refreshed.append(sha),
    )

    values = dict(
        line.split("=", 1) for line in staging.read_text().splitlines() if "=" in line
    )
    assert result == {"release_id": "release-a", "enabled": True}
    assert refreshed == ["a" * 40]
    assert events == [
        "temporary-start",
        "authenticated",
        "lease-expiry-restart",
        "stale-fenced",
        "temporary-stop",
        "temporary-start",
        "authenticated",
        "qualified",
        "temporary-stop",
    ]
    assert units == {"worker": "inactive", "supervisor": "inactive"}
    assert values["PWC_DB_NAME"] == "pwc"
    assert values["PWC_CHAT_EXTERNAL_PI_SHADOW_ENABLED"] == "true"
    assert values["PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED"] == "true"
    for key in (
        "PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED",
        "PWC_CHAT_REMOTE_WORKSPACE_TOOLS_ENABLED",
        "PWC_CHAT_SANDBOX_EXECUTOR_ENABLED",
        "PWC_CHAT_REMOTE_BASH_ENABLED",
        "PWC_CHAT_REMOTE_READ_ENABLED",
        "PWC_CHAT_LAZY_WORKSPACE_ENABLED",
    ):
        assert values[key] == "false"
    assert worker.read_text() == (f"PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN={'t' * 32}\n")
    assert stat.S_IMODE(worker.stat().st_mode) == 0o640


def test_guard_refuses_production_wrong_release_or_failed_qualification(tmp_path: Path):
    _release(tmp_path)
    config = tmp_path / "config"
    config.mkdir()
    (config / "staging.env").write_text("PWC_DB_NAME=pwc\n")
    report = tmp_path / "report.json"
    _report(report, passed=False)

    for environment, release_id, match in (
        ("production", "release-a", "staging-only"),
        ("staging", "release-b", "exact current release"),
        ("staging", "release-a", "successful qualification"),
    ):
        with pytest.raises(ShadowActivationError, match=match):
            apply_staging_shadow_activation(
                environment=environment,
                expected_release_id=release_id,
                report_path=report,
                enabled=True,
                app_root=tmp_path,
                config_root=config,
                qualify=lambda *_args: _evidence(),
                deactivate=None,
                refresh=lambda _sha: None,
            )


def test_failed_refresh_restores_the_complete_prior_environment(tmp_path: Path):
    _release(tmp_path)
    config = tmp_path / "config"
    config.mkdir()
    staging = config / "staging.env"
    original = "PWC_DB_NAME=pwc\nPWC_CHAT_EXTERNAL_PI_SHADOW_ENABLED=false\n"
    staging.write_text(original)
    report = tmp_path / "report.json"

    def qualify(_release, _sha, destination):
        evidence = _evidence()
        _report(destination, evidence=evidence)
        return evidence

    with pytest.raises(RuntimeError, match="refresh failed"):
        apply_staging_shadow_activation(
            environment="staging",
            expected_release_id="release-a",
            report_path=report,
            enabled=True,
            app_root=tmp_path,
            config_root=config,
            qualify=qualify,
            deactivate=None,
            refresh=lambda _sha: (_ for _ in ()).throw(RuntimeError("refresh failed")),
        )

    assert staging.read_text() == original


def test_temporary_qualification_always_drains_and_stops_on_failure(tmp_path: Path):
    events = []
    generations = iter((4, 6))

    with pytest.raises(RuntimeError, match="qualification failed"):
        run_temporary_shadow_qualification(
            environment="staging",
            slot="blue",
            release_id="release-a",
            report_path=tmp_path / "report.json",
            start=lambda *_args: events.append("start"),
            authenticated=lambda *_args: (
                events.append("authenticated") or next(generations)
            ),
            expire_and_restart=lambda *_args: events.append("restart") or 5,
            stale_probe=lambda *_args: True,
            qualify=lambda *_args: (_ for _ in ()).throw(
                RuntimeError("qualification failed")
            ),
            stop=lambda *_args: events.append("stop"),
        )

    assert events == [
        "start",
        "authenticated",
        "restart",
        "stop",
        "start",
        "authenticated",
        "stop",
    ]


def test_disable_drains_active_units_before_flags_false_and_refresh(tmp_path: Path):
    _release(tmp_path)
    config = tmp_path / "config"
    config.mkdir()
    staging = config / "staging.env"
    staging.write_text(
        "PWC_CHAT_EXTERNAL_PI_SHADOW_ENABLED=true\n"
        "PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED=true\n"
        f"PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN={'t' * 32}\n"
    )
    (config / "external-pi-worker.env").write_text(
        f"PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN={'t' * 32}\n"
    )
    units = {"worker": "active", "supervisor": "active"}
    events = []

    def deactivate(release_id, _git_sha):
        assert release_id == "release-a"
        assert "SHADOW_ENABLED=true" in staging.read_text()
        assert units == {"worker": "active", "supervisor": "active"}
        units.update(worker="inactive", supervisor="inactive")
        events.append("proven-stop")

    def refresh(_sha):
        assert "SHADOW_ENABLED=false" in staging.read_text()
        assert units == {"worker": "inactive", "supervisor": "inactive"}
        events.append("refresh")

    result = apply_staging_shadow_activation(
        environment="staging",
        expected_release_id="release-a",
        report_path=tmp_path / "unused.json",
        enabled=False,
        app_root=tmp_path,
        config_root=config,
        qualify=None,
        deactivate=deactivate,
        refresh=refresh,
    )

    assert result == {"release_id": "release-a", "enabled": False}
    assert events == ["proven-stop", "refresh"]
    assert units == {"worker": "inactive", "supervisor": "inactive"}


def test_disable_refresh_failure_stays_stopped_and_fail_closed(tmp_path: Path):
    _release(tmp_path)
    config = tmp_path / "config"
    config.mkdir()
    staging = config / "staging.env"
    staging.write_text(
        "PWC_CHAT_EXTERNAL_PI_SHADOW_ENABLED=true\n"
        "PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED=true\n"
    )
    units = {"worker": "active", "supervisor": "active"}

    def deactivate(*_args):
        units.update(worker="inactive", supervisor="inactive")

    with pytest.raises(ShadowActivationError, match="proven stopped.*remain disabled"):
        apply_staging_shadow_activation(
            environment="staging",
            expected_release_id="release-a",
            report_path=tmp_path / "unused.json",
            enabled=False,
            app_root=tmp_path,
            config_root=config,
            qualify=None,
            deactivate=deactivate,
            refresh=lambda _sha: (_ for _ in ()).throw(RuntimeError("refresh failed")),
        )

    assert units == {"worker": "inactive", "supervisor": "inactive"}
    assert "SHADOW_ENABLED=false" in staging.read_text()


def test_refresh_command_uses_positional_git_sha():
    assert refresh_command("staging", "a" * 40) == [
        "pwc-deploy",
        "staging",
        "a" * 40,
        "--refresh-environment",
    ]


def test_false_false_disable_still_deactivates_orphan_units(tmp_path: Path):
    _release(tmp_path)
    config = tmp_path / "config"
    config.mkdir()
    (config / "staging.env").write_text(
        "PWC_CHAT_EXTERNAL_PI_SHADOW_ENABLED=false\n"
        "PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED=false\n"
    )
    events = []

    apply_staging_shadow_activation(
        environment="staging",
        expected_release_id="release-a",
        report_path=tmp_path / "unused.json",
        enabled=False,
        app_root=tmp_path,
        config_root=config,
        qualify=None,
        deactivate=lambda *_args: events.append("deactivate"),
        refresh=lambda _sha: events.append("refresh"),
    )

    assert events == ["deactivate", "refresh"]


def test_deactivation_rejects_active_unit_when_slot_resolution_fails():
    def resolve(_environment, _slot):
        raise ValueError("missing release pointer")

    with pytest.raises(ShadowActivationError, match="blue units remain active"):
        deactivate_external_pi_slots(
            "release-a",
            active_slot="blue",
            resolve=resolve,
            stop=lambda *_args: None,
            unit_inactive=lambda unit: "worker@blue" in unit,
        )


def test_temporary_qualification_cleans_up_on_base_exception(tmp_path: Path):
    events = []
    generations = iter((4, 6))

    with pytest.raises(KeyboardInterrupt):
        run_temporary_shadow_qualification(
            environment="staging",
            slot="blue",
            release_id="release-a",
            report_path=tmp_path / "report.json",
            start=lambda *_args: events.append("start"),
            authenticated=lambda *_args: next(generations),
            expire_and_restart=lambda *_args: 5,
            stale_probe=lambda *_args: True,
            qualify=lambda *_args: (_ for _ in ()).throw(KeyboardInterrupt()),
            stop=lambda *_args: events.append("stop"),
        )

    assert events == ["start", "stop", "start", "stop"]


def test_enable_restores_flags_and_token_on_refresh_base_exception(tmp_path: Path):
    _release(tmp_path)
    config = tmp_path / "config"
    config.mkdir()
    staging = config / "staging.env"
    original = (
        "PWC_CHAT_EXTERNAL_PI_SHADOW_ENABLED=false\n"
        "PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED=false\n"
    )
    staging.write_text(original)
    report = tmp_path / "report.json"

    def qualify(_release, _sha, destination):
        evidence = _evidence()
        _report(destination, evidence=evidence)
        return evidence

    with pytest.raises(KeyboardInterrupt):
        apply_staging_shadow_activation(
            environment="staging",
            expected_release_id="release-a",
            report_path=report,
            enabled=True,
            app_root=tmp_path,
            config_root=config,
            qualify=qualify,
            deactivate=None,
            refresh=lambda _sha: (_ for _ in ()).throw(KeyboardInterrupt()),
        )

    assert staging.read_text() == original
    assert not (config / "external-pi-worker.env").exists()


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        (lambda value: value.update(worker_id="wrong"), "not proven"),
        (lambda value: value.update(worker_generation=5), "not proven"),
        (lambda value: value.update(qualification_nonce="x" * 32), "not proven"),
        (lambda value: value.update(qualified_at_unix_ms=1), "not proven"),
        (lambda value: value.update(duration_ms=True), "not proven"),
    ],
)
def test_report_rejects_identity_replay_and_boolean_integers(
    tmp_path: Path, mutation, match: str
):
    path = tmp_path / "report.json"
    _report(path)
    value = json.loads(path.read_text())
    mutation(value)
    path.write_text(json.dumps(value))

    with pytest.raises(ShadowActivationError, match=match):
        _validate_report(
            path,
            "release-a",
            _evidence(),
            now_unix_ms=int(time.time() * 1000),
        )


def test_real_sigterm_runs_temporary_unit_cleanup(tmp_path: Path):
    _release(tmp_path)
    config = tmp_path / "config"
    config.mkdir()
    original = (
        "PWC_CHAT_EXTERNAL_PI_SHADOW_ENABLED=false\n"
        "PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED=false\n"
    )
    (config / "staging.env").write_text(original)
    script = r"""
import sys, time
from pathlib import Path
from deploy.external_pi_shadow_activation import (
    activation_signal_context, apply_staging_shadow_activation,
    run_temporary_shadow_qualification,
)
root = Path(sys.argv[1])
events = root / "events"
generations = iter((4, 6))
def record(value):
    with events.open("a", encoding="utf-8") as handle:
        handle.write(value + "\n")
def qualify(release_id, _sha, report_path):
    return run_temporary_shadow_qualification(
        environment="staging", slot="blue", release_id=release_id,
        report_path=report_path,
        start=lambda *_args: record("start"),
        authenticated=lambda *_args: next(generations),
        expire_and_restart=lambda *_args: 5,
        stale_probe=lambda *_args: True,
        stop=lambda *_args: record("stop"),
        qualify=lambda *_args: (
            (root / "ready").write_text("ready", encoding="utf-8"),
            time.sleep(30),
        ),
    )
with activation_signal_context():
    apply_staging_shadow_activation(
        environment="staging", expected_release_id="release-a",
        report_path=root / "report.json", enabled=True, app_root=root,
        config_root=root / "config", qualify=qualify, deactivate=None,
        refresh=lambda _sha: None,
    )
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=Path(__file__).parents[2],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    _wait_for(tmp_path / "ready")
    process.terminate()
    _, stderr = process.communicate(timeout=5)

    assert process.returncode == 1
    assert "ShadowActivationInterrupted" in stderr
    assert (tmp_path / "events").read_text().splitlines() == [
        "start",
        "stop",
        "start",
        "stop",
    ]
    assert (config / "staging.env").read_text() == original
    assert not (config / "external-pi-worker.env").exists()


def test_activation_signal_context_restores_prior_handlers():
    previous_term = signal.getsignal(signal.SIGTERM)
    previous_int = signal.getsignal(signal.SIGINT)

    with activation_signal_context():
        assert signal.getsignal(signal.SIGTERM) != previous_term
        assert signal.getsignal(signal.SIGINT) != previous_int

    assert signal.getsignal(signal.SIGTERM) == previous_term
    assert signal.getsignal(signal.SIGINT) == previous_int


def test_real_sigterm_during_start_still_stops_owned_units(tmp_path: Path):
    script = r"""
import sys, time
from pathlib import Path
from deploy.external_pi_shadow_activation import (
    activation_signal_context, run_temporary_shadow_qualification,
)
root = Path(sys.argv[1]); events = root / "events"
def record(value):
    with events.open("a", encoding="utf-8") as handle:
        handle.write(value + "\n")
def start(*_args):
    record("partially-started")
    (root / "ready").write_text("ready", encoding="utf-8")
    time.sleep(30)
with activation_signal_context():
    run_temporary_shadow_qualification(
        environment="staging", slot="blue", release_id="release-a",
        report_path=root / "report.json", start=start,
        authenticated=lambda *_args: 4,
        expire_and_restart=lambda *_args: 5,
        stale_probe=lambda *_args: True,
        qualify=lambda *_args: None,
        stop=lambda *_args: record("stop"),
    )
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=Path(__file__).parents[2],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    _wait_for(tmp_path / "ready")
    process.terminate()
    _, stderr = process.communicate(timeout=5)

    assert process.returncode == 1
    assert "ShadowActivationInterrupted" in stderr
    assert (tmp_path / "events").read_text().splitlines() == [
        "partially-started",
        "stop",
    ]


def test_real_sigterm_during_refresh_restores_false_flags(tmp_path: Path):
    _release(tmp_path)
    config = tmp_path / "config"
    config.mkdir()
    original = (
        "PWC_CHAT_EXTERNAL_PI_SHADOW_ENABLED=false\n"
        "PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED=false\n"
    )
    (config / "staging.env").write_text(original)
    script = r"""
import json, sys, time
from pathlib import Path
import deploy.external_pi_shadow_activation as activation
from deploy.external_pi_shadow_activation import (
    QualificationEvidence, activation_signal_context,
    apply_staging_shadow_activation,
)
root = Path(sys.argv[1]); config = root / "config"
original_atomic_write = activation._atomic_write
def slow_rollback(path, content, mode):
    if path.name == "staging.env" and (root / "ready").exists() and b"SHADOW_ENABLED=false" in content:
        (root / "rollback").write_text("rollback", encoding="utf-8")
        time.sleep(1)
    return original_atomic_write(path, content, mode)
activation._atomic_write = slow_rollback
evidence = QualificationEvidence("staging-blue", 4, 5, 6, True, True, "n" * 32)
names = (
    "linear_history", "branching_history", "tool_history",
    "eight_isolated_sessions", "capacity_no_queue",
    "restart_after_lease_expiry", "stale_generation_fencing",
    "drain_recovery", "zero_external_work",
)
def qualify(_release, _sha, destination):
    destination.write_text(json.dumps({
        "release_id": "release-a", "worker_id": evidence.worker_id,
        "worker_generation": evidence.recovery_generation,
        "qualification_nonce": evidence.nonce,
        "qualified_at_unix_ms": int(time.time() * 1000), "passed": True,
        "case_count": 9, "duration_ms": 1,
        "external_work_counts": {"shadow_requests": 20, "model_calls": 0,
            "tool_calls": 0, "provider_calls": 0, "modal_calls": 0,
            "billing_events": 0},
        "cases": [{"name": name, "passed": True, "count": 1,
            "duration_ms": 1, "failure_code": None} for name in names],
    }), encoding="utf-8")
    return evidence
def refresh(_sha):
    (root / "ready").write_text("ready", encoding="utf-8")
    time.sleep(30)
with activation_signal_context():
    apply_staging_shadow_activation(
        environment="staging", expected_release_id="release-a",
        report_path=root / "report.json", enabled=True, app_root=root,
        config_root=config, qualify=qualify, deactivate=None, refresh=refresh,
    )
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=Path(__file__).parents[2],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    _wait_for(tmp_path / "ready")
    process.terminate()
    _wait_for(tmp_path / "rollback")
    process.send_signal(signal.SIGINT)
    _, stderr = process.communicate(timeout=5)

    assert process.returncode != 0
    assert "ShadowActivationInterrupted" in stderr or "KeyboardInterrupt" in stderr
    assert (config / "staging.env").read_text() == original
    assert not (config / "external-pi-worker.env").exists()


def test_real_sigterm_during_disable_preserves_true_recovery_state(tmp_path: Path):
    _release(tmp_path)
    config = tmp_path / "config"
    config.mkdir()
    original = (
        "PWC_CHAT_EXTERNAL_PI_SHADOW_ENABLED=true\n"
        "PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED=true\n"
    )
    (config / "staging.env").write_text(original)
    script = r"""
import sys, time
from pathlib import Path
from deploy.external_pi_shadow_activation import (
    activation_signal_context, apply_staging_shadow_activation,
)
root = Path(sys.argv[1])
def deactivate(*_args):
    (root / "partial-stop").write_text("partial", encoding="utf-8")
    (root / "ready").write_text("ready", encoding="utf-8")
    time.sleep(30)
with activation_signal_context():
    apply_staging_shadow_activation(
        environment="staging", expected_release_id="release-a",
        report_path=root / "unused.json", enabled=False, app_root=root,
        config_root=root / "config", qualify=None, deactivate=deactivate,
        refresh=lambda _sha: (root / "refreshed").write_text("bad", encoding="utf-8"),
    )
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=Path(__file__).parents[2],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    _wait_for(tmp_path / "ready")
    process.terminate()
    _, stderr = process.communicate(timeout=5)

    assert process.returncode == 1
    assert "ShadowActivationRecoveryRequired" in stderr
    assert (tmp_path / "partial-stop").is_file()
    assert not (tmp_path / "refreshed").exists()
    assert (config / "staging.env").read_text() == original
    assert not (config / "external-pi-worker.env").exists()


def test_real_signal_during_handler_restoration_restores_all_handlers(tmp_path: Path):
    script = r"""
import signal, sys, time
from pathlib import Path
import deploy.external_pi_shadow_activation as activation
root = Path(sys.argv[1])
def prior_term(_number, _frame):
    (root / "delivered").write_text("term", encoding="utf-8")
def prior_int(_number, _frame):
    (root / "delivered").write_text("int", encoding="utf-8")
signal.signal(signal.SIGTERM, prior_term)
signal.signal(signal.SIGINT, prior_int)
real_signal = activation.signal.signal
def slow_restore(number, handler):
    if number == signal.SIGTERM and handler is prior_term:
        (root / "restoring").write_text("restoring", encoding="utf-8")
        time.sleep(1)
    return real_signal(number, handler)
activation.signal.signal = slow_restore
with activation.activation_signal_context():
    pass
assert signal.getsignal(signal.SIGTERM) is prior_term
assert signal.getsignal(signal.SIGINT) is prior_int
(root / "restored").write_text("restored", encoding="utf-8")
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=Path(__file__).parents[2],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    _wait_for(tmp_path / "restoring")
    process.terminate()
    _, stderr = process.communicate(timeout=5)

    assert process.returncode == 0, stderr
    assert (tmp_path / "delivered").read_text() == "term"
    assert (tmp_path / "restored").is_file()
