from backend.scripts.qualify_chat_pool import PoolSample, summarize


def test_pool_qualification_summary_is_sanitized_and_reports_active_cost():
    samples = [
        PoolSample(
            request_id="00000000-0000-0000-0000-000000000001",
            acquisition_outcome="pool_hit",
            pool_lookup_ms=20,
            sdk_dispatch_ms=80,
            first_delta_ms=300,
            total_ms=500,
            estimated_active_cost_usd=0.00001,
            terminal_status="complete",
            error_code=None,
        ),
        PoolSample(
            request_id="00000000-0000-0000-0000-000000000002",
            acquisition_outcome="pool_hit",
            pool_lookup_ms=30,
            sdk_dispatch_ms=90,
            first_delta_ms=350,
            total_ms=550,
            estimated_active_cost_usd=0.00002,
            terminal_status="complete",
            error_code=None,
        ),
    ]

    result = summarize(samples)

    assert result["complete"] == 2
    assert result["pool_hits"] == 2
    assert result["sdk_dispatch_ms"]["p95"] == 90
    assert result["estimated_active_cost_usd"] == {
        "total": 0.00003,
        "per_completed_turn": 0.000015,
    }
