from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

import deploy.external_pi_slot_lifecycle as lifecycle
import deploy.external_pi_slot_launcher as launcher
import deploy.cli as deploy_cli


def _release(root: Path, slot: str, runtime_id: str = "a" * 64) -> Path:
    release = root / "releases" / f"release-{slot}"
    release.mkdir(parents=True)
    (release / "release.json").write_text(
        json.dumps(
            {
                "release_id": f"release-{slot}",
                "external_pi_runtime": {
                    "identity_schema": 1,
                    "runtime_id": runtime_id,
                    "contract": "external-pi-v1",
                },
            }
        )
    )
    slot_root = root / "environments" / "staging" / "slots" / slot
    slot_root.mkdir(parents=True)
    (slot_root / "release").symlink_to(release)
    runtime = root / "runtimes/external-pi" / runtime_id
    (runtime / "node" / "bin").mkdir(parents=True)
    (runtime / "app" / "dist" / "src").mkdir(parents=True)
    (runtime / "assets").mkdir()
    (runtime / "node" / "bin" / "node").write_text("node")
    (runtime / "app" / "dist" / "src" / "external_http_main.js").write_text("main")
    (runtime / "assets" / "pi-system-prompt.txt").write_text("prompt")
    return release


def test_slot_runtime_is_staging_only_and_uses_recorded_immutable_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _release(tmp_path, "blue")
    monkeypatch.setattr(lifecycle, "APP_ROOT", tmp_path)
    monkeypatch.setattr(
        lifecycle,
        "external_pi_runtime_manifest",
        lambda runtime, **expected: {
            "entry_point": "app/dist/src/external_http_main.js",
            "expected": expected,
        },
    )

    resolved = lifecycle.resolve_external_pi_slot("staging", "blue")

    assert resolved.port == 8766
    assert resolved.worker_id == "staging-blue"
    assert resolved.release_id == "release-blue"
    assert resolved.runtime.name == "a" * 64
    assert resolved.node == resolved.runtime / "node/bin/node"
    with pytest.raises(ValueError, match="staging-only"):
        lifecycle.resolve_external_pi_slot("production", "blue")


def test_wrong_or_unrecorded_runtime_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    release = _release(tmp_path, "green")
    monkeypatch.setattr(lifecycle, "APP_ROOT", tmp_path)
    value = json.loads((release / "release.json").read_text())
    del value["external_pi_runtime"]
    (release / "release.json").write_text(json.dumps(value))

    with pytest.raises(ValueError, match="recorded external Pi runtime"):
        lifecycle.resolve_external_pi_slot("staging", "green")


def test_child_environments_are_strictly_scrubbed(tmp_path: Path):
    resolved = lifecycle.ExternalPiSlot(
        slot="green",
        port=8767,
        worker_id="staging-green",
        release=tmp_path / "release",
        release_id="release-green",
        runtime=tmp_path / "runtime",
        node=tmp_path / "runtime/node/bin/node",
        entry_point=tmp_path / "runtime/dist/src/external_http_main.js",
        prompt=tmp_path / "runtime/assets/pi-system-prompt.txt",
        status_path=tmp_path / "status.json",
    )
    protected = {
        "PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN": "t" * 32,
        "PWC_DB_HOST": "db",
        "PWC_DB_PORT": "5432",
        "PWC_DB_NAME": "pwc",
        "PWC_DB_USER": "staging",
        "PWC_DB_PASSWORD": "secret",
        "PWC_DB_SEARCH_PATH": "staging",
        "PWC_HF_TOKEN": "must-not-leak",
        "PWC_OPENAI_API_KEY": "must-not-leak",
        "MODAL_TOKEN_ID": "must-not-leak",
        "PWC_CHAT_SANDBOX_EXECUTOR_TOKEN": "must-not-leak",
        "PATH": "/usr/bin",
    }

    node = lifecycle.node_environment(resolved, protected, instance_id="i" * 36)
    supervisor = lifecycle.supervisor_environment(resolved, protected)

    assert node == {
        "PWC_EXTERNAL_PI_HOST": "127.0.0.1",
        "PWC_EXTERNAL_PI_PORT": "8767",
        "PWC_EXTERNAL_PI_TOKEN": "t" * 32,
        "PWC_EXTERNAL_PI_MAX_SESSIONS": "8",
        "PWC_EXTERNAL_PI_WORKER_ID": "staging-green",
        "PWC_EXTERNAL_PI_INSTANCE_ID": "i" * 36,
        "PWC_EXTERNAL_PI_RELEASE_ID": "release-green",
        "PWC_EXTERNAL_PI_PROMPT_PATH": str(resolved.prompt),
        "PWC_EXTERNAL_PI_TOOL_NAMES": "[]",
    }
    assert set(supervisor) == {
        "PWC_ENVIRONMENT",
        "PWC_RELEASE_ID",
        "PWC_DB_HOST",
        "PWC_DB_PORT",
        "PWC_DB_NAME",
        "PWC_DB_USER",
        "PWC_DB_PASSWORD",
        "PWC_DB_SEARCH_PATH",
        "PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED",
        "PWC_CHAT_EXTERNAL_PI_WORKER_URL",
        "PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN",
        "PWC_CHAT_EXTERNAL_PI_WORKER_CONTRACT_VERSION",
        "PWC_CHAT_EXTERNAL_PI_WORKER_MAX_SESSIONS",
        "PWC_CHAT_EXTERNAL_PI_HEARTBEAT_SECONDS",
        "PWC_CHAT_EXTERNAL_PI_LEASE_SECONDS",
        "PWC_CHAT_EXTERNAL_PI_STARTUP_TIMEOUT_SECONDS",
        "PWC_CHAT_EXTERNAL_PI_DRAIN_SECONDS",
        "PWC_CHAT_EXTERNAL_PI_DRAIN_POLL_SECONDS",
        "PWC_EXTERNAL_PI_STATUS_PATH",
    }
    assert supervisor["PWC_CHAT_EXTERNAL_PI_WORKER_URL"] == "http://127.0.0.1:8767"
    assert supervisor["PWC_CHAT_EXTERNAL_PI_WORKER_MAX_SESSIONS"] == "8"
    assert "PWC_HF_TOKEN" not in supervisor


