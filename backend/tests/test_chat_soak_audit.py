import json
from datetime import UTC, date, datetime, timedelta

from backend.scripts.audit_chat_soak import _parse_time, _status, render_report


def test_parse_time_requires_an_explicit_timezone():
    assert _parse_time("2026-07-31T12:00:00Z") == datetime(2026, 7, 31, 12, tzinfo=UTC)

    try:
        _parse_time("2026-07-31T12:00:00")
    except ValueError as error:
        assert "timezone" in str(error)
    else:
        raise AssertionError("timezone-free start was accepted")


def test_render_report_serializes_dates_as_iso_8601():
    rendered = json.loads(
        render_report(
            {
                "observed_at": datetime(2026, 8, 4, 7, 16, tzinfo=UTC),
                "billing_cycle": date(2026, 8, 1),
            }
        )
    )

    assert rendered == {
        "observed_at": "2026-08-04T07:16:00+00:00",
        "billing_cycle": "2026-08-01",
    }


def test_status_fails_health_before_elapsed_or_sample_gates():
    now = datetime(2026, 7, 31, 12, tzinfo=UTC)
    finish = now + timedelta(days=1)

    assert (
        _status(
            now=now,
            finish=finish,
            sample_gates={"samples": False},
            health_gates={"healthy": False},
        )
        == "failed"
    )
    assert (
        _status(
            now=now,
            finish=finish,
            sample_gates={"samples": False},
            health_gates={"healthy": True},
        )
        == "soaking"
    )


def test_status_requires_samples_after_the_full_window():
    now = datetime(2026, 8, 7, 12, tzinfo=UTC)
    finish = now - timedelta(seconds=1)

    assert (
        _status(
            now=now,
            finish=finish,
            sample_gates={"samples": False},
            health_gates={"healthy": True},
        )
        == "insufficient_samples"
    )
    assert (
        _status(
            now=now,
            finish=finish,
            sample_gates={"samples": True},
            health_gates={"healthy": True},
        )
        == "telemetry_ready"
    )
