#!/usr/bin/env python3
"""Idempotently install shared-session keys into deployed app environments."""

from __future__ import annotations

import argparse
import os

from configure_host_env import (
    CONFIG_ROOT,
    assign,
    read_lines,
    shared_session_keys,
    write_env,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--confirm",
        choices=["INSTALL_SHARED_AUTH"],
        required=True,
    )
    parser.parse_args()
    if os.geteuid() != 0:
        parser.error("run through sudo")

    production = read_lines(CONFIG_ROOT / "production.env")
    staging = read_lines(CONFIG_ROOT / "staging.env")
    if not production or not staging:
        parser.error("production.env and staging.env must already exist")

    private_key, public_key = shared_session_keys(production, staging)
    common = {
        "PWC_AUTH_AUTHORITY_ORIGIN": "https://paperswithcode.co",
        "PWC_AUTH_RETURN_ORIGINS": (
            "https://paperswithcode.co,https://staging.paperswithcode.co"
        ),
        "PWC_SHARED_SESSION_COOKIE_DOMAIN": ".paperswithcode.co",
        "PWC_SHARED_SESSION_COOKIE_NAME": "pwc_shared_session",
        "PWC_SESSION_VERIFICATION_PUBLIC_KEY": public_key,
    }
    production = assign(
        production,
        {**common, "PWC_SESSION_SIGNING_PRIVATE_KEY": private_key},
    )
    staging.pop("PWC_SESSION_SIGNING_PRIVATE_KEY", None)
    staging = assign(staging, common)

    write_env(CONFIG_ROOT / "production.env", production, "pwc-production")
    write_env(CONFIG_ROOT / "staging.env", staging, "pwc-staging")
    print("installed shared-session verifier and production-only signer")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
