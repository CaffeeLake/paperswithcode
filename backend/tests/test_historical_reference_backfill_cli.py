"""Contracts for the historical reference-backfill credential gate."""

from __future__ import annotations

import sys
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

WORKFLOWS_PATH = Path(__file__).resolve().parents[2] / ".github" / "workflows"
if str(WORKFLOWS_PATH) not in sys.path:
    sys.path.insert(0, str(WORKFLOWS_PATH))

from scripts.backfill.backfill_method_references import (  # noqa: E402
    main,
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


def test_reference_backfill_cli_fails_when_provider_lookup_stops_progress(
    monkeypatch, capsys
):
    client = SimpleNamespace(close=lambda: None)
    monkeypatch.setattr(sys, "argv", ["backfill_method_references.py"])
    monkeypatch.setattr(
        "scripts.backfill.backfill_method_references.get_settings",
        lambda: SimpleNamespace(semantic_scholar_api_key_2="secondary"),
    )
    monkeypatch.setattr(
        "scripts.backfill.backfill_method_references.validate_secondary_key",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "scripts.backfill.backfill_method_references.SemanticScholarClient",
        lambda **_kwargs: client,
    )
    monkeypatch.setattr(
        "scripts.backfill.backfill_method_references.run_reference_backfill",
        lambda *_args, **_kwargs: SimpleNamespace(papers_failed=1),
    )
    monkeypatch.setattr(
        "scripts.backfill.backfill_method_references.db_manager",
        SimpleNamespace(session_local=lambda: nullcontext(SimpleNamespace())),
    )

    assert main() == 1
    assert "provider lookup failure" in capsys.readouterr().err
