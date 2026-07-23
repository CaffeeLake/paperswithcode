#!/usr/bin/env python3
"""Read-only audit of release, process, nginx, and legacy checkout coupling."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


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
    for environment in ("production", "staging"):
        base = root / "environments" / environment
        pointers[environment] = {
            name: str((base / name).resolve(strict=False))
            if (base / name).is_symlink()
            else None
            for name in ("current", "previous")
        }
    return {
        "findings": findings,
        "pointers": pointers,
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
