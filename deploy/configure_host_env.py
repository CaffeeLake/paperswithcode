#!/usr/bin/env python3
"""Create the two deployed app environments and the CRON credential overlay."""

from __future__ import annotations

import argparse
import ast
import base64
import grp
import hashlib
import os
import pwd
import secrets
import subprocess
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

CONFIG_ROOT = Path("/etc/paperswithcode")

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
    "PWC_CHAT_DEFAULT_BACKEND",
    "PWC_CHAT_LANGFUSE_ENABLED",
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
    "PWC_CHAT_PERSISTENT_SANDBOX_LIFETIME_SECONDS",
    "PWC_CHAT_PERSISTENT_WORKER_ENABLED",
    "PWC_CHAT_PWC_CLI_VERSION",
    "PWC_CHAT_SANDBOX_CPU",
    "PWC_CHAT_SANDBOX_CPU_LIMIT",
    "PWC_CHAT_SANDBOX_MEMORY_LIMIT_MIB",
    "PWC_CHAT_SANDBOX_MEMORY_MIB",
    "PWC_CHAT_SANDBOX_TOTAL_LIVE_CAP",
    "PWC_CHAT_SYSTEM_PROMPT_SHA256",
    "PWC_CHAT_WORKER_CONTRACT_VERSION",
    "PWC_CHAT_WORKER_READY_TIMEOUT_SECONDS",
    "PWC_CHAT_WORKSPACE_SNAPSHOTS_ENABLED",
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


def staging_openrouter_values(legacy: dict[str, str]) -> dict[str, str]:
    key = "PWC_OPENROUTER_API_KEY"
    if key not in legacy:
        raise ValueError(f"legacy environment is missing: {key}")
    return {"PWC_CHAT_OPENROUTER_API_KEY": decoded_value(legacy[key])}


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
    parser.add_argument("--staging-openrouter-only", action="store_true")
    parser.add_argument("--staging-openrouter-disable-only", action="store_true")
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("run through sudo")
    legacy = read_lines(args.legacy_env)
    if args.staging_openrouter_disable_only:
        if (
            args.production_codex_only
            or args.staging_codex_too
            or args.staging_langfuse_only
            or args.staging_openrouter_only
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
    shared_auth = {
        "PWC_AUTH_AUTHORITY_ORIGIN": "https://paperswithcode.co",
        "PWC_AUTH_RETURN_ORIGINS": (
            "https://paperswithcode.co,https://staging.paperswithcode.co"
        ),
        "PWC_SHARED_SESSION_COOKIE_DOMAIN": ".paperswithcode.co",
        "PWC_SHARED_SESSION_COOKIE_NAME": "pwc_shared_session",
        "PWC_SESSION_VERIFICATION_PUBLIC_KEY": session_public_key,
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
