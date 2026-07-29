"""Tests for CRON process detection without self-matching diagnostics."""

from types import SimpleNamespace
from unittest.mock import patch

from backend.services.cron_health import is_process_running


def _processes(*lines: str):
    return SimpleNamespace(returncode=0, stdout="\n".join(lines))


def test_process_detection_ignores_health_command_and_its_parent():
    output = _processes(
        "50 1 uv run pwc cron health backfill_method_references",
        "100 50 python -m backend.cli cron health backfill_method_references",
    )

    with (
        patch("backend.services.cron_health.os.getpid", return_value=100),
        patch("backend.services.cron_health.subprocess.run", return_value=output),
    ):
        assert not is_process_running(("backfill_method_references",))


def test_process_detection_finds_an_independent_worker():
    output = _processes(
        "50 1 uv run pwc cron health backfill_method_references",
        "100 50 python -m backend.cli cron health backfill_method_references",
        "200 1 python -m scripts.backfill.backfill_method_references --resume",
    )

    with (
        patch("backend.services.cron_health.os.getpid", return_value=100),
        patch("backend.services.cron_health.subprocess.run", return_value=output),
    ):
        assert is_process_running(("backfill_method_references",))
