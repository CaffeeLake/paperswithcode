#!/usr/bin/env python3
"""Raise the production chat application circuit below the provider budget."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

try:
    from deploy.configure_host_env import assign, decoded_value, read_lines, write_env
except ModuleNotFoundError:
    from configure_host_env import assign, decoded_value, read_lines, write_env

CONFIG_PATH = Path("/etc/paperswithcode/production.env")
CONFIRMATION = "RAISE_PRODUCTION_CHAT_APPLICATION_CAP_225"


def raised_values(current: dict[str, str]) -> dict[str, str]:
    expected = {
        "PWC_CHAT_SANDBOX_WARNING_MICROUSD": "75000000",
        "PWC_CHAT_SANDBOX_APPLICATION_CAP_MICROUSD": "100000000",
        "PWC_CHAT_SANDBOX_ENVIRONMENT_CAP_MICROUSD": "250000000",
        "PWC_CHAT_SANDBOX_WORKSPACE_CAP_MICROUSD": "250000000",
        "PWC_CHAT_SANDBOX_PROVIDER_MODE": "team_environments",
        "PWC_CHAT_SANDBOX_BUDGET_ATTESTATION": (
            "modal-workspace-paperswithcode-250-production-250-v2"
        ),
    }
    actual = {key: decoded_value(current.get(key, "")).strip() for key in expected}
    if actual != expected:
        raise ValueError("production chat budget does not match reviewed policy v2")
    return assign(
        current,
        {
            "PWC_CHAT_SANDBOX_WARNING_MICROUSD": "200000000",
            "PWC_CHAT_SANDBOX_APPLICATION_CAP_MICROUSD": "225000000",
            "PWC_CHAT_SANDBOX_BUDGET_ATTESTATION": (
                "modal-workspace-paperswithcode-250-production-250-warn200-app225-v3"
            ),
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm")
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("run through sudo")
    if args.confirm != CONFIRMATION:
        parser.error(f"--confirm must be {CONFIRMATION}")
    try:
        updated = raised_values(read_lines(CONFIG_PATH))
    except ValueError as error:
        parser.error(str(error))
    write_env(CONFIG_PATH, updated, "pwc-production")
    print("raised production chat warning/application caps to $200/$225")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
