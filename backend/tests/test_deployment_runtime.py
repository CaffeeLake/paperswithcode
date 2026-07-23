from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import deploy.cli as deploy_cli
import deploy.configure_host_env as configure_host_env
import deploy.cron_launcher as cron_launcher
import deploy.run_backend as run_backend
from backend.config import Settings
from backend.services.runtime_validation import validate_runtime
from deploy.cli import parser_for
from deploy.nginx_validate import validate as validate_nginx
from deploy.release import (
    atomic_symlink,
    build_manifest,
    profile_features,
    validate_manifest,
)
from deploy.smoke_test import validate_local_bundle


def make_bundle(root: Path, *, chat: bool) -> Path:
    release = root / ("release-staging" if chat else "release-production")
    dist = release / "frontend-dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (assets / "app-abc123.js").write_text("export {}")
    (assets / "app-abc123.css").write_text("body{}")
    (dist / "index.html").write_text(
        '<script type="module" src="/assets/app-abc123.js"></script>'
        '<link rel="stylesheet" href="/assets/app-abc123.css">'
    )
    (dist / "features.json").write_text(
        json.dumps(profile_features("staging" if chat else "production"))
    )
    (release / "backend").mkdir()
    (release / "backend" / "main.py").write_text("")
    sha = "a" * 40
    environment = "staging" if chat else "production"
    (release / "release.json").write_text(json.dumps(build_manifest(sha, environment)))
    return release


def deployed_settings(tmp_path: Path, release: Path, environment: str) -> Settings:
    state = tmp_path / "state"
    thumbnail = tmp_path / "thumbnails"
    for path in (
        state,
        thumbnail,
        state / "cache",
        state / "logs",
        state / "locks",
        state / "spool",
        state / "agent",
        state / "recovery",
    ):
        path.mkdir(parents=True, exist_ok=True)
    features = profile_features(environment)
    return Settings(
        environment=environment,
        release_id=json.loads((release / "release.json").read_text())["release_id"],
        frontend_dist_dir=str(release / "frontend-dist"),
        runtime_data_dir=str(state),
        thumbnail_cache_dir=str(thumbnail),
        thumbnail_temp_cache_dir=str(state / "cache"),
        cron_log_dir=str(state / "logs"),
        cron_lock_dir=str(state / "locks"),
        codex_add_evals_spool_dir=str(state / "spool"),
        chat_agent_cwd=str(state / "agent"),
        chat_recovery_spool_dir=str(state / "recovery"),
        jwt_secret="test-only",
        production_jwt_fingerprint=("0" * 64 if environment == "staging" else ""),
        session_cookie_domain="",
        session_cookie_name=(
            "pwc_staging_session" if environment == "staging" else "pwc_session"
        ),
        chat_enabled=environment == "staging",
        codex_jobs_enabled=features["codex_add_evals"]
        or features["codex_enrich_paper"],
        codex_add_evals_enabled=features["codex_add_evals"],
        codex_enrich_paper_enabled=features["codex_enrich_paper"],
        codex_jobs_namespace="nielsr" if environment == "production" else "",
        codex_jobs_token="hf-token" if environment == "production" else "",
        codex_jobs_openai_api_key=(
            "openai-token" if environment == "production" else ""
        ),
        github_token="github-token" if environment == "production" else "",
        catalog_mutations_enabled=environment == "production",
        thumbnail_mutations_enabled=False,
        cron_enabled=environment == "production",
        db_search_path="staging,public" if environment == "staging" else "public",
    )


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_deployed_runtime_validation(tmp_path: Path, environment: str):
    release = make_bundle(tmp_path, chat=environment == "staging")
    settings = deployed_settings(tmp_path, release, environment)
    assert validate_runtime(settings) == profile_features(environment)


def test_deployed_runtime_rejects_relative_path(tmp_path: Path):
    release = make_bundle(tmp_path, chat=False)
    settings = deployed_settings(tmp_path, release, "production")
    settings.runtime_data_dir = "./runtime"
    with pytest.raises(RuntimeError, match="must be absolute"):
        validate_runtime(settings)


def test_deployed_runtime_rejects_source_shell(tmp_path: Path):
    release = make_bundle(tmp_path, chat=False)
    (release / "frontend-dist" / "index.html").write_text(
        '<script type="module" src="/src/main.tsx"></script>'
    )
    with pytest.raises(RuntimeError, match="/src/main.tsx"):
        validate_runtime(deployed_settings(tmp_path, release, "production"))


def test_release_manifest_rejects_feature_mismatch(tmp_path: Path):
    release = make_bundle(tmp_path, chat=False)
    features = profile_features("production")
    features["codex_add_evals"] = False
    (release / "frontend-dist" / "features.json").write_text(json.dumps(features))
    with pytest.raises(ValueError, match="features.json"):
        validate_manifest(release, "production")


