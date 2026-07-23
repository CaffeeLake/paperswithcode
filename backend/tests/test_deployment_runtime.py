from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.config import Settings
from backend.services.runtime_validation import validate_runtime
from deploy.nginx_validate import validate as validate_nginx
from deploy.release import atomic_symlink, build_manifest, validate_manifest
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
    (dist / "features.json").write_text(json.dumps({"chat": chat}))
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
    assert validate_runtime(settings) == {"chat": environment == "staging"}


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
    (release / "frontend-dist" / "features.json").write_text('{"chat": true}')
    with pytest.raises(ValueError, match="features.json"):
        validate_manifest(release, "production")


def test_smoke_bundle_parser_catches_missing_asset(tmp_path: Path):
    release = make_bundle(tmp_path, chat=False)
    (release / "frontend-dist" / "assets" / "app-abc123.js").unlink()
    assert any(
        "missing asset" in item for item in validate_local_bundle(release, False)
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
