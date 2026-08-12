#!/usr/bin/env python3
"""Create the two deployed app environments and the CRON credential overlay."""

from __future__ import annotations

import argparse
import ast
import base64
import grp
import hashlib
import json
import os
import pwd
import secrets
import subprocess
import tomllib
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

CONFIG_ROOT = Path("/etc/paperswithcode")
PRODUCTION_CHAT_SEALED_CONFIG = CONFIG_ROOT / "production-chat-prepared.env"

STAGING_EXCLUDED_PREFIXES = (
    "PWC_POSTGRES_BACKUP_",
    "PWC_GITHUB_",
    "GITHUB_",
)
STAGING_EXCLUDED_KEYS = {
    "ARTIFICIAL_ANALYSIS_API_KEY",
    "EXA_API_KEY",
    "OPENAI_API_KEY",
    "PWC_ADMIN_API_TOKEN",
    "PWC_DATALAB_API_KEY",
    "PWC_GEMINI_API_KEY",
    "PWC_OPENAI_API_KEY",
    "PWC_OPENROUTER_API_KEY",
}
CRON_ONLY_KEYS = {
    "PWC_GITHUB_TOKEN_HOT",
    "PWC_SEMANTIC_SCHOLAR_API_KEY_2",
}
STAGING_RUNTIME_PASSTHROUGH_KEYS = {
    "LANGFUSE_BASE_URL",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "MODAL_TOKEN_ID",
    "MODAL_TOKEN_SECRET",
    "MODAL_ENVIRONMENT",
    "PWC_CHAT_DEFAULT_BACKEND",
    "PWC_CHAT_LANGFUSE_ENABLED",
    "PWC_CHAT_MAX_CONCURRENCY",
    "PWC_CHAT_BLANK_POOL_ENABLED",
    "PWC_CHAT_BLANK_POOL_MAX",
    "PWC_CHAT_BLANK_POOL_MIN",
    "PWC_CHAT_BLANK_POOL_MIN_REMAINING_SECONDS",
    "PWC_CHAT_BLANK_POOL_MONTHLY_BUDGET_USD",
    "PWC_CHAT_BLANK_POOL_REFILL_CONCURRENCY",
    "PWC_CHAT_BLANK_POOL_REPORTED_MONTH_TO_DATE_USD",
    "PWC_CHAT_BLANK_POOL_ROTATE_BEFORE_SECONDS",
    "PWC_CHAT_CANCEL_GRACE_SECONDS",
    "PWC_CHAT_MODAL_IMAGE_VERSION",
    "PWC_CHAT_NEW_CHAT_MODAL_PERCENTAGE",
    "PWC_CHAT_OPENROUTER_CREDENTIAL_ACTIVE_KEY_VERSION",
    "PWC_CHAT_OPENROUTER_CREDENTIAL_KEYRING",
    "PWC_CHAT_OPENROUTER_MONTHLY_USER_BUDGET_USD",
    "PWC_CHAT_OPENROUTER_SERVER_FUNDED_ENABLED",
    "PWC_CHAT_OPENROUTER_USER_TRACKING_SECRET",
    "PWC_CHAT_OPENROUTER_WORKSPACE_MONTHLY_BUDGET_USD",
    "PWC_CHAT_PERSISTENT_SANDBOX_LIFETIME_SECONDS",
    "PWC_CHAT_PERSISTENT_WORKER_ENABLED",
    "PWC_CHAT_PWC_CLI_VERSION",
    "PWC_CHAT_SANDBOX_CPU",
    "PWC_CHAT_SANDBOX_CPU_LIMIT",
    "PWC_CHAT_SANDBOX_MEMORY_LIMIT_MIB",
    "PWC_CHAT_SANDBOX_MEMORY_MIB",
    "PWC_CHAT_SANDBOX_TOTAL_LIVE_CAP",
    "PWC_CHAT_SANDBOX_WARNING_MICROUSD",
    "PWC_CHAT_SANDBOX_SPEND_ENFORCEMENT_ENABLED",
    "PWC_CHAT_SANDBOX_APPLICATION_CAP_MICROUSD",
    "PWC_CHAT_SANDBOX_ENVIRONMENT_CAP_MICROUSD",
    "PWC_CHAT_SANDBOX_WORKSPACE_CAP_MICROUSD",
    "PWC_CHAT_SANDBOX_PROVIDER_MODE",
    "PWC_CHAT_SANDBOX_BUDGET_ATTESTATION",
    "PWC_CHAT_SANDBOX_MODAL_ENVIRONMENT",
    "PWC_CHAT_SANDBOX_MODAL_WORKSPACE",
    "PWC_CHAT_SANDBOX_MODAL_OWNER_USERNAME",
    "PWC_CHAT_SANDBOX_WATCHDOG_SECONDS",
    "PWC_CHAT_SANDBOX_DRAIN_GRACE_SECONDS",
    "PWC_CHAT_SANDBOX_TERMINATION_GRACE_SECONDS",
    "PWC_CHAT_SANDBOX_RECONCILIATION_ALLOWANCE_MICROUSD",
    "PWC_CHAT_SANDBOX_RECONCILIATION_INTERVAL_SECONDS",
    "PWC_CHAT_SANDBOX_RECONCILIATION_STALE_SECONDS",
    "PWC_CHAT_SANDBOX_PROVIDER_FLOOR_MICROUSD",
    "PWC_CHAT_SANDBOX_PROVIDER_REPORTED_AT",
    "PWC_CHAT_SANDBOX_SLACK_WEBHOOK_URL",
    "PWC_CHAT_SANDBOX_ALERT_FALLBACK_WEBHOOK_URL",
    "PWC_CHAT_SANDBOX_RUNBOOK_URL",
    "PWC_CHAT_SANDBOX_OPERATOR_USERNAMES",
    "PWC_CHAT_SYSTEM_PROMPT_SHA256",
    "PWC_CHAT_TITLE_BILL_TO",
    "PWC_CHAT_TITLE_CREDENTIAL_ENVIRONMENT",
    "PWC_CHAT_TITLE_CREDENTIAL_OWNER",
    "PWC_CHAT_TITLE_GENERATION_ENABLED",
    "PWC_CHAT_TITLE_HF_TOKEN",
    "PWC_CHAT_TITLE_MAX_CALL_MICROUSD",
    "PWC_CHAT_TITLE_MAX_TOKENS",
    "PWC_CHAT_TITLE_MODEL",
    "PWC_CHAT_TITLE_MONTHLY_CAP_MICROUSD",
    "PWC_CHAT_TITLE_PROVIDER",
    "PWC_CHAT_TITLE_WARNING_MICROUSD",
    "PWC_CHAT_WORKER_CONTRACT_VERSION",
    "PWC_CHAT_WORKER_READY_TIMEOUT_SECONDS",
    "PWC_CHAT_WORKSPACE_SNAPSHOTS_ENABLED",
    "PWC_CHAT_WEB_SEARCH_ENABLED",
    "PWC_CHAT_WEB_SEARCH_PROVIDER",
    "PWC_CHAT_WEB_SEARCH_EXA_API_KEY",
    "PWC_CHAT_WEB_SEARCH_EXA_URL",
    "PWC_CHAT_WEB_SEARCH_MAX_CALLS",
    "PWC_CHAT_WEB_SEARCH_TIMEOUT_SECONDS",
    "PWC_CHAT_WEB_SEARCH_RESULT_COUNT",
    "PWC_CHAT_WEB_SEARCH_MAX_RESULT_BYTES",
    "PWC_CHAT_WEB_SEARCH_QUERY_MAX_CHARS",
    "PWC_CHAT_WEB_SEARCH_MONTHLY_WARNING_CALLS",
    "PWC_CHAT_WEB_SEARCH_MONTHLY_HARD_CALLS",
    "PWC_CHAT_WEB_SEARCH_TRANSIENT_COOLDOWN_SECONDS",
    "PWC_CHAT_WEB_SEARCH_DOMAIN_DENYLIST",
}