def test_legacy_release_manifest_remains_a_valid_rollback_target(tmp_path: Path):
    release = make_bundle(tmp_path, chat=False)
    manifest_path = release / "release.json"
    manifest = json.loads(manifest_path.read_text())
    manifest.pop("feature_contract_version")
    manifest["backend_features"] = {"chat": False}
    manifest["frontend_features"] = {"chat": False}
    manifest_path.write_text(json.dumps(manifest))
    (release / "frontend-dist" / "features.json").write_text(
        json.dumps({"chat": False})
    )

    assert validate_manifest(release, "production")["git_sha"] == "a" * 40


def test_v2_release_manifest_remains_a_valid_rollback_target(tmp_path: Path):
    release = make_bundle(tmp_path, chat=False)
    manifest_path = release / "release.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["feature_contract_version"] = 2
    manifest["backend_features"] = {
        "chat": False,
        "codex_add_evals": False,
        "codex_enrich_paper": False,
    }
    manifest["frontend_features"] = manifest["backend_features"]
    manifest_path.write_text(json.dumps(manifest))
    (release / "frontend-dist" / "features.json").write_text(
        json.dumps(manifest["backend_features"])
    )

    assert validate_manifest(release, "production")["git_sha"] == "a" * 40


def test_staging_profile_keeps_unmediated_catalog_actions_hidden():
    assert profile_features("staging") == {
        "chat": True,
        "codex_add_evals": False,
        "codex_enrich_paper": False,
    }


def test_production_profile_enables_admin_catalog_actions():
    assert profile_features("production") == {
        "chat": False,
        "codex_add_evals": True,
        "codex_enrich_paper": True,
    }


def test_production_codex_jobs_require_all_credentials(tmp_path: Path):
    release = make_bundle(tmp_path, chat=False)
    settings = deployed_settings(tmp_path, release, "production")
    settings.codex_jobs_token = ""
    with pytest.raises(RuntimeError, match="production Codex jobs require"):
        validate_runtime(settings)


def test_backend_launcher_uses_release_specific_feature_flags(
    tmp_path: Path, monkeypatch
):
    release = make_bundle(tmp_path, chat=False)
    monkeypatch.setenv("PWC_FRONTEND_DIST_DIR", str(release / "frontend-dist"))
    run_backend.configure_release_environment(release)
    assert os.environ["PWC_CODEX_JOBS_ENABLED"] == "true"
    assert os.environ["PWC_CODEX_ADD_EVALS_ENABLED"] == "true"
    assert os.environ["PWC_CODEX_ENRICH_PAPER_ENABLED"] == "true"


def test_backend_launcher_disables_features_for_legacy_rollback(
    tmp_path: Path, monkeypatch
):
    release = make_bundle(tmp_path, chat=False)
    manifest_path = release / "release.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["backend_features"] = {"chat": False}
    manifest_path.write_text(json.dumps(manifest))
    monkeypatch.setenv("PWC_FRONTEND_DIST_DIR", str(release / "frontend-dist"))
    run_backend.configure_release_environment(release)
    assert os.environ["PWC_CODEX_JOBS_ENABLED"] == "false"
    assert os.environ["PWC_CODEX_ADD_EVALS_ENABLED"] == "false"
    assert os.environ["PWC_CODEX_ENRICH_PAPER_ENABLED"] == "false"


def test_smoke_bundle_parser_catches_missing_asset(tmp_path: Path):
    release = make_bundle(tmp_path, chat=False)
    (release / "frontend-dist" / "assets" / "app-abc123.js").unlink()
    assert any(
        "missing asset" in item
        for item in validate_local_bundle(release, profile_features("production"))
    )


def test_smoke_script_runs_from_outside_repository(tmp_path: Path):
    script = Path(__file__).parents[2] / "deploy" / "smoke_test.py"
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=tmp_path,
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr


def test_nginx_cross_environment_references_are_rejected():
    failures = validate_nginx(
        "root /srv/paperswithcode/environments/production/current/frontend-dist;"
        " upstream pwc_staging_backend { server 127.0.0.1:8001; } location / { }",
        "root /srv/paperswithcode/environments/staging/current/frontend-dist;"
        " location = /_admin_check { internal; } location / { }",
    )
    assert "production references staging backend" in failures


