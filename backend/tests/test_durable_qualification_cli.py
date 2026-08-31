from __future__ import annotations

import signal
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_build_synthetic_transport_config_keeps_32_distinct_secrets_redacted():
    from backend.scripts.qualify_durable_external_turns import (
        build_synthetic_transport_config,
    )

    subjects: list[str] = []

    def encode(subject: str) -> str:
        subjects.append(subject)
        return f"secret-cookie-{subject}"

    config = build_synthetic_transport_config(
        run_id="run-123",
        admin_token="a" * 32,
        model="gpt-5.6-luna@openai",
        cookie_encoder=encode,
        max_spend_usd="1.25",
    )

    assert len(config.synthetic_cookies) == 32
    assert len(set(config.synthetic_cookies)) == 32
    assert subjects == [
        f"operator:pi-qualification:run-123:{ordinal}" for ordinal in range(32)
    ]
    rendered = repr(config)
    assert "secret-cookie" not in rendered
    assert "a" * 32 not in rendered


@pytest.mark.parametrize("value", ("", "0", "10.01", "nan", "inf"))
def test_synthetic_transport_requires_a_bounded_spend_envelope(value: str):
    from backend.scripts.qualify_durable_external_turns import (
        QualificationRefused,
        build_synthetic_transport_config,
    )

    with pytest.raises(QualificationRefused, match="spend_envelope"):
        build_synthetic_transport_config(
            run_id="run-123",
            admin_token="a" * 32,
            model="gpt-5.6-luna@openai",
            cookie_encoder=lambda subject: subject,
            max_spend_usd=value,
        )


def test_whole_window_sampler_aggregates_and_refuses_stall():
    from backend.scripts.qualify_durable_external_turns import (
        DurableResourceSample,
        QualificationRefused,
        WholeWindowResourceSampler,
    )

    now = [10.0]
    samples = iter(
        (
            DurableResourceSample(10, 20, 3_000, 10.0, 1, 1, 0),
            DurableResourceSample(30, 40, 2_000, 50.0, 32, 1, 16),
        )
    )
    sampler = WholeWindowResourceSampler(
        sample=lambda: next(samples),
        monotonic=lambda: now[0],
        interval_seconds=0.1,
        threaded=False,
    )
    sampler.start()
    now[0] = 10.1
    resources = sampler.stop()

    assert resources.peak_memory_bytes == 70
    assert resources.minimum_host_mem_available_bytes == 2_000
    assert resources.peak_cpu_percent == 50.0
    assert resources.peak_active_backend_turns == 32
    assert resources.peak_active_external_workers == 1
    assert resources.peak_active_sandboxes == 16

    stalled = WholeWindowResourceSampler(
        sample=lambda: DurableResourceSample(1, 1, 3_000, 1.0, 0, 1, 0),
        monotonic=lambda: now[0],
        interval_seconds=0.1,
        threaded=False,
    )
    stalled.start()
    now[0] += 0.6
    with pytest.raises(QualificationRefused, match="resource_sampling_stalled"):
        stalled.stop()


def test_live_runner_starts_and_stops_sampler_around_chat_window(monkeypatch):
    adapter = pytest.importorskip("backend.loadtests.external_pi_fleet_locustfile")
    from backend.loadtests.durable_chat_transport import DurableChatTransportConfig

    events = []
    sampled = adapter.DurableRunResources(70, 2_000, 50.0, 32, 1, 16)

    class Sampler:
        def start(self):
            events.append("start")

        def stop(self):
            events.append("stop")
            return sampled

    monkeypatch.setattr(
        adapter,
        "_run_durable_observations",
        lambda **_kwargs: events.append("run") or (),
    )
    result = adapter.run_live_durable_profile(
        profile_name="32-functional-turns",
        transport_config=DurableChatTransportConfig(
            base_url="https://staging.paperswithcode.co",
            synthetic_cookies=("cookie",),
            initial_model="gpt-5.6-luna@openai",
            qualification_run_id="run-123",
            admin_token="a" * 32,
        ),
        resources=Sampler(),
        qualification_scope_id=__import__("uuid").uuid4(),
    )

    assert events == ["start", "run", "stop"]
    assert result.resources is sampled


