from backend.scripts.report_chat_ttft import distribution, passes


def test_ttft_report_distribution_and_gate_are_explicit():
    values = list(range(1, 101))

    result = distribution(values)

    assert result == {
        "count": 100,
        "min": 1,
        "p50": 50,
        "p75": 75,
        "p90": 90,
        "p95": 95,
        "p99": 99,
        "max": 100,
    }
    assert passes(result, count=50, p50=50, p90=90)
    assert not passes(result, count=101, p50=50, p90=90)