def test_atomic_symlink_replaces_pointer(tmp_path: Path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    link = tmp_path / "current"
    atomic_symlink(first, link)
    atomic_symlink(second, link)
    assert link.resolve() == second


@pytest.mark.parametrize(
    ("program", "arguments", "handler"),
    [
        ("pwc-deploy", ["staging", "abc123"], "deploy"),
        ("pwc-rollback", ["staging"], "rollback"),
        ("pwc-cleanup", ["--confirm", "CLEAN_RELEASES"], "cleanup_command"),
        ("pwc-status", [], "status"),
    ],
)
def test_installed_deployment_command_dispatch(program, arguments, handler):
    args = parser_for(program).parse_args(arguments)
    assert args.handler.__name__ == handler


def test_environment_config_directory_is_search_only(tmp_path: Path, monkeypatch):
    config = tmp_path / "paperswithcode" / "staging.env"
    monkeypatch.setattr(configure_host_env.os, "chown", lambda *_: None)
    monkeypatch.setattr(
        configure_host_env.grp,
        "getgrnam",
        lambda _group: type("Group", (), {"gr_gid": 123})(),
    )

    configure_host_env.write_env(config, {"KEY": "KEY=value"}, "pwc-staging")

    assert config.parent.stat().st_mode & 0o777 == 0o711
    assert config.stat().st_mode & 0o777 == 0o640


def test_production_codex_credentials_are_mapped_without_enabling_base_flags():
    values = configure_host_env.production_codex_values(
        {
            "OPENAI_API_KEY": "OPENAI_API_KEY=openai-secret",
            "PWC_HF_TOKEN": "PWC_HF_TOKEN=hf-secret",
        },
        "nielsr",
    )
    assert values == {
        "PWC_CODEX_ADD_EVALS_ENABLED": "false",
        "PWC_CODEX_ENRICH_PAPER_ENABLED": "false",
        "PWC_CODEX_JOBS_ENABLED": "false",
        "PWC_CODEX_JOBS_NAMESPACE": "nielsr",
        "PWC_CODEX_JOBS_OPENAI_API_KEY": "openai-secret",
        "PWC_CODEX_JOBS_TOKEN": "hf-secret",
    }


def test_cron_jobs_declare_bounded_execution_contracts():
    assert cron_launcher.COMMANDS
    for spec in cron_launcher.COMMANDS.values():
        assert spec.command
        assert spec.timeout in {"30m", "50m", "2h", "6h"}
        assert spec.mutates_shared_data is True
        assert spec.idempotency
        assert spec.health_job


def test_cron_status_reports_exact_production_release(
    tmp_path: Path, monkeypatch, capsys
):
    current = tmp_path / "current"
    current.mkdir()
    (current / "release.json").write_text(
        json.dumps(
            {
                "release_id": "a" * 12 + "-production",
                "git_sha": "a" * 40,
            }
        )
    )
    monkeypatch.setattr(cron_launcher, "CURRENT", current)
    monkeypatch.setattr(cron_launcher.sys, "argv", ["pwc-cron", "status"])

    assert cron_launcher.main() == 0
    status = json.loads(capsys.readouterr().out)
    assert status["environment"] == "production"
    assert status["release_id"] == "a" * 12 + "-production"
    assert status["git_sha"] == "a" * 40
    assert status["jobs"]["refresh_paper_embeddings"]["timeout"] == "6h"


def test_shared_runtime_is_made_service_readable(tmp_path: Path, monkeypatch):
    runtime = tmp_path / ".venv"
    package = runtime / "lib" / "package.py"
    base = tmp_path / "base-python"
    neutral_base = tmp_path / "python-runtime"
    interpreter = base / "bin" / "python3.12"
    package.parent.mkdir(parents=True)
    (runtime / "bin").mkdir()
    interpreter.parent.mkdir(parents=True)
    package.write_text("value = 1\n")
    interpreter.write_text("python")
    interpreter.chmod(0o755)
    (runtime / "bin" / "python").symlink_to(interpreter)
    (runtime / "pyvenv.cfg").write_text(f"home = {base / 'bin'}\n")
    runtime.chmod(0o700)
    package.parent.chmod(0o700)
    package.chmod(0o600)
    monkeypatch.setattr(deploy_cli, "VENV", runtime)
    monkeypatch.setattr(deploy_cli, "PYTHON_RUNTIME", neutral_base)

    deploy_cli.make_runtime_readable()

    assert runtime.stat().st_mode & 0o055 == 0o055
    assert package.parent.stat().st_mode & 0o055 == 0o055
    assert package.stat().st_mode & 0o044 == 0o044
    assert (runtime / "bin" / "python").resolve() == (
        neutral_base / "bin" / "python3.12"
    )
    assert str(neutral_base) in (runtime / "pyvenv.cfg").read_text()


def test_immutable_release_is_world_readable(tmp_path: Path):
    release = tmp_path / "release"
    package = release / "backend"
    module = package / "main.py"
    script = release / "scripts" / "job.sh"
    package.mkdir(parents=True)
    script.parent.mkdir()
    module.write_text("app = object()\n")
    script.write_text("#!/bin/sh\n")
    package.chmod(0o700)
    module.chmod(0o600)
    script.chmod(0o700)

    deploy_cli.make_release_readable(release)

    assert release.stat().st_mode & 0o555 == 0o555
    assert package.stat().st_mode & 0o555 == 0o555
    assert module.stat().st_mode & 0o444 == 0o444
    assert script.stat().st_mode & 0o555 == 0o555
    assert module.stat().st_mode & 0o222 == 0