def test_candidate_requires_authenticated_durable_lifecycle_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", tmp_path)
    status = tmp_path / "staging-blue.json"
    status.write_text(
        json.dumps(
            {
                "release_id": "release-blue",
                "worker_id": "staging-blue",
                "state": "ready",
                "authenticated": True,
                "registered": True,
                "generation": 3,
                "heartbeats": 1,
            }
        )
    )

    assert lifecycle.qualify_candidate("staging", "blue", "release-blue") == 3
    value = json.loads(status.read_text())
    value["authenticated"] = False
    status.write_text(json.dumps(value))
    with pytest.raises(lifecycle.ExternalPiSlotError, match="qualification"):
        lifecycle.qualify_candidate(
            "staging", "blue", "release-blue", timeout_seconds=0.01
        )


def test_qualification_proves_drain_and_restart_generation(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[tuple] = []
    generations = iter([4, 5])
    monkeypatch.setattr(
        lifecycle, "start_slot", lambda environment, slot: calls.append(("start", slot))
    )
    monkeypatch.setattr(
        lifecycle,
        "qualify_candidate",
        lambda environment, slot, release_id: next(generations),
    )
    monkeypatch.setattr(
        lifecycle,
        "stop_slot",
        lambda environment, slot, release_id, **kwargs: calls.append(("stop", slot)),
    )

    assert lifecycle.prepare_candidate("staging", "green", "release-green") == 5
    assert calls == [("start", "green"), ("stop", "green"), ("start", "green")]


def test_drain_timeout_fails_the_slot_lifecycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", tmp_path)
    (tmp_path / "staging-blue.json").write_text(
        json.dumps({"release_id": "release-blue", "state": "ready"})
    )

    def timeout(*_args, **_kwargs):
        raise lifecycle.subprocess.TimeoutExpired("systemctl", 65)

    monkeypatch.setattr(lifecycle.subprocess, "run", timeout)
    with pytest.raises(lifecycle.ExternalPiSlotError, match="drain timed out"):
        lifecycle.stop_slot("staging", "blue", "release-blue")


def test_candidate_failure_stops_the_failed_unit(
    monkeypatch: pytest.MonkeyPatch,
):
    commands: list[tuple[list[str], bool]] = []
    monkeypatch.setattr(lifecycle, "start_slot", lambda *_args: None)
    monkeypatch.setattr(
        lifecycle,
        "qualify_candidate",
        lambda *_args: (_ for _ in ()).throw(
            lifecycle.ExternalPiSlotError("candidate unavailable")
        ),
    )
    monkeypatch.setattr(
        lifecycle.subprocess,
        "run",
        lambda command, *, check, timeout: commands.append((command, check)),
    )

    with pytest.raises(lifecycle.ExternalPiSlotError, match="candidate unavailable"):
        lifecycle.prepare_candidate("staging", "green", "release-green")

    assert commands == [
        (
            ["systemctl", "stop", "paperswithcode-staging-external-pi@green.service"],
            False,
        )
    ]


def test_recovery_stop_ignores_a_stale_status_from_the_previous_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", tmp_path)
    (tmp_path / "staging-green.json").write_text(
        json.dumps(
            {
                "release_id": "previous-release",
                "state": "offline",
                "drained": True,
            }
        )
    )
    commands: list[list[str]] = []
    monkeypatch.setattr(
        lifecycle.subprocess,
        "run",
        lambda command, **_kwargs: commands.append(command),
    )

    lifecycle.stop_slot("staging", "green", "new-candidate")

    assert commands == [
        ["systemctl", "stop", "paperswithcode-staging-external-pi@green.service"]
    ]


def test_disabled_switch_is_a_complete_noop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config = tmp_path / "staging.env"
    config.write_text("PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED=false\n")
    monkeypatch.setattr(lifecycle, "CONFIG_ROOT", tmp_path)
    monkeypatch.setattr(
        lifecycle,
        "prepare_candidate",
        lambda *_args: pytest.fail("disabled lifecycle started a service"),
    )

    assert not lifecycle.prepare_candidate_if_enabled("staging", "blue", "release")
    assert not lifecycle.stop_slot_if_enabled("staging", "blue", "release")
    assert not lifecycle.prepare_candidate_if_enabled("production", "blue", "release")


def test_launcher_execs_release_python_with_only_scrubbed_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    release = tmp_path / "release"
    python_runtime = tmp_path / "python-runtime"
    python = python_runtime / "bin/python"
    resolved = lifecycle.ExternalPiSlot(
        slot="blue",
        port=8766,
        worker_id="staging-blue",
        release=release,
        release_id="release-blue",
        runtime=tmp_path / "external-runtime",
        node=tmp_path / "external-runtime/node/bin/node",
        entry_point=tmp_path / "external-runtime/dist/src/external_http_main.js",
        prompt=tmp_path / "external-runtime/assets/pi-system-prompt.txt",
        status_path=tmp_path / "status.json",
    )
    monkeypatch.setattr(
        launcher,
        "resolve_slot",
        lambda environment, slot: (
            release,
            python_runtime,
            {"release_id": "release-blue"},
        ),
    )
    monkeypatch.setattr(launcher, "resolve_external_pi_slot", lambda *_args: resolved)
    monkeypatch.setenv("PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN", "t" * 32)
    monkeypatch.setenv("PWC_HF_TOKEN", "must-not-leak")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-leak")
    monkeypatch.setattr(launcher.os, "chdir", lambda path: None)
    executed: dict = {}

    def execve(executable, arguments, environment):
        executed.update(
            executable=executable, arguments=arguments, environment=environment
        )
        raise RuntimeError("exec")

    monkeypatch.setattr(launcher.os, "execve", execve)
    monkeypatch.setattr(launcher.sys, "argv", ["launcher", "staging", "blue"])

    with pytest.raises(RuntimeError, match="exec"):
        launcher.main()

    assert executed["executable"] == str(python)
    assert executed["arguments"] == [
        str(python),
        "-m",
        "backend.scripts.run_external_pi_slot",
    ]
    assert executed["environment"]["PWC_EXTERNAL_PI_PORT"] == "8766"
    assert executed["environment"]["PWC_EXTERNAL_PI_TOOL_NAMES"] == "[]"
    assert "PWC_HF_TOKEN" not in executed["environment"]
    assert "OPENAI_API_KEY" not in executed["environment"]


def test_systemd_template_is_staging_slot_scoped_and_loopback_launcher_owned():
    unit = (
        Path(__file__).parents[2]
        / "deploy/systemd/paperswithcode-staging-external-pi@.service"
    ).read_text()

    assert "external_pi_slot_launcher.py staging %i" in unit
    assert "EnvironmentFile=/etc/paperswithcode/staging.env" in unit
    assert "paperswithcode-production" not in unit
    assert "ReadOnlyPaths=/srv/paperswithcode" in unit
    assert "KillMode=mixed" in unit


def test_deployment_status_reports_shadow_unit_and_durable_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    environments = tmp_path / "environments"
    (environments / "staging").mkdir(parents=True)
    monkeypatch.setattr(deploy_cli, "APP_ROOT", tmp_path)
    monkeypatch.setattr(deploy_cli, "ENVIRONMENTS", ("staging",))
    monkeypatch.setattr(deploy_cli, "ENVIRONMENTS_ROOT", environments)
    monkeypatch.setattr(deploy_cli, "RUNTIME_LOCK", tmp_path / "runtime-lock")
    monkeypatch.setattr(
        deploy_cli,
        "read_pointers",
        lambda _root: SimpleNamespace(current=None, previous=None),
    )
    monkeypatch.setattr(deploy_cli, "_active_slot", lambda _environment: "blue")
    monkeypatch.setattr(
        deploy_cli, "_nginx_uses_active_slot", lambda _environment: True
    )
    monkeypatch.setattr(deploy_cli, "_slot_release", lambda *_args: None)
    monkeypatch.setattr(deploy_cli, "_systemctl_state", lambda unit: "active")
    monkeypatch.setattr(deploy_cli, "_unix_json", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        deploy_cli,
        "external_pi_slot_status",
        lambda _environment, slot: {
            "worker_id": f"staging-{slot}",
            "generation": 7,
            "heartbeats": 2,
            "state": "ready",
        },
    )

    assert deploy_cli.status(Namespace()) == 0

    value = json.loads(capsys.readouterr().out)
    shadow = value["environments"]["staging"]["slots"]["blue"]["external_pi_shadow"]
    assert shadow == {
        "service": "active",
        "lifecycle": {
            "worker_id": "staging-blue",
            "generation": 7,
            "heartbeats": 2,
            "state": "ready",
        },
    }