def test_durable_signal_context_restores_handlers_and_raises_typed_interrupt(
    monkeypatch,
):
    from backend.scripts.qualify_durable_external_turns import (
        DurableQualificationInterrupted,
        qualification_signal_context,
    )

    handlers = {signal.SIGINT: object(), signal.SIGTERM: object()}
    installed = []
    monkeypatch.setattr(signal, "getsignal", lambda number: handlers[number])
    monkeypatch.setattr(
        signal, "signal", lambda number, handler: installed.append((number, handler))
    )
    monkeypatch.setattr(signal, "pthread_sigmask", lambda *_args: set())

    with pytest.raises(DurableQualificationInterrupted):
        with qualification_signal_context():
            active = dict(installed[-2:])
            active[signal.SIGTERM](signal.SIGTERM, None)

    assert installed[-2:] == [
        (signal.SIGTERM, handlers[signal.SIGTERM]),
        (signal.SIGINT, handlers[signal.SIGINT]),
    ] or installed[-2:] == [
        (signal.SIGINT, handlers[signal.SIGINT]),
        (signal.SIGTERM, handlers[signal.SIGTERM]),
    ]


def test_cli_parser_help_is_import_safe(capsys):
    from backend.scripts.qualify_durable_external_turns import build_parser

    parser = build_parser()
    with pytest.raises(SystemExit) as stopped:
        parser.parse_args(["--help"])
    assert stopped.value.code == 0
    help_text = capsys.readouterr().out
    assert "QUALIFY_STAGING_DURABLE_EXTERNAL_TURNS" in help_text
    assert "32-functional-turns" in help_text


def test_cli_report_destination_is_fixed(tmp_path: Path):
    from backend.scripts.qualify_durable_external_turns import (
        DURABLE_REPORT_PATH,
        build_parser,
    )

    args = build_parser().parse_args(
        [
            "--environment",
            "staging",
            "--release-id",
            "0123456789ab-staging",
            "--confirm",
            "QUALIFY_STAGING_DURABLE_EXTERNAL_TURNS",
            "--max-spend-usd",
            "1",
        ]
    )
    assert not hasattr(args, "report")
    assert str(DURABLE_REPORT_PATH).endswith(
        "/staging/durable-external-turn-qualification.json"
    )


def _release_tree(tmp_path: Path):
    app_root = tmp_path / "paperswithcode"
    releases = app_root / "releases"
    releases.mkdir(parents=True)
    staging = releases / "0123456789ab-staging"
    production = releases / "fedcba987654-production"
    staging.mkdir()
    production.mkdir()
    for environment, release in (("staging", staging), ("production", production)):
        directory = app_root / "environments" / environment
        directory.mkdir(parents=True)
        (directory / "current").symlink_to(release)
    return app_root


def _safe_settings(**updates):
    values = {
        "environment": "staging",
        "release_id": "0123456789ab-staging",
        "chat_external_pi_admission_enabled": False,
        "chat_new_session_pi_percentage": 0,
        "chat_sandbox_executor_enabled": False,
        "chat_remote_workspace_tools_enabled": False,
        "chat_remote_bash_enabled": False,
        "chat_remote_read_enabled": False,
        "chat_lazy_workspace_enabled": False,
    }
    values.update(updates)
    return SimpleNamespace(**values)


def _ready_prerequisites(**updates):
    from backend.scripts.qualify_durable_external_turns import (
        StagingQualificationPrerequisites,
    )

    values = {
        "migrations_ready": True,
        "runtime_ready": True,
        "worker_environment": "staging",
        "worker_id": "staging-worker",
        "configured_worker_id": "staging-worker",
        "worker_release_id": "0123456789ab-staging",
        "worker_state": "ready",
        "worker_contract_version": "external-pi-v1",
        "maximum_sessions": 32,
        "active_sessions": 0,
    }
    values.update(updates)
    return StagingQualificationPrerequisites(**values)


def test_system_control_plane_independently_resolves_exact_release_and_flags(tmp_path):
    from backend.scripts.qualify_durable_external_turns import (
        SystemDurableQualificationControlPlane,
    )

    control = SystemDurableQualificationControlPlane(
        release_id="0123456789ab-staging",
        settings=_safe_settings(),
        app_root=_release_tree(tmp_path),
        environ={"PWC_RELEASE_ID": "0123456789ab-staging"},
        mem_total=lambda: 16 * 1024**3,
        prerequisites=_ready_prerequisites,
        resource_preflight=lambda _profile: None,
        sampler_factory=lambda _profile: object(),
        cleanup_probe=lambda: None,
        modal_rate_path=tmp_path / "rate.json",
    )

    environment = control.environment()
    assert environment.staging_release == "0123456789ab-staging"
    assert environment.production_release == "fedcba987654-production"
    assert set(control.snapshot_flags().values()) == {False}

    staging_current = tmp_path / "paperswithcode/environments/staging/current"
    staging_current.unlink()
    staging_current.symlink_to(
        tmp_path / "paperswithcode/releases/fedcba987654-production"
    )
    with pytest.raises(Exception, match="exact_staging_release"):
        control.environment()


