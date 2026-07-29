"""Contracts for the historical reference-backfill credential gate."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

WORKFLOWS_PATH = Path(__file__).resolve().parents[2] / ".github" / "workflows"
if str(WORKFLOWS_PATH) not in sys.path:
    sys.path.insert(0, str(WORKFLOWS_PATH))

from scripts.backfill.backfill_method_references import (  # noqa: E402
    validate_secondary_key,
)


def test_secondary_key_probe_waits_one_request_cadence():
    sleeps: list[float] = []

    validate_secondary_key(
        "secondary",
        request_delay=1.5,
        probe=lambda _name: SimpleNamespace(success=True, http_status=200),
        sleep=sleeps.append,
    )

    assert sleeps == [1.5]


def test_secondary_key_gate_fails_closed_without_fallback():
    with pytest.raises(SystemExit, match="primary-key fallback is forbidden"):
        validate_secondary_key(
            "",
            request_delay=1,
            probe=lambda _name: SimpleNamespace(success=True, http_status=200),
            sleep=lambda _seconds: None,
        )

    with pytest.raises(SystemExit, match="validation failed \\(HTTP 429\\)"):
        validate_secondary_key(
            "secondary",
            request_delay=1,
            probe=lambda _name: SimpleNamespace(success=False, http_status=429),
            sleep=lambda _seconds: None,
        )
