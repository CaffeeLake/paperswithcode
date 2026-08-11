from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import deploy.cli as deploy_cli
import deploy.configure_host_env as configure_host_env
import deploy.configure_role_allowlists as configure_role_allowlists
import deploy.cron_launcher as cron_launcher
import deploy.run_backend as run_backend
import deploy.smoke_test as smoke_test
from backend.chat_sandbox_worker.contract import (
    MODAL_IMAGE_ID,
    PRODUCTION_MODAL_IMAGE_ID,
)
from backend.config import Settings
from backend.services import openrouter_budget_service as deploy_openrouter
from backend.services.runtime_validation import validate_chat_schema, validate_runtime
from deploy.cli import (
    _chat_descriptor_from_source,
    _configured_chat_enabled,
    parser_for,
    require_production_chat_monitor,
)
from deploy.install_deploy_tools import (
    RUNTIME_CONTRACT_PATHS,
    bundle_runtime_contract,
    cron_wrapper,
    deployment_wrapper,
)
from deploy.nginx_validate import (
    CURATION_CALLBACK_LOCATION,
    SEO_LOCATIONS,
    SHARE_API_LOCATION,
    SHARE_PAGE_LOCATION,
    location_block,
)
from deploy.nginx_validate import (
    validate as validate_nginx,
)
from deploy.release import (
    atomic_symlink,
    build_manifest,
    profile_features,
    validate_manifest,
    validate_rolling_compatibility,
)
from deploy.run_backend import RELEASE_ROOT, configure_release_environment
from deploy.smoke_test import validate_local_bundle


@pytest.fixture(autouse=True)
def _avoid_live_openrouter_guardrail(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        deploy_openrouter, "validate_openrouter_guardrail", lambda _settings: None
    )


