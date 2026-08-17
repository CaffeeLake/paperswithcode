from backend.scripts.qualify_chat_browser import qualification_passes


def test_browser_gate_requires_real_reasoning_and_both_latency_cohorts():
    rendered = {"new_reasoning": 50, "followup_reasoning": 50}
    gates = {
        "component": True,
        "model_to_application": True,
        "pool_browser": True,
        "reused_browser": True,
        "reliability": True,
        "accounting": True,
        "isolation": True,
        "hit_rate": False,
    }

    assert qualification_passes(
        rendered=rendered,
        minimum_reasoning=50,
        gates=gates,
        marked=100,
        session_count=50,
    )
    gates["reused_browser"] = False
    assert not qualification_passes(
        rendered=rendered,
        minimum_reasoning=50,
        gates=gates,
        marked=100,
        session_count=50,
    )
