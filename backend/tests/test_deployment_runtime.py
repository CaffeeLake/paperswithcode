from __future__ import annotations

import json
from pathlib import Path

import pytest

import deploy.cli as deploy_cli
import deploy.cron_launcher as cron_launcher
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
    features["codex_add_evals"] = True
    (release / "frontend-dist" / "features.json").write_text(json.dumps(features))
    with pytest.raises(ValueError, match="features.json"):
        validate_manifest(release, "production")


def test_staging_profile_keeps_unmediated_catalog_actions_hidden():
    assert profile_features("staging") == {
        "chat": True,
        "codex_add_evals": False,
        "codex_enrich_paper": False,
    }


def test_smoke_bundle_parser_catches_missing_asset(tmp_path: Path):
    release = make_bundle(tmp_path, chat=False)
    (release / "frontend-dist" / "assets" / "app-abc123.js").unlink()
    assert any(
        "missing asset" in item
        for item in validate_local_bundle(release, profile_features("production"))
    )


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