def test_deployment_tool_bundle_includes_chat_runtime_contract(tmp_path: Path):
    repository = Path(__file__).resolve().parents[2]
    staging = tmp_path / "staging"
    source = staging / "deploy"
    source.mkdir(parents=True)
    shutil.copy2(repository / "deploy" / "release.py", source / "release.py")
    for relative in RUNTIME_CONTRACT_PATHS:
        origin = repository / relative
        target = staging / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origin, target)

    bundle_runtime_contract(staging, source)

    for relative in RUNTIME_CONTRACT_PATHS:
        backend_relative = Path(relative).relative_to("backend")
        assert (source / "backend" / backend_relative).is_file()
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import release; assert release.chat_runtime('staging')['enabled']",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(source)},
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("pwc-deploy", "{production,staging} source"),
        ("pwc-rollback", "{production,staging}"),
    ],
)
def test_installed_wrapper_preserves_command_parser(
    command: str,
    expected: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    wrapper = deployment_wrapper(command)
    assert f"export PWC_DEPLOY_COMMAND={command}\n" in wrapper
    monkeypatch.setenv("PWC_DEPLOY_COMMAND", command)
    monkeypatch.setattr(sys, "argv", ["cli.py", "--help"])

    with pytest.raises(SystemExit) as exc:
        deploy_cli.main()

    output = capsys.readouterr().out
    assert exc.value.code == 0
    assert f"usage: {command}" in output
    assert expected in output


def test_cron_wrapper_grants_journal_access_only_to_chat_monitor():
    wrapper = cron_wrapper()

    assert 'if [ "$1" = "monitor_chat_operational_alerts" ]' in wrapper
    assert wrapper.count("SupplementaryGroups=systemd-journal") == 1
    assert wrapper.count("cron_launcher.py") == 2


def test_chat_alert_timer_uses_only_the_allowlisted_cron_interface():
    systemd = Path(__file__).resolve().parents[2] / "deploy" / "systemd"
    service = (systemd / "pwc-chat-alert-monitor.service").read_text()
    timer = (systemd / "pwc-chat-alert-monitor.timer").read_text()

    assert (
        "ExecStart=/usr/local/sbin/pwc-cron monitor_chat_operational_alerts" in service
    )
    assert "backend.scripts" not in service
    assert "OnUnitActiveSec=1m" in timer
    assert "WantedBy=timers.target" in timer


def test_production_sha_resolves_from_bare_main_ref(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source = tmp_path / "source"
    origin = tmp_path / "origin.git"
    repository = tmp_path / "repository.git"
    source.mkdir()

    def git(*arguments: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *arguments],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )

    git("init", "--initial-branch=main", cwd=source)
    git("config", "user.name", "Deployment Test", cwd=source)
    git("config", "user.email", "deployment-test@example.invalid", cwd=source)
    (source / "README.md").write_text("test\n")
    git("add", "README.md", cwd=source)
    git("commit", "-m", "Initial commit", cwd=source)
    sha = git("rev-parse", "HEAD", cwd=source).stdout.strip()
    git("clone", "--bare", str(source), str(origin))
    git("init", "--bare", str(repository))
    git("--git-dir", str(repository), "remote", "add", "origin", str(origin))
    git(
        "--git-dir",
        str(repository),
        "config",
        "remote.origin.fetch",
        "+refs/heads/*:refs/heads/*",
    )
    monkeypatch.setattr(deploy_cli, "REPOSITORY", repository)

    assert deploy_cli.resolve_sha(sha, "production") == sha
    assert (
        git(
            "--git-dir", str(repository), "rev-parse", "--verify", "refs/heads/main"
        ).stdout.strip()
        == sha
    )
    missing_remote_ref = subprocess.run(
        [
            "git",
            "--git-dir",
            str(repository),
            "rev-parse",
            "--verify",
            "refs/remotes/origin/main",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert missing_remote_ref.returncode != 0


def test_candidate_overrides_follow_environment_file(tmp_path: Path):
    release = tmp_path / "release"
    manifest = {
        "release_id": "a" * 12 + "-production",
        "backend_features": profile_features("production"),
    }
    command = deploy_cli.candidate_start_command(
        release, "production", manifest, 8123, "candidate-test"
    )

    environment_file = command.index(
        f"EnvironmentFile={deploy_cli.CONFIG_ROOT / 'production.env'}"
    )
    env_command = command.index("/usr/bin/env")
    python = command.index(str(deploy_cli.VENV / "bin" / "python"))
    assert environment_file < env_command < python
    assert command[env_command + 1 : python] == [
        "UVICORN_PORT=8123",
        "PWC_PORT=8123",
        f"PWC_RELEASE_ID={manifest['release_id']}",
        f"PWC_FRONTEND_DIST_DIR={release / 'frontend-dist'}",
        "PWC_CHAT_ENABLED=false",
        "PWC_CODEX_ADD_EVALS_ENABLED=true",
        "PWC_CODEX_ENRICH_PAPER_ENABLED=true",
        "PWC_CODEX_JOBS_ENABLED=true",
    ]
    assert "--setenv" not in command


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
    (dist / "features.json").write_text(json.dumps(profile_features(environment)))
    descriptor = None
    if environment == "staging":
        descriptor = {
            **build_manifest(sha, environment)["chat_runtime"],
            "modal_image_version": "im-test-immutable",
        }
    (release / "release.json").write_text(
        json.dumps(build_manifest(sha, environment, chat_descriptor=descriptor))
    )
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
    runtime = json.loads((release / "release.json").read_text())["chat_runtime"]
    private_key = Ed25519PrivateKey.from_private_bytes(b"\x01" * 32)
    private_value = base64.urlsafe_b64encode(b"\x01" * 32).rstrip(b"=").decode()
    public_value = (
        base64.urlsafe_b64encode(
            private_key.public_key().public_bytes(
                serialization.Encoding.Raw,
                serialization.PublicFormat.Raw,
            )
        )
        .rstrip(b"=")
        .decode()
    )
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
        shared_session_cookie_name="pwc_shared_session",
        shared_session_cookie_domain=".paperswithcode.co",
        session_signing_private_key=(
            private_value if environment == "production" else ""
        ),
        session_verification_public_key=public_value,
        auth_authority_origin="https://paperswithcode.co",
        auth_return_origins=(
            "https://paperswithcode.co,https://staging.paperswithcode.co"
        ),
        hf_oauth_client_id="test-oauth-client",
        hf_oauth_client_secret="test-oauth-secret",
        hf_oauth_credential_secret="test-oauth-credential-secret",
        chat_enabled=environment == "staging",
        chat_public_admission_enabled=environment == "staging",
        chat_sandbox_admission_enabled=environment == "staging",
        chat_default_backend=runtime["default_backend"],
        chat_new_chat_modal_percentage=runtime["new_chat_modal_percentage"],
        chat_modal_image_version=runtime["modal_image_version"],
        chat_pwc_cli_version=runtime["pwc_cli_version"],
        chat_worker_contract_version=runtime["worker_contract_version"],
        chat_system_prompt_sha256=runtime["system_prompt_sha256"],
        chat_max_concurrency=2 if environment == "staging" else 1,
        chat_user_max_concurrency=2,
        chat_sandbox_total_live_cap=3,
        chat_blank_pool_enabled=environment == "staging",
        chat_blank_pool_min=1,
        chat_blank_pool_max=1,
        chat_persistent_worker_enabled=environment == "staging",
        chat_sandbox_spend_enforcement_enabled=environment == "staging",
        chat_sandbox_provider_mode="starter_workspace",
        chat_sandbox_budget_attestation=(
            "modal-workspace-nielsrogge-250-staging-starter-v1"
            if environment == "staging"
            else ""
        ),
        chat_sandbox_modal_environment=(
            "pwc-chat-staging" if environment == "staging" else ""
        ),
        chat_sandbox_modal_workspace=("nielsrogge" if environment == "staging" else ""),
        chat_sandbox_modal_owner_username=(
            "nielsrogge" if environment == "staging" else ""
        ),
        chat_sandbox_slack_webhook_url=(
            "https://hooks.slack.test/services/test" if environment == "staging" else ""
        ),
        chat_sandbox_alert_fallback_webhook_url=(
            "https://alerts.test/fallback" if environment == "staging" else ""
        ),
        chat_sandbox_runbook_url=(
            "https://example.test/runbook" if environment == "staging" else ""
        ),
        chat_sandbox_operator_usernames=("root" if environment == "staging" else ""),
        chat_gateway_url=(
            "https://chat-gateway-staging.paperswithcode.co/api/internal/chat-gateway"
            if environment == "staging"
            else ""
        ),
        chat_title_generation_enabled=environment == "staging",
        chat_title_hf_token=(
            "test-only-isolated-title-token" if environment == "staging" else ""
        ),
        chat_title_bill_to=("huggingface" if environment == "staging" else ""),
        chat_title_credential_owner=("nielsr" if environment == "staging" else ""),
        chat_title_credential_environment=(
            "staging" if environment == "staging" else ""
        ),
        codex_jobs_enabled=True,
        codex_add_evals_enabled=True,
        codex_enrich_paper_enabled=True,
        codex_jobs_namespace="test",
        codex_jobs_token="test-only",
        codex_jobs_openai_api_key="test-only",
        codex_jobs_api_url=(
            "https://staging.paperswithcode.co/api/v1"
            if environment == "staging"
            else "https://paperswithcode.co/api/v1"
        ),
        github_token="test-only",
        hf_token="test-only-hf-token" if environment == "staging" else "",
        chat_openrouter_api_key=(
            "test-only-openrouter-token" if environment == "staging" else ""
        ),
        chat_openrouter_server_funded_enabled=environment == "staging",
        chat_openrouter_monthly_user_budget_usd=1,
        chat_openrouter_workspace_monthly_budget_usd=200,
        chat_openrouter_credential_keyring=(
            json.dumps({"1": base64.urlsafe_b64encode(b"k" * 32).rstrip(b"=").decode()})
            if environment == "staging"
            else ""
        ),
        chat_openrouter_user_tracking_secret=(
            "test-only-tracking-secret" if environment == "staging" else ""
        ),
        catalog_mutations_enabled=environment == "production",
        thumbnail_mutations_enabled=False,
        cron_enabled=environment == "production",
        db_search_path="staging,public" if environment == "staging" else "public",
    )


def test_run_backend_derives_features_from_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    release = make_bundle(tmp_path, chat=False)
    monkeypatch.setenv("PWC_FRONTEND_DIST_DIR", str(release / "frontend-dist"))
    monkeypatch.setenv("PWC_RUNTIME_DATA_DIR", str(tmp_path / "runtime-data"))

    manifest = configure_release_environment(release)

    assert manifest["build_profile"] == "production"
    assert os.environ["PWC_CHAT_ENABLED"] == "false"
    assert os.environ["PWC_CODEX_ADD_EVALS_ENABLED"] == "true"
    assert os.environ["PWC_CODEX_ENRICH_PAPER_ENABLED"] == "true"
    assert os.environ["PWC_CODEX_JOBS_ENABLED"] == "true"


def test_run_backend_prepends_immutable_release_root():
    assert sys.path[0] == str(RELEASE_ROOT)
    assert RELEASE_ROOT == Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_deployed_runtime_validation(tmp_path: Path, environment: str):
    release = make_bundle(tmp_path, chat=environment == "staging")
    settings = deployed_settings(tmp_path, release, environment)
    assert validate_runtime(settings) == profile_features(environment)


def test_staging_runtime_rejects_unapproved_team_environment_policy(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.chat_sandbox_provider_mode = "team_environments"
    settings.chat_sandbox_environment_cap_microusd = 125_000_000
    settings.chat_sandbox_budget_attestation = "modal-workspace-250-staging-125-v1"

    with pytest.raises(RuntimeError, match=r"\$75/\$100/\$250"):
        validate_runtime(settings)


def test_enabled_chat_rejects_missing_hf_inference_credential_path(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.hf_oauth_credential_secret = ""

    with pytest.raises(RuntimeError, match="OAuth inference credential path"):
        validate_runtime(settings)


def test_enabled_chat_does_not_require_general_server_hf_token(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.hf_token = ""

    assert validate_runtime(settings) == profile_features("staging")


def test_enabled_chat_requires_title_organization_billing(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.chat_title_bill_to = ""

    with pytest.raises(RuntimeError, match="billed to the huggingface organization"):
        validate_runtime(settings)


def test_starter_runtime_rejects_unenforced_environment_cap(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.chat_sandbox_environment_cap_microusd = 125_000_000

    with pytest.raises(RuntimeError, match="no environment cap"):
        validate_runtime(settings)


def test_staging_requires_alerts_even_when_blank_pool_is_disabled(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.chat_sandbox_slack_webhook_url = ""
    settings.chat_sandbox_alert_fallback_webhook_url = ""
    settings.chat_blank_pool_enabled = False
    with pytest.raises(RuntimeError, match="alert destinations are required"):
        validate_runtime(settings)


def test_staging_allows_budgeted_server_funded_openrouter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.chat_openrouter_server_funded_enabled = True
    monkeypatch.setattr(
        "backend.services.openrouter_budget_service.validate_openrouter_guardrail",
        lambda _settings: None,
    )

    assert validate_runtime(settings) == profile_features("staging")


@pytest.mark.parametrize("budget", [5, 199, 201])
def test_staging_rejects_openrouter_workspace_budget_other_than_200(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, budget: int
):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.chat_openrouter_server_funded_enabled = True
    settings.chat_openrouter_workspace_monthly_budget_usd = budget
    monkeypatch.setattr(
        "backend.services.openrouter_budget_service.validate_openrouter_guardrail",
        lambda _settings: None,
    )

    with pytest.raises(RuntimeError, match="must equal \\$200"):
        validate_runtime(settings)


def test_staging_rejects_missing_provider_enforced_guardrail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.chat_openrouter_server_funded_enabled = True

    def missing(_settings):
        raise deploy_openrouter.OpenRouterBudgetUnavailable("no hard limit")

    monkeypatch.setattr(deploy_openrouter, "validate_openrouter_guardrail", missing)
    with pytest.raises(RuntimeError, match="provider-enforced guardrail"):
        validate_runtime(settings)


def test_staging_rejects_openrouter_request_bound_above_user_budget(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.chat_openrouter_server_funded_enabled = True
    settings.chat_openrouter_monthly_user_budget_usd = 0.1

    with pytest.raises(RuntimeError, match=r"per-user budget must equal \$1"):
        validate_runtime(settings)


def test_staging_openrouter_values_preserve_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config_root = tmp_path / "config"
    config_root.mkdir()
    key = base64.urlsafe_b64encode(b"a" * 32).rstrip(b"=").decode()
    (config_root / "staging.env").write_text(
        "PWC_CHAT_OPENROUTER_CREDENTIAL_KEYRING='"
        + json.dumps({"1": key}, separators=(",", ":"))
        + "'\n"
        "PWC_CHAT_OPENROUTER_USER_TRACKING_SECRET=stable-secret\n"
    )
    monkeypatch.setattr(configure_host_env, "CONFIG_ROOT", config_root)

    values = configure_host_env.staging_openrouter_values(
        {"PWC_OPENROUTER_API_KEY": "PWC_OPENROUTER_API_KEY=provider-key"}
    )

    assert json.loads(values["PWC_CHAT_OPENROUTER_CREDENTIAL_KEYRING"]) == {"1": key}
    assert values["PWC_CHAT_OPENROUTER_USER_TRACKING_SECRET"] == "stable-secret"
    assert values["PWC_CHAT_OPENROUTER_MONTHLY_USER_BUDGET_USD"] == "1.00"
    assert values["PWC_CHAT_OPENROUTER_WORKSPACE_MONTHLY_BUDGET_USD"] == "200.00"


def test_staging_openrouter_secret_rotation_preserves_decryption_versions():
    old_key = base64.urlsafe_b64encode(b"a" * 32).rstrip(b"=").decode()
    current = {
        "PWC_CHAT_OPENROUTER_CREDENTIAL_KEYRING": (
            "PWC_CHAT_OPENROUTER_CREDENTIAL_KEYRING='"
            + json.dumps({"1": old_key}, separators=(",", ":"))
            + "'"
        ),
        "PWC_CHAT_OPENROUTER_CREDENTIAL_ACTIVE_KEY_VERSION": (
            "PWC_CHAT_OPENROUTER_CREDENTIAL_ACTIVE_KEY_VERSION=1"
        ),
        "PWC_CHAT_OPENROUTER_USER_TRACKING_SECRET": (
            "PWC_CHAT_OPENROUTER_USER_TRACKING_SECRET=old-secret"
        ),
    }

    values = configure_host_env.rotate_staging_openrouter_secret_values(current)

    keyring = json.loads(values["PWC_CHAT_OPENROUTER_CREDENTIAL_KEYRING"])
    assert keyring["1"] == old_key
    assert (
        len(base64.urlsafe_b64decode(keyring["2"] + "=" * (-len(keyring["2"]) % 4)))
        == 32
    )
    assert values["PWC_CHAT_OPENROUTER_CREDENTIAL_ACTIVE_KEY_VERSION"] == "2"
    assert values["PWC_CHAT_OPENROUTER_USER_TRACKING_SECRET"] != "old-secret"


def test_production_rejects_server_funded_openrouter(tmp_path: Path):
    release = make_bundle(tmp_path, chat=False)
    settings = deployed_settings(tmp_path, release, "production")
    settings.chat_openrouter_server_funded_enabled = True

    with pytest.raises(RuntimeError, match="production OpenRouter.*prohibited"):
        validate_runtime(settings)


def test_staging_runtime_rejects_shared_session_signer(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.session_signing_private_key = (
        base64.urlsafe_b64encode(b"\x01" * 32).rstrip(b"=").decode()
    )
    with pytest.raises(RuntimeError, match="staging must not have"):
        validate_runtime(settings)


def test_production_runtime_rejects_mismatched_session_keys(tmp_path: Path):
    release = make_bundle(tmp_path, chat=False)
    settings = deployed_settings(tmp_path, release, "production")
    settings.session_signing_private_key = (
        base64.urlsafe_b64encode(b"\x03" * 32).rstrip(b"=").decode()
    )
    with pytest.raises(RuntimeError, match="signing and verification keys differ"):
        validate_runtime(settings)


def test_shared_session_key_generation_is_stable():
    private_value, public_value = configure_host_env.shared_session_keys({}, {})
    production = {
        "PWC_SESSION_SIGNING_PRIVATE_KEY": (
            f"PWC_SESSION_SIGNING_PRIVATE_KEY={private_value}"
        ),
        "PWC_SESSION_VERIFICATION_PUBLIC_KEY": (
            f"PWC_SESSION_VERIFICATION_PUBLIC_KEY={public_value}"
        ),
    }
    staging = {
        "PWC_SESSION_VERIFICATION_PUBLIC_KEY": (
            f"PWC_SESSION_VERIFICATION_PUBLIC_KEY={public_value}"
        )
    }

    assert configure_host_env.shared_session_keys(production, staging) == (
        private_value,
        public_value,
    )


def test_shared_oauth_credential_secret_is_stable_and_conflict_safe():
    production = {
        "PWC_HF_OAUTH_CREDENTIAL_SECRET": (
            "PWC_HF_OAUTH_CREDENTIAL_SECRET=shared-secret"
        )
    }
    staging = dict(production)

    assert (
        configure_host_env.shared_oauth_credential_secret(production, staging)
        == "shared-secret"
    )
    staging["PWC_HF_OAUTH_CREDENTIAL_SECRET"] = (
        "PWC_HF_OAUTH_CREDENTIAL_SECRET=other-secret"
    )
    with pytest.raises(ValueError, match="differs"):
        configure_host_env.shared_oauth_credential_secret(production, staging)


def test_deployed_runtime_rejects_relative_path(tmp_path: Path):
    release = make_bundle(tmp_path, chat=False)
    settings = deployed_settings(tmp_path, release, "production")
    settings.runtime_data_dir = "./runtime"
    with pytest.raises(RuntimeError, match="must be absolute"):
        validate_runtime(settings)


def test_staging_runtime_rejects_directory_snapshot_feature(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.chat_workspace_snapshots_enabled = True
    with pytest.raises(RuntimeError, match="snapshots must remain disabled"):
        validate_runtime(settings)


def test_staging_blank_pool_requires_persistent_workers(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.chat_blank_pool_enabled = True
    settings.chat_persistent_worker_enabled = False
    with pytest.raises(RuntimeError, match="blank pool requires persistent workers"):
        validate_runtime(settings)


def test_staging_blank_pool_rejects_inverted_capacity(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.chat_blank_pool_min = 2
    settings.chat_blank_pool_max = 1
    with pytest.raises(RuntimeError, match="capacity must be"):
        validate_runtime(settings)


def test_production_rejects_blank_pool_activation(tmp_path: Path):
    release = make_bundle(tmp_path, chat=False)
    settings = deployed_settings(tmp_path, release, "production")
    settings.chat_blank_pool_enabled = True
    with pytest.raises(
        RuntimeError, match="active or incomplete chat runtime descriptor"
    ):
        validate_runtime(settings)


def test_disabled_production_accepts_complete_dormant_worker_descriptor(
    tmp_path: Path,
):
    release = make_bundle(tmp_path, chat=False)
    settings = deployed_settings(tmp_path, release, "production")

    assert settings.chat_enabled is False
    assert settings.chat_public_admission_enabled is False
    assert settings.chat_sandbox_admission_enabled is False
    assert settings.chat_blank_pool_enabled is False
    assert settings.chat_new_chat_modal_percentage == 0
    assert settings.chat_default_backend == "modal_cli"
    assert validate_runtime(settings) == profile_features("production")


def test_disabled_production_accepts_armed_configuration_for_atomic_rollback(
    tmp_path: Path,
):
    release = make_bundle(tmp_path, chat=False)
    settings = deployed_settings(tmp_path, release, "production")
    settings.chat_max_concurrency = 2
    settings.chat_persistent_worker_enabled = True
    settings.chat_sandbox_spend_enforcement_enabled = True
    settings.chat_sandbox_cpu_limit = 1
    settings.chat_sandbox_memory_limit_mib = 2048
    settings.chat_sandbox_modal_environment = "pwc-chat-production"
    settings.chat_sandbox_modal_workspace = "nielsrogge"
    settings.chat_sandbox_modal_owner_username = "nielsrogge"
    settings.chat_sandbox_budget_attestation = (
        "modal-workspace-nielsrogge-250-production-starter-v1"
    )
    settings.chat_sandbox_slack_webhook_url = (
        "https://hooks.slack.test/services/production"
    )
    settings.chat_sandbox_alert_fallback_webhook_url = (
        "https://alerts.test/production-fallback"
    )
    settings.chat_sandbox_runbook_url = "https://example.test/production-runbook"
    settings.chat_sandbox_operator_usernames = "nielsr"
    settings.chat_operational_alerts_enabled = True
    settings.chat_gateway_url = (
        "https://chat-gateway.paperswithcode.co/api/internal/chat-gateway"
    )
    settings.chat_title_generation_enabled = True
    settings.chat_title_hf_token = "test-only-production-title-token"
    settings.chat_title_bill_to = "huggingface"
    settings.chat_title_credential_owner = "nielsr"
    settings.chat_title_credential_environment = "production"

    assert settings.chat_enabled is False
    assert settings.chat_new_chat_modal_percentage == 0
    assert settings.chat_public_admission_enabled is False
    assert settings.chat_sandbox_admission_enabled is False
    assert settings.chat_blank_pool_enabled is False
    assert validate_runtime(settings) == profile_features("production")


def test_disabled_legacy_production_rejects_armed_configuration(tmp_path: Path):
    release = make_bundle(tmp_path, chat=False)
    settings = deployed_settings(tmp_path, release, "production")
    settings.chat_default_backend = "local_mcp"
    settings.chat_modal_image_version = ""
    settings.chat_pwc_cli_version = ""
    settings.chat_worker_contract_version = ""
    settings.chat_system_prompt_sha256 = ""
    settings.chat_title_generation_enabled = True

    with pytest.raises(RuntimeError, match="legacy production"):
        validate_runtime(settings)


def test_disabled_bridge_releases_can_replace_legacy_production_safely():
    legacy = {
        "chat_runtime": {
            "enabled": False,
            "gateway_contract_version": 1,
            "gateway_compatible_from": 1,
            "database_contract_version": 1,
        }
    }
    first_bridge = build_manifest("a" * 40, "production")
    second_bridge = build_manifest("b" * 40, "production")

    validate_rolling_compatibility(legacy, first_bridge)
    validate_rolling_compatibility(first_bridge, second_bridge)


def test_hf_catalog_gateway_upgrade_has_one_explicit_fail_closed_rollback():
    active = {
        "chat_runtime": {
            "enabled": True,
            "gateway_contract_version": 26,
            "gateway_compatible_from": 26,
            "database_contract_version": 1,
        }
    }
    candidate = {
        "chat_runtime": {
            "enabled": True,
            "gateway_contract_version": 27,
            "gateway_compatible_from": 26,
            "database_contract_version": 1,
        }
    }
    validate_rolling_compatibility(active, candidate)
    candidate["chat_runtime"]["gateway_contract_version"] = 28
    with pytest.raises(ValueError, match="rollback"):
        validate_rolling_compatibility(active, candidate)


class _ChatSchemaResult:
    def __init__(self, *, scalar=None, rows=None, first=None):
        self._scalar = scalar
        self._rows = rows
        self._first = first

    def scalar_one(self):
        return self._scalar

    def all(self):
        return self._rows

    def first(self):
        return self._first


class _ChatSchemaDB:
    def __init__(
        self,
        transaction_read_only: str,
        *,
        include_edit_columns: bool = True,
        include_share_columns: bool = True,
        include_share_constraint: bool = True,
        include_pool_columns: bool = True,
        include_latency_columns: bool = True,
        include_qualification_columns: bool = True,
    ):
        self.transaction_read_only = transaction_read_only
        self.include_edit_columns = include_edit_columns
        self.include_share_columns = include_share_columns
        self.include_share_constraint = include_share_constraint
        self.include_pool_columns = include_pool_columns
        self.include_latency_columns = include_latency_columns
        self.include_qualification_columns = include_qualification_columns

    def execute(self, statement):
        sql = str(statement)
        if "SHOW transaction_read_only" in sql:
            return _ChatSchemaResult(scalar=self.transaction_read_only)
        if "to_regclass" in sql:
            names = (
                "chat_sessions",
                "chat_messages",
                "chat_shares",
                "chat_sandbox_leases",
                "chat_sandbox_pool",
                "chat_sandbox_compute_intervals",
                "chat_sandbox_budget_states",
                "chat_sandbox_circuit_events",
                "chat_title_budget_states",
                "chat_title_provider_calls",
                "chat_title_budget_events",
                "chat_turn_capabilities",
                "chat_turn_latency",
                "chat_openrouter_credentials",
                "chat_openrouter_monthly_usage",
                "chat_openrouter_provider_calls",
                "chat_openrouter_credential_audit",
            )
            return _ChatSchemaResult(rows=[(name, name) for name in names])
        if "information_schema.columns" in sql:
            rows = [
                ("chat_sessions", "execution_backend"),
                ("chat_messages", "finish_reason"),
                ("chat_messages", "paper_mentions"),
                ("chat_messages", "effective_prompt"),
                ("chat_messages", "langfuse_trace_id"),
                ("chat_sandbox_compute_intervals", "accrued_microusd"),
                ("chat_sandbox_budget_states", "circuit_state"),
                ("chat_sandbox_budget_states", "provider_floor_microusd"),
                (
                    "chat_sandbox_budget_states",
                    "last_reconciliation_attempt_at",
                ),
                ("chat_sandbox_circuit_events", "fallback_delivery_state"),
                (
                    "chat_sandbox_circuit_events",
                    "fallback_next_delivery_attempt_at",
                ),
                ("chat_title_budget_states", "reserved_microusd"),
                ("chat_title_budget_states", "spent_microusd"),
                ("chat_title_provider_calls", "actual_microusd"),
                ("chat_title_provider_calls", "provider_generation_id"),
                ("chat_title_budget_events", "fallback_delivery_state"),
                ("chat_turn_capabilities", "provider_mode"),
                ("chat_turn_capabilities", "provider_credential_revision"),
                ("chat_turn_capabilities", "provider_error_code"),
                ("chat_openrouter_credentials", "credential_revision"),
                ("chat_openrouter_monthly_usage", "reserved_microusd"),
                ("chat_openrouter_provider_calls", "actual_microusd"),
            ]
            if self.include_edit_columns:
                rows.extend(
                    [
                        ("chat_messages", "prepared_fork_sdk_session_id"),
                        ("chat_messages", "prepared_fork_sdk_project_key"),
                    ]
                )
            if self.include_share_columns:
                rows.extend(
                    [
                        ("chat_shares", "snapshot_version"),
                        ("chat_shares", "messages"),
                    ]
                )
            if self.include_pool_columns:
                rows.extend(
                    [
                        ("chat_sandbox_leases", "worker_generation"),
                        ("chat_sandbox_pool", "modal_sandbox_id"),
                        ("chat_sandbox_pool", "worker_generation"),
                        ("chat_sandbox_pool", "billing_month"),
                        ("chat_sandbox_pool", "estimated_blank_cost_usd"),
                    ]
                )
            if self.include_latency_columns:
                rows.extend(
                    [
                        ("chat_turn_latency", "request_id"),
                        ("chat_turn_latency", "terminal_status"),
                        ("chat_turn_latency", "browser_first_visible_delta_ms"),
                        ("chat_turn_latency", "estimated_active_cost_usd"),
                    ]
                )
            if self.include_qualification_columns:
                rows.extend(
                    [
                        ("chat_turn_latency", "qualification_run_id"),
                        ("chat_turn_latency", "qualification_scenario"),
                    ]
                )
            return _ChatSchemaResult(rows=rows)
        if "chat_shares_messages_array_check" in sql:
            return _ChatSchemaResult(
                first=(1,) if self.include_share_constraint else None
            )
        raise AssertionError(f"Unexpected schema validation query: {sql}")


def test_chat_schema_rejects_read_only_staging_connection():
    with pytest.raises(RuntimeError, match="database connection is read-only"):
        validate_chat_schema(
            _ChatSchemaDB("on"),
            Settings(environment="staging", chat_openrouter_server_funded_enabled=True),
        )


def test_chat_schema_accepts_writable_staging_connection():
    validate_chat_schema(
        _ChatSchemaDB("off"),
        Settings(environment="staging", chat_openrouter_server_funded_enabled=True),
    )


def test_chat_schema_production_profile_does_not_require_openrouter_tables():
    db = _ChatSchemaDB("off")
    original_execute = db.execute

    def without_openrouter(statement):
        result = original_execute(statement)
        if "to_regclass" in str(statement):
            result._rows = [
                row for row in result._rows if not row[0].startswith("chat_openrouter_")
            ]
        elif "information_schema.columns" in str(statement):
            result._rows = [
                row for row in result._rows if not row[0].startswith("chat_openrouter_")
            ]
        return result

    db.execute = without_openrouter
    validate_chat_schema(
        db,
        Settings(environment="production", chat_openrouter_server_funded_enabled=False),
    )


def test_chat_schema_requires_qualification_metadata_columns():
    with pytest.raises(RuntimeError, match="required chat sandbox schema is missing"):
        validate_chat_schema(
            _ChatSchemaDB("off", include_qualification_columns=False),
            Settings(environment="staging", chat_openrouter_server_funded_enabled=True),
        )


def test_chat_schema_requires_typed_edit_preparation_columns():
    with pytest.raises(RuntimeError, match="required chat sandbox schema is missing"):
        validate_chat_schema(
            _ChatSchemaDB("off", include_edit_columns=False),
            Settings(environment="staging", chat_openrouter_server_funded_enabled=True),
        )


def test_chat_schema_requires_self_contained_share_snapshot_columns():
    with pytest.raises(RuntimeError, match="required chat sandbox schema is missing"):
        validate_chat_schema(
            _ChatSchemaDB("off", include_share_columns=False),
            Settings(environment="staging", chat_openrouter_server_funded_enabled=True),
        )


def test_chat_schema_requires_share_snapshot_array_constraint():
    with pytest.raises(RuntimeError, match="required chat sandbox schema is missing"):
        validate_chat_schema(
            _ChatSchemaDB("off", include_share_constraint=False),
            Settings(environment="staging", chat_openrouter_server_funded_enabled=True),
        )


def test_chat_schema_requires_blank_pool_accounting_columns():
    with pytest.raises(RuntimeError, match="required chat sandbox schema is missing"):
        validate_chat_schema(
            _ChatSchemaDB("off", include_pool_columns=False),
            Settings(environment="staging", chat_openrouter_server_funded_enabled=True),
        )


def test_chat_schema_requires_latency_telemetry_columns():
    with pytest.raises(RuntimeError, match="required chat sandbox schema is missing"):
        validate_chat_schema(
            _ChatSchemaDB("off", include_latency_columns=False),
            Settings(environment="staging", chat_openrouter_server_funded_enabled=True),
        )


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


@pytest.mark.parametrize(
    ("environment", "version", "features"),
    [
        (
            "staging",
            2,
            {
                "chat": True,
                "codex_add_evals": False,
                "codex_enrich_paper": False,
            },
        ),
        (
            "production",
            3,
            {
                "chat": False,
                "codex_add_evals": True,
                "codex_enrich_paper": True,
            },
        ),
    ],
)
def test_pre_bridge_versioned_manifest_remains_valid(
    tmp_path: Path, environment: str, version: int, features: dict[str, bool]
):
    release = make_bundle(tmp_path, chat=environment == "staging")
    manifest_path = release / "release.json"
    manifest = json.loads(manifest_path.read_text())
    manifest.pop("chat_runtime")
    manifest["feature_contract_version"] = version
    manifest["backend_features"] = features
    manifest["frontend_features"] = features
    manifest_path.write_text(json.dumps(manifest))
    (release / "frontend-dist" / "features.json").write_text(json.dumps(features))

    assert (
        validate_manifest(release, environment)["release_id"] == manifest["release_id"]
    )


def test_staging_manifest_requires_immutable_modal_image(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    manifest_path = release / "release.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["chat_runtime"]["modal_image_version"] = "pwc-chat-v1"
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="immutable Modal image ID"):
        validate_manifest(release, "staging")


def test_chat_descriptor_is_extracted_from_selected_source():
    source = Path(__file__).resolve().parents[2]
    descriptor = _chat_descriptor_from_source(source, "staging")
    assert descriptor["modal_image_version"] == MODAL_IMAGE_ID
    assert descriptor["worker_contract_version"] == "57"
    dormant = _chat_descriptor_from_source(source, "production")
    assert dormant is not None
    assert dormant["enabled"] is False
    assert dormant["new_chat_modal_percentage"] == 0
    assert dormant["system_prompt_sha256"] == descriptor["system_prompt_sha256"]
    production = _chat_descriptor_from_source(source, "production", chat_enabled=True)
    assert production["modal_image_version"] == PRODUCTION_MODAL_IMAGE_ID
    assert production["enabled"] is True
    assert (
        production["new_chat_modal_percentage"]
        == descriptor["new_chat_modal_percentage"]
    )
    assert production["system_prompt_sha256"] == descriptor["system_prompt_sha256"]


def test_disabled_production_manifest_uses_selected_source_descriptor():
    source = Path(__file__).resolve().parents[2]
    descriptor = _chat_descriptor_from_source(source, "production", chat_enabled=False)
    assert descriptor is not None

    manifest = build_manifest("a" * 40, "production", chat_descriptor=descriptor)

    assert manifest["chat_runtime"] == descriptor
    assert manifest["backend_features"]["chat"] is False


def test_production_chat_activation_builds_one_consistent_manifest(tmp_path: Path):
    release = make_bundle(tmp_path, chat=False)
    sha = "a" * 40
    descriptor = _chat_descriptor_from_source(
        Path(__file__).resolve().parents[2],
        "production",
        chat_enabled=True,
    )
    assert descriptor is not None
    descriptor["modal_image_version"] = "im-test-immutable"
    features = profile_features("production", production_chat_enabled=True)
    manifest = build_manifest(
        sha,
        "production",
        chat_descriptor=descriptor,
        production_chat_enabled=True,
    )
    (release / "release.json").write_text(json.dumps(manifest))
    (release / "frontend-dist" / "features.json").write_text(json.dumps(features))

    validated = validate_manifest(release, "production")

    assert validated["backend_features"] == features
    assert validated["frontend_features"] == features
    assert validated["chat_runtime"]["enabled"] is True
    assert validate_local_bundle(release, validated["frontend_features"]) == []


def test_fully_configured_production_chat_runtime_can_start(tmp_path: Path):
    release = make_bundle(tmp_path, chat=False)
    sha = "a" * 40
    descriptor = _chat_descriptor_from_source(
        Path(__file__).resolve().parents[2],
        "production",
        chat_enabled=True,
    )
    assert descriptor is not None
    descriptor["modal_image_version"] = "im-test-immutable"
    features = profile_features("production", production_chat_enabled=True)
    (release / "release.json").write_text(
        json.dumps(
            build_manifest(
                sha,
                "production",
                chat_descriptor=descriptor,
                production_chat_enabled=True,
            )
        )
    )
    (release / "frontend-dist" / "features.json").write_text(json.dumps(features))
    settings = deployed_settings(tmp_path, release, "production")
    settings.chat_enabled = True
    settings.chat_public_admission_enabled = True
    settings.chat_sandbox_admission_enabled = True
    settings.chat_max_concurrency = 2
    settings.chat_blank_pool_enabled = True
    settings.chat_persistent_worker_enabled = True
    settings.chat_sandbox_spend_enforcement_enabled = True
    settings.chat_sandbox_modal_environment = "pwc-chat-production"
    settings.chat_sandbox_modal_workspace = "nielsrogge"
    settings.chat_sandbox_modal_owner_username = "nielsrogge"
    settings.chat_sandbox_budget_attestation = (
        "modal-workspace-nielsrogge-250-production-starter-v1"
    )
    settings.chat_sandbox_slack_webhook_url = (
        "https://hooks.slack.test/services/production"
    )
    settings.chat_sandbox_alert_fallback_webhook_url = (
        "https://alerts.test/production-fallback"
    )
    settings.chat_sandbox_runbook_url = "https://example.test/production-runbook"
    settings.chat_sandbox_operator_usernames = "nielsr"
    settings.chat_operational_alerts_enabled = True
    settings.chat_gateway_url = (
        "https://chat-gateway.paperswithcode.co/api/internal/chat-gateway"
    )
    settings.chat_title_generation_enabled = True
    settings.chat_title_hf_token = "test-only-production-title-token"
    settings.chat_title_bill_to = "huggingface"
    settings.chat_title_credential_owner = "nielsr"
    settings.chat_title_credential_environment = "production"

    assert validate_runtime(settings) == features
    settings.chat_operational_alerts_enabled = False
    with pytest.raises(RuntimeError, match="operational alerts"):
        validate_runtime(settings)


def test_production_chat_activation_requires_enabled_operational_monitor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(deploy_cli, "CONFIG_ROOT", tmp_path)
    (tmp_path / "production.env").write_text("PWC_CHAT_ENABLED=true\n")
    observed = []

    def fake_run(command, **_kwargs):
        observed.append(command)
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(deploy_cli.subprocess, "run", fake_run)
    with pytest.raises(deploy_cli.DeployError, match="operational alert"):
        require_production_chat_monitor("production")
    assert observed == [
        ["systemctl", "is-enabled", "--quiet", "pwc-chat-alert-monitor.timer"]
    ]

    observed.clear()
    (tmp_path / "production.env").write_text("PWC_CHAT_ENABLED=false\n")
    require_production_chat_monitor("production")
    assert observed == []


def test_production_chat_activation_requires_protected_environment_switch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config_root = tmp_path / "config"
    config_root.mkdir()
    monkeypatch.setattr(deploy_cli, "CONFIG_ROOT", config_root)

    assert _configured_chat_enabled("production") is False
    (config_root / "production.env").write_text("PWC_CHAT_ENABLED=false\n")
    assert _configured_chat_enabled("production") is False
    (config_root / "production.env").write_text("PWC_CHAT_ENABLED='true'\n")
    assert _configured_chat_enabled("production") is True


def test_production_chat_activation_rejects_invalid_protected_switch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config_root = tmp_path / "config"
    config_root.mkdir()
    (config_root / "production.env").write_text("PWC_CHAT_ENABLED=maybe\n")
    monkeypatch.setattr(deploy_cli, "CONFIG_ROOT", config_root)

    with pytest.raises(deploy_cli.DeployError, match="true or false"):
        _configured_chat_enabled("production")


def test_staging_runtime_rejects_public_gateway_origin(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.chat_gateway_url = (
        "https://staging.paperswithcode.co/api/internal/chat-gateway"
    )
    with pytest.raises(RuntimeError, match="dedicated HTTPS origin"):
        validate_runtime(settings)


def test_legacy_release_manifest_remains_a_valid_rollback_target(tmp_path: Path):
    release = make_bundle(tmp_path, chat=False)
    manifest_path = release / "release.json"
    manifest = json.loads(manifest_path.read_text())
    manifest.pop("feature_contract_version")
    manifest.pop("chat_runtime")
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
    manifest.pop("chat_runtime")
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


def test_modal_bridge_manifest_remains_a_valid_rollback_target(tmp_path: Path):
    release = make_bundle(tmp_path, chat=False)
    manifest_path = release / "release.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["chat_runtime"] = {
        "enabled": False,
        "new_chat_modal_percentage": 0,
        "default_backend": "local_mcp",
        "modal_image_version": "",
        "pwc_cli_version": "",
        "worker_contract_version": "",
        "system_prompt_sha256": "",
    }
    manifest_path.write_text(json.dumps(manifest))

    assert validate_manifest(release, "production")["git_sha"] == "a" * 40


def test_disabled_production_runtime_remains_valid_after_worker_upgrade(
    tmp_path: Path,
):
    release = make_bundle(tmp_path, chat=False)
    manifest_path = release / "release.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["chat_runtime"].update(
        {
            "modal_image_version": "im-previous-production-image",
            "worker_contract_version": "54",
            "system_prompt_sha256": "0" * 64,
        }
    )
    manifest_path.write_text(json.dumps(manifest))

    assert validate_manifest(release, "production")["git_sha"] == "a" * 40


@pytest.mark.parametrize(
    ("field", "value"),
    [("enabled", True), ("new_chat_modal_percentage", 1)],
)
def test_disabled_production_runtime_rejects_active_chat(
    tmp_path: Path, field: str, value: object
):
    release = make_bundle(tmp_path, chat=False)
    manifest_path = release / "release.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["chat_runtime"][field] = value
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(ValueError, match="active chat runtime"):
        validate_manifest(release, "production")


def test_staging_profile_inherits_admin_catalog_actions():
    assert profile_features("staging") == {
        "chat": True,
        "codex_add_evals": True,
        "codex_enrich_paper": True,
    }


def test_version_three_staging_release_remains_valid_after_profile_expansion(
    tmp_path: Path,
):
    release = make_bundle(tmp_path, chat=True)
    manifest_path = release / "release.json"
    manifest = json.loads(manifest_path.read_text())
    previous_features = {
        "chat": True,
        "codex_add_evals": False,
        "codex_enrich_paper": False,
    }
    manifest["feature_contract_version"] = 3
    manifest["backend_features"] = previous_features
    manifest["frontend_features"] = previous_features
    manifest_path.write_text(json.dumps(manifest))
    (release / "frontend-dist" / "features.json").write_text(
        json.dumps(previous_features)
    )

    assert validate_manifest(release, "staging")["feature_contract_version"] == 3


def test_production_profile_enables_admin_catalog_actions():
    assert profile_features("production") == {
        "chat": False,
        "codex_add_evals": True,
        "codex_enrich_paper": True,
    }


@pytest.mark.parametrize(
    ("environment", "expected"),
    [
        (
            "production",
            {
                "VITE_AUTH_URL": "",
                "VITE_CHAT_ENABLED": "0",
                "VITE_CHAT_LIVE": "0",
                "VITE_CODEX_ADD_EVALS_ENABLED": "1",
                "VITE_CODEX_ENRICH_PAPER_ENABLED": "1",
            },
        ),
        (
            "staging",
            {
                "VITE_AUTH_URL": "https://paperswithcode.co",
                "VITE_CHAT_ENABLED": "1",
                "VITE_CHAT_LIVE": "1",
                "VITE_CODEX_ADD_EVALS_ENABLED": "1",
                "VITE_CODEX_ENRICH_PAPER_ENABLED": "1",
            },
        ),
    ],
)
def test_frontend_build_flags_follow_release_profile(environment: str, expected: dict):
    assert deploy_cli.frontend_feature_environment(environment) == expected


def test_production_activation_frontend_flags_are_enabled_together():
    assert deploy_cli.frontend_feature_environment(
        "production", production_chat_enabled=True
    ) == {
        "VITE_AUTH_URL": "",
        "VITE_CHAT_ENABLED": "1",
        "VITE_CHAT_LIVE": "1",
        "VITE_CODEX_ADD_EVALS_ENABLED": "1",
        "VITE_CODEX_ENRICH_PAPER_ENABLED": "1",
    }


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_codex_jobs_require_all_credentials(tmp_path: Path, environment: str):
    release = make_bundle(tmp_path, chat=environment == "staging")
    settings = deployed_settings(tmp_path, release, environment)
    settings.codex_jobs_token = ""
    with pytest.raises(RuntimeError, match="Codex jobs require"):
        validate_runtime(settings)


def test_backend_launcher_uses_release_specific_feature_flags(
    tmp_path: Path, monkeypatch
):
    release = make_bundle(tmp_path, chat=False)
    monkeypatch.setenv("PWC_FRONTEND_DIST_DIR", str(release / "frontend-dist"))
    runtime_data_dir = tmp_path / "runtime-data"
    monkeypatch.setenv("PWC_RUNTIME_DATA_DIR", str(runtime_data_dir))
    monkeypatch.delenv("HF_HOME", raising=False)
    monkeypatch.delenv("HF_XET_CACHE", raising=False)
    run_backend.configure_release_environment(release)
    assert os.environ["PWC_CODEX_JOBS_ENABLED"] == "true"
    assert os.environ["PWC_CODEX_ADD_EVALS_ENABLED"] == "true"
    assert os.environ["PWC_CODEX_ENRICH_PAPER_ENABLED"] == "true"
    assert os.environ["HF_HOME"] == str(runtime_data_dir / "hf-cache")
    assert os.environ["HF_XET_CACHE"] == str(runtime_data_dir / "hf-cache" / "xet")


def test_backend_launcher_preserves_explicit_hugging_face_cache(
    tmp_path: Path, monkeypatch
):
    release = make_bundle(tmp_path, chat=False)
    monkeypatch.setenv("PWC_FRONTEND_DIST_DIR", str(release / "frontend-dist"))
    monkeypatch.setenv("PWC_RUNTIME_DATA_DIR", str(tmp_path / "runtime-data"))
    monkeypatch.setenv("HF_HOME", "/custom/hf")
    monkeypatch.setenv("HF_XET_CACHE", "/custom/xet")

    run_backend.configure_release_environment(release)

    assert os.environ["HF_HOME"] == "/custom/hf"
    assert os.environ["HF_XET_CACHE"] == "/custom/xet"


def test_backend_launcher_disables_features_for_legacy_rollback(
    tmp_path: Path, monkeypatch
):
    release = make_bundle(tmp_path, chat=False)
    manifest_path = release / "release.json"
    manifest = json.loads(manifest_path.read_text())
    manifest.pop("feature_contract_version")
    manifest.pop("chat_runtime")
    manifest["backend_features"] = {"chat": False}
    manifest["frontend_features"] = {"chat": False}
    manifest_path.write_text(json.dumps(manifest))
    (release / "frontend-dist" / "features.json").write_text(
        json.dumps({"chat": False})
    )
    monkeypatch.setenv("PWC_FRONTEND_DIST_DIR", str(release / "frontend-dist"))
    monkeypatch.setenv("PWC_RUNTIME_DATA_DIR", str(tmp_path / "runtime-data"))
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


def test_staging_smoke_accepts_versioned_feature_manifest(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    assert validate_local_bundle(release, True) == []


def _seo_sitemap_index() -> bytes:
    names = (
        "papers-2026-1.xml",
        "tasks.xml",
        "methods.xml",
        "benchmarks.xml",
        "conferences.xml",
        "organizations.xml",
        "authors-0.xml",
    )
    return (
        "<sitemapindex>"
        + "".join(
            f"<sitemap><loc>https://paperswithcode.co/sitemaps/{name}</loc></sitemap>"
            for name in names
        )
        + "</sitemapindex>"
    ).encode()


def _entity_sitemap_response(url: str):
    paths = {
        "tasks.xml": "/tasks/example",
        "methods.xml": "/methods/example",
        "benchmarks.xml": "/benchmark/example",
        "conferences.xml": "/conferences/example",
        "organizations.xml": "/example-org",
        "authors-0.xml": "/authors/1",
    }
    path = paths.get(url.rsplit("/", 1)[-1])
    if path is None:
        return None
    location = f"https://paperswithcode.co{path}"
    return (
        200,
        {"Content-Type": "application/xml"},
        f"<urlset><url><loc>{location}</loc></url></urlset>".encode(),
    )


def _entity_page_response(url: str):
    paths = (
        "/tasks/example",
        "/methods/example",
        "/benchmark/example",
        "/conferences/example",
        "/example-org",
        "/authors/1",
    )
    path = next((candidate for candidate in paths if url.endswith(candidate)), None)
    if path is None:
        return None
    canonical = f"https://paperswithcode.co{path}"
    return (
        200,
        {},
        (
            f'<link rel="canonical" href="{canonical}">'
            '<main data-pwc-initial-document="discovery"><h1>Entity</h1>'
            '<a href="/paper/1">Paper</a></main>'
        ).encode(),
    )


def _markdown_page_response(url: str, headers: dict[str, str] | None):
    if not headers or headers.get("Accept") != "text/markdown":
        return None
    paths = (
        "/",
        "/paper/2607.24653",
        "/tasks/image-classification",
        "/papers/recent",
    )
    path = next((candidate for candidate in paths if url.endswith(candidate)), None)
    if path is None:
        return None
    canonical = f"https://paperswithcode.co{path}"
    return (
        200,
        {
            "Content-Type": "text/markdown; charset=utf-8",
            "Vary": "Accept",
            "Link": f'<{canonical}>; rel="canonical"',
        },
        (
            "---\n"
            f'title: "Example"\ncanonical: "{canonical}"\n'
            'description: "Example"\ntype: "page"\n---\n\n# Example\n'
        ).encode(),
    )


def test_staging_candidate_smoke_leaves_spa_to_nginx(monkeypatch):
    requested: list[str] = []

    def request(
        url: str,
        *,
        allow_redirects: bool = True,
        headers: dict[str, str] | None = None,
    ):
        requested.append(url)
        if response := _markdown_page_response(url, headers):
            return response
        if response := _entity_sitemap_response(url):
            return response
        if response := _entity_page_response(url):
            return response
        if url.endswith("/robots.txt"):
            return 200, {"Content-Type": "text/plain"}, b"User-agent: *\nDisallow: /\n"
        if url.rstrip("/").endswith(":8100"):
            links = b"".join(
                f'<a href="/paper/{i}">Paper</a>'.encode() for i in range(20)
            ) + b"".join(f'<a href="/tasks/{i}">Task</a>'.encode() for i in range(5))
            return (
                200,
                {},
                b'<main data-pwc-initial-document="discovery">' + links + b"</main>",
            )
        if url.endswith("/health"):
            return 200, {}, b'{"release_id":"release-staging"}'
        if url.endswith("/api/v1/papers/1"):
            return 404, {}, b'{"detail":"Paper not found"}'
        if url.endswith("/api/v1/chat/sessions"):
            return 401, {}, b""
        if url.endswith("/paper/2607.24653"):
            return (
                200,
                {"Link": "<https://paperswithcode.co/paper/2607.24653>; rel=canonical"},
                b'<main data-pwc-initial-document="paper"><h1>Kimi K3: Open Frontier Intelligence</h1><h2 id="abstract-heading"></h2><meta name="citation_arxiv_id" content="2607.24653"><script type="application/ld+json"></script></main>',
            )
        if url.endswith("/paper/9999.99999"):
            return 404, {}, b""
        if url.endswith("/papers/2607.24653"):
            return 301, {"Location": "/paper/2607.24653"}, b""
        if url.endswith("/sitemap.xml"):
            return (
                200,
                {"Content-Type": "application/xml"},
                _seo_sitemap_index(),
            )
        if url.endswith("/sitemaps/papers-2026-1.xml"):
            return 200, {"Content-Type": "application/xml"}, b"<urlset/>"
        if url.endswith("/papers/recent"):
            return 200, {}, b'<a href="/paper/2607.24653">Kimi K3</a>'
        raise AssertionError(f"unexpected candidate request: {url}")

    monkeypatch.setattr(smoke_test, "request", request)

    assert (
        smoke_test.run_http_smoke(
            "staging",
            "http://127.0.0.1:8100",
            expected_release="release-staging",
            candidate=True,
        )
        == []
    )
    assert all(not url.endswith("/chat") for url in requested)


def test_staging_candidate_smoke_rejects_numeric_paper_server_error(monkeypatch):
    def request(
        url: str,
        *,
        allow_redirects: bool = True,
        headers: dict[str, str] | None = None,
    ):
        if response := _markdown_page_response(url, headers):
            return response
        if response := _entity_sitemap_response(url):
            return response
        if response := _entity_page_response(url):
            return response
        if url.endswith("/robots.txt"):
            return 200, {"Content-Type": "text/plain"}, b"User-agent: *\nDisallow: /\n"
        if url.rstrip("/").endswith(":8100"):
            links = b"".join(
                f'<a href="/paper/{i}">Paper</a>'.encode() for i in range(20)
            ) + b"".join(f'<a href="/tasks/{i}">Task</a>'.encode() for i in range(5))
            return (
                200,
                {},
                b'<main data-pwc-initial-document="discovery">' + links + b"</main>",
            )
        if url.endswith("/health"):
            return 200, {}, b'{"release_id":"release-staging"}'
        if url.endswith("/api/v1/papers/1"):
            return 500, {}, b"Internal Server Error"
        if url.endswith("/api/v1/chat/sessions"):
            return 401, {}, b""
        if url.endswith("/paper/2607.24653"):
            return (
                200,
                {"Link": "<https://paperswithcode.co/paper/2607.24653>; rel=canonical"},
                b'<main data-pwc-initial-document="paper"><h1>Kimi K3: Open Frontier Intelligence</h1><h2 id="abstract-heading"></h2><meta name="citation_arxiv_id" content="2607.24653"><script type="application/ld+json"></script></main>',
            )
        if url.endswith("/paper/9999.99999"):
            return 404, {}, b""
        if url.endswith("/papers/2607.24653"):
            return 301, {"Location": "/paper/2607.24653"}, b""
        if url.endswith("/sitemap.xml"):
            return (
                200,
                {"Content-Type": "application/xml"},
                _seo_sitemap_index(),
            )
        if url.endswith("/sitemaps/papers-2026-1.xml"):
            return 200, {"Content-Type": "application/xml"}, b"<urlset/>"
        if url.endswith("/papers/recent"):
            return 200, {}, b'<a href="/paper/2607.24653">Kimi K3</a>'
        raise AssertionError(f"unexpected candidate request: {url}")

    monkeypatch.setattr(smoke_test, "request", request)

    assert smoke_test.run_http_smoke(
        "staging",
        "http://127.0.0.1:8100",
        expected_release="release-staging",
        candidate=True,
    ) == ["numeric paper API returned 500"]


def test_seo_smoke_treats_http_headers_case_insensitively(monkeypatch):
    requested: list[str] = []

    def request(
        url: str,
        *,
        allow_redirects: bool = True,
        headers: dict[str, str] | None = None,
    ):
        requested.append(url)
        if response := _markdown_page_response(url, headers):
            return response
        if response := _entity_sitemap_response(url):
            return response
        if response := _entity_page_response(url):
            return response
        if url.endswith("/robots.txt"):
            return (
                200,
                {"content-type": "text/plain"},
                b"User-agent: *\nAllow: /\nSitemap: https://paperswithcode.co/sitemap.xml\n",
            )
        if url.rstrip("/").endswith(":8100"):
            links = b"".join(
                f'<a href="/paper/{i}">Paper</a>'.encode() for i in range(20)
            ) + b"".join(f'<a href="/tasks/{i}">Task</a>'.encode() for i in range(5))
            return (
                200,
                {},
                b'<main data-pwc-initial-document="discovery">' + links + b"</main>",
            )
        if url.endswith("/paper/2607.24653"):
            return (
                200,
                {"link": "<https://paperswithcode.co/paper/2607.24653>; rel=canonical"},
                b'<main data-pwc-initial-document="paper"><h1>Kimi K3: Open Frontier Intelligence</h1><h2 id="abstract-heading"></h2><meta name="citation_arxiv_id" content="2607.24653"><script type="application/ld+json"></script></main>',
            )
        if url.endswith("/paper/9999.99999"):
            return 404, {}, b""
        if url.endswith("/papers/2607.24653"):
            return 301, {"location": "/paper/2607.24653"}, b""
        if url.endswith("/sitemap.xml"):
            return (
                200,
                {"content-type": "application/xml"},
                _seo_sitemap_index(),
            )
        if url.endswith("/sitemaps/papers-2026-1.xml"):
            return 200, {"content-type": "application/xml"}, b"<urlset/>"
        if url.endswith("/papers/recent"):
            return 200, {}, b'<a href="/paper/2607.24653">Kimi K3</a>'
        raise AssertionError(url)

    monkeypatch.setattr(smoke_test, "request", request)
    assert smoke_test.run_seo_http_smoke("http://127.0.0.1:8100") == []
    assert "http://127.0.0.1:8100/sitemaps/papers-2026-1.xml" in requested
    assert "https://example.test/sitemaps/papers-2026-1.xml" not in requested


def test_nginx_cross_environment_references_are_rejected():
    failures = validate_nginx(
        "root /srv/paperswithcode/environments/production/current/frontend-dist;"
        " upstream pwc_staging_backend { server 127.0.0.1:8001; } location / { }",
        "root /srv/paperswithcode/environments/staging/current/frontend-dist;"
        " location = /_staging_access_check { internal; "
        "proxy_pass http://pwc_staging_backend/api/v1/auth/staging-check; } "
        "location / { }"
        " server_name chat-gateway-staging.paperswithcode.co;"
        " client_max_body_size 512k;"
        " location = /api/internal/chat-gateway/catalog { }"
        " location = /api/internal/chat-gateway/session-store { }"
        " location = /api/internal/chat-gateway/web-fetch { }"
        " location = /api/internal/chat-gateway/v1/messages { }",
    )
    assert "production references staging backend" in failures


def test_staging_nginx_requires_bearer_authenticated_curation_callback_route():
    repository = Path(__file__).resolve().parents[2]
    production = (repository / "deploy/nginx/paperswithcode.co.conf").read_text()
    staging = (repository / "deploy/nginx/staging.paperswithcode.co.conf").read_text()

    assert validate_nginx(production, staging) == []

    failures = validate_nginx(
        production,
        staging.replace(CURATION_CALLBACK_LOCATION, "location /missing-callback"),
    )
    assert "staging job-token callback route is missing" in failures


def test_staging_nginx_requires_an_unbuffered_chat_stream_route():
    repository = Path(__file__).resolve().parents[2]
    production = (repository / "deploy/nginx/paperswithcode.co.conf").read_text()
    staging = (repository / "deploy/nginx/staging.paperswithcode.co.conf").read_text()

    assert validate_nginx(production, staging) == []
    for directive in (
        "proxy_buffering off;",
        "proxy_cache off;",
        "gzip off;",
        "proxy_read_timeout 190s;",
    ):
        failures = validate_nginx(production, staging.replace(directive, "", 1))
        assert f"staging chat stream route misses: {directive}" in failures


def test_nginx_requires_isolated_production_and_staging_gateways():
    repository = Path(__file__).resolve().parents[2]
    production = (repository / "deploy/nginx/paperswithcode.co.conf").read_text()
    staging = (repository / "deploy/nginx/staging.paperswithcode.co.conf").read_text()

    assert validate_nginx(production, staging) == []
    failures = validate_nginx(
        production.replace(
            "server_name chat-gateway.paperswithcode.co;",
            "server_name missing-production-gateway.paperswithcode.co;",
        ),
        staging,
    )
    assert "production chat gateway hostname is missing" in failures

    failures = validate_nginx(
        production,
        staging.replace(
            "location = /api/internal/chat-gateway/catalog {\n"
            "        limit_except POST { deny all; }\n"
            "        proxy_pass http://pwc_staging_backend;",
            "location = /api/internal/chat-gateway/catalog {\n"
            "        limit_except POST { deny all; }\n"
            "        proxy_pass http://missing_staging_backend;",
        ),
    )
    assert "staging chat gateway catalog misses pwc_staging_backend" in failures


def test_nginx_requires_backend_routes_for_seo_surfaces():
    repository = Path(__file__).resolve().parents[2]
    production = (repository / "deploy/nginx/paperswithcode.co.conf").read_text()
    staging = (repository / "deploy/nginx/staging.paperswithcode.co.conf").read_text()

    assert validate_nginx(production, staging) == []
    failures = validate_nginx(
        production.replace(SEO_LOCATIONS[0], "location = /missing-sitemap"),
        staging,
    )
    assert "production SEO route is missing" in " ".join(failures)


def test_nginx_public_page_proxies_preserve_accept_and_origin_headers():
    repository = Path(__file__).resolve().parents[2]
    production = (repository / "deploy/nginx/paperswithcode.co.conf").read_text()
    staging = (repository / "deploy/nginx/staging.paperswithcode.co.conf").read_text()

    assert validate_nginx(production, staging) == []
    assert "proxy_set_header Accept" not in production
    assert "proxy_set_header Accept" not in staging
    assert "proxy_hide_header Content-Type" not in production + staging
    assert "proxy_hide_header Vary" not in production + staging
    assert "proxy_hide_header Link" not in production + staging
    assert "proxy_hide_header Cache-Control" not in production + staging


def test_spa_shell_hides_initial_documents_before_javascript_paint():
    repository = Path(__file__).resolve().parents[2]
    shell = (repository / "frontend/index.html").read_text()

    marker = 'document.documentElement.classList.add("pwc-js")'
    hiding_rule = (
        ".pwc-js [data-pwc-initial-document], "
        ".pwc-js .initial-discovery-footer { display: none; }"
    )
    assert marker in shell
    assert hiding_rule in shell
    assert shell.index(marker) < shell.index("<style>")
    assert 'data-pwc-initial-document="paper"' not in shell
    assert '<div id="root"></div>' in shell


def test_nginx_share_capability_bypasses_only_narrow_public_get_surfaces():
    repository = Path(__file__).resolve().parents[2]
    production = (repository / "deploy/nginx/paperswithcode.co.conf").read_text()
    staging = (repository / "deploy/nginx/staging.paperswithcode.co.conf").read_text()

    assert validate_nginx(production, staging) == []
    for config in (production, staging):
        page = location_block(config, SHARE_PAGE_LOCATION)
        api = location_block(config, SHARE_API_LOCATION)
        assert "auth_request" not in page + api
        assert "limit_except GET" in page
        assert "limit_except GET" in api
        assert 'X-Robots-Tag "noindex, nofollow" always' in page
        assert 'Cache-Control "no-store"' in page

    assets = staging.split("location ^~ /assets/", 1)[1].split("}", 1)[0]
    auth_me = staging.split("location = /api/v1/auth/me", 1)[1].split("}", 1)[0]
    owner_api = staging.split("location /api/", 1)[1].split("}", 1)[0]
    catch_all = staging.split("location / {", 1)[1].split("}", 1)[0]
    assert "auth_request" not in assets + auth_me
    assert "auth_request /_staging_access_check;" in owner_api
    assert "auth_request /_staging_access_check;" in catch_all


def test_staging_access_request_surface_is_public_and_narrow():
    repository = Path(__file__).resolve().parents[2]
    production = (repository / "deploy/nginx/paperswithcode.co.conf").read_text()
    staging = (repository / "deploy/nginx/staging.paperswithcode.co.conf").read_text()

    assert validate_nginx(production, staging) == []
    page = location_block(staging, "location = /request-access")
    api = location_block(staging, "location = /api/v1/staging-access-request")
    forbidden = location_block(staging, "location @staging_forbidden")

    assert "auth_request" not in page + api
    assert "try_files /index.html =404;" in page
    assert 'X-Robots-Tag "noindex, nofollow" always' in page
    assert "limit_except POST" in api
    assert "proxy_pass http://pwc_staging_backend;" in api
    assert "return 302 /request-access;" in forbidden


def test_chat_share_migration_is_environment_owned_and_idempotent():
    repository = Path(__file__).resolve().parents[2]
    migration = (
        repository / "backend/database/migrations/add_chat_shares.sql"
    ).read_text()

    assert "current_schema() NOT IN ('staging', 'public')" in migration
    assert "CREATE TABLE IF NOT EXISTS chat_shares" in migration
    assert "snapshot_version SMALLINT NOT NULL DEFAULT 1" in migration
    assert "messages JSONB NOT NULL" in migration
    assert "chat_shares_messages_array_check" in migration
    assert "REFERENCES chat_messages" not in migration
    assert migration.count("ON DELETE CASCADE") >= 1
    assert "ADD COLUMN IF NOT EXISTS finish_reason VARCHAR(64)" in migration
    assert "ALTER TABLE chat_shares OWNER TO pwc_staging_owner" in migration
    assert "ALTER TABLE chat_shares OWNER TO paperswithcode_user" in migration
    assert "DROP TABLE IF EXISTS chat_share_messages" in migration
    assert (
        "EXECUTE\n            "
        "'SELECT EXISTS (SELECT 1 FROM chat_share_messages LIMIT 1)'" in migration
    )
    assert "AND EXISTS (SELECT FROM chat_share_messages LIMIT 1)" not in migration
    assert "TO pwc_staging;" in migration
    assert "TO paperswithcode_user;" in migration
    assert "FROM paperswithcode_user;" in migration


def test_staging_role_defaults_to_read_only_outside_application_pool():
    repository = Path(__file__).resolve().parents[2]
    migration = (
        repository / "backend/database/migrations/consolidate_staging_schema.sql"
    ).read_text()
    connection = (repository / "backend/database/connection.py").read_text()
    audit = (repository / "deploy/audit_staging_db.py").read_text()

    assert "ALTER ROLE pwc_staging SET default_transaction_read_only = on" in migration
    assert "ALTER ROLE pwc_staging RESET default_transaction_read_only" not in migration
    assert 'options += " -c default_transaction_read_only=off"' in connection
    assert 'read_only_default != "on"' in audit


def test_chat_edit_preparation_migration_is_environment_scoped_and_typed():
    repository = Path(__file__).resolve().parents[2]
    migration = (
        repository / "backend/database/migrations/add_chat_edit_preparation_state.sql"
    ).read_text()

    assert "current_schema() NOT IN ('staging', 'public')" in migration
    assert "prepared_fork_sdk_session_id UUID" in migration
    assert "prepared_fork_sdk_project_key TEXT" in migration
    assert "chat_messages_prepared_fork_pair_check" in migration


def test_common_chat_migrations_support_isolated_production_schema():
    repository = Path(__file__).resolve().parents[2]
    migrations = (
        "add_chat_sessions.sql",
        "add_chat_sandbox_runtime.sql",
        "add_chat_turn_latency.sql",
        "add_chat_sandbox_pool.sql",
        "add_chat_active_cost.sql",
        "add_chat_user_billing.sql",
        "add_chat_qualification_metadata.sql",
        "add_chat_sandbox_spend_cap.sql",
        "add_chat_shares.sql",
        "add_chat_edit_preparation_state.sql",
        "add_chat_paper_mentions.sql",
        "add_chat_title_budget.sql",
    )

    for name in migrations:
        migration = (repository / "backend/database/migrations" / name).read_text()
        assert "current_schema() NOT IN ('staging', 'public')" in migration

    sessions = (
        repository / "backend/database/migrations/add_chat_sessions.sql"
    ).read_text()
    assert "ALTER TABLE chat_sessions OWNER TO pwc_staging_owner" in sessions
    assert "ALTER TABLE chat_sessions OWNER TO paperswithcode_user" in sessions
    assert "FROM paperswithcode_user" in sessions
    assert "FROM pwc_staging" in sessions

    billing = (
        repository / "backend/database/migrations/add_chat_user_billing.sql"
    ).read_text()
    assert "provider_mode VARCHAR(32)" in billing
    assert "provider_credential_revision UUID" in billing
    assert "provider_error_code VARCHAR(64)" in billing


def test_chat_archiving_migration_is_additive_and_idempotent():
    repository = Path(__file__).resolve().parents[2]
    migration = (
        repository / "backend/database/migrations/add_chat_session_archiving.sql"
    ).read_text()

    assert "ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ" in migration
    assert "WHERE archived_at IS NULL" in migration
    assert "DROP " not in migration


def test_chat_title_budget_migration_is_environment_isolated_and_idempotent():
    repository = Path(__file__).resolve().parents[2]
    migration = (
        repository / "backend/database/migrations/add_chat_title_budget.sql"
    ).read_text()

    assert "current_schema() NOT IN ('staging', 'public')" in migration
    assert "CREATE TABLE IF NOT EXISTS chat_title_budget_states" in migration
    assert "UNIQUE (environment, billing_cycle)" in migration
    assert "CREATE TABLE IF NOT EXISTS chat_title_provider_calls" in migration
    assert "CREATE TABLE IF NOT EXISTS chat_title_budget_events" in migration
    assert (
        "ALTER TABLE chat_title_budget_states OWNER TO pwc_staging_owner" in migration
    )
    assert (
        "ALTER TABLE chat_title_budget_states OWNER TO paperswithcode_user" in migration
    )
    assert "FROM paperswithcode_user" in migration
    assert "FROM pwc_staging" in migration


def test_atomic_symlink_replaces_pointer(tmp_path: Path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    link = tmp_path / "current"
    atomic_symlink(first, link)
    atomic_symlink(second, link)
    assert link.resolve() == second


def test_activation_rollback_restores_runtime_before_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    environment_root = tmp_path / "environments"
    root = environment_root / "staging"
    failed = tmp_path / "failed"
    previous = tmp_path / "previous"
    failed.mkdir()
    previous.mkdir()
    root.mkdir(parents=True)
    atomic_symlink(failed, root / "current")
    atomic_symlink(previous, root / "previous")
    events: list[object] = []

    monkeypatch.setattr(deploy_cli, "ENVIRONMENTS_ROOT", environment_root)
    monkeypatch.setattr(
        deploy_cli,
        "restore_runtime",
        lambda lock: events.append(("restore", lock)),
    )
    monkeypatch.setattr(
        deploy_cli, "run", lambda command, **_kwargs: events.append(command)
    )
    monkeypatch.setattr(
        deploy_cli,
        "log_event",
        lambda *_args, **_kwargs: events.append("logged"),
    )
    monkeypatch.setattr(
        deploy_cli,
        "validate_manifest",
        lambda *_args, **_kwargs: {"release_id": "previous"},
    )
    monkeypatch.setattr(deploy_cli, "wait_for_release", lambda *_args: True)
    monkeypatch.setattr(deploy_cli, "smoke_public", lambda *_args: None)

    deploy_cli.rollback_after_failed_activation(
        "staging", failed, previous_runtime_lock="old-lock"
    )

    assert (root / "current").resolve() == previous
    assert events[0] == ("restore", "old-lock")
    assert events[1] == [
        "systemctl",
        "restart",
        "paperswithcode-backend@staging.service",
    ]


def test_manual_rollback_syncs_target_runtime_before_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    environment_root = tmp_path / "environments"
    root = environment_root / "staging"
    current = tmp_path / "current"
    previous = tmp_path / "previous"
    current.mkdir()
    previous.mkdir()
    root.mkdir(parents=True)
    atomic_symlink(current, root / "current")
    atomic_symlink(previous, root / "previous")
    events: list[object] = []

    monkeypatch.setattr(deploy_cli, "ENVIRONMENTS_ROOT", environment_root)
    monkeypatch.setattr(deploy_cli, "require_root", lambda: None)
    monkeypatch.setattr(
        deploy_cli,
        "validate_manifest",
        lambda release, *_args: {"release_id": release.name},
    )
    monkeypatch.setattr(
        deploy_cli,
        "sync_runtime",
        lambda release: events.append(("sync", release)) or True,
    )
    monkeypatch.setattr(
        deploy_cli, "run", lambda command, **_kwargs: events.append(command)
    )
    monkeypatch.setattr(
        deploy_cli,
        "_read_json",
        lambda *_args, **_kwargs: {"release_id": "previous"},
    )
    monkeypatch.setattr(deploy_cli, "log_event", lambda *_args, **_kwargs: None)

    assert deploy_cli.rollback(Namespace(environment="staging", confirm="")) == 0
    assert events[:2] == [
        ("sync", previous),
        [
            "systemctl",
            "restart",
            "paperswithcode-backend@staging.service",
        ],
    ]


def test_runtime_sync_failure_restores_previous_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    events: list[object] = []

    def fail_sync(_release):
        events.append("sync")
        raise OSError("partial runtime mutation")

    monkeypatch.setattr(deploy_cli, "sync_runtime", fail_sync)
    monkeypatch.setattr(
        deploy_cli,
        "restore_runtime",
        lambda lock: events.append(("restore", lock)),
    )

    with pytest.raises(OSError, match="partial runtime"):
        deploy_cli.sync_runtime_with_recovery(tmp_path, "old-lock")

    assert events == ["sync", ("restore", "old-lock")]


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


def test_deploy_parser_accepts_environment_refresh():
    args = parser_for("pwc-deploy").parse_args(
        ["staging", "abc123", "--refresh-environment"]
    )

    assert args.refresh_environment


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


def test_qualified_staging_capacity_keeps_one_warm_sandbox():
    assert configure_host_env.staging_chat_capacity_values() == {
        "PWC_CHAT_MAX_CONCURRENCY": "2",
        "PWC_CHAT_SANDBOX_TOTAL_LIVE_CAP": "3",
        "PWC_CHAT_BLANK_POOL_MIN": "1",
        "PWC_CHAT_BLANK_POOL_MAX": "1",
        "PWC_CHAT_SANDBOX_CPU": "0.5",
        "PWC_CHAT_SANDBOX_CPU_LIMIT": "1",
        "PWC_CHAT_SANDBOX_MEMORY_MIB": "512",
        "PWC_CHAT_SANDBOX_MEMORY_LIMIT_MIB": "2048",
    }


def test_staging_capacity_configuration_preserves_explicit_pool_toggle():
    enabled = {"PWC_CHAT_BLANK_POOL_ENABLED": "PWC_CHAT_BLANK_POOL_ENABLED=true"}
    values = configure_host_env.staging_chat_capacity_configuration(enabled)

    assert "PWC_CHAT_BLANK_POOL_ENABLED" not in values
    assert (
        configure_host_env.staging_chat_capacity_configuration({})[
            "PWC_CHAT_BLANK_POOL_ENABLED"
        ]
        == "false"
    )


def test_staging_chat_pool_toggle_is_narrow_and_bounded():
    assert configure_host_env.staging_chat_pool_values(enabled=True) == {
        "PWC_CHAT_BLANK_POOL_ENABLED": "true",
        "PWC_CHAT_MAX_CONCURRENCY": "2",
        "PWC_CHAT_SANDBOX_TOTAL_LIVE_CAP": "3",
        "PWC_CHAT_BLANK_POOL_MIN": "1",
        "PWC_CHAT_BLANK_POOL_MAX": "1",
        "PWC_CHAT_SANDBOX_CPU": "0.5",
        "PWC_CHAT_SANDBOX_CPU_LIMIT": "1",
        "PWC_CHAT_SANDBOX_MEMORY_MIB": "512",
        "PWC_CHAT_SANDBOX_MEMORY_LIMIT_MIB": "2048",
    }
    assert configure_host_env.staging_chat_pool_values(enabled=False) == {
        "PWC_CHAT_BLANK_POOL_ENABLED": "false"
    }


def test_staging_chat_alert_values_are_distinct_https_destinations():
    values = configure_host_env.staging_chat_alert_values(
        {
            "PWC_CHAT_SANDBOX_SLACK_WEBHOOK_URL": (
                "PWC_CHAT_SANDBOX_SLACK_WEBHOOK_URL=https://hooks.slack.test/primary"
            ),
            "PWC_CHAT_SANDBOX_ALERT_FALLBACK_WEBHOOK_URL": (
                "PWC_CHAT_SANDBOX_ALERT_FALLBACK_WEBHOOK_URL="
                "https://hooks.slack.test/fallback"
            ),
        }
    )

    assert values == {
        "PWC_CHAT_SANDBOX_SLACK_WEBHOOK_URL": ("https://hooks.slack.test/primary"),
        "PWC_CHAT_SANDBOX_ALERT_FALLBACK_WEBHOOK_URL": (
            "https://hooks.slack.test/fallback"
        ),
    }


@pytest.mark.parametrize(
    "legacy",
    [
        {},
        {
            "PWC_CHAT_SANDBOX_SLACK_WEBHOOK_URL": (
                "PWC_CHAT_SANDBOX_SLACK_WEBHOOK_URL=http://alerts.test/primary"
            ),
            "PWC_CHAT_SANDBOX_ALERT_FALLBACK_WEBHOOK_URL": (
                "PWC_CHAT_SANDBOX_ALERT_FALLBACK_WEBHOOK_URL="
                "https://alerts.test/fallback"
            ),
        },
        {
            "PWC_CHAT_SANDBOX_SLACK_WEBHOOK_URL": (
                "PWC_CHAT_SANDBOX_SLACK_WEBHOOK_URL=https://alerts.test/same"
            ),
            "PWC_CHAT_SANDBOX_ALERT_FALLBACK_WEBHOOK_URL": (
                "PWC_CHAT_SANDBOX_ALERT_FALLBACK_WEBHOOK_URL=https://alerts.test/same"
            ),
        },
    ],
)
def test_staging_chat_alert_values_reject_unsafe_configuration(legacy):
    with pytest.raises(ValueError):
        configure_host_env.staging_chat_alert_values(legacy)


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


def test_historical_semantic_scholar_key_is_cron_only_and_preserved():
    secondary = "PWC_SEMANTIC_SCHOLAR_API_KEY_2"
    legacy = {
        "PWC_GITHUB_TOKEN": "PWC_GITHUB_TOKEN=github",
        secondary: f"{secondary}=new-secondary",
    }
    current = {secondary: f"{secondary}=old-secondary"}

    cron = configure_host_env.cron_passthrough_credentials(legacy, current)
    assert cron[secondary] == f"{secondary}=new-secondary"
    assert secondary not in configure_host_env.without_cron_only_credentials(legacy)

    preserved = configure_host_env.cron_passthrough_credentials(
        {"PWC_GITHUB_TOKEN": "PWC_GITHUB_TOKEN=github"}, current
    )
    assert preserved[secondary] == f"{secondary}=old-secondary"


def test_staging_chat_runtime_credentials_are_preserved():
    preserved = configure_host_env.staging_runtime_passthrough(
        {
            "MODAL_TOKEN_ID": "MODAL_TOKEN_ID=id",
            "MODAL_TOKEN_SECRET": "MODAL_TOKEN_SECRET=secret",
            "PWC_CHAT_MODAL_IMAGE_VERSION": "PWC_CHAT_MODAL_IMAGE_VERSION=im-123",
            "PWC_CHAT_TITLE_HF_TOKEN": "PWC_CHAT_TITLE_HF_TOKEN=title-secret",
            "PWC_CHAT_TITLE_BILL_TO": "PWC_CHAT_TITLE_BILL_TO=huggingface",
            "PWC_CHAT_GATEWAY_URL": "PWC_CHAT_GATEWAY_URL=https://stale.example",
            "PWC_DB_PASSWORD": "PWC_DB_PASSWORD=secret",
        }
    )

    assert preserved == {
        "MODAL_TOKEN_ID": "MODAL_TOKEN_ID=id",
        "MODAL_TOKEN_SECRET": "MODAL_TOKEN_SECRET=secret",
        "PWC_CHAT_MODAL_IMAGE_VERSION": "PWC_CHAT_MODAL_IMAGE_VERSION=im-123",
        "PWC_CHAT_TITLE_HF_TOKEN": "PWC_CHAT_TITLE_HF_TOKEN=title-secret",
        "PWC_CHAT_TITLE_BILL_TO": "PWC_CHAT_TITLE_BILL_TO=huggingface",
    }


def test_staging_title_values_are_exact_and_isolated():
    source = {
        "PWC_CHAT_TITLE_GENERATION_ENABLED": ("PWC_CHAT_TITLE_GENERATION_ENABLED=true"),
        "PWC_CHAT_TITLE_HF_TOKEN": "PWC_CHAT_TITLE_HF_TOKEN=title-secret",
        "PWC_CHAT_TITLE_BILL_TO": "PWC_CHAT_TITLE_BILL_TO=huggingface",
        "PWC_CHAT_TITLE_CREDENTIAL_OWNER": "PWC_CHAT_TITLE_CREDENTIAL_OWNER=nielsr",
        "PWC_CHAT_TITLE_CREDENTIAL_ENVIRONMENT": (
            "PWC_CHAT_TITLE_CREDENTIAL_ENVIRONMENT=staging"
        ),
    }

    values = configure_host_env.staging_title_values(
        source,
        {"PWC_HF_TOKEN": "PWC_HF_TOKEN=general-secret"},
        {"PWC_CHAT_TITLE_HF_TOKEN": "PWC_CHAT_TITLE_HF_TOKEN=production-secret"},
    )

    assert values == {
        "PWC_CHAT_TITLE_GENERATION_ENABLED": "true",
        "PWC_CHAT_TITLE_HF_TOKEN": "title-secret",
        "PWC_CHAT_TITLE_BILL_TO": "huggingface",
        "PWC_CHAT_TITLE_CREDENTIAL_OWNER": "nielsr",
        "PWC_CHAT_TITLE_CREDENTIAL_ENVIRONMENT": "staging",
        "PWC_CHAT_TITLE_MODEL": "openai/gpt-oss-120b",
        "PWC_CHAT_TITLE_PROVIDER": "cerebras",
        "PWC_CHAT_TITLE_MAX_TOKENS": "64",
        "PWC_CHAT_TITLE_MONTHLY_CAP_MICROUSD": "25000000",
        "PWC_CHAT_TITLE_WARNING_MICROUSD": "20000000",
        "PWC_CHAT_TITLE_MAX_CALL_MICROUSD": "10000",
    }

    reused = dict(source)
    reused["PWC_CHAT_TITLE_HF_TOKEN"] = "PWC_CHAT_TITLE_HF_TOKEN=general-secret"
    with pytest.raises(ValueError, match="distinct from general and production"):
        configure_host_env.staging_title_values(
            reused,
            {"PWC_HF_TOKEN": "PWC_HF_TOKEN=general-secret"},
            {},
        )


def _production_chat_preparation_source() -> dict[str, str]:
    values = {
        "MODAL_TOKEN_ID": "modal-id",
        "MODAL_TOKEN_SECRET": "modal-secret",
        "PWC_CHAT_SANDBOX_MODAL_WORKSPACE": "nielsrogge",
        "PWC_CHAT_SANDBOX_MODAL_OWNER_USERNAME": "nielsrogge",
        "PWC_CHAT_SANDBOX_OPERATOR_USERNAMES": "root,nielsr",
        "PWC_CHAT_SANDBOX_BUDGET_ATTESTATION": (
            "modal-workspace-nielsrogge-250-production-starter-v1"
        ),
        "PWC_CHAT_SANDBOX_SLACK_WEBHOOK_URL": (
            "https://alerts-primary.test/production"
        ),
        "PWC_CHAT_SANDBOX_ALERT_FALLBACK_WEBHOOK_URL": (
            "https://alerts-fallback.test/production"
        ),
        "PWC_CHAT_TITLE_GENERATION_ENABLED": "true",
        "PWC_CHAT_TITLE_HF_TOKEN": "production-title-secret",
        "PWC_CHAT_TITLE_BILL_TO": "huggingface",
        "PWC_CHAT_TITLE_CREDENTIAL_OWNER": "nielsr",
        "PWC_CHAT_TITLE_CREDENTIAL_ENVIRONMENT": "production",
    }
    return {key: f"{key}={value}" for key, value in values.items()}


def test_production_environment_example_exposes_sealed_preparation_contract():
    source = Path(__file__).resolve().parents[2]
    values = configure_host_env.read_lines(
        source / "deploy" / "env" / "production.env.example"
    )

    assert configure_host_env.decoded_value(values["PWC_CHAT_ENABLED"]) == "false"
    assert (
        configure_host_env.decoded_value(values["PWC_CHAT_PUBLIC_ADMISSION_ENABLED"])
        == "false"
    )
    assert (
        configure_host_env.decoded_value(values["PWC_CHAT_SANDBOX_ADMISSION_ENABLED"])
        == "false"
    )
    assert (
        configure_host_env.decoded_value(
            values["PWC_CHAT_OPENROUTER_SERVER_FUNDED_ENABLED"]
        )
        == "false"
    )
    assert {
        "PWC_CHAT_TITLE_HF_TOKEN",
        "PWC_CHAT_SANDBOX_MODAL_WORKSPACE",
        "PWC_CHAT_SANDBOX_MODAL_OWNER_USERNAME",
        "PWC_CHAT_SANDBOX_OPERATOR_USERNAMES",
        "PWC_CHAT_SANDBOX_BUDGET_ATTESTATION",
        "PWC_CHAT_SANDBOX_SLACK_WEBHOOK_URL",
        "PWC_CHAT_SANDBOX_ALERT_FALLBACK_WEBHOOK_URL",
        "MODAL_TOKEN_ID",
        "MODAL_TOKEN_SECRET",
    } <= values.keys()


def test_production_chat_preparation_is_sealed_and_fail_closed():
    values = configure_host_env.production_chat_preparation_values(
        _production_chat_preparation_source(),
        {"PWC_HF_TOKEN": "PWC_HF_TOKEN=general-secret"},
        {"PWC_CHAT_TITLE_HF_TOKEN": "PWC_CHAT_TITLE_HF_TOKEN=staging-secret"},
    )

    assert values["PWC_CHAT_ENABLED"] == "true"
    assert values["PWC_CHAT_NEW_CHAT_MODAL_PERCENTAGE"] == "100"
    assert values["PWC_CHAT_PUBLIC_ADMISSION_ENABLED"] == "false"
    assert values["PWC_CHAT_SANDBOX_ADMISSION_ENABLED"] == "false"
    assert values["PWC_CHAT_BLANK_POOL_ENABLED"] == "false"
    assert values["PWC_CHAT_OPENROUTER_SERVER_FUNDED_ENABLED"] == "false"
    assert values["PWC_CHAT_OPERATIONAL_ALERTS_ENABLED"] == "true"
    assert values["PWC_CHAT_PROVIDER_ALERT_WINDOW_SECONDS"] == "300"
    assert values["PWC_CHAT_PROVIDER_ALERT_MIN_FAILURES"] == "5"
    assert values["PWC_CHAT_PROVIDER_ALERT_FAILURE_PERCENT"] == "50"
    assert values["PWC_CHAT_SANDBOX_MODAL_ENVIRONMENT"] == "pwc-chat-production"
    assert values["PWC_CHAT_SANDBOX_APPLICATION_CAP_MICROUSD"] == "100000000"
    assert values["PWC_CHAT_SANDBOX_WORKSPACE_CAP_MICROUSD"] == "250000000"
    assert values["PWC_CHAT_TITLE_MONTHLY_CAP_MICROUSD"] == "25000000"
    assert values["PWC_CHAT_TITLE_HF_TOKEN"] == "production-title-secret"
    assert values["PWC_CHAT_MAX_CONCURRENCY"] == "2"
    assert values["PWC_CHAT_SANDBOX_TOTAL_LIVE_CAP"] == "3"


def test_production_modal_profile_is_imported_without_persisting_a_copy(
    tmp_path: Path,
):
    config = tmp_path / ".modal.toml"
    config.write_text(
        '[nielsrogge]\ntoken_id = "modal-id"\n'
        'token_secret = "modal-secret"\nactive = true\n'
    )
    config.chmod(0o600)
    source = {"PWC_CHAT_ENABLED": "PWC_CHAT_ENABLED=false"}

    updated = configure_host_env.production_modal_profile_source(
        source,
        config,
        "nielsrogge",
    )

    assert source == {"PWC_CHAT_ENABLED": "PWC_CHAT_ENABLED=false"}
    assert updated["MODAL_TOKEN_ID"] == "MODAL_TOKEN_ID=modal-id"
    assert updated["MODAL_TOKEN_SECRET"] == "MODAL_TOKEN_SECRET=modal-secret"


@pytest.mark.parametrize(
    ("mode", "profile", "source", "match"),
    [
        (0o644, "nielsrogge", {}, "group/world readable"),
        (0o600, "missing", {}, "profile is missing"),
        (
            0o600,
            "nielsrogge",
            {"MODAL_TOKEN_ID": "MODAL_TOKEN_ID=other"},
            "conflicts",
        ),
    ],
)
def test_production_modal_profile_rejects_unsafe_import(
    tmp_path: Path,
    mode: int,
    profile: str,
    source: dict[str, str],
    match: str,
):
    config = tmp_path / ".modal.toml"
    config.write_text(
        '[nielsrogge]\ntoken_id = "modal-id"\n'
        'token_secret = "modal-secret"\nactive = true\n'
    )
    config.chmod(mode)

    with pytest.raises(ValueError, match=match):
        configure_host_env.production_modal_profile_source(
            source,
            config,
            profile,
        )


def test_production_chat_install_revalidates_exact_sealed_bundle():
    values = configure_host_env.production_chat_preparation_values(
        _production_chat_preparation_source(),
        {"PWC_HF_TOKEN": "PWC_HF_TOKEN=general-secret"},
        {"PWC_CHAT_TITLE_HF_TOKEN": "PWC_CHAT_TITLE_HF_TOKEN=staging-secret"},
    )
    sealed = {key: f"{key}={value}" for key, value in values.items()}

    assert (
        configure_host_env.production_chat_install_values(
            sealed,
            {"PWC_HF_TOKEN": "PWC_HF_TOKEN=general-secret"},
            {"PWC_CHAT_TITLE_HF_TOKEN": "PWC_CHAT_TITLE_HF_TOKEN=staging-secret"},
        )
        == values
    )


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        ({"PWC_CHAT_ENABLED": "PWC_CHAT_ENABLED=false"}, "stale"),
        ({"UNREVIEWED_SECRET": "UNREVIEWED_SECRET=value"}, "unexpected"),
    ],
)
def test_production_chat_install_rejects_tampered_bundle(mutation, match):
    values = configure_host_env.production_chat_preparation_values(
        _production_chat_preparation_source(),
        {"PWC_HF_TOKEN": "PWC_HF_TOKEN=general-secret"},
        {"PWC_CHAT_TITLE_HF_TOKEN": "PWC_CHAT_TITLE_HF_TOKEN=staging-secret"},
    )
    sealed = {key: f"{key}={value}" for key, value in values.items()}
    sealed.update(mutation)

    with pytest.raises(ValueError, match=match):
        configure_host_env.production_chat_install_values(
            sealed,
            {"PWC_HF_TOKEN": "PWC_HF_TOKEN=general-secret"},
            {"PWC_CHAT_TITLE_HF_TOKEN": ("PWC_CHAT_TITLE_HF_TOKEN=staging-secret")},
        )


@pytest.mark.parametrize(
    ("key", "value", "match"),
    [
        ("PWC_CHAT_TITLE_HF_TOKEN", "general-secret", "distinct"),
        ("PWC_CHAT_OPENROUTER_API_KEY", "forbidden", "prohibits"),
        (
            "PWC_CHAT_SANDBOX_ALERT_FALLBACK_WEBHOOK_URL",
            "https://alerts-primary.test/production",
            "distinct",
        ),
        (
            "PWC_CHAT_SANDBOX_BUDGET_ATTESTATION",
            "unattested",
            "does not match",
        ),
    ],
)
def test_production_chat_preparation_rejects_unsafe_inputs(key, value, match):
    source = _production_chat_preparation_source()
    source[key] = f"{key}={value}"

    with pytest.raises(ValueError, match=match):
        configure_host_env.production_chat_preparation_values(
            source,
            {"PWC_HF_TOKEN": "PWC_HF_TOKEN=general-secret"},
            {"PWC_CHAT_TITLE_HF_TOKEN": "PWC_CHAT_TITLE_HF_TOKEN=staging-secret"},
        )


def test_staging_langfuse_credentials_are_bounded_and_preserved():
    legacy = {
        "LANGFUSE_BASE_URL": "LANGFUSE_BASE_URL=https://cloud.langfuse.com",
        "LANGFUSE_PUBLIC_KEY": "LANGFUSE_PUBLIC_KEY=pk-test",
        "LANGFUSE_SECRET_KEY": "LANGFUSE_SECRET_KEY=sk-test",
    }

    assert configure_host_env.staging_langfuse_values(legacy) == {
        "LANGFUSE_BASE_URL": "https://cloud.langfuse.com",
        "LANGFUSE_PUBLIC_KEY": "pk-test",
        "LANGFUSE_SECRET_KEY": "sk-test",
        "PWC_CHAT_LANGFUSE_ENABLED": "true",
    }
    lines = {
        **legacy,
        "PWC_CHAT_LANGFUSE_ENABLED": "PWC_CHAT_LANGFUSE_ENABLED=true",
    }
    assert configure_host_env.staging_runtime_passthrough(lines) == lines


def test_staging_openrouter_credential_gets_a_chat_only_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(configure_host_env, "CONFIG_ROOT", tmp_path)
    values = configure_host_env.staging_openrouter_values(
        {"PWC_OPENROUTER_API_KEY": "PWC_OPENROUTER_API_KEY=secret"}
    )
    assert values["PWC_CHAT_OPENROUTER_API_KEY"] == "secret"
    assert values["PWC_CHAT_OPENROUTER_SERVER_FUNDED_ENABLED"] == "true"
    assert values["PWC_CHAT_OPENROUTER_MONTHLY_USER_BUDGET_USD"] == "1.00"
    assert values["PWC_CHAT_OPENROUTER_WORKSPACE_MONTHLY_BUDGET_USD"] == "200.00"
    encoded_key = json.loads(values["PWC_CHAT_OPENROUTER_CREDENTIAL_KEYRING"])["1"]
    assert (
        len(base64.urlsafe_b64decode(encoded_key + "=" * (-len(encoded_key) % 4))) == 32
    )
    assert values["PWC_CHAT_OPENROUTER_USER_TRACKING_SECRET"]

    with pytest.raises(ValueError, match="PWC_OPENROUTER_API_KEY"):
        configure_host_env.staging_openrouter_values({})


def test_staging_web_search_configuration_is_scoped_and_bounded():
    values = configure_host_env.staging_web_search_values(
        {"EXA_API_KEY": "EXA_API_KEY=server-secret"}
    )

    assert values["PWC_CHAT_WEB_SEARCH_EXA_API_KEY"] == "server-secret"
    assert values["PWC_CHAT_WEB_SEARCH_ENABLED"] == "true"
    assert values["PWC_CHAT_WEB_SEARCH_MAX_CALLS"] == "3"
    assert values["PWC_CHAT_WEB_SEARCH_RESULT_COUNT"] == "5"
    assert values["PWC_CHAT_WEB_SEARCH_MAX_RESULT_BYTES"] == "16384"
    assert values["PWC_CHAT_WEB_SEARCH_MONTHLY_WARNING_CALLS"] == "1000"
    assert values["PWC_CHAT_WEB_SEARCH_MONTHLY_HARD_CALLS"] == "1200"
    assert set(values) <= configure_host_env.STAGING_RUNTIME_PASSTHROUGH_KEYS
    with pytest.raises(ValueError, match="EXA_API_KEY"):
        configure_host_env.staging_web_search_values({})


def test_staging_github_configuration_is_single_key_and_non_empty():
    assert configure_host_env.staging_github_values(
        {"PWC_GITHUB_TOKEN": "PWC_GITHUB_TOKEN=github-secret"}
    ) == {"PWC_GITHUB_TOKEN": "github-secret"}
    with pytest.raises(ValueError, match="PWC_GITHUB_TOKEN"):
        configure_host_env.staging_github_values({})


def test_staging_openrouter_disable_removes_key_and_pins_flag_off():
    assert configure_host_env.without_staging_openrouter(
        {
            "PWC_CHAT_OPENROUTER_API_KEY": "PWC_CHAT_OPENROUTER_API_KEY=secret",
            "PWC_CHAT_OPENROUTER_SERVER_FUNDED_ENABLED": (
                "PWC_CHAT_OPENROUTER_SERVER_FUNDED_ENABLED=true"
            ),
            "PWC_CHAT_LANGFUSE_ENABLED": "PWC_CHAT_LANGFUSE_ENABLED=true",
        }
    ) == {
        "PWC_CHAT_OPENROUTER_SERVER_FUNDED_ENABLED": (
            "PWC_CHAT_OPENROUTER_SERVER_FUNDED_ENABLED=false"
        ),
        "PWC_CHAT_LANGFUSE_ENABLED": "PWC_CHAT_LANGFUSE_ENABLED=true",
    }


def test_staging_chat_latency_rollout_settings_are_preserved():
    rollout_keys = {
        "PWC_CHAT_BLANK_POOL_ENABLED",
        "PWC_CHAT_BLANK_POOL_MAX",
        "PWC_CHAT_BLANK_POOL_MIN",
        "PWC_CHAT_BLANK_POOL_MIN_REMAINING_SECONDS",
        "PWC_CHAT_BLANK_POOL_MONTHLY_BUDGET_USD",
        "PWC_CHAT_BLANK_POOL_REFILL_CONCURRENCY",
        "PWC_CHAT_BLANK_POOL_REPORTED_MONTH_TO_DATE_USD",
        "PWC_CHAT_BLANK_POOL_ROTATE_BEFORE_SECONDS",
        "PWC_CHAT_CANCEL_GRACE_SECONDS",
        "PWC_CHAT_PERSISTENT_SANDBOX_LIFETIME_SECONDS",
        "PWC_CHAT_PERSISTENT_WORKER_ENABLED",
        "PWC_CHAT_SANDBOX_CPU",
        "PWC_CHAT_SANDBOX_CPU_LIMIT",
        "PWC_CHAT_SANDBOX_MEMORY_LIMIT_MIB",
        "PWC_CHAT_SANDBOX_MEMORY_MIB",
        "PWC_CHAT_SANDBOX_TOTAL_LIVE_CAP",
        "PWC_CHAT_WORKER_READY_TIMEOUT_SECONDS",
    }
    lines = {key: f"{key}=configured" for key in rollout_keys}

    assert rollout_keys <= configure_host_env.STAGING_RUNTIME_PASSTHROUGH_KEYS
    assert configure_host_env.staging_runtime_passthrough(lines) == lines


def test_cron_jobs_declare_bounded_execution_contracts():
    assert cron_launcher.COMMANDS
    for name, spec in cron_launcher.COMMANDS.items():
        assert spec.command
        assert spec.timeout in {"1m", "30m", "45m", "50m", "2h", "6h"}
        assert spec.mutates_shared_data is (name != "monitor_chat_operational_alerts")
        assert spec.idempotency
        assert spec.health_job


def test_hot_workflow_runs_on_the_activated_production_schedule():
    workflow = (
        Path(__file__).resolve().parents[2]
        / ".github"
        / "workflows"
        / "cron-update-hot-github-trending.yml"
    ).read_text()
    assert "workflow_dispatch:" in workflow
    assert "schedule:" in workflow
    assert 'cron: "*/15 * * * *"' in workflow

    cron_env_example = (
        Path(__file__).resolve().parents[2]
        / "deploy"
        / "env"
        / "production-cron.env.example"
    ).read_text()
    assert "PWC_GITHUB_HOT_WINDOW_DAYS" not in cron_env_example


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
    assert status["jobs"]["update_hot_github_trending"]["timeout"] == "30m"
    assert status["jobs"]["sync_3d_arena"]["timeout"] == "30m"
    assert status["jobs"]["sync_open_asr"]["timeout"] == "30m"


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


def test_host_environment_subject_roles_are_shared_and_conflict_safe():
    production = {
        "PWC_ADMIN_HF_SUBJECTS": "PWC_ADMIN_HF_SUBJECTS=admin-sub",
        "PWC_CONTRIBUTOR_HF_SUBJECTS": ("PWC_CONTRIBUTOR_HF_SUBJECTS=one-sub,two-sub"),
    }
    staging = dict(production)
    assert configure_host_env.shared_role_values(production, staging) == {
        "PWC_ADMIN_HF_SUBJECTS": "admin-sub",
        "PWC_CONTRIBUTOR_HF_SUBJECTS": "one-sub,two-sub",
    }
    staging["PWC_ADMIN_HF_SUBJECTS"] = "PWC_ADMIN_HF_SUBJECTS=other-sub"
    with pytest.raises(ValueError, match="differs"):
        configure_host_env.shared_role_values(production, staging)


def test_host_profiles_keep_contributor_direct_edits_default_off():
    repository = Path(__file__).resolve().parents[2]
    script = (repository / "deploy/configure_host_env.py").read_text()
    assert script.count('"PWC_CONTRIBUTOR_DIRECT_EDITS_ENABLED": "false"') == 2


def test_role_allowlist_installer_normalizes_and_rejects_usernames():
    assert (
        configure_role_allowlists.normalized_subjects(
            [" subject-b ", "subject-a", "subject-a"]
        )
        == "subject-a,subject-b"
    )
    with pytest.raises(ValueError, match="Malformed"):
        configure_role_allowlists.normalized_subjects(["not a subject"])
