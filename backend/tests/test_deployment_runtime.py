from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import deploy.cli as deploy_cli
import deploy.configure_host_env as configure_host_env
import deploy.configure_role_allowlists as configure_role_allowlists
import deploy.cron_launcher as cron_launcher
import deploy.run_backend as run_backend
import deploy.smoke_test as smoke_test
from backend.chat_sandbox_worker.contract import MODAL_IMAGE_ID
from backend.config import Settings
from backend.services import openrouter_budget_service as deploy_openrouter
from backend.services.runtime_validation import validate_chat_schema, validate_runtime
from deploy.cli import _chat_descriptor_from_source, parser_for
from deploy.install_deploy_tools import (
    RUNTIME_CONTRACT_PATHS,
    bundle_runtime_contract,
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
)
from deploy.run_backend import RELEASE_ROOT, configure_release_environment
from deploy.smoke_test import validate_local_bundle


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
        chat_enabled=environment == "staging",
        chat_default_backend=runtime["default_backend"],
        chat_new_chat_modal_percentage=runtime["new_chat_modal_percentage"],
        chat_modal_image_version=runtime["modal_image_version"],
        chat_pwc_cli_version=runtime["pwc_cli_version"],
        chat_worker_contract_version=runtime["worker_contract_version"],
        chat_system_prompt_sha256=runtime["system_prompt_sha256"],
        chat_sandbox_spend_enforcement_enabled=environment == "staging",
        chat_sandbox_budget_attestation=(
            "modal-workspace-250-staging-125-v1" if environment == "staging" else ""
        ),
        chat_sandbox_modal_environment=(
            "pwc-chat-staging" if environment == "staging" else ""
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
        chat_openrouter_monthly_user_budget_usd=1,
        chat_openrouter_workspace_monthly_budget_usd=5,
        chat_openrouter_credential_keyring=json.dumps(
            {"1": base64.urlsafe_b64encode(b"k" * 32).rstrip(b"=").decode()}
        ),
        chat_openrouter_user_tracking_secret="test-only-tracking-secret",
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

    with pytest.raises(RuntimeError, match="request bound exceeds"):
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
    assert values["PWC_CHAT_OPENROUTER_WORKSPACE_MONTHLY_BUDGET_USD"] == "5.00"


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

    with pytest.raises(RuntimeError, match="prohibited in production"):
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


def test_staging_runtime_accepts_directory_snapshot_feature(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.chat_workspace_snapshots_enabled = True
    assert validate_runtime(settings) == profile_features("staging")


def test_staging_blank_pool_requires_persistent_workers(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.chat_blank_pool_enabled = True
    settings.chat_persistent_worker_enabled = False
    with pytest.raises(RuntimeError, match="requires persistent workers"):
        validate_runtime(settings)


def test_staging_blank_pool_rejects_inverted_capacity(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.chat_blank_pool_min = 2
    settings.chat_blank_pool_max = 1
    with pytest.raises(RuntimeError, match="minimum exceeds"):
        validate_runtime(settings)


def test_production_rejects_blank_pool_activation(tmp_path: Path):
    release = make_bundle(tmp_path, chat=False)
    settings = deployed_settings(tmp_path, release, "production")
    settings.chat_blank_pool_enabled = True
    with pytest.raises(RuntimeError, match="active chat runtime descriptor"):
        validate_runtime(settings)


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
        validate_chat_schema(_ChatSchemaDB("on"))


def test_chat_schema_accepts_writable_staging_connection():
    validate_chat_schema(_ChatSchemaDB("off"))


def test_chat_schema_requires_qualification_metadata_columns():
    with pytest.raises(RuntimeError, match="required chat sandbox schema is missing"):
        validate_chat_schema(_ChatSchemaDB("off", include_qualification_columns=False))


def test_chat_schema_requires_typed_edit_preparation_columns():
    with pytest.raises(RuntimeError, match="required chat sandbox schema is missing"):
        validate_chat_schema(_ChatSchemaDB("off", include_edit_columns=False))


def test_chat_schema_requires_self_contained_share_snapshot_columns():
    with pytest.raises(RuntimeError, match="required chat sandbox schema is missing"):
        validate_chat_schema(_ChatSchemaDB("off", include_share_columns=False))


def test_chat_schema_requires_share_snapshot_array_constraint():
    with pytest.raises(RuntimeError, match="required chat sandbox schema is missing"):
        validate_chat_schema(_ChatSchemaDB("off", include_share_constraint=False))


def test_chat_schema_requires_blank_pool_accounting_columns():
    with pytest.raises(RuntimeError, match="required chat sandbox schema is missing"):
        validate_chat_schema(_ChatSchemaDB("off", include_pool_columns=False))


def test_chat_schema_requires_latency_telemetry_columns():
    with pytest.raises(RuntimeError, match="required chat sandbox schema is missing"):
        validate_chat_schema(_ChatSchemaDB("off", include_latency_columns=False))


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
    assert descriptor["worker_contract_version"] == "29"
    assert _chat_descriptor_from_source(source, "production") is None


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
    manifest.pop("feature_contract_version")
    manifest.pop("chat_runtime")
    manifest["backend_features"] = {"chat": False}
    manifest["frontend_features"] = {"chat": False}
    manifest_path.write_text(json.dumps(manifest))
    (release / "frontend-dist" / "features.json").write_text(
        json.dumps({"chat": False})
    )
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


def test_chat_share_migration_is_staging_owned_and_idempotent():
    repository = Path(__file__).resolve().parents[2]
    migration = (
        repository / "backend/database/migrations/add_chat_shares.sql"
    ).read_text()

    assert "current_schema() <> 'staging'" in migration
    assert "CREATE TABLE IF NOT EXISTS chat_shares" in migration
    assert "snapshot_version SMALLINT NOT NULL DEFAULT 1" in migration
    assert "messages JSONB NOT NULL" in migration
    assert "chat_shares_messages_array_check" in migration
    assert "REFERENCES chat_messages" not in migration
    assert migration.count("ON DELETE CASCADE") >= 1
    assert "ADD COLUMN IF NOT EXISTS finish_reason VARCHAR(64)" in migration
    assert "ALTER TABLE chat_shares OWNER TO pwc_staging_owner" in migration
    assert "DROP TABLE IF EXISTS chat_share_messages" in migration
    assert (
        "EXECUTE\n            "
        "'SELECT EXISTS (SELECT 1 FROM chat_share_messages LIMIT 1)'" in migration
    )
    assert "AND EXISTS (SELECT FROM chat_share_messages LIMIT 1)" not in migration
    assert "TO pwc_staging;" in migration
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


def test_chat_edit_preparation_migration_is_staging_only_and_typed():
    repository = Path(__file__).resolve().parents[2]
    migration = (
        repository / "backend/database/migrations/add_chat_edit_preparation_state.sql"
    ).read_text()

    assert "current_schema() <> 'staging'" in migration
    assert "prepared_fork_sdk_session_id UUID" in migration
    assert "prepared_fork_sdk_project_key TEXT" in migration
    assert "chat_messages_prepared_fork_pair_check" in migration


def test_chat_archiving_migration_is_additive_and_idempotent():
    repository = Path(__file__).resolve().parents[2]
    migration = (
        repository / "backend/database/migrations/add_chat_session_archiving.sql"
    ).read_text()

    assert "ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ" in migration
    assert "WHERE archived_at IS NULL" in migration
    assert "DROP " not in migration


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
    }


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
            "PWC_CHAT_GATEWAY_URL": "PWC_CHAT_GATEWAY_URL=https://stale.example",
            "PWC_DB_PASSWORD": "PWC_DB_PASSWORD=secret",
        }
    )

    assert preserved == {
        "MODAL_TOKEN_ID": "MODAL_TOKEN_ID=id",
        "MODAL_TOKEN_SECRET": "MODAL_TOKEN_SECRET=secret",
        "PWC_CHAT_MODAL_IMAGE_VERSION": "PWC_CHAT_MODAL_IMAGE_VERSION=im-123",
    }


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
    assert values["PWC_CHAT_OPENROUTER_WORKSPACE_MONTHLY_BUDGET_USD"] == "5.00"
    encoded_key = json.loads(values["PWC_CHAT_OPENROUTER_CREDENTIAL_KEYRING"])["1"]
    assert (
        len(base64.urlsafe_b64decode(encoded_key + "=" * (-len(encoded_key) % 4))) == 32
    )
    assert values["PWC_CHAT_OPENROUTER_USER_TRACKING_SECRET"]

    with pytest.raises(ValueError, match="PWC_OPENROUTER_API_KEY"):
        configure_host_env.staging_openrouter_values({})


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
    for spec in cron_launcher.COMMANDS.values():
        assert spec.command
        assert spec.timeout in {"30m", "50m", "2h", "6h"}
        assert spec.mutates_shared_data is True
        assert spec.idempotency
        assert spec.health_job


def test_hot_workflow_is_manual_only_until_production_activation():
    workflow = (
        Path(__file__).resolve().parents[2]
        / ".github"
        / "workflows"
        / "cron-update-hot-github-trending.yml"
    ).read_text()
    assert "workflow_dispatch:" in workflow
    assert "schedule:" not in workflow
    assert 'cron: "*/15 * * * *"' not in workflow

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