@pytest.mark.parametrize(
    "updates",
    (
        {"migrations_ready": False},
        {"runtime_ready": False},
        {"worker_environment": "production"},
        {"worker_release_id": "fedcba987654-production"},
        {"worker_state": "draining"},
        {"worker_contract_version": "old"},
        {"maximum_sessions": 31},
        {"active_sessions": 1},
        {"configured_worker_id": "some-other-worker"},
    ),
)
def test_system_control_plane_refuses_missing_staging_prerequisite(tmp_path, updates):
    from backend.scripts.qualify_durable_external_turns import (
        QualificationRefused,
        SystemDurableQualificationControlPlane,
    )
    from backend.loadtests.external_pi_fleet_core import resolve_durable_profile

    control = SystemDurableQualificationControlPlane(
        release_id="0123456789ab-staging",
        settings=_safe_settings(),
        app_root=_release_tree(tmp_path),
        environ={"PWC_RELEASE_ID": "0123456789ab-staging"},
        mem_total=lambda: 16 * 1024**3,
        prerequisites=lambda: _ready_prerequisites(**updates),
        resource_preflight=lambda _profile: None,
        sampler_factory=lambda _profile: object(),
        cleanup_probe=lambda: None,
        modal_rate_path=tmp_path / "rate.json",
    )

    with pytest.raises(QualificationRefused, match="staging_prerequisite"):
        control.setup_profile(resolve_durable_profile("32-functional-turns"))


def test_cleanup_counts_only_transient_workers_and_exact_scope(tmp_path):
    from backend.scripts.qualify_durable_external_turns import (
        ScopedCleanupState,
        SystemDurableQualificationControlPlane,
    )

    # The configured baseline worker remains active outside this scoped state.
    control = SystemDurableQualificationControlPlane(
        release_id="0123456789ab-staging",
        settings=_safe_settings(),
        app_root=_release_tree(tmp_path),
        environ={"PWC_RELEASE_ID": "0123456789ab-staging"},
        mem_total=lambda: 16 * 1024**3,
        prerequisites=_ready_prerequisites,
        resource_preflight=lambda _profile: None,
        sampler_factory=lambda _profile: object(),
        cleanup_probe=lambda: ScopedCleanupState(True, 0, 0, 0, 0, 0, 0, 0),
        modal_rate_path=tmp_path / "rate.json",
    )

    proof = control.cleanup_transient_workers()
    assert proof.passed is True
    assert proof.final_active_external_workers == 0


def test_modal_rate_evidence_requires_root_owned_mode_0600_bounded_file(tmp_path):
    from backend.scripts.qualify_durable_external_turns import (
        QualificationRefused,
        SystemDurableQualificationControlPlane,
    )
    from backend.loadtests.external_pi_fleet_core import resolve_durable_profile

    path = tmp_path / "rate.json"
    path.write_text(json.dumps({"PWC_RELEASE_ID": "0123456789ab-staging"}))
    path.chmod(0o600)
    control = SystemDurableQualificationControlPlane(
        release_id="0123456789ab-staging",
        settings=_safe_settings(),
        app_root=_release_tree(tmp_path),
        environ={"PWC_RELEASE_ID": "0123456789ab-staging"},
        mem_total=lambda: 16 * 1024**3,
        prerequisites=_ready_prerequisites,
        resource_preflight=lambda _profile: None,
        sampler_factory=lambda _profile: object(),
        cleanup_probe=lambda: None,
        modal_rate_path=path,
    )
    profile = resolve_durable_profile("32-functional-turns")

    assert control.protected_runtime_evidence(profile)["PWC_RELEASE_ID"].endswith(
        "-staging"
    )
    path.chmod(0o644)
    with pytest.raises(QualificationRefused, match="modal_rate"):
        control.protected_runtime_evidence(profile)


def test_model_selection_requires_one_discovered_direct_openai_route():
    from backend.scripts.qualify_durable_external_turns import (
        QualificationRefused,
        select_staging_pi_openai_model,
    )

    direct = {
        "id": "gpt-5.6-luna@openai",
        "provider": "openai",
        "protocol": "openai-responses",
        "route": "gpt-5.6-luna",
    }
    assert (
        select_staging_pi_openai_model(SimpleNamespace(chat_model_choices=(direct,)))
        == direct["id"]
    )
    for choices in ((), (direct, direct)):
        with pytest.raises(QualificationRefused, match="pi_openai_model"):
            select_staging_pi_openai_model(SimpleNamespace(chat_model_choices=choices))
