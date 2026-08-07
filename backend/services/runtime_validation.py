"""Fail-closed validation for deployed environment and release configuration."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from sqlalchemy import text

from backend.chat_sandbox_worker.contract import PROVIDER_OUTPUT_TOKEN_LIMIT
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
        if not settings.catalog_mutations_enabled or not settings.cron_enabled:
            raise RuntimeError(
                "production catalog mutations and CRON must remain enabled"
            )
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

    if settings.environment == "production" and any(
        (
            settings.chat_openrouter_server_funded_enabled,
            settings.chat_openrouter_api_key,
            settings.chat_openrouter_credential_keyring,
            settings.chat_openrouter_user_tracking_secret,
        )
    ):
        raise RuntimeError("production OpenRouter chat credentials are prohibited")

    if not settings.chat_enabled:
        if settings.environment == "production" and (
            settings.chat_default_backend != "local_mcp"
            or settings.chat_new_chat_modal_percentage != 0
            or settings.chat_modal_image_version
            or settings.chat_persistent_worker_enabled
            or settings.chat_blank_pool_enabled
            or settings.chat_public_admission_enabled
            or settings.chat_sandbox_admission_enabled
            or settings.chat_title_generation_enabled
            or settings.chat_sandbox_cpu_limit is not None
            or settings.chat_sandbox_memory_limit_mib is not None
        ):
            raise RuntimeError(
                "disabled production contains an active chat runtime descriptor"
            )
    else:
        if not all(
            (
                settings.hf_oauth_client_id,
                settings.hf_oauth_client_secret,
                settings.hf_oauth_credential_secret,
            )
        ):
            raise RuntimeError(
                "enabled chat requires the Hugging Face OAuth inference credential path"
            )
        expected_hf_route = "deepseek-ai/DeepSeek-V4-Flash-0731:fastest"
        if settings.chat_deepseek_v4_flash_route != expected_hf_route:
            raise RuntimeError("DeepSeek V4 Flash must use the reviewed :fastest route")
        discovered = settings.chat_model_choices
        if settings.environment == "production":
            if len(discovered) != 1 or any(
                choice["provider"] != "huggingface" for choice in discovered
            ):
                raise RuntimeError(
                    "production chat discovery must be Hugging Face-only"
                )
        else:
            expected_ids = {
                "deepseek-ai/DeepSeek-V4-Flash-0731",
                "openai/gpt-5.6-luna",
                "openai/gpt-5.6-terra",
            }
            if {choice["id"] for choice in discovered} != expected_ids:
                raise RuntimeError(
                    "staging chat discovery must contain DeepSeek, Luna, and Terra"
                )
        if settings.chat_default_backend != "modal_cli":
            raise RuntimeError("deployed chat must use the isolated Modal backend")
        if settings.chat_new_chat_modal_percentage != 100:
            raise RuntimeError("chat must not spill new sessions to local execution")
        if settings.chat_web_search_enabled:
            web_search_url = urlsplit(settings.chat_web_search_exa_url)
            if (
                settings.chat_web_search_provider != "exa"
                or not settings.chat_web_search_exa_api_key
                or web_search_url.scheme != "https"
                or web_search_url.hostname != "api.exa.ai"
                or web_search_url.path.rstrip("/") != "/search"
                or settings.chat_web_search_max_calls != 3
                or settings.chat_web_search_timeout_seconds != 3
                or settings.chat_web_search_result_count != 5
                or settings.chat_web_search_max_result_bytes != 16 * 1024
                or settings.chat_web_search_query_max_chars != 500
                or settings.chat_web_search_monthly_warning_calls != 1_000
                or settings.chat_web_search_monthly_hard_calls != 1_200
            ):
                raise RuntimeError("web-search runtime descriptor is invalid")
        if not settings.chat_sandbox_spend_enforcement_enabled:
            raise RuntimeError("PWC_CHAT_SANDBOX_SPEND_ENFORCEMENT_ENABLED is required")
        if (
            settings.chat_sandbox_warning_microusd,
            settings.chat_sandbox_application_cap_microusd,
            settings.chat_sandbox_environment_cap_microusd,
            settings.chat_sandbox_workspace_cap_microusd,
        ) != (75_000_000, 100_000_000, 0, 250_000_000):
            raise RuntimeError(
                "sandbox spend policy must be $75/$100/$250 with no environment cap"
            )
        if settings.chat_sandbox_provider_mode != "starter_workspace":
            raise RuntimeError(
                "chat sandbox spend must use the workspace-level outer cap"
            )
        if (
            settings.chat_max_concurrency != 2
            or settings.chat_user_max_concurrency != 2
            or settings.chat_sandbox_total_live_cap != 3
            or settings.chat_blank_pool_min != 1
            or settings.chat_blank_pool_max != 1
        ):
            raise RuntimeError(
                "chat capacity must be two active turns plus one warm blank"
            )
        expected_modal_environment = f"pwc-chat-{settings.environment}"
        if settings.chat_sandbox_modal_environment != expected_modal_environment:
            raise RuntimeError(
                f"PWC_CHAT_SANDBOX_MODAL_ENVIRONMENT must be {expected_modal_environment}"
            )
        if not settings.chat_sandbox_modal_workspace:
            raise RuntimeError("PWC_CHAT_SANDBOX_MODAL_WORKSPACE is required")
        if not settings.chat_sandbox_modal_owner_username:
            raise RuntimeError("PWC_CHAT_SANDBOX_MODAL_OWNER_USERNAME is required")
        expected_attestation = (
            f"modal-workspace-{settings.chat_sandbox_modal_workspace}-250-"
            f"{settings.environment}-starter-v1"
        )
        if settings.chat_sandbox_budget_attestation != expected_attestation:
            raise RuntimeError(
                "PWC_CHAT_SANDBOX_BUDGET_ATTESTATION does not match configured policy"
            )
        primary_alert = settings.chat_sandbox_slack_webhook_url
        fallback_alert = settings.chat_sandbox_alert_fallback_webhook_url
        if not primary_alert or not fallback_alert:
            raise RuntimeError(
                "primary and fallback chat alert destinations are required"
            )
        if fallback_alert == primary_alert:
            raise RuntimeError(
                "primary and fallback chat alert destinations must differ"
            )
        if not settings.chat_sandbox_runbook_url:
            raise RuntimeError("PWC_CHAT_SANDBOX_RUNBOOK_URL is required")
        if not settings.chat_sandbox_operator_username_set:
            raise RuntimeError("PWC_CHAT_SANDBOX_OPERATOR_USERNAMES is required")
        rate = (settings.chat_sandbox_cpu_limit or settings.chat_sandbox_cpu) * 40 + (
            settings.chat_sandbox_memory_limit_mib or settings.chat_sandbox_memory_mib
        ) / 1024 * 7
        burst = int(
            rate
            * settings.chat_sandbox_total_live_cap
            * (
                settings.chat_sandbox_watchdog_seconds
                + settings.chat_sandbox_drain_grace_seconds
                + settings.chat_sandbox_termination_grace_seconds
            )
        ) + (
            settings.chat_sandbox_reconciliation_allowance_microusd
            * settings.chat_sandbox_total_live_cap
        )
        if (
            settings.chat_sandbox_workspace_cap_microusd
            - settings.chat_sandbox_application_cap_microusd
            < burst
        ):
            raise RuntimeError(
                "sandbox provider reserve is smaller than the worst-case aggregate burst"
            )
        if not all(
            (
                settings.chat_modal_image_version,
                settings.chat_pwc_cli_version,
                settings.chat_worker_contract_version,
                settings.chat_system_prompt_sha256,
            )
        ):
            raise RuntimeError("chat runtime descriptor is incomplete")
        expected_gateway = {
            "staging": "chat-gateway-staging.paperswithcode.co",
            "production": "chat-gateway.paperswithcode.co",
        }[settings.environment]
        try:
            require_immutable_image_id(settings.chat_modal_image_version)
            gateway_host = dedicated_gateway_hostname(settings.chat_gateway_url)
        except ValueError as error:
            raise RuntimeError(f"chat runtime is invalid: {error}") from error
        if gateway_host != expected_gateway:
            raise RuntimeError(f"chat gateway must use {expected_gateway}")
        if settings.chat_workspace_snapshots_enabled:
            raise RuntimeError("directory snapshots must remain disabled")
        if (
            settings.chat_session_limit != 100
            or settings.chat_user_byte_limit != 100 * 1024 * 1024
        ):
            raise RuntimeError(
                "chat retention quotas must remain 100 active chats and 100 MB"
            )
        if (
            not settings.chat_title_generation_enabled
            or not settings.chat_title_hf_token
            or settings.chat_title_bill_to != "huggingface"
            or settings.chat_title_credential_owner != "nielsr"
            or settings.chat_title_credential_environment != settings.environment
        ):
            raise RuntimeError(
                "an isolated nielsr title credential billed to the huggingface "
                "organization is required"
            )
        if settings.chat_title_hf_token == settings.hf_token:
            raise RuntimeError("the title credential must not reuse PWC_HF_TOKEN")
        if (
            settings.chat_title_model != "openai/gpt-oss-120b"
            or settings.chat_title_provider != "cerebras"
            or settings.chat_title_max_tokens != 64
            or settings.chat_title_monthly_cap_microusd != 25_000_000
            or not 0
            < settings.chat_title_warning_microusd
            < settings.chat_title_monthly_cap_microusd
            or settings.chat_title_max_call_microusd
            > settings.chat_title_monthly_cap_microusd
            or settings.chat_title_max_call_microusd
            < (
                8_000 * settings.chat_title_input_microusd_per_token
                + settings.chat_title_max_tokens
                * settings.chat_title_output_microusd_per_token
            )
        ):
            raise RuntimeError("the title model and $25 monthly circuit are invalid")
        if settings.environment == "staging":
            if not settings.chat_openrouter_server_funded_enabled:
                raise RuntimeError(
                    "staging OpenRouter funded/BYOK paths must remain enabled"
                )
            if not settings.chat_openrouter_api_key:
                raise RuntimeError(
                    "server-funded OpenRouter chat requires an OpenRouter key"
                )
            if settings.chat_openrouter_workspace_monthly_budget_usd != 200:
                raise RuntimeError(
                    "staging OpenRouter workspace budget must equal $200"
                )
            if settings.chat_openrouter_monthly_user_budget_usd != 1:
                raise RuntimeError("staging OpenRouter per-user budget must equal $1")
            if not settings.chat_openrouter_user_tracking_secret:
                raise RuntimeError("OpenRouter user tracking HMAC is required")
            from backend.services.openrouter_byok_service import credential_keyring
            from backend.services.openrouter_user_budget_service import (
                RequestBounds,
                safe_maximum_microusd,
            )

            try:
                credential_keyring(settings)
                maximum = max(
                    safe_maximum_microusd(
                        settings,
                        route,
                        RequestBounds(
                            request_bytes=1,
                            maximum_output_tokens=PROVIDER_OUTPUT_TOKEN_LIMIT,
                            payload={"messages": [{"role": "user", "content": "x"}]},
                        ),
                    )
                    for route in settings.chat_openrouter_routes
                )
            except (ValueError, RuntimeError) as error:
                raise RuntimeError(
                    "OpenRouter durable accounting configuration is invalid"
                ) from error
            if maximum > 1_000_000:
                raise RuntimeError(
                    "OpenRouter minimum request bound exceeds the per-user hard budget"
                )
            from backend.services.openrouter_budget_service import (
                OpenRouterBudgetUnavailable,
                validate_openrouter_guardrail,
            )

            try:
                validate_openrouter_guardrail(settings)
            except OpenRouterBudgetUnavailable as error:
                raise RuntimeError(
                    "OpenRouter provider-enforced guardrail is invalid"
                ) from error
        if (
            settings.chat_sandbox_cpu_limit is not None
            and settings.chat_sandbox_cpu_limit < settings.chat_sandbox_cpu
        ):
            raise RuntimeError("chat CPU limit is below its request")
        if (
            settings.chat_sandbox_memory_limit_mib is not None
            and settings.chat_sandbox_memory_limit_mib
            < settings.chat_sandbox_memory_mib
        ):
            raise RuntimeError("chat memory limit is below its request")
        if settings.chat_blank_pool_enabled:
            if not settings.chat_persistent_worker_enabled:
                raise RuntimeError("blank pool requires persistent workers")
            if (
                settings.chat_blank_pool_min_remaining_seconds
                >= settings.chat_persistent_sandbox_lifetime_seconds
            ):
                raise RuntimeError("blank pool minimum remaining lifetime is invalid")
            if (
                settings.chat_blank_pool_rotate_before_seconds
                >= settings.chat_persistent_sandbox_lifetime_seconds
            ):
                raise RuntimeError("blank pool rotation window is invalid")
        from backend.chat_sandbox_worker.prompt import sha256 as prompt_sha256

        effective_prompt_hash = prompt_sha256(
            max_turns=settings.chat_max_turns,
            max_calls=settings.chat_max_tool_calls,
            max_searches=settings.chat_max_direct_search_calls,
        )
        if settings.chat_system_prompt_sha256 != effective_prompt_hash:
            raise RuntimeError("chat prompt and execution limits disagree")

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
    projected_runtime = (
        {key: runtime.get(key) for key in expected_runtime}
        if isinstance(runtime, dict)
        else runtime
    )
    if (
        projected_runtime != expected_runtime
        or manifest.get("release_id") != settings.release_id
    ):
        raise RuntimeError("running chat runtime differs from the release manifest")

    if settings.thumbnail_mutations_enabled:
        raise RuntimeError("deployed web services must not mutate thumbnails")
    return validate_frontend_dist(settings)


def validate_chat_schema(db, settings: Settings) -> None:
    """Validate only the tables required by the enabled provider profile."""

    if db.execute(text("SHOW transaction_read_only")).scalar_one() != "off":
        raise RuntimeError("chat database connection is read-only")
    common_tables = {
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
    }
    openrouter_tables = {
        "chat_openrouter_credentials",
        "chat_openrouter_monthly_usage",
        "chat_openrouter_provider_calls",
        "chat_openrouter_credential_audit",
    }
    web_search_tables = {
        "chat_web_search_budget_states",
        "chat_web_search_circuit_events",
        "chat_web_search_owner_usage",
    }
    required_tables = (
        common_tables
        | (
            openrouter_tables
            if settings.chat_openrouter_server_funded_enabled
            else set()
        )
        | (web_search_tables if settings.chat_web_search_enabled else set())
    )
    rows = dict(
        db.execute(
            text("""
                SELECT name, to_regclass(name)::text
                FROM (VALUES
                    ('chat_sessions'),
                    ('chat_messages'),
                    ('chat_shares'),
                    ('chat_sandbox_leases'),
                    ('chat_sandbox_pool'),
                    ('chat_sandbox_compute_intervals'),
                    ('chat_sandbox_budget_states'),
                    ('chat_sandbox_circuit_events'),
                    ('chat_title_budget_states'),
                    ('chat_title_provider_calls'),
                    ('chat_title_budget_events'),
                    ('chat_turn_capabilities'),
                    ('chat_turn_latency'),
                    ('chat_openrouter_credentials'),
                    ('chat_openrouter_monthly_usage'),
                    ('chat_openrouter_provider_calls'),
                    ('chat_openrouter_credential_audit')
                    ,('chat_web_search_budget_states')
                    ,('chat_web_search_circuit_events')
                    ,('chat_web_search_owner_usage')
                ) AS required(name)
                """)
        ).all()
    )
    missing = [name for name in required_tables if rows.get(name) is None]
    common_columns = {
        ("chat_sessions", "execution_backend"),
        ("chat_messages", "finish_reason"),
        ("chat_messages", "prepared_fork_sdk_session_id"),
        ("chat_messages", "prepared_fork_sdk_project_key"),
        ("chat_messages", "paper_mentions"),
        ("chat_messages", "effective_prompt"),
        ("chat_messages", "langfuse_trace_id"),
        ("chat_shares", "snapshot_version"),
        ("chat_shares", "messages"),
        ("chat_sandbox_leases", "worker_generation"),
        ("chat_sandbox_pool", "modal_sandbox_id"),
        ("chat_sandbox_pool", "worker_generation"),
        ("chat_sandbox_pool", "billing_month"),
        ("chat_sandbox_pool", "estimated_blank_cost_usd"),
        ("chat_sandbox_compute_intervals", "accrued_microusd"),
        ("chat_sandbox_budget_states", "circuit_state"),
        ("chat_sandbox_budget_states", "provider_floor_microusd"),
        ("chat_sandbox_budget_states", "last_reconciliation_attempt_at"),
        ("chat_sandbox_circuit_events", "fallback_delivery_state"),
        ("chat_sandbox_circuit_events", "fallback_next_delivery_attempt_at"),
        ("chat_title_budget_states", "reserved_microusd"),
        ("chat_title_budget_states", "spent_microusd"),
        ("chat_title_provider_calls", "actual_microusd"),
        ("chat_title_provider_calls", "provider_generation_id"),
        ("chat_title_budget_events", "fallback_delivery_state"),
        ("chat_turn_latency", "request_id"),
        ("chat_turn_latency", "terminal_status"),
        ("chat_turn_latency", "browser_first_visible_delta_ms"),
        ("chat_turn_latency", "estimated_active_cost_usd"),
        ("chat_turn_latency", "qualification_run_id"),
        ("chat_turn_latency", "qualification_scenario"),
        ("chat_turn_capabilities", "provider_mode"),
        ("chat_turn_capabilities", "provider_credential_revision"),
        ("chat_turn_capabilities", "provider_error_code"),
    }
    openrouter_columns = {
        ("chat_openrouter_credentials", "credential_revision"),
        ("chat_openrouter_monthly_usage", "reserved_microusd"),
        ("chat_openrouter_provider_calls", "actual_microusd"),
    }
    web_search_columns = {
        ("chat_sessions", "web_search_enabled"),
        ("chat_messages", "web_search_enabled"),
        ("chat_turn_capabilities", "web_search_calls"),
        ("chat_turn_capabilities", "web_search_failed"),
    }
    expected_columns = (
        common_columns
        | (
            openrouter_columns
            if settings.chat_openrouter_server_funded_enabled
            else set()
        )
        | (web_search_columns if settings.chat_web_search_enabled else set())
    )
    present_columns = set(
        db.execute(
            text("""
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE (table_name, column_name) IN (
                ('chat_sessions', 'execution_backend'),
                ('chat_messages', 'finish_reason'),
                ('chat_messages', 'prepared_fork_sdk_session_id'),
                ('chat_messages', 'prepared_fork_sdk_project_key'),
                ('chat_messages', 'paper_mentions'),
                ('chat_messages', 'effective_prompt'),
                ('chat_messages', 'langfuse_trace_id'),
                ('chat_shares', 'snapshot_version'),
                ('chat_shares', 'messages'),
                ('chat_sandbox_leases', 'worker_generation'),
                ('chat_sandbox_pool', 'modal_sandbox_id'),
                ('chat_sandbox_pool', 'worker_generation'),
                ('chat_sandbox_pool', 'billing_month'),
                ('chat_sandbox_pool', 'estimated_blank_cost_usd'),
                ('chat_sandbox_compute_intervals', 'accrued_microusd'),
                ('chat_sandbox_budget_states', 'circuit_state'),
                ('chat_sandbox_budget_states', 'provider_floor_microusd'),
                ('chat_sandbox_budget_states', 'last_reconciliation_attempt_at'),
                ('chat_sandbox_circuit_events', 'fallback_delivery_state'),
                ('chat_sandbox_circuit_events', 'fallback_next_delivery_attempt_at'),
                ('chat_title_budget_states', 'reserved_microusd'),
                ('chat_title_budget_states', 'spent_microusd'),
                ('chat_title_provider_calls', 'actual_microusd'),
                ('chat_title_provider_calls', 'provider_generation_id'),
                ('chat_title_budget_events', 'fallback_delivery_state'),
                ('chat_turn_latency', 'request_id'),
                ('chat_turn_latency', 'terminal_status'),
                ('chat_turn_latency', 'browser_first_visible_delta_ms'),
                ('chat_turn_latency', 'estimated_active_cost_usd'),
                ('chat_turn_latency', 'qualification_run_id'),
                ('chat_turn_latency', 'qualification_scenario'),
                ('chat_turn_capabilities', 'provider_mode'),
                ('chat_turn_capabilities', 'provider_credential_revision'),
                ('chat_turn_capabilities', 'provider_error_code'),
                ('chat_openrouter_credentials', 'credential_revision'),
                ('chat_openrouter_monthly_usage', 'reserved_microusd'),
                ('chat_openrouter_provider_calls', 'actual_microusd')
                ,('chat_sessions', 'web_search_enabled')
                ,('chat_messages', 'web_search_enabled')
                ,('chat_turn_capabilities', 'web_search_calls')
                ,('chat_turn_capabilities', 'web_search_failed')
            )
            """)
        ).all()
    )
    if missing or not expected_columns.issubset(present_columns):
        raise RuntimeError("required chat sandbox schema is missing")
    share_snapshot_constraint = db.execute(
        text("""
            SELECT 1
            FROM pg_constraint
            WHERE conrelid = 'chat_shares'::regclass
              AND conname = 'chat_shares_messages_array_check'
            """)
    ).first()
    if share_snapshot_constraint is None:
        raise RuntimeError("required chat sandbox schema is missing")
