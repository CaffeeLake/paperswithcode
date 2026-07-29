"""Fail-closed validation for deployed environment and release configuration."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from sqlalchemy import text

from backend.config import Settings
from backend.services.chat_runtime_contract import (
    dedicated_gateway_hostname,
    require_immutable_image_id,
)

_ASSET_RE = re.compile(
    r"""(?:src|href)=["'](?P<path>/assets/[^"'?#]+\.(?:js|css))(?:[?#][^"']*)?["']"""
)
_RELEASE_ROOT = Path("/srv/paperswithcode/releases")


def _resolved_absolute(name: str, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise RuntimeError(f"PWC_{name} must be absolute in deployed environments")
    resolved = path.resolve(strict=False)
    if resolved == _RELEASE_ROOT or _RELEASE_ROOT in resolved.parents:
        raise RuntimeError(f"PWC_{name} must be outside immutable releases")
    return resolved


def validate_frontend_dist(settings: Settings) -> dict[str, bool]:
    dist = Path(settings.frontend_dist_dir)
    if not dist.is_absolute():
        raise RuntimeError("PWC_FRONTEND_DIST_DIR must be absolute")
    index = dist / "index.html"
    if not index.is_file():
        raise RuntimeError(f"built frontend shell is missing: {index}")
    html = index.read_text(encoding="utf-8")
    if "/src/main.tsx" in html:
        raise RuntimeError("deployed frontend shell references /src/main.tsx")
    assets = {
        match.group("path").removeprefix("/") for match in _ASSET_RE.finditer(html)
    }
    if not any(asset.endswith(".js") for asset in assets):
        raise RuntimeError("deployed frontend shell has no module JavaScript asset")
    for asset in assets:
        candidate = (dist / asset).resolve()
        if dist.resolve() not in candidate.parents or not candidate.is_file():
            raise RuntimeError(
                f"frontend asset is missing or escapes the bundle: {asset}"
            )

    features_path = dist / "features.json"
    if not features_path.is_file():
        raise RuntimeError("frontend features.json is missing")
    features = json.loads(features_path.read_text(encoding="utf-8"))
    expected_features = {
        "chat": settings.chat_enabled,
        "codex_add_evals": (
            settings.codex_jobs_enabled and settings.codex_add_evals_enabled
        ),
        "codex_enrich_paper": (
            settings.codex_jobs_enabled and settings.codex_enrich_paper_enabled
        ),
    }
    if features != expected_features:
        raise RuntimeError(
            "frontend/backend feature mismatch: "
            f"frontend={features!r} backend={expected_features!r}"
        )
    return features


def validate_runtime(settings: Settings) -> dict[str, bool]:
    """Validate deployed paths, auth, feature composition, and writable state."""

    if not settings.is_deployed:
        return {"chat": settings.chat_enabled}
    if settings.environment not in {"production", "staging"}:
        raise RuntimeError("PWC_ENVIRONMENT must be production or staging")
    if not settings.release_id or settings.release_id == "development":
        raise RuntimeError("PWC_RELEASE_ID is required")
    if not settings.jwt_secret:
        raise RuntimeError("PWC_JWT_SECRET is required")
    if settings.session_cookie_domain:
        raise RuntimeError("deployed session cookies must be host-only")
    expected_cookie = {
        "production": "pwc_session",
        "staging": "pwc_staging_session",
    }[settings.environment]
    if settings.session_cookie_name != expected_cookie:
        raise RuntimeError(
            f"PWC_SESSION_COOKIE_NAME must be {expected_cookie!r} for "
            f"{settings.environment}"
        )
    if settings.shared_session_cookie_name != "pwc_shared_session":
        raise RuntimeError(
            "PWC_SHARED_SESSION_COOKIE_NAME must be 'pwc_shared_session'"
        )
    if settings.shared_session_cookie_domain != ".paperswithcode.co":
        raise RuntimeError(
            "PWC_SHARED_SESSION_COOKIE_DOMAIN must be '.paperswithcode.co'"
        )
    if not settings.session_verification_public_key:
        raise RuntimeError("PWC_SESSION_VERIFICATION_PUBLIC_KEY is required")
    try:
        public_bytes = base64.urlsafe_b64decode(
            settings.session_verification_public_key
            + "=" * (-len(settings.session_verification_public_key) % 4)
        )
        Ed25519PublicKey.from_public_bytes(public_bytes)
    except (ValueError, TypeError) as error:
        raise RuntimeError(
            "PWC_SESSION_VERIFICATION_PUBLIC_KEY must be a base64url Ed25519 key"
        ) from error
    if settings.auth_authority_origin != "https://paperswithcode.co":
        raise RuntimeError(
            "PWC_AUTH_AUTHORITY_ORIGIN must be 'https://paperswithcode.co'"
        )
    required_return_origins = {
        "https://paperswithcode.co",
        "https://staging.paperswithcode.co",
    }
    if settings.auth_return_origin_set != required_return_origins:
        raise RuntimeError(
            "PWC_AUTH_RETURN_ORIGINS must contain production and staging origins"
        )

    if not Path(settings.frontend_dist_dir).is_absolute():
        raise RuntimeError("PWC_FRONTEND_DIST_DIR must be absolute")
    writable = {
        "RUNTIME_DATA_DIR": settings.runtime_data_dir,
        "CODEX_ADD_EVALS_SPOOL_DIR": settings.codex_add_evals_spool_dir,
        "CHAT_AGENT_CWD": settings.chat_agent_cwd,
        "CHAT_RECOVERY_SPOOL_DIR": settings.chat_recovery_spool_dir,
    }
    for name, value in writable.items():
        path = _resolved_absolute(name, value)
        if not path.is_dir() or not os.access(path, os.W_OK | os.X_OK):
            raise RuntimeError(f"PWC_{name} must be an existing writable directory")

    for name, value in {
        "CRON_LOG_DIR": settings.cron_log_dir,
        "CRON_LOCK_DIR": settings.cron_lock_dir,
    }.items():
        path = _resolved_absolute(name, value)
        if not path.is_dir() or not os.access(path, os.R_OK | os.X_OK):
            raise RuntimeError(f"PWC_{name} must be an existing readable directory")

    thumbnail_store = _resolved_absolute(
        "THUMBNAIL_TEMP_CACHE_DIR", settings.thumbnail_temp_cache_dir
    )
    if not thumbnail_store.is_dir() or not os.access(thumbnail_store, os.R_OK):
        raise RuntimeError(
            "PWC_THUMBNAIL_CACHE_DIR must be an existing readable directory"
        )

    if settings.codex_jobs_enabled:
        if (
            not settings.codex_jobs_namespace
            or not settings.codex_jobs_token
            or not settings.codex_jobs_openai_api_key
            or not settings.github_token
        ):
            raise RuntimeError(
                "Codex jobs require namespace, HF, OpenAI, and GitHub credentials"
            )
        expected_api_url = {
            "production": "https://paperswithcode.co/api/v1",
            "staging": "https://staging.paperswithcode.co/api/v1",
        }[settings.environment]
        if settings.codex_jobs_api_url.rstrip("/") != expected_api_url:
            raise RuntimeError(
                f"{settings.environment} Codex jobs must target {expected_api_url}"
            )

    if settings.environment == "production":
        if not settings.session_signing_private_key:
            raise RuntimeError("production requires PWC_SESSION_SIGNING_PRIVATE_KEY")
        try:
            private_bytes = base64.urlsafe_b64decode(
                settings.session_signing_private_key
                + "=" * (-len(settings.session_signing_private_key) % 4)
            )
            private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
            derived_public = private_key.public_key().public_bytes(
                serialization.Encoding.Raw,
                serialization.PublicFormat.Raw,
            )
        except (ValueError, TypeError) as error:
            raise RuntimeError(
                "PWC_SESSION_SIGNING_PRIVATE_KEY must be a base64url Ed25519 key"
            ) from error
        if derived_public != public_bytes:
            raise RuntimeError("shared-session signing and verification keys differ")
        if settings.chat_enabled:
            raise RuntimeError(
                "production chat is not authorized by this release policy"
            )
        if not settings.catalog_mutations_enabled or not settings.cron_enabled:
            raise RuntimeError(
                "production catalog mutations and CRON must remain enabled"
            )
        if (
            settings.chat_default_backend != "local_mcp"
            or settings.chat_new_chat_modal_percentage != 0
            or settings.chat_modal_image_version
            or settings.chat_persistent_worker_enabled
            or settings.chat_sandbox_cpu_limit is not None
            or settings.chat_sandbox_memory_limit_mib is not None
        ):
            raise RuntimeError("production contains an active chat runtime descriptor")
    else:
        if settings.session_signing_private_key:
            raise RuntimeError("staging must not have the session signing private key")
        if settings.catalog_mutations_enabled:
            raise RuntimeError("staging catalog mutations must be disabled")
        if settings.cron_enabled:
            raise RuntimeError("staging CRON must be disabled")
        if settings.db_search_path != "staging,public":
            raise RuntimeError("staging database search_path must be staging,public")
        if not settings.production_jwt_fingerprint:
            raise RuntimeError("staging requires PWC_PRODUCTION_JWT_FINGERPRINT")
        fingerprint = hashlib.sha256(settings.jwt_secret.encode()).hexdigest()
        if fingerprint == settings.production_jwt_fingerprint:
            raise RuntimeError("staging must not reuse the production JWT secret")
        if not settings.chat_enabled:
            raise RuntimeError("staging chat feature must be enabled")
        if not all(
            (
                settings.chat_modal_image_version,
                settings.chat_pwc_cli_version,
                settings.chat_worker_contract_version,
                settings.chat_system_prompt_sha256,
            )
        ):
            raise RuntimeError("staging chat runtime descriptor is incomplete")
        try:
            require_immutable_image_id(settings.chat_modal_image_version)
            dedicated_gateway_hostname(settings.chat_gateway_url)
        except ValueError as error:
            raise RuntimeError(f"staging chat runtime is invalid: {error}") from error
        if not settings.hf_token:
            raise RuntimeError("staging chat model gateway requires an HF token")
        if (
            settings.chat_sandbox_cpu_limit is not None
            and settings.chat_sandbox_cpu_limit < settings.chat_sandbox_cpu
        ):
            raise RuntimeError("staging chat CPU limit is below its request")
        if (
            settings.chat_sandbox_memory_limit_mib is not None
            and settings.chat_sandbox_memory_limit_mib
            < settings.chat_sandbox_memory_mib
        ):
            raise RuntimeError("staging chat memory limit is below its request")
        from backend.chat_sandbox_worker.prompt import sha256 as prompt_sha256

        effective_prompt_hash = prompt_sha256(
            max_turns=settings.chat_max_turns,
            max_calls=settings.chat_max_tool_calls,
            max_searches=settings.chat_max_direct_search_calls,
        )
        if settings.chat_system_prompt_sha256 != effective_prompt_hash:
            raise RuntimeError("staging chat prompt and execution limits disagree")

    manifest_path = Path(settings.frontend_dist_dir).parent / "release.json"
    if not manifest_path.is_file():
        raise RuntimeError("release.json is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    runtime = manifest.get("chat_runtime")
    expected_runtime = {
        "enabled": settings.chat_enabled,
        "new_chat_modal_percentage": settings.chat_new_chat_modal_percentage,
        "default_backend": settings.chat_default_backend,
        "modal_image_version": settings.chat_modal_image_version,
        "pwc_cli_version": settings.chat_pwc_cli_version,
        "worker_contract_version": settings.chat_worker_contract_version,
        "system_prompt_sha256": settings.chat_system_prompt_sha256,
    }
    if runtime != expected_runtime or manifest.get("release_id") != settings.release_id:
        raise RuntimeError("running chat runtime differs from the release manifest")

    if settings.thumbnail_mutations_enabled:
        raise RuntimeError("deployed web services must not mutate thumbnails")
    return validate_frontend_dist(settings)


def validate_chat_schema(db) -> None:
    """Fail readiness when the additive staging chat runtime schema is absent."""

    if db.execute(text("SHOW transaction_read_only")).scalar_one() != "off":
        raise RuntimeError("staging chat database connection is read-only")
    rows = dict(
        db.execute(
            text(
                """
                SELECT name, to_regclass(name)::text
                FROM (VALUES
                    ('chat_sessions'),
                    ('chat_messages'),
                    ('chat_shares'),
                    ('chat_sandbox_leases'),
                    ('chat_turn_capabilities'),
                    ('chat_turn_latency')
                ) AS required(name)
                """
            )
        ).all()
    )
    missing = [name for name, resolved in rows.items() if resolved is None]
    required_columns = db.execute(
        text(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE (table_name, column_name) IN (
                ('chat_sessions', 'execution_backend'),
                ('chat_messages', 'finish_reason'),
                ('chat_messages', 'prepared_fork_sdk_session_id'),
                ('chat_messages', 'prepared_fork_sdk_project_key'),
                ('chat_shares', 'snapshot_version'),
                ('chat_shares', 'messages'),
                ('chat_turn_latency', 'request_id'),
                ('chat_turn_latency', 'terminal_status'),
                ('chat_turn_latency', 'browser_first_visible_delta_ms')
            )
            """
        )
    ).all()
    if missing or set(required_columns) != {
        ("chat_sessions", "execution_backend"),
        ("chat_messages", "finish_reason"),
        ("chat_messages", "prepared_fork_sdk_session_id"),
        ("chat_messages", "prepared_fork_sdk_project_key"),
        ("chat_shares", "snapshot_version"),
        ("chat_shares", "messages"),
        ("chat_turn_latency", "request_id"),
        ("chat_turn_latency", "terminal_status"),
        ("chat_turn_latency", "browser_first_visible_delta_ms"),
    }:
        raise RuntimeError("required chat sandbox schema is missing")
    share_snapshot_constraint = db.execute(
        text(
            """
            SELECT 1
            FROM pg_constraint
            WHERE conrelid = 'chat_shares'::regclass
              AND conname = 'chat_shares_messages_array_check'
            """
        )
    ).first()
    if share_snapshot_constraint is None:
        raise RuntimeError("required chat sandbox schema is missing")
