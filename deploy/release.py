"""Release manifest and immutable filesystem helpers."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ENVIRONMENTS = ("production", "staging")
FEATURE_CONTRACT_VERSION = 4


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def profile_features(environment: str) -> dict[str, bool]:
    if environment not in ENVIRONMENTS:
        raise ValueError(f"unsupported environment: {environment}")
    return {
        "chat": environment == "staging",
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


def release_id(git_sha: str, environment: str) -> str:
    if len(git_sha) != 40 or any(c not in "0123456789abcdef" for c in git_sha):
        raise ValueError("git_sha must be a full lowercase SHA-1")
    if environment not in ENVIRONMENTS:
        raise ValueError(f"unsupported environment: {environment}")
    return f"{git_sha[:12]}-{environment}"


def build_manifest(git_sha: str, environment: str) -> dict[str, object]:
    features = profile_features(environment)
    return {
        "release_id": release_id(git_sha, environment),
        "git_sha": git_sha,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "build_profile": environment,
        "feature_contract_version": FEATURE_CONTRACT_VERSION,
        "backend_features": features,
        "frontend_features": features,
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
    current_required = legacy_required | {"feature_contract_version"}
    bridge_required = current_required | {"chat_runtime"}
    if set(manifest) == legacy_required:
        expected = {"chat": manifest["build_profile"] == "staging"}
    elif set(manifest) in {frozenset(current_required), frozenset(bridge_required)}:
        expected = _profile_features_for_version(
            manifest["build_profile"], manifest["feature_contract_version"]
        )
        if "chat_runtime" in manifest and not isinstance(
            manifest["chat_runtime"], dict
        ):
            raise ValueError("release chat_runtime must be an object")
    else:
        raise ValueError("release.json has an unexpected schema")
    profile = manifest["build_profile"]
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
