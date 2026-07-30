"""Build and retain immutable Python runtimes keyed by ``uv.lock``."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

try:
    from deploy.release import sha256_file
except ModuleNotFoundError:
    from release import sha256_file  # type: ignore[no-redef]

UV_BINARY = Path(os.environ.get("PWC_DEPLOY_UV", "/usr/local/bin/uv"))


def runtime_id(release: Path) -> str:
    return sha256_file(release / "uv.lock")


def runtime_manifest(runtime: Path) -> dict:
    value = json.loads((runtime / "runtime.json").read_text(encoding="utf-8"))
    if set(value) != {"lock_sha256", "python_version"}:
        raise ValueError("runtime manifest has an unexpected schema")
    if value["lock_sha256"] != runtime.name:
        raise ValueError("runtime manifest lock hash does not match its path")
    if not (runtime / "bin" / "python").is_file():
        raise ValueError("runtime Python launcher is missing")
    return value


def make_tree_readonly(root: Path) -> None:
    for path in sorted(root.rglob("*"), reverse=True):
        if path.is_symlink():
            continue
        mode = path.stat().st_mode
        path.chmod(mode | (0o555 if path.is_dir() else 0o444))
    root.chmod(root.stat().st_mode | 0o555)


def prepare_runtime(
    release: Path,
    runtimes_root: Path,
    *,
    runner=subprocess.run,
    version_runner=subprocess.run,
) -> tuple[Path, bool]:
    """Build once in a temporary directory and publish by atomic rename."""

    identifier = runtime_id(release)
    target = runtimes_root / identifier
    if target.exists():
        runtime_manifest(target)
        return target, False
    runtimes_root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{identifier}.new-", dir=runtimes_root))
    try:
        environment = os.environ.copy()
        environment["UV_PROJECT_ENVIRONMENT"] = str(temporary)
        runner(
            [
                str(UV_BINARY),
                "sync",
                "--frozen",
                "--no-install-project",
                "--project",
                str(release),
            ],
            env=environment,
            check=True,
        )
        version = version_runner(
            [str(temporary / "bin" / "python"), "--version"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        (temporary / "runtime.json").write_text(
            json.dumps(
                {"lock_sha256": identifier, "python_version": version},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        make_tree_readonly(temporary)
        try:
            os.replace(temporary, target)
        except FileExistsError:
            runtime_manifest(target)
        return target, True
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def cleanup_runtimes(runtimes_root: Path, protected_ids: set[str]) -> list[str]:
    removed: list[str] = []
    if not runtimes_root.is_dir():
        return removed
    for path in runtimes_root.iterdir():
        if (
            path.is_dir()
            and not path.name.startswith(".")
            and path.name not in protected_ids
        ):
            shutil.rmtree(path)
            removed.append(path.name)
    return removed
