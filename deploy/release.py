"""Release manifest and immutable filesystem helpers."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from backend.chat_sandbox_worker.contract import (
    DATABASE_CONTRACT_VERSION,
    DEFAULT_AGENT_HARNESS,
    DEFAULT_BACKEND,
    GATEWAY_COMPATIBLE_FROM,
    GATEWAY_CONTRACT_VERSION,
    MODAL_IMAGE_ID,
    NEW_CHAT_MODAL_PERCENTAGE,
    NEW_SESSION_PI_PERCENTAGE,
    PI_NODE_SHA256,
    PI_NODE_VERSION,
    PI_SOURCE_COMMIT,
    PI_VERSION,
    PRODUCTION_MODAL_IMAGE_ID,
    PWC_CLI_VERSION,
    RESTRICTED_HF_CLI_VERSION,
    SDK_VERSION,
    SUPPORTED_AGENT_HARNESSES,
    WORKER_CONTRACT_VERSION,
)
from backend.services.chat_runtime_contract import require_immutable_image_id
from deploy.production_chat_contract import DISABLED_DATABASE_CONTRACT_VERSION

ENVIRONMENTS = ("production", "staging")
FEATURE_CONTRACT_VERSION = 4


def legacy_production_chat_runtime() -> dict[str, object]:
    """Descriptor accepted only for rollback from pre-bridge production releases."""

    return {
        "enabled": False,
        "new_chat_modal_percentage": 0,
        "default_backend": "local_mcp",
        "modal_image_version": "",
        "pwc_cli_version": "",
        "worker_contract_version": "",
        "gateway_contract_version": 1,
        "gateway_compatible_from": 1,
        "database_contract_version": 1,
        "system_prompt_sha256": "",
        "supported_agent_harnesses": ["claude"],
        "default_agent_harness": "claude",
        "new_session_pi_percentage": 0,
        "claude_sdk_version": "",
        "pi_version": "",
        "pi_source_commit": "",
        "pi_node_version": "",
        "pi_node_sha256": "",
        "restricted_hf_cli_version": "",
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def profile_features(
    environment: str, *, production_chat_enabled: bool = False
) -> dict[str, bool]:
    if environment not in ENVIRONMENTS:
        raise ValueError(f"unsupported environment: {environment}")
    return {
        "chat": environment == "staging" or production_chat_enabled,
        # Staging inherits production capabilities and layers preview features
        # such as chat on top.
        "codex_add_evals": True,
        "codex_enrich_paper": True,
    }


def _profile_features_v2(environment: str) -> dict[str, bool]:
    if environment not in ENVIRONMENTS:
        raise ValueError(f"unsupported environment: {environment}")
    return {
        "chat": environment == "staging",
        "codex_add_evals": False,
        "codex_enrich_paper": False,
    }


def _profile_features_v3(environment: str) -> dict[str, bool]:
    if environment not in ENVIRONMENTS:
        raise ValueError(f"unsupported environment: {environment}")
    return {
        "chat": environment == "staging",
        "codex_add_evals": environment == "production",
        "codex_enrich_paper": environment == "production",
    }


def _profile_features_for_version(environment: str, version: int) -> dict[str, bool]:
    if version == 2:
        return _profile_features_v2(environment)
    if version == 3:
        return _profile_features_v3(environment)
    if version == FEATURE_CONTRACT_VERSION:
        return profile_features(environment)
    raise ValueError("unsupported release feature contract version")


def chat_runtime(
    environment: str, descriptor: dict[str, object] | None = None
) -> dict[str, object]:
    if environment not in ENVIRONMENTS:
        raise ValueError(f"unsupported environment: {environment}")
    if descriptor is not None:
        return descriptor
    if environment == "production":
        from backend.chat_sandbox_worker.prompt import sha256

        return {
            "enabled": False,
            "new_chat_modal_percentage": 0,
            "default_backend": DEFAULT_BACKEND,
            "modal_image_version": PRODUCTION_MODAL_IMAGE_ID,
            "pwc_cli_version": PWC_CLI_VERSION,
            "worker_contract_version": WORKER_CONTRACT_VERSION,
            "gateway_contract_version": GATEWAY_CONTRACT_VERSION,
            "gateway_compatible_from": GATEWAY_COMPATIBLE_FROM,
            "database_contract_version": DISABLED_DATABASE_CONTRACT_VERSION,
            "system_prompt_sha256": sha256(),
            "supported_agent_harnesses": ["claude"],
            "default_agent_harness": "claude",
            "new_session_pi_percentage": 0,
            "claude_sdk_version": SDK_VERSION,
            "pi_version": "",
            "pi_source_commit": "",
            "pi_node_version": "",
            "pi_node_sha256": "",
            "restricted_hf_cli_version": RESTRICTED_HF_CLI_VERSION,
        }
    from backend.chat_sandbox_worker.prompt import sha256

    return {
        "enabled": True,
        "new_chat_modal_percentage": NEW_CHAT_MODAL_PERCENTAGE,
        "default_backend": DEFAULT_BACKEND,
        "modal_image_version": MODAL_IMAGE_ID,
        "pwc_cli_version": PWC_CLI_VERSION,
        "worker_contract_version": WORKER_CONTRACT_VERSION,
        "gateway_contract_version": GATEWAY_CONTRACT_VERSION,
        "gateway_compatible_from": GATEWAY_COMPATIBLE_FROM,
        "database_contract_version": DATABASE_CONTRACT_VERSION,
        "system_prompt_sha256": sha256(),
        "supported_agent_harnesses": list(SUPPORTED_AGENT_HARNESSES),
        "default_agent_harness": DEFAULT_AGENT_HARNESS,
        "new_session_pi_percentage": NEW_SESSION_PI_PERCENTAGE,
        "claude_sdk_version": SDK_VERSION,
        "pi_version": PI_VERSION,
        "pi_source_commit": PI_SOURCE_COMMIT,
        "pi_node_version": PI_NODE_VERSION,
        "pi_node_sha256": PI_NODE_SHA256,
        "restricted_hf_cli_version": RESTRICTED_HF_CLI_VERSION,
    }


def release_id(git_sha: str, environment: str) -> str:
    if len(git_sha) != 40 or any(c not in "0123456789abcdef" for c in git_sha):
        raise ValueError("git_sha must be a full lowercase SHA-1")
    if environment not in ENVIRONMENTS:
        raise ValueError(f"unsupported environment: {environment}")
    return f"{git_sha[:12]}-{environment}"


def build_manifest(
    git_sha: str,
    environment: str,
    *,
    chat_descriptor: dict[str, object] | None = None,
    production_chat_enabled: bool = False,
) -> dict[str, object]:
    if production_chat_enabled and environment != "production":
        raise ValueError("production chat activation is production-only")
    features = profile_features(
        environment, production_chat_enabled=production_chat_enabled
    )
    return {
        "release_id": release_id(git_sha, environment),
        "git_sha": git_sha,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "build_profile": environment,
        "feature_contract_version": FEATURE_CONTRACT_VERSION,
        "backend_features": features,
        "frontend_features": features,
        "chat_runtime": chat_runtime(
            environment,
            chat_descriptor,
        ),
        "frontend_entrypoint": "frontend-dist/index.html",
    }


def validate_manifest(release_dir: Path, environment: str | None = None) -> dict:
    manifest_path = release_dir / "release.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    legacy_required = {
        "release_id",
        "git_sha",
        "built_at",
        "build_profile",
        "backend_features",
        "frontend_features",
        "frontend_entrypoint",
    }
    versioned_required = legacy_required | {"feature_contract_version"}
    bridge_required = versioned_required | {"chat_runtime"}
    profile = manifest.get("build_profile")
    if set(manifest) == legacy_required:
        expected = {"chat": profile == "staging"}
    elif set(manifest) == versioned_required:
        expected = _profile_features_for_version(
            profile, manifest["feature_contract_version"]
        )
    elif set(manifest) == bridge_required:
        version = manifest["feature_contract_version"]
        if version == FEATURE_CONTRACT_VERSION and profile == "production":
            backend_features = manifest.get("backend_features")
            declared_chat = (
                backend_features.get("chat")
                if isinstance(backend_features, dict)
                else None
            )
            if not isinstance(declared_chat, bool):
                raise ValueError("production chat feature flag must be boolean")
            expected = profile_features(profile, production_chat_enabled=declared_chat)
        else:
            expected = _profile_features_for_version(profile, version)
    else:
        raise ValueError("release.json has an unexpected schema")
    if environment is not None and profile != environment:
        raise ValueError("release profile does not match target environment")
    if (
        manifest["backend_features"] != expected
        or manifest["frontend_features"] != expected
    ):
        raise ValueError("release feature manifests do not match the build profile")
    if manifest["release_id"] != release_id(manifest["git_sha"], profile):
        raise ValueError("release ID does not match SHA and profile")
    if manifest["frontend_entrypoint"] != "frontend-dist/index.html":
        raise ValueError("unsupported frontend entrypoint")
    runtime = manifest.get("chat_runtime")
    if runtime is None:
        return _validate_release_files(release_dir, manifest, expected)
    legacy_runtime_keys = {
        "enabled",
        "new_chat_modal_percentage",
        "default_backend",
        "modal_image_version",
        "pwc_cli_version",
        "worker_contract_version",
        "system_prompt_sha256",
    }
    rolling_runtime_keys = legacy_runtime_keys | {
        "gateway_contract_version",
        "gateway_compatible_from",
        "database_contract_version",
    }
    pi_runtime_keys = rolling_runtime_keys | {
        "supported_agent_harnesses",
        "default_agent_harness",
        "new_session_pi_percentage",
        "claude_sdk_version",
        "pi_version",
        "pi_source_commit",
        "pi_node_version",
        "pi_node_sha256",
        "restricted_hf_cli_version",
    }
    runtime_keys = frozenset(runtime) if isinstance(runtime, dict) else frozenset()
    if not isinstance(runtime, dict) or runtime_keys not in {
        frozenset(legacy_runtime_keys),
        frozenset(rolling_runtime_keys),
        frozenset(pi_runtime_keys),
    }:
        raise ValueError("release chat_runtime has an unexpected schema")
    if not expected["chat"]:
        if runtime["enabled"] is not False or runtime["new_chat_modal_percentage"] != 0:
            raise ValueError("disabled release contains an active chat runtime")
    else:
        percentage = runtime["new_chat_modal_percentage"]
        if not isinstance(percentage, int) or not 0 <= percentage <= 100:
            raise ValueError("chat runtime rollout percentage is invalid")
        if runtime["default_backend"] not in {"local_mcp", "modal_cli"}:
            raise ValueError("chat runtime default backend is invalid")
        if percentage == 0 and runtime["default_backend"] != "local_mcp":
            raise ValueError("zero-percent rollout must default to local_mcp")
        if percentage == 100 and runtime["default_backend"] != "modal_cli":
            raise ValueError("full rollout must default to modal_cli")
        for key in (
            "pwc_cli_version",
            "worker_contract_version",
        ):
            if not isinstance(runtime[key], str) or not runtime[key]:
                raise ValueError(f"chat runtime {key} is required")
        require_immutable_image_id(runtime["modal_image_version"])
        prompt_hash = runtime["system_prompt_sha256"]
        if (
            not isinstance(prompt_hash, str)
            or len(prompt_hash) != 64
            or any(character not in "0123456789abcdef" for character in prompt_hash)
        ):
            raise ValueError("chat runtime system prompt hash is invalid")
        if runtime["enabled"] is not True:
            raise ValueError("enabled chat runtime must be active")
    if set(runtime) in (rolling_runtime_keys, pi_runtime_keys) and runtime["enabled"]:
        gateway_version = runtime["gateway_contract_version"]
        compatible_from = runtime["gateway_compatible_from"]
        database_version = runtime["database_contract_version"]
        if (
            not isinstance(gateway_version, int)
            or not isinstance(compatible_from, int)
            or gateway_version < 1
            or compatible_from < 1
            or compatible_from > gateway_version
        ):
            raise ValueError("chat gateway rolling contract is invalid")
        if not isinstance(database_version, int) or database_version < 1:
            raise ValueError("chat database contract is invalid")
    if set(runtime) == pi_runtime_keys:
        supported = runtime["supported_agent_harnesses"]
        if supported not in (["claude"], ["claude", "pi"]):
            raise ValueError("chat runtime harness set is invalid")
        if runtime["default_agent_harness"] not in supported:
            raise ValueError("default chat harness is not supported")
        pi_percentage = runtime["new_session_pi_percentage"]
        if pi_percentage not in (0, 100):
            raise ValueError("Pi rollout must be stopped or fully cut over")
        if pi_percentage == 100 and runtime["default_agent_harness"] != "pi":
            raise ValueError("full Pi rollout must default to Pi")
        if pi_percentage == 0 and runtime["default_agent_harness"] != "claude":
            raise ValueError("stopped Pi rollout must default to Claude")
        if "pi" in supported:
            required_pi = (
                "claude_sdk_version",
                "pi_version",
                "pi_source_commit",
                "pi_node_version",
                "pi_node_sha256",
                "restricted_hf_cli_version",
            )
            if any(
                not isinstance(runtime[key], str) or not runtime[key]
                for key in required_pi
            ):
                raise ValueError("Pi runtime identity is incomplete")
            if len(runtime["pi_source_commit"]) != 40:
                raise ValueError("Pi source commit is invalid")
            if len(runtime["pi_node_sha256"]) != 64:
                raise ValueError("Pi Node digest is invalid")
    return _validate_release_files(release_dir, manifest, expected)


def rolling_contract(manifest: dict) -> tuple[int, int, int]:
    """Return gateway emitted/accepted and database contracts for bridges."""

    runtime = manifest.get("chat_runtime") or {}
    worker = runtime.get("worker_contract_version")
    fallback = int(worker) if str(worker).isdigit() else 1
    return (
        int(runtime.get("gateway_contract_version", fallback)),
        int(runtime.get("gateway_compatible_from", fallback)),
        int(runtime.get("database_contract_version", 1)),
    )


def validate_rolling_compatibility(active: dict, candidate: dict) -> None:
    """Prove forward drain and reverse automatic-rollback compatibility."""

    active_emits, active_accepts, active_database = rolling_contract(active)
    candidate_emits, candidate_accepts, candidate_database = rolling_contract(candidate)
    active_runtime = active.get("chat_runtime") or {}
    candidate_runtime = candidate.get("chat_runtime") or {}
    if (
        active_runtime.get("enabled") is False
        and candidate_runtime.get("enabled") is False
    ):
        if active_database != candidate_database:
            raise ValueError("release database contracts are incompatible")
        return
    if not candidate_accepts <= active_emits <= candidate_emits:
        raise ValueError("candidate cannot accept the active worker contract")
    # Gateway 27 adds only /hf-catalog. Gateway 26 still serves every older
    # route; a worker-57 HF call after automatic rollback receives a bounded
    # unavailable result from the broker and cannot fall through elsewhere.
    hf_catalog_fail_closed_rollback = (
        active_emits == 26
        and active_accepts == 26
        and candidate_emits == 27
        and candidate_accepts == 26
    )
    # The first Pi-aware release is an additive, zero-assignment bridge.  Its
    # rollback target cannot interpret Pi-only gateway/store operations, but no
    # Pi session can exist yet: assignment is stopped, Claude remains the
    # default, and the schema migration preserves defaults used by old Claude
    # writers.  A second identical-contract release must displace this bridge
    # before operators may assign even an admin Pi session.
    pi_zero_assignment_bridge = (
        (
            (active_emits == 27 and active_accepts == 26)
            or (
                active_runtime.get("enabled") is False
                and active_emits == 28
                and active_accepts == 27
            )
        )
        and active_database == 1
        and candidate_emits == 28
        and candidate_accepts == 27
        and candidate_database == 2
        and candidate_runtime.get("supported_agent_harnesses") == ["claude", "pi"]
        and candidate_runtime.get("default_agent_harness") == "claude"
        and candidate_runtime.get("new_session_pi_percentage") == 0
    )
    if (
        not active_accepts <= candidate_emits <= active_emits
        and not hf_catalog_fail_closed_rollback
        and not pi_zero_assignment_bridge
    ):
        raise ValueError("active release cannot serve candidate workers on rollback")
    if active_database != candidate_database and not pi_zero_assignment_bridge:
        raise ValueError("release database contracts are incompatible")


def _validate_release_files(
    release_dir: Path, manifest: dict, expected: dict[str, bool]
) -> dict:
    features = json.loads(
        (release_dir / "frontend-dist" / "features.json").read_text(encoding="utf-8")
    )
    if features != expected:
        raise ValueError("features.json does not match release.json")
    index = release_dir / manifest["frontend_entrypoint"]
    html = index.read_text(encoding="utf-8")
    if "/src/main.tsx" in html or "/assets/" not in html:
        raise ValueError("release frontend shell is not a built asset bundle")
    if not (release_dir / "backend" / "main.py").is_file():
        raise ValueError("release backend is missing")
    return manifest


def atomic_symlink(target: Path, link: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    temporary = link.with_name(f".{link.name}.new-{os.getpid()}")
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(target)
    os.replace(temporary, link)


@dataclass(frozen=True)
class ReleasePointers:
    current: Path | None
    previous: Path | None


def read_pointers(environment_root: Path) -> ReleasePointers:
    def target(name: str) -> Path | None:
        link = environment_root / name
        return link.resolve(strict=False) if link.is_symlink() else None

    return ReleasePointers(current=target("current"), previous=target("previous"))
