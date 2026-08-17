#!/usr/bin/env python3
"""Align production chat with the reviewed $250 Modal Environment budget."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from deploy.configure_host_env import assign, decoded_value, read_lines, write_env

CONFIG_PATH = Path("/etc/paperswithcode/production.env")
CONFIRMATION = "ALIGN_PRODUCTION_CHAT_ENVIRONMENT_BUDGET_250"


def aligned_values(current: dict[str, str]) -> dict[str, str]:
    expected = {
        "PWC_CHAT_SANDBOX_WARNING_MICROUSD": "75000000",
        "PWC_CHAT_SANDBOX_APPLICATION_CAP_MICROUSD": "100000000",
        "PWC_CHAT_SANDBOX_ENVIRONMENT_CAP_MICROUSD": "125000000",
        "PWC_CHAT_SANDBOX_WORKSPACE_CAP_MICROUSD": "250000000",
        "PWC_CHAT_SANDBOX_PROVIDER_MODE": "team_environments",
        "PWC_CHAT_SANDBOX_BUDGET_ATTESTATION": (
            "modal-workspace-paperswithcode-250-production-125-v1"
        ),
    }
    actual = {key: decoded_value(current.get(key, "")).strip() for key in expected}
    if actual != expected:
        raise ValueError("production chat budget does not match reviewed policy v1")
    return assign(
        current,
        {
            "PWC_CHAT_SANDBOX_ENVIRONMENT_CAP_MICROUSD": "250000000",
            "PWC_CHAT_SANDBOX_BUDGET_ATTESTATION": (
                "modal-workspace-paperswithcode-250-production-250-v2"
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
        updated = aligned_values(read_lines(CONFIG_PATH))
    except ValueError as error:
        parser.error(str(error))
    write_env(CONFIG_PATH, updated, "pwc-production")
    print("aligned production chat with the $250 Modal Environment budget")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