STAGING_LANGFUSE_KEYS = {
    "LANGFUSE_BASE_URL",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
}


def read_lines(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.is_file():
        return result
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0]
        if key.replace("_", "").isalnum() and not key[0].isdigit():
            result[key] = line
    return result


def decoded_value(line: str) -> str:
    value = line.split("=", 1)[1].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return str(ast.literal_eval(value))
    return value


def existing_or_random(lines: dict[str, str], key: str) -> str:
    line = lines.get(key)
    return decoded_value(line) if line else secrets.token_urlsafe(48)


def shared_role_values(*sources: dict[str, str]) -> dict[str, str]:
    """Preserve one identical subject allowlist across both environments."""

    result: dict[str, str] = {}
    for key in ("PWC_ADMIN_HF_SUBJECTS", "PWC_CONTRIBUTOR_HF_SUBJECTS"):
        configured = {decoded_value(source[key]) for source in sources if key in source}
        if len(configured) > 1:
            raise ValueError(f"{key} differs between protected environments")
        result[key] = next(iter(configured), "")
    return result


def shared_session_keys(
    production: dict[str, str], staging: dict[str, str]
) -> tuple[str, str]:
    private_line = production.get("PWC_SESSION_SIGNING_PRIVATE_KEY")
    public_line = production.get("PWC_SESSION_VERIFICATION_PUBLIC_KEY")
    staging_public_line = staging.get("PWC_SESSION_VERIFICATION_PUBLIC_KEY")
    if private_line:
        private_value = decoded_value(private_line)
        private_bytes = base64.urlsafe_b64decode(
            private_value + "=" * (-len(private_value) % 4)
        )
        private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
    else:
        private_key = Ed25519PrivateKey.generate()
        private_bytes = private_key.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
        private_value = base64.urlsafe_b64encode(private_bytes).rstrip(b"=").decode()
    public_bytes = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    public_value = base64.urlsafe_b64encode(public_bytes).rstrip(b"=").decode()
    for line in (public_line, staging_public_line):
        if line and decoded_value(line) != public_value:
            raise ValueError("configured shared-session public key does not match")
    return private_value, public_value


def shared_oauth_credential_secret(
    production: dict[str, str], staging: dict[str, str]
) -> str:
    """Preserve one credential-encryption secret across both environments."""

    key = "PWC_HF_OAUTH_CREDENTIAL_SECRET"
    configured = {
        decoded_value(source[key]) for source in (production, staging) if key in source
    }
    if len(configured) > 1:
        raise ValueError(f"{key} differs between protected environments")
    return next(iter(configured), secrets.token_urlsafe(48))


def assign(lines: dict[str, str], values: dict[str, str]) -> dict[str, str]:
    updated = dict(lines)
    updated.update({key: f"{key}={value}" for key, value in values.items()})
    return updated


def without_cron_only_credentials(lines: dict[str, str]) -> dict[str, str]:
    """Keep workload-owned credentials out of application environments."""
    return {key: line for key, line in lines.items() if key not in CRON_ONLY_KEYS}


def staging_runtime_passthrough(lines: dict[str, str]) -> dict[str, str]:
    """Preserve provisioned staging chat credentials and immutable pins."""
    return {
        key: line
        for key, line in lines.items()
        if key in STAGING_RUNTIME_PASSTHROUGH_KEYS
    }


def staging_langfuse_values(legacy: dict[str, str]) -> dict[str, str]:
    missing = sorted(STAGING_LANGFUSE_KEYS - legacy.keys())
    if missing:
        raise ValueError("legacy environment is missing: " + ", ".join(missing))
    return {
        **{key: decoded_value(legacy[key]) for key in STAGING_LANGFUSE_KEYS},
        "PWC_CHAT_LANGFUSE_ENABLED": "true",
    }


def staging_openrouter_accounting_values(current: dict[str, str]) -> dict[str, str]:
    """Preserve or generate the durable, non-provider staging secrets."""

    keyring_line = current.get("PWC_CHAT_OPENROUTER_CREDENTIAL_KEYRING")
    if keyring_line:
        keyring = decoded_value(keyring_line)
    else:
        encryption_key = (
            base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
        )
        keyring = json.dumps({"1": encryption_key}, separators=(",", ":"))
    tracking_secret = existing_or_random(
        current, "PWC_CHAT_OPENROUTER_USER_TRACKING_SECRET"
    )
    return {
        "PWC_CHAT_OPENROUTER_MONTHLY_USER_BUDGET_USD": "5.00",
        "PWC_CHAT_OPENROUTER_WORKSPACE_MONTHLY_BUDGET_USD": "200.00",
        "PWC_CHAT_OPENROUTER_CREDENTIAL_KEYRING": keyring,
        "PWC_CHAT_OPENROUTER_CREDENTIAL_ACTIVE_KEY_VERSION": "1",
        "PWC_CHAT_OPENROUTER_USER_TRACKING_SECRET": tracking_secret,
    }


