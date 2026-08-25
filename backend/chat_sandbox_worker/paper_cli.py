#!/usr/bin/env python3
"""Authenticated, current-turn-only client for private paper operations."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

BROKER = "http://127.0.0.1:8765"
EVENT_PREFIX = "@@PWC_PAPER@@"
MAX_RESPONSE = 32 * 1024


def _command(operation: str, *, title: str | None = None) -> int:
    payload = {"operation": operation, **({"title": title} if title else {})}
    request = urllib.request.Request(
        f"{BROKER}/paper",
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(),
        {"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=130) as response:
            data = response.read(MAX_RESPONSE + 1)
    except urllib.error.HTTPError as error:
        detail = error.read(8 * 1024).decode(errors="replace")
        raise RuntimeError(detail or f"Paper request failed ({error.code})") from None
    if len(data) > MAX_RESPONSE:
        raise RuntimeError("Paper response exceeded its bound")
    result = json.loads(data)
    if not isinstance(result, dict) or set(result) != {
        "operation",
        "activated",
        "paper",
    }:
        raise RuntimeError("Invalid paper response")
    print(EVENT_PREFIX + json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="pwc-paper")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--title", required=True)
    commands.add_parser("begin-edit")
    args = parser.parse_args()
    try:
        return _command(args.command, title=getattr(args, "title", None))
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
