from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from deploy.external_pi_shadow_activation import (
    ShadowActivationError,
    apply_staging_shadow_activation,
    run_temporary_shadow_qualification,
)


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


def _report(path: Path, *, passed: bool = True, release_id: str = "release-a"):
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
                "worker_id": "staging-blue",
                "worker_generation": 5,
                "passed": passed,
                "case_count": 9,
                "duration_ms": 12,
                "external_work_counts": {
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
    _report(report)
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

        def authenticated(*_args):
            assert units == {"worker": "active", "supervisor": "active"}
            events.append("authenticated")
            return 4

        def stop(*_args):
            units.update(worker="inactive", supervisor="inactive")
            events.append("temporary-stop")

        run_temporary_shadow_qualification(
            environment="staging",
            slot="blue",
            release_id=release_id,
            report_path=report_path,
            start=start,
            authenticated=authenticated,
            qualify=lambda *_args: None,
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
    assert events == ["temporary-start", "authenticated", "temporary-stop"]
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
                qualify=lambda *_args: None,
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
    _report(report)

    with pytest.raises(RuntimeError, match="refresh failed"):
        apply_staging_shadow_activation(
            environment="staging",
            expected_release_id="release-a",
            report_path=report,
            enabled=True,
            app_root=tmp_path,
            config_root=config,
            qualify=lambda *_args: None,
            deactivate=None,
            refresh=lambda _sha: (_ for _ in ()).throw(RuntimeError("refresh failed")),
        )

    assert staging.read_text() == original


def test_temporary_qualification_always_drains_and_stops_on_failure(tmp_path: Path):
    events = []

    with pytest.raises(RuntimeError, match="qualification failed"):
        run_temporary_shadow_qualification(
            environment="staging",
            slot="blue",
            release_id="release-a",
            report_path=tmp_path / "report.json",
            start=lambda *_args: events.append("start"),
            authenticated=lambda *_args: events.append("authenticated") or 4,
            qualify=lambda *_args: (_ for _ in ()).throw(
                RuntimeError("qualification failed")
            ),
            stop=lambda *_args: events.append("stop"),
        )

    assert events == ["start", "authenticated", "stop"]


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
