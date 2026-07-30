#!/usr/bin/env python3
"""Read-only audit of release, process, nginx, and legacy checkout coupling."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

try:
    from deploy.runtime import runtime_id, runtime_manifest
except ModuleNotFoundError:
    from runtime import runtime_id, runtime_manifest  # type: ignore[no-redef]


def output(command: list[str]) -> str:
    return subprocess.run(command, text=True, capture_output=True, check=False).stdout


def audit(root: Path = Path("/srv/paperswithcode")) -> dict[str, object]:
    processes = output(["ps", "-eo", "user,pid,args"])
    nginx = output(["nginx", "-T"])
    checkout = "/root/python_projects/paperswithcode"
    findings = []
    if checkout in processes:
        findings.append("running process references developer checkout")
    if "localhost:8081" in nginx or "127.0.0.1:8081" in nginx:
        findings.append("nginx exposes a Vite staging upstream")
    staging_start = nginx.find("server_name staging.paperswithcode.co")
    staging_end = nginx.find("\nserver {", staging_start + 1)
    staging = nginx[staging_start : staging_end if staging_end > 0 else None]
    if "127.0.0.1:8000" in staging:
        findings.append("staging nginx references production backend")
    if not root.exists():
        findings.append("/srv/paperswithcode does not exist")
    pointers = {}
    slots = {}
    for environment in ("production", "staging"):
        base = root / "environments" / environment
        pointers[environment] = {
            name: str((base / name).resolve(strict=False))
            if (base / name).is_symlink()
            else None
            for name in ("current", "previous")
        }
        active = base / "active"
        active_target = active.resolve(strict=False) if active.is_symlink() else None
        slots[environment] = {
            "active": str(active_target) if active_target else None,
            "blue": {},
            "green": {},
        }
        for slot in ("blue", "green"):
            slot_root = base / "slots" / slot
            release_link = slot_root / "release"
            release = (
                release_link.resolve(strict=False)
                if release_link.is_symlink()
                else None
            )
            item = {
                "release": str(release) if release else None,
                "backend_socket": str(
                    (slot_root / "backend.sock").resolve(strict=False)
                )
                if (slot_root / "backend.sock").is_symlink()
                else None,
                "runtime_id": None,
                "runtime_valid": None,
            }
            if release and (release / "uv.lock").is_file():
                identifier = runtime_id(release)
                item["runtime_id"] = identifier
                runtime = root / "runtimes" / identifier
                try:
                    runtime_manifest(runtime)
                    item["runtime_valid"] = True
                except (OSError, ValueError, json.JSONDecodeError):
                    item["runtime_valid"] = False
                    if active_target == slot_root.resolve(strict=False):
                        findings.append(
                            f"{environment} active slot runtime is missing or invalid"
                        )
            slots[environment][slot] = item
        if active_target:
            valid_targets = {
                (base / "slots" / slot).resolve(strict=False)
                for slot in ("blue", "green")
            }
            if active_target not in valid_targets:
                findings.append(f"{environment} active pointer is outside its slots")
            current = pointers[environment]["current"]
            active_release = (
                active_target / "release" if active_target is not None else None
            )
            if (
                current
                and active_release
                and active_release.is_symlink()
                and str(active_release.resolve(strict=False)) != current
            ):
                findings.append(
                    f"{environment} current and active slot release disagree"
                )
            expected_upstream = (
                "server unix:/srv/paperswithcode/environments/"
                f"{environment}/active/backend.sock;"
            )
            if expected_upstream not in nginx:
                findings.append(
                    f"{environment} active slot is prepared but nginx is still legacy"
                )
    return {
        "findings": findings,
        "pointers": pointers,
        "slots": slots,
        "ports": output(["ss", "-ltnp"]),
        "disk": output(["df", "-h", "/"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = audit()
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("Topology findings:")
        for finding in result["findings"]:
            print(f"- {finding}")
    return 1 if result["findings"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
