#!/usr/bin/env python3
"""Explicit nginx lifecycle command; ordinary deploys never call this."""

from __future__ import annotations

import argparse
import difflib
import os
import shutil
import subprocess
import sys
from pathlib import Path

INSTALL_ROOT = Path("/usr/local/lib/paperswithcode-deploy")
SITES = {
    "production": "paperswithcode.co",
    "staging": "staging.paperswithcode.co",
}
CONFIRMATIONS = {
    "production": "APPLY_NGINX_PRODUCTION",
    "staging": "APPLY_NGINX_STAGING",
}


def main() -> int:
    parser = argparse.ArgumentParser(prog="pwc-nginx")
    parser.add_argument("environment", choices=SITES)
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("run through sudo")
    if args.confirm != CONFIRMATIONS[args.environment]:
        parser.error(f"expected --confirm {CONFIRMATIONS[args.environment]}")
    name = SITES[args.environment]
    source = INSTALL_ROOT / "nginx" / f"{name}.conf"
    target = Path("/etc/nginx/sites-available") / name
    current = target.read_text().splitlines(keepends=True) if target.exists() else []
    candidate = source.read_text().splitlines(keepends=True)
    sys.stdout.writelines(
        difflib.unified_diff(
            current, candidate, fromfile=str(target), tofile=str(source)
        )
    )
    backup = target.with_suffix(target.suffix + ".pre-pwc-nginx")
    if target.exists():
        shutil.copy2(target, backup)
    shutil.copy2(source, target)
    enabled = Path("/etc/nginx/sites-enabled") / name
    if not enabled.exists():
        enabled.symlink_to(target)
    try:
        subprocess.run(["nginx", "-t"], check=True)
        subprocess.run(["systemctl", "reload", "nginx"], check=True)
        subprocess.run(
            [
                "/srv/paperswithcode/.venv/bin/python",
                str(INSTALL_ROOT / "smoke_test.py"),
                "--environment",
                args.environment,
                "--base-url",
                (
                    "https://paperswithcode.co"
                    if args.environment == "production"
                    else "https://staging.paperswithcode.co"
                ),
                "--monitor-subset",
            ],
            check=True,
        )
    except subprocess.CalledProcessError:
        if backup.exists():
            shutil.copy2(backup, target)
            subprocess.run(["nginx", "-t"], check=True)
            subprocess.run(["systemctl", "reload", "nginx"], check=True)
        raise
    backup.unlink(missing_ok=True)
    print(f"applied and validated nginx configuration for {args.environment}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