def rotate_staging_openrouter_secret_values(
    current: dict[str, str],
) -> dict[str, str]:
    """Add a new active AES key while retaining versions needed for decrypt."""

    line = current.get("PWC_CHAT_OPENROUTER_CREDENTIAL_KEYRING")
    if not line:
        raise ValueError("staging OpenRouter credential keyring is not configured")
    try:
        parsed = json.loads(decoded_value(line))
        keyring = {str(int(version)): str(value) for version, value in parsed.items()}
    except (AttributeError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("staging OpenRouter credential keyring is invalid") from error
    if not keyring:
        raise ValueError("staging OpenRouter credential keyring is empty")
    next_version = max(int(version) for version in keyring) + 1
    keyring[str(next_version)] = (
        base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    )
    return {
        "PWC_CHAT_OPENROUTER_CREDENTIAL_KEYRING": json.dumps(
            keyring, separators=(",", ":")
        ),
        "PWC_CHAT_OPENROUTER_CREDENTIAL_ACTIVE_KEY_VERSION": str(next_version),
        "PWC_CHAT_OPENROUTER_USER_TRACKING_SECRET": secrets.token_urlsafe(48),
    }


def staging_openrouter_values(legacy: dict[str, str]) -> dict[str, str]:
    key = "PWC_OPENROUTER_API_KEY"
    if key not in legacy:
        raise ValueError(f"legacy environment is missing: {key}")
    current = read_lines(CONFIG_ROOT / "staging.env")
    return {
        **staging_openrouter_accounting_values(current),
        "PWC_CHAT_OPENROUTER_API_KEY": decoded_value(legacy[key]),
        "PWC_CHAT_OPENROUTER_SERVER_FUNDED_ENABLED": "true",
    }


def staging_web_search_values(legacy: dict[str, str]) -> dict[str, str]:
    key = "EXA_API_KEY"
    if key not in legacy or not decoded_value(legacy[key]).strip():
        raise ValueError(f"legacy environment is missing: {key}")
    return {
        "PWC_CHAT_WEB_SEARCH_ENABLED": "true",
        "PWC_CHAT_WEB_SEARCH_PROVIDER": "exa",
        "PWC_CHAT_WEB_SEARCH_EXA_API_KEY": decoded_value(legacy[key]).strip(),
        "PWC_CHAT_WEB_SEARCH_EXA_URL": "https://api.exa.ai/search",
        "PWC_CHAT_WEB_SEARCH_MAX_CALLS": "3",
        "PWC_CHAT_WEB_SEARCH_TIMEOUT_SECONDS": "3",
        "PWC_CHAT_WEB_SEARCH_RESULT_COUNT": "5",
        "PWC_CHAT_WEB_SEARCH_MAX_RESULT_BYTES": "16384",
        "PWC_CHAT_WEB_SEARCH_QUERY_MAX_CHARS": "500",
        "PWC_CHAT_WEB_SEARCH_MONTHLY_WARNING_CALLS": "1000",
        "PWC_CHAT_WEB_SEARCH_MONTHLY_HARD_CALLS": "1200",
        "PWC_CHAT_WEB_SEARCH_TRANSIENT_COOLDOWN_SECONDS": "60",
        "PWC_CHAT_WEB_SEARCH_DOMAIN_DENYLIST": "",
    }


def staging_github_values(legacy: dict[str, str]) -> dict[str, str]:
    key = "PWC_GITHUB_TOKEN"
    if key not in legacy or not decoded_value(legacy[key]).strip():
        raise ValueError(f"legacy environment is missing: {key}")
    return {key: decoded_value(legacy[key]).strip()}


def staging_title_values(
    source: dict[str, str],
    current_staging: dict[str, str],
    current_production: dict[str, str],
) -> dict[str, str]:
    """Validate and isolate the staging-only server-funded title credential."""

    required = {
        "PWC_CHAT_TITLE_GENERATION_ENABLED",
        "PWC_CHAT_TITLE_HF_TOKEN",
        "PWC_CHAT_TITLE_BILL_TO",
        "PWC_CHAT_TITLE_CREDENTIAL_OWNER",
        "PWC_CHAT_TITLE_CREDENTIAL_ENVIRONMENT",
    }
    missing = sorted(required - source.keys())
    if missing:
        raise ValueError("title environment is missing: " + ", ".join(missing))
    values = {key: decoded_value(source[key]).strip() for key in required}
    expected = {
        "PWC_CHAT_TITLE_GENERATION_ENABLED": "true",
        "PWC_CHAT_TITLE_BILL_TO": "huggingface",
        "PWC_CHAT_TITLE_CREDENTIAL_OWNER": "nielsr",
        "PWC_CHAT_TITLE_CREDENTIAL_ENVIRONMENT": "staging",
    }
    for key, value in expected.items():
        if values[key] != value:
            raise ValueError(f"{key} must be {value}")
    token = values["PWC_CHAT_TITLE_HF_TOKEN"]
    if not token:
        raise ValueError("PWC_CHAT_TITLE_HF_TOKEN must be non-empty")
    forbidden_tokens = {
        decoded_value(lines[key])
        for lines, key in (
            (source, "PWC_HF_TOKEN"),
            (current_staging, "PWC_HF_TOKEN"),
            (current_production, "PWC_CHAT_TITLE_HF_TOKEN"),
        )
        if key in lines and decoded_value(lines[key])
    }
    if token in forbidden_tokens:
        raise ValueError(
            "the staging title token must be distinct from general and production tokens"
        )
    return {
        **values,
        "PWC_CHAT_TITLE_MODEL": "deepseek/deepseek-v4-flash-0731",
        "PWC_CHAT_TITLE_PROVIDER": "openrouter",
        "PWC_CHAT_TITLE_MAX_TOKENS": "64",
        "PWC_CHAT_TITLE_MONTHLY_CAP_MICROUSD": "25000000",
        "PWC_CHAT_TITLE_WARNING_MICROUSD": "20000000",
        "PWC_CHAT_TITLE_MAX_CALL_MICROUSD": "10000",
    }


def production_title_values(
    source: dict[str, str],
    current_production: dict[str, str],
    current_staging: dict[str, str],
) -> dict[str, str]:
    """Validate the distinct production-only server-funded title credential."""

    required = {
        "PWC_CHAT_TITLE_GENERATION_ENABLED",
        "PWC_CHAT_TITLE_HF_TOKEN",
        "PWC_CHAT_TITLE_BILL_TO",
        "PWC_CHAT_TITLE_CREDENTIAL_OWNER",
        "PWC_CHAT_TITLE_CREDENTIAL_ENVIRONMENT",
    }
    missing = sorted(required - source.keys())
    if missing:
        raise ValueError("title environment is missing: " + ", ".join(missing))
    values = {key: decoded_value(source[key]).strip() for key in required}
    expected = {
        "PWC_CHAT_TITLE_GENERATION_ENABLED": "true",
        "PWC_CHAT_TITLE_BILL_TO": "huggingface",
        "PWC_CHAT_TITLE_CREDENTIAL_OWNER": "nielsr",
        "PWC_CHAT_TITLE_CREDENTIAL_ENVIRONMENT": "production",
    }
    for key, value in expected.items():
        if values[key] != value:
            raise ValueError(f"{key} must be {value}")
    token = values["PWC_CHAT_TITLE_HF_TOKEN"]
    if not token:
        raise ValueError("PWC_CHAT_TITLE_HF_TOKEN must be non-empty")
    forbidden_tokens = {
        decoded_value(lines[key])
        for lines, key in (
            (source, "PWC_HF_TOKEN"),
            (current_production, "PWC_HF_TOKEN"),
            (current_staging, "PWC_CHAT_TITLE_HF_TOKEN"),
        )
        if key in lines and decoded_value(lines[key])
    }
    if token in forbidden_tokens:
        raise ValueError(
            "the production title token must be distinct from general and staging tokens"
        )
    return {
        **values,
        "PWC_CHAT_TITLE_MODEL": "deepseek/deepseek-v4-flash-0731",
        "PWC_CHAT_TITLE_PROVIDER": "openrouter",
        "PWC_CHAT_TITLE_MAX_TOKENS": "64",
        "PWC_CHAT_TITLE_MONTHLY_CAP_MICROUSD": "25000000",
        "PWC_CHAT_TITLE_WARNING_MICROUSD": "20000000",
        "PWC_CHAT_TITLE_MAX_CALL_MICROUSD": "10000",
    }


def without_staging_openrouter(lines: dict[str, str]) -> dict[str, str]:
    """Remove shared-provider credentials and explicitly keep the preview off."""
    updated = dict(lines)
    updated.pop("PWC_CHAT_OPENROUTER_API_KEY", None)
    return assign(
        updated,
        {"PWC_CHAT_OPENROUTER_SERVER_FUNDED_ENABLED": "false"},
    )


def cron_passthrough_credentials(
    legacy: dict[str, str], current_cron: dict[str, str]
) -> dict[str, str]:
    """Build the preserved credential subset for the production CRON overlay."""
    result = {
        key: line
        for key, line in legacy.items()
        if key.startswith(("PWC_POSTGRES_BACKUP_", "PWC_GITHUB_HOT_", "GITHUB_"))
        or key == "PWC_GITHUB_RATE_LIMIT_RESERVE"
        or key
        in {
            "PWC_GITHUB_TOKEN",
            "PWC_GITHUB_TOKEN_HOT",
            "PWC_SEMANTIC_SCHOLAR_API_KEY_2",
        }
    }
    secondary_key = "PWC_SEMANTIC_SCHOLAR_API_KEY_2"
    if secondary_key not in result and secondary_key in current_cron:
        result[secondary_key] = current_cron[secondary_key]
    return result


def write_env(path: Path, lines: dict[str, str], group: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Identities need search permission to reach their own group-readable file,
    # but must not be able to list the other environment filenames.
    path.parent.chmod(0o711)
    temporary = path.with_name(f".{path.name}.new-{os.getpid()}")
    temporary.write_text(
        "\n".join(lines[key] for key in sorted(lines)) + "\n",
        encoding="utf-8",
    )
    os.chown(temporary, 0, grp.getgrnam(group).gr_gid)
    temporary.chmod(0o640)
    os.replace(temporary, path)


def staging_chat_capacity_values() -> dict[str, str]:
    """Qualified staging shape: two turns plus one warm blank sandbox."""

    return {
        "PWC_CHAT_MAX_CONCURRENCY": "2",
        "PWC_CHAT_SANDBOX_TOTAL_LIVE_CAP": "3",
        "PWC_CHAT_BLANK_POOL_MIN": "1",
        "PWC_CHAT_BLANK_POOL_MAX": "1",
        "PWC_CHAT_SANDBOX_CPU": "0.5",
        "PWC_CHAT_SANDBOX_CPU_LIMIT": "1",
        "PWC_CHAT_SANDBOX_MEMORY_MIB": "512",
        "PWC_CHAT_SANDBOX_MEMORY_LIMIT_MIB": "2048",
    }


def staging_chat_capacity_configuration(existing: dict[str, str]) -> dict[str, str]:
    """Apply the qualified shape without changing an explicit pool toggle."""

    values = {**staging_chat_capacity_values(), **staging_chat_spend_values()}
    if "PWC_CHAT_BLANK_POOL_ENABLED" in existing:
        values.pop("PWC_CHAT_BLANK_POOL_ENABLED")
    return values


def staging_chat_pool_values(*, enabled: bool) -> dict[str, str]:
    """Toggle only the qualified one-blank staging pool shape."""

    values = {"PWC_CHAT_BLANK_POOL_ENABLED": "true" if enabled else "false"}
    if enabled:
        values.update(staging_chat_capacity_values())
    return values


def staging_chat_spend_values() -> dict[str, str]:
    return {
        "PWC_CHAT_BLANK_POOL_ENABLED": "false",
        "PWC_CHAT_SANDBOX_WARNING_MICROUSD": "75000000",
        "PWC_CHAT_SANDBOX_SPEND_ENFORCEMENT_ENABLED": "true",
        "PWC_CHAT_SANDBOX_PROVIDER_MODE": "starter_workspace",
        "PWC_CHAT_SANDBOX_BUDGET_ATTESTATION": "modal-workspace-nielsrogge-250-staging-starter-v1",
        "PWC_CHAT_SANDBOX_APPLICATION_CAP_MICROUSD": "100000000",
        "PWC_CHAT_SANDBOX_ENVIRONMENT_CAP_MICROUSD": "0",
        "PWC_CHAT_SANDBOX_WORKSPACE_CAP_MICROUSD": "250000000",
        "PWC_CHAT_SANDBOX_MODAL_ENVIRONMENT": "pwc-chat-staging",
        "PWC_CHAT_SANDBOX_MODAL_WORKSPACE": "nielsrogge",
        "PWC_CHAT_SANDBOX_MODAL_OWNER_USERNAME": "nielsrogge",
        "MODAL_ENVIRONMENT": "pwc-chat-staging",
        "PWC_CHAT_SANDBOX_WATCHDOG_SECONDS": "15",
        "PWC_CHAT_SANDBOX_DRAIN_GRACE_SECONDS": "30",
        "PWC_CHAT_SANDBOX_TERMINATION_GRACE_SECONDS": "30",
        "PWC_CHAT_SANDBOX_RECONCILIATION_ALLOWANCE_MICROUSD": "1000000",
        "PWC_CHAT_SANDBOX_RECONCILIATION_INTERVAL_SECONDS": "3600",
        "PWC_CHAT_SANDBOX_RECONCILIATION_STALE_SECONDS": "7200",
        "PWC_CHAT_SANDBOX_RUNBOOK_URL": "https://github.com/huggingface/paperswithcode/blob/main/docs/chat-sandbox-spend-runbook.md",
        "PWC_CHAT_SANDBOX_OPERATOR_USERNAMES": "root",
    }


def staging_chat_alert_values(legacy: dict[str, str]) -> dict[str, str]:
    return chat_alert_values(legacy, environment="staging")


def chat_alert_values(source: dict[str, str], *, environment: str) -> dict[str, str]:
    keys = (
        "PWC_CHAT_SANDBOX_SLACK_WEBHOOK_URL",
        "PWC_CHAT_SANDBOX_ALERT_FALLBACK_WEBHOOK_URL",
    )
    missing = [key for key in keys if key not in source]
    if missing:
        raise ValueError("chat alert environment is missing: " + ", ".join(missing))
    values = {key: decoded_value(source[key]).strip() for key in keys}
    for key, value in values.items():
        parsed = urlsplit(value)
        if (
            not value
            or len(value) > 2000
            or parsed.scheme != "https"
            or not parsed.hostname
        ):
            raise ValueError(f"{key} must be a non-empty HTTPS webhook URL")
    if values[keys[0]] == values[keys[1]]:
        raise ValueError(f"{environment} chat alert webhooks must be distinct")
    return values


def production_chat_preparation_values(
    source: dict[str, str],
    current_production: dict[str, str],
    current_staging: dict[str, str],
) -> dict[str, str]:
    """Build a validated, non-loaded production chat preparation bundle."""

    required = {
        "MODAL_TOKEN_ID",
        "MODAL_TOKEN_SECRET",
        "PWC_CHAT_SANDBOX_BUDGET_ATTESTATION",
        "PWC_CHAT_SANDBOX_MODAL_WORKSPACE",
        "PWC_CHAT_SANDBOX_MODAL_OWNER_USERNAME",
        "PWC_CHAT_SANDBOX_OPERATOR_USERNAMES",
    }
    missing = sorted(required - source.keys())
    if missing:
        raise ValueError(
            "production chat environment is missing: " + ", ".join(missing)
        )
    protected = {key: decoded_value(source[key]).strip() for key in required}
    empty = sorted(key for key, value in protected.items() if not value)
    if empty:
        raise ValueError("production chat environment is empty: " + ", ".join(empty))
    forbidden_openrouter = sorted(
        key
        for key in (
            "PWC_CHAT_OPENROUTER_API_KEY",
            "PWC_CHAT_OPENROUTER_CREDENTIAL_KEYRING",
            "PWC_CHAT_OPENROUTER_USER_TRACKING_SECRET",
        )
        if key in source and decoded_value(source[key]).strip()
    )
    if forbidden_openrouter:
        raise ValueError(
            "production chat preparation prohibits: " + ", ".join(forbidden_openrouter)
        )
    workspace = protected["PWC_CHAT_SANDBOX_MODAL_WORKSPACE"]
    expected_attestation = f"modal-workspace-{workspace}-250-production-starter-v1"
    if protected["PWC_CHAT_SANDBOX_BUDGET_ATTESTATION"] != expected_attestation:
        raise ValueError(
            "PWC_CHAT_SANDBOX_BUDGET_ATTESTATION does not match the production policy"
        )
    return {
        **protected,
        **production_title_values(source, current_production, current_staging),
        **chat_alert_values(source, environment="production"),
        **staging_chat_capacity_values(),
        "PWC_CHAT_ENABLED": "true",
        "PWC_CHAT_NEW_CHAT_MODAL_PERCENTAGE": "100",
        "PWC_CHAT_PUBLIC_ADMISSION_ENABLED": "false",
        "PWC_CHAT_SANDBOX_ADMISSION_ENABLED": "false",
        "PWC_CHAT_BLANK_POOL_ENABLED": "false",
        "PWC_CHAT_PERSISTENT_WORKER_ENABLED": "true",
        "PWC_CHAT_WORKSPACE_SNAPSHOTS_ENABLED": "false",
        "PWC_CHAT_GATEWAY_URL": (
            "https://chat-gateway.paperswithcode.co/api/internal/chat-gateway"
        ),
        "PWC_CHAT_HF_BILL_TO": "huggingface",
        "PWC_CHAT_OPENROUTER_SERVER_FUNDED_ENABLED": "false",
        "PWC_CHAT_SANDBOX_WARNING_MICROUSD": "75000000",
        "PWC_CHAT_SANDBOX_SPEND_ENFORCEMENT_ENABLED": "true",
        "PWC_CHAT_SANDBOX_PROVIDER_MODE": "starter_workspace",
        "PWC_CHAT_SANDBOX_BUDGET_ATTESTATION": expected_attestation,
        "PWC_CHAT_SANDBOX_APPLICATION_CAP_MICROUSD": "100000000",
        "PWC_CHAT_SANDBOX_ENVIRONMENT_CAP_MICROUSD": "0",
        "PWC_CHAT_SANDBOX_WORKSPACE_CAP_MICROUSD": "250000000",
        "PWC_CHAT_SANDBOX_MODAL_ENVIRONMENT": "pwc-chat-production",
        "MODAL_ENVIRONMENT": "pwc-chat-production",
        "PWC_CHAT_SANDBOX_WATCHDOG_SECONDS": "15",
        "PWC_CHAT_SANDBOX_DRAIN_GRACE_SECONDS": "30",
        "PWC_CHAT_SANDBOX_TERMINATION_GRACE_SECONDS": "30",
        "PWC_CHAT_SANDBOX_RECONCILIATION_ALLOWANCE_MICROUSD": "1000000",
        "PWC_CHAT_SANDBOX_RECONCILIATION_INTERVAL_SECONDS": "3600",
        "PWC_CHAT_SANDBOX_RECONCILIATION_STALE_SECONDS": "7200",
        "PWC_CHAT_OPERATIONAL_ALERTS_ENABLED": "true",
        "PWC_CHAT_PROVIDER_ALERT_WINDOW_SECONDS": "300",
        "PWC_CHAT_PROVIDER_ALERT_MIN_FAILURES": "5",
        "PWC_CHAT_PROVIDER_ALERT_FAILURE_PERCENT": "50",
        "PWC_CHAT_SANDBOX_RUNBOOK_URL": (
            "https://github.com/huggingface/paperswithcode/blob/main/"
            "docs/chat-sandbox-spend-runbook.md"
        ),
    }


def production_modal_profile_source(
    source: dict[str, str],
    config_path: Path,
    profile: str,
) -> dict[str, str]:
    """Import one protected Modal profile without exposing or duplicating it."""

    if not config_path.is_file():
        raise ValueError("Modal profile configuration is missing")
    if config_path.stat().st_mode & 0o077:
        raise ValueError("Modal profile configuration must not be group/world readable")
    try:
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ValueError("Modal profile configuration is invalid") from error
    selected = config.get(profile)
    if not isinstance(selected, dict):
        raise ValueError("requested Modal profile is missing")
    values = {
        "MODAL_TOKEN_ID": selected.get("token_id"),
        "MODAL_TOKEN_SECRET": selected.get("token_secret"),
    }
    if any(
        not isinstance(value, str) or not value.strip() for value in values.values()
    ):
        raise ValueError("requested Modal profile has incomplete credentials")
    normalized = {key: value.strip() for key, value in values.items()}
    for key, value in normalized.items():
        existing = decoded_value(source[key]).strip() if key in source else ""
        if existing and existing != value:
            raise ValueError(f"{key} conflicts with the requested Modal profile")
    return assign(source, normalized)


def production_chat_install_values(
    sealed: dict[str, str],
    current_production: dict[str, str],
    current_staging: dict[str, str],
) -> dict[str, str]:
    """Revalidate the sealed bundle before a separately authorized install."""

    if not sealed:
        raise ValueError("sealed production chat preparation is missing")
    values = production_chat_preparation_values(
        sealed,
        current_production,
        current_staging,
    )
    normalized = {key: decoded_value(line).strip() for key, line in sealed.items()}
    unexpected = sorted(set(normalized) - set(values))
    if unexpected:
        raise ValueError(
            "sealed production chat preparation contains unexpected keys: "
            + ", ".join(unexpected)
        )
    mismatched = sorted(
        key for key, value in values.items() if normalized.get(key) != value
    )
    if mismatched:
        raise ValueError(
            "sealed production chat preparation is incomplete or stale: "
            + ", ".join(mismatched)
        )
    return values


def production_codex_values(legacy: dict[str, str], namespace: str) -> dict[str, str]:
    return {
        # The immutable release launcher overrides these non-secret capability
        # flags from release.json, preserving rollback compatibility.
        "PWC_CODEX_ADD_EVALS_ENABLED": "false",
        "PWC_CODEX_ENRICH_PAPER_ENABLED": "false",
        "PWC_CODEX_JOBS_ENABLED": "false",
        "PWC_CODEX_JOBS_NAMESPACE": namespace,
        "PWC_CODEX_JOBS_OPENAI_API_KEY": decoded_value(legacy["OPENAI_API_KEY"]),
        "PWC_CODEX_JOBS_TOKEN": decoded_value(legacy["PWC_HF_TOKEN"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy-env", type=Path, required=True)
    parser.add_argument("--codex-jobs-namespace")
    parser.add_argument("--production-codex-only", action="store_true")
    parser.add_argument("--staging-codex-too", action="store_true")
    parser.add_argument("--staging-langfuse-only", action="store_true")
    parser.add_argument("--staging-title-only", action="store_true")
    parser.add_argument("--staging-openrouter-only", action="store_true")
    parser.add_argument("--staging-openrouter-disable-only", action="store_true")
    parser.add_argument("--staging-openrouter-secrets-rotate-only", action="store_true")
    parser.add_argument("--staging-chat-capacity-only", action="store_true")
    parser.add_argument("--staging-chat-alerts-only", action="store_true")
    parser.add_argument("--staging-chat-pool-enable-only", action="store_true")
    parser.add_argument("--staging-chat-pool-disable-only", action="store_true")
    parser.add_argument("--staging-web-search-only", action="store_true")
    parser.add_argument("--staging-github-only", action="store_true")
    parser.add_argument("--production-chat-seal-only", action="store_true")
    parser.add_argument("--production-chat-install-only", action="store_true")
    parser.add_argument("--modal-profile")
    parser.add_argument(
        "--modal-profile-config",
        type=Path,
        default=Path("/root/.modal.toml"),
    )
    parser.add_argument("--confirm")
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("run through sudo")
    legacy = read_lines(args.legacy_env)
    if args.modal_profile and not args.production_chat_seal_only:
        parser.error("--modal-profile requires --production-chat-seal-only")
    if args.production_chat_seal_only or args.production_chat_install_only:
        other_modes = (
            args.production_codex_only,
            args.staging_codex_too,
            args.staging_langfuse_only,
            args.staging_title_only,
            args.staging_openrouter_only,
            args.staging_openrouter_disable_only,
            args.staging_openrouter_secrets_rotate_only,
            args.staging_chat_capacity_only,
            args.staging_chat_alerts_only,
            args.staging_chat_pool_enable_only,
            args.staging_chat_pool_disable_only,
            args.staging_web_search_only,
            args.staging_github_only,
        )
        if any(other_modes) or (
            args.production_chat_seal_only and args.production_chat_install_only
        ):
            parser.error(
                "production chat preparation modes cannot be combined with other modes"
            )
        if args.production_chat_install_only:
            confirmation = "INSTALL_PRODUCTION_CHAT_PREPARATION"
            if args.confirm != confirmation:
                parser.error(f"--confirm must be {confirmation}")
            current_production = read_lines(CONFIG_ROOT / "production.env")
            current_staging = read_lines(CONFIG_ROOT / "staging.env")
            try:
                values = production_chat_install_values(
                    read_lines(PRODUCTION_CHAT_SEALED_CONFIG),
                    current_production,
                    current_staging,
                )
            except ValueError as error:
                parser.error(str(error))
            write_env(
                CONFIG_ROOT / "production.env",
                assign(current_production, values),
                "pwc-production",
            )
            print(
                "installed sealed production chat preparation; "
                "no service was restarted and admission remains disabled"
            )
            return 0
        confirmation = "SEAL_PRODUCTION_CHAT_PREPARATION"
        if args.confirm != confirmation:
            parser.error(f"--confirm must be {confirmation}")
        if args.modal_profile:
            try:
                legacy = production_modal_profile_source(
                    legacy,
                    args.modal_profile_config,
                    args.modal_profile,
                )
            except ValueError as error:
                parser.error(str(error))
        try:
            values = production_chat_preparation_values(
                legacy,
                read_lines(CONFIG_ROOT / "production.env"),
                read_lines(CONFIG_ROOT / "staging.env"),
            )
        except ValueError as error:
            parser.error(str(error))
        write_env(
            PRODUCTION_CHAT_SEALED_CONFIG,
            assign({}, values),
            "pwc-production",
        )
        print(
            "sealed non-loaded production chat preparation; "
            "the active production environment was not changed"
        )
        return 0
    if args.staging_github_only:
        other_modes = (
            args.production_codex_only,
            args.staging_codex_too,
            args.staging_langfuse_only,
            args.staging_title_only,
            args.staging_openrouter_only,
            args.staging_openrouter_disable_only,
            args.staging_openrouter_secrets_rotate_only,
            args.staging_chat_capacity_only,
            args.staging_chat_alerts_only,
            args.staging_chat_pool_enable_only,
            args.staging_chat_pool_disable_only,
            args.staging_web_search_only,
            args.production_chat_seal_only,
            args.production_chat_install_only,
        )
        if any(other_modes):
            parser.error("--staging-github-only cannot be combined with other modes")
        try:
            values = staging_github_values(legacy)
        except ValueError as error:
            parser.error(str(error))
        staging = assign(read_lines(CONFIG_ROOT / "staging.env"), values)
        write_env(CONFIG_ROOT / "staging.env", staging, "pwc-staging")
        print("installed staging GitHub credential")
        return 0
    if args.staging_web_search_only:
        other_modes = (
            args.production_codex_only,
            args.staging_codex_too,
            args.staging_langfuse_only,
            args.staging_title_only,
            args.staging_openrouter_only,
            args.staging_openrouter_disable_only,
            args.staging_openrouter_secrets_rotate_only,
            args.staging_chat_capacity_only,
            args.staging_chat_alerts_only,
            args.staging_chat_pool_enable_only,
            args.staging_chat_pool_disable_only,
            args.production_chat_seal_only,
        )
        if any(other_modes):
            parser.error(
                "--staging-web-search-only cannot be combined with other modes"
            )
        try:
            values = staging_web_search_values(legacy)
        except ValueError as error:
            parser.error(str(error))
        staging = assign(read_lines(CONFIG_ROOT / "staging.env"), values)
        write_env(CONFIG_ROOT / "staging.env", staging, "pwc-staging")
        print("installed staging web-search configuration")
        return 0
    if args.staging_title_only:
        if any(
            (
                args.production_codex_only,
                args.staging_codex_too,
                args.staging_langfuse_only,
                args.staging_openrouter_only,
                args.staging_openrouter_disable_only,
                args.staging_openrouter_secrets_rotate_only,
                args.staging_chat_capacity_only,
                args.staging_chat_alerts_only,
                args.staging_chat_pool_enable_only,
                args.staging_chat_pool_disable_only,
            )
        ):
            parser.error("--staging-title-only cannot be combined with other modes")
        try:
            values = staging_title_values(
                legacy,
                read_lines(CONFIG_ROOT / "staging.env"),
                read_lines(CONFIG_ROOT / "production.env"),
            )
        except ValueError as error:
            parser.error(str(error))
        staging = assign(read_lines(CONFIG_ROOT / "staging.env"), values)
        write_env(CONFIG_ROOT / "staging.env", staging, "pwc-staging")
        print("installed isolated staging title credential")
        return 0
    if args.staging_chat_pool_enable_only or args.staging_chat_pool_disable_only:
        if (
            args.staging_chat_pool_enable_only and args.staging_chat_pool_disable_only
        ) or any(
            (
                args.production_codex_only,
                args.staging_codex_too,
                args.staging_langfuse_only,
                args.staging_openrouter_only,
                args.staging_openrouter_disable_only,
                args.staging_openrouter_secrets_rotate_only,
                args.staging_chat_capacity_only,
                args.staging_chat_alerts_only,
            )
        ):
            parser.error(
                "staging chat pool enable/disable cannot be combined with other modes"
            )
        enabled = args.staging_chat_pool_enable_only
        staging = assign(
            read_lines(CONFIG_ROOT / "staging.env"),
            staging_chat_pool_values(enabled=enabled),
        )
        write_env(CONFIG_ROOT / "staging.env", staging, "pwc-staging")
        print(f"{'enabled' if enabled else 'disabled'} staging chat blank pool")
        return 0
    if args.staging_openrouter_secrets_rotate_only:
        if any(
            (
                args.production_codex_only,
                args.staging_codex_too,
                args.staging_langfuse_only,
                args.staging_openrouter_only,
                args.staging_openrouter_disable_only,
                args.staging_chat_capacity_only,
                args.staging_chat_alerts_only,
            )
        ):
            parser.error(
                "--staging-openrouter-secrets-rotate-only cannot be combined "
                "with other modes"
            )
        try:
            staging = assign(
                read_lines(CONFIG_ROOT / "staging.env"),
                rotate_staging_openrouter_secret_values(
                    read_lines(CONFIG_ROOT / "staging.env")
                ),
            )
        except ValueError as error:
            parser.error(str(error))
        write_env(CONFIG_ROOT / "staging.env", staging, "pwc-staging")
        print("rotated staging OpenRouter encryption and tracking secrets")
        return 0
    if args.staging_chat_capacity_only:
        if (
            args.production_codex_only
            or args.staging_codex_too
            or args.staging_langfuse_only
            or args.staging_openrouter_only
            or args.staging_openrouter_disable_only
            or args.staging_chat_alerts_only
        ):
            parser.error(
                "--staging-chat-capacity-only cannot be combined with other modes"
            )
        existing = read_lines(CONFIG_ROOT / "staging.env")
        staging = assign(existing, staging_chat_capacity_configuration(existing))
        write_env(CONFIG_ROOT / "staging.env", staging, "pwc-staging")
        print("configured qualified staging chat capacity")
        return 0
    if args.staging_chat_alerts_only:
        if (
            args.production_codex_only
            or args.staging_codex_too
            or args.staging_langfuse_only
            or args.staging_openrouter_only
            or args.staging_openrouter_disable_only
        ):
            parser.error(
                "--staging-chat-alerts-only cannot be combined with other modes"
            )
        try:
            values = staging_chat_alert_values(legacy)
        except ValueError as error:
            parser.error(str(error))
        staging = assign(read_lines(CONFIG_ROOT / "staging.env"), values)
        write_env(CONFIG_ROOT / "staging.env", staging, "pwc-staging")
        print("installed staging chat alert destinations")
        return 0
    if args.staging_openrouter_disable_only:
        if (
            args.production_codex_only
            or args.staging_codex_too
            or args.staging_langfuse_only
            or args.staging_openrouter_only
            or args.staging_chat_alerts_only
        ):
            parser.error(
                "--staging-openrouter-disable-only cannot be combined with other modes"
            )
        staging = without_staging_openrouter(read_lines(CONFIG_ROOT / "staging.env"))
        write_env(CONFIG_ROOT / "staging.env", staging, "pwc-staging")
        print("disabled server-funded staging OpenRouter chat")
        return 0
    if args.staging_openrouter_only:
        if (
            args.production_codex_only
            or args.staging_codex_too
            or args.staging_langfuse_only
            or args.staging_chat_alerts_only
        ):
            parser.error(
                "--staging-openrouter-only cannot be combined with Codex modes"
            )
        try:
            values = staging_openrouter_values(legacy)
        except ValueError as error:
            parser.error(str(error))
        staging = assign(read_lines(CONFIG_ROOT / "staging.env"), values)
        write_env(CONFIG_ROOT / "staging.env", staging, "pwc-staging")
        print("installed staging OpenRouter chat credential")
        return 0
    if args.staging_langfuse_only:
        if (
            args.production_codex_only
            or args.staging_codex_too
            or args.staging_openrouter_only
            or args.staging_chat_alerts_only
        ):
            parser.error("--staging-langfuse-only cannot be combined with Codex modes")
        try:
            values = staging_langfuse_values(legacy)
        except ValueError as error:
            parser.error(str(error))
        staging = assign(read_lines(CONFIG_ROOT / "staging.env"), values)
        write_env(CONFIG_ROOT / "staging.env", staging, "pwc-staging")
        print("installed staging Langfuse credentials")
        return 0
    if not args.codex_jobs_namespace:
        parser.error("--codex-jobs-namespace is required")
    required = {
        "PWC_DB_HOST",
        "PWC_DB_NAME",
        "PWC_DB_PASSWORD",
        "PWC_DB_PORT",
        "PWC_DB_USER",
        "PWC_HF_OAUTH_CLIENT_ID",
        "PWC_HF_OAUTH_CLIENT_SECRET",
        "PWC_HF_TOKEN",
        "PWC_JWT_SECRET",
        "PWC_GITHUB_TOKEN",
        "PWC_OPENROUTER_API_KEY",
        "OPENAI_API_KEY",
    }
    missing = sorted(required - legacy.keys())
    if missing:
        parser.error("legacy environment is missing: " + ", ".join(missing))

    if args.production_codex_only:
        production = assign(
            read_lines(CONFIG_ROOT / "production.env"),
            production_codex_values(legacy, args.codex_jobs_namespace),
        )
        write_env(CONFIG_ROOT / "production.env", production, "pwc-production")
        if args.staging_codex_too:
            staging = assign(
                read_lines(CONFIG_ROOT / "staging.env"),
                {
                    **production_codex_values(legacy, args.codex_jobs_namespace),
                    "PWC_CODEX_JOBS_API_URL": (
                        "https://staging.paperswithcode.co/api/v1"
                    ),
                    "PWC_GITHUB_TOKEN": decoded_value(legacy["PWC_GITHUB_TOKEN"]),
                },
            )
            write_env(CONFIG_ROOT / "staging.env", staging, "pwc-staging")
            print("installed production and staging Codex credentials")
        else:
            print("installed production Codex credentials")
        return 0
    if args.staging_codex_too:
        parser.error("--staging-codex-too requires --production-codex-only")

    current_production = read_lines(CONFIG_ROOT / "production.env")
    current_staging = read_lines(CONFIG_ROOT / "staging.env")
    current_cron = read_lines(CONFIG_ROOT / "production-cron.env")
    staging_db_password = existing_or_random(current_staging, "PWC_DB_PASSWORD")
    staging_jwt = existing_or_random(current_staging, "PWC_JWT_SECRET")
    backup_db_password = existing_or_random(
        current_cron, "PWC_POSTGRES_BACKUP_DB_PASSWORD"
    )
    production_jwt = decoded_value(legacy["PWC_JWT_SECRET"])
    session_private_key, session_public_key = shared_session_keys(
        current_production, current_staging
    )
    oauth_credential_secret = shared_oauth_credential_secret(
        current_production, current_staging
    )
    shared_auth = {
        "PWC_AUTH_AUTHORITY_ORIGIN": "https://paperswithcode.co",
        "PWC_AUTH_RETURN_ORIGINS": (
            "https://paperswithcode.co,https://staging.paperswithcode.co"
        ),
        "PWC_SHARED_SESSION_COOKIE_DOMAIN": ".paperswithcode.co",
        "PWC_SHARED_SESSION_COOKIE_NAME": "pwc_shared_session",
        "PWC_SESSION_VERIFICATION_PUBLIC_KEY": session_public_key,
        "PWC_HF_OAUTH_CREDENTIAL_SECRET": oauth_credential_secret,
    }
    shared_roles = shared_role_values(current_production, current_staging, legacy)

    production = assign(
        legacy,
        {
            **shared_auth,
            **shared_roles,
            "PWC_CATALOG_MUTATIONS_ENABLED": "true",
            "PWC_CONTRIBUTOR_DIRECT_EDITS_ENABLED": "false",
            "PWC_CHAT_ENABLED": "false",
            "PWC_CHAT_AGENT_CWD": ("/var/lib/paperswithcode/production/chat-agent"),
            "PWC_CHAT_RECOVERY_SPOOL_DIR": (
                "/var/lib/paperswithcode/production/chat-recovery-spool"
            ),
            "PWC_CHAT_REQUIRE_AUTH": "true",
            "PWC_CODEX_ADD_EVALS_SPOOL_DIR": (
                "/var/lib/paperswithcode/production/recovery-spool"
            ),
            **production_codex_values(legacy, args.codex_jobs_namespace),
            "PWC_CRON_ENABLED": "true",
            "PWC_CRON_LOCK_DIR": "/var/lib/paperswithcode/production/cron-locks",
            "PWC_CRON_LOG_DIR": "/var/lib/paperswithcode/production/cron-logs",
            "PWC_DB_SEARCH_PATH": "public",
            "PWC_ENVIRONMENT": "production",
            "PWC_FRONTEND_DIST_DIR": (
                "/srv/paperswithcode/environments/production/current/frontend-dist"
            ),
            "PWC_RUNTIME_DATA_DIR": "/var/lib/paperswithcode/production",
            "PWC_SESSION_COOKIE_DOMAIN": "",
            "PWC_SESSION_COOKIE_NAME": "pwc_session",
            "PWC_SESSION_SIGNING_PRIVATE_KEY": session_private_key,
            "PWC_THUMBNAIL_CACHE_DIR": ("/var/lib/paperswithcode/shared/thumbnails"),
            "PWC_THUMBNAIL_MUTATIONS_ENABLED": "false",
            "PWC_THUMBNAIL_TEMP_CACHE_DIR": (
                "/var/lib/paperswithcode/shared/thumbnails"
            ),
            "UVICORN_HOST": "127.0.0.1",
            "UVICORN_PORT": "8000",
            "WEB_CONCURRENCY": "2",
        },
    )
    # The optional hot-queue credential is automation-only. Keep it out of the
    # application environment and install it only in the CRON overlay below.
    production = without_cron_only_credentials(production)

    staging = {
        key: line
        for key, line in legacy.items()
        if key not in STAGING_EXCLUDED_KEYS
        and not key.startswith(STAGING_EXCLUDED_PREFIXES)
    }
    staging.update(staging_runtime_passthrough(current_staging))
    staging = assign(
        staging,
        {
            **shared_auth,
            **shared_roles,
            **production_codex_values(legacy, args.codex_jobs_namespace),
            "PWC_CATALOG_MUTATIONS_ENABLED": "false",
            "PWC_CONTRIBUTOR_DIRECT_EDITS_ENABLED": "false",
            "PWC_CHAT_AGENT_CWD": "/var/lib/paperswithcode/staging/chat-agent",
            "PWC_CHAT_ENABLED": "true",
            "PWC_CHAT_GATEWAY_URL": (
                "https://chat-gateway-staging.paperswithcode.co/"
                "api/internal/chat-gateway"
            ),
            "PWC_CHAT_HF_BILL_TO": "huggingface",
            "PWC_CHAT_OPENROUTER_API_KEY": decoded_value(
                legacy["PWC_OPENROUTER_API_KEY"]
            ),
            **staging_openrouter_accounting_values(current_staging),
            "PWC_CHAT_OPENROUTER_SERVER_FUNDED_ENABLED": "true",
            "PWC_CHAT_RECOVERY_SPOOL_DIR": (
                "/var/lib/paperswithcode/staging/chat-recovery-spool"
            ),
            "PWC_CHAT_REQUIRE_AUTH": "true",
            "PWC_CODEX_ADD_EVALS_ENABLED": "false",
            "PWC_CODEX_ADD_EVALS_SPOOL_DIR": (
                "/var/lib/paperswithcode/staging/recovery-spool"
            ),
            "PWC_CODEX_ADD_EVALS_WORK_DIR": (
                "/var/lib/paperswithcode/staging/codex-work"
            ),
            "PWC_CODEX_JOBS_API_URL": ("https://staging.paperswithcode.co/api/v1"),
            "PWC_CRON_ENABLED": "false",
            "PWC_CRON_LOCK_DIR": "/var/lib/paperswithcode/staging/cron-locks",
            "PWC_CRON_LOG_DIR": "/var/lib/paperswithcode/staging/cron-logs",
            "PWC_DB_PASSWORD": staging_db_password,
            "PWC_DB_SEARCH_PATH": "staging,public",
            "PWC_DB_USER": "pwc_staging",
            "PWC_ENVIRONMENT": "staging",
            "PWC_FRONTEND_DIST_DIR": (
                "/srv/paperswithcode/environments/staging/current/frontend-dist"
            ),
            "PWC_GITHUB_TOKEN": decoded_value(legacy["PWC_GITHUB_TOKEN"]),
            "PWC_JWT_SECRET": staging_jwt,
            "PWC_PRODUCTION_JWT_FINGERPRINT": hashlib.sha256(
                production_jwt.encode()
            ).hexdigest(),
            "PWC_RUNTIME_DATA_DIR": "/var/lib/paperswithcode/staging",
            "PWC_SESSION_COOKIE_DOMAIN": "",
            "PWC_SESSION_COOKIE_NAME": "pwc_staging_session",
            "PWC_THUMBNAIL_CACHE_DIR": ("/var/lib/paperswithcode/shared/thumbnails"),
            "PWC_THUMBNAIL_MUTATIONS_ENABLED": "false",
            "PWC_THUMBNAIL_TEMP_CACHE_DIR": (
                "/var/lib/paperswithcode/shared/thumbnails"
            ),
            "UVICORN_HOST": "127.0.0.1",
            "UVICORN_PORT": "8001",
            "WEB_CONCURRENCY": "1",
        },
    )
    staging = without_cron_only_credentials(staging)

    cron = cron_passthrough_credentials(legacy, current_cron)
    cron.update(
        {
            key: line
            for key, line in current_cron.items()
            if key.startswith("PWC_TRENDING_PIN_")
        }
    )
    cron = assign(
        cron,
        {
            "HF_HOME": "/var/lib/paperswithcode/production/hf-cache",
            # Bucket uploads use Xet for database-sized objects. The
            # organization-authorized Hub token is required for that path.
            "PWC_POSTGRES_BACKUP_HF_TOKEN": decoded_value(legacy["PWC_HF_TOKEN"]),
            "PWC_POSTGRES_BACKUP_DB_PASSWORD": backup_db_password,
            "PWC_POSTGRES_BACKUP_DB_USER": "pwc_backup",
            "PWC_POSTGRES_BACKUP_LOCAL_KEEP_COUNT": "3",
            "PWC_POSTGRES_BACKUP_REMOTE_KEEP_COUNT": "30",
        },
    )

    write_env(CONFIG_ROOT / "production.env", production, "pwc-production")
    write_env(CONFIG_ROOT / "staging.env", staging, "pwc-staging")
    write_env(CONFIG_ROOT / "production-cron.env", cron, "pwc-cron")
    production_group = grp.getgrnam("pwc-production").gr_name
    cron_user = pwd.getpwnam("pwc-cron").pw_name
    subprocess.run(
        ["usermod", "--append", "--groups", production_group, cron_user],
        check=True,
    )
    print("installed production, staging, and CRON environment files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
