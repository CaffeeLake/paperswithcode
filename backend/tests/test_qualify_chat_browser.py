from backend.scripts import qualify_chat_browser
from backend.scripts.qualify_chat_browser import (
    ChromePage,
    ORIGIN,
    pilot_passes,
    qualification_passes,
)


def test_devtools_connection_disables_idle_ping_timeout(monkeypatch):
    captured = {}
    expected = object()

    def fake_connect(url, **kwargs):
        captured.update(url=url, **kwargs)
        return expected

    monkeypatch.setattr(qualify_chat_browser, "connect", fake_connect)

    assert qualify_chat_browser._connect_devtools("ws://local") is expected
    assert captured == {
        "url": "ws://local",
        "open_timeout": 5,
        "ping_interval": None,
    }


def test_browser_populates_empty_composer_before_waiting_for_send(monkeypatch):
    page = object.__new__(ChromePage)
    page.timeout = 1
    evaluations: list[str] = []

    def evaluate(expression: str):
        evaluations.append(expression)
        if expression == "location.origin":
            return ORIGIN
        if "querySelectorAll('.chat-msg-assistant').length" in expression:
            return 0
        if "HTMLTextAreaElement.prototype" in expression:
            return True
        if 'button[aria-label="Send message"].click' in expression:
            return None
        return {
            "reasoning": True,
            "tool": False,
            "answer": False,
            "busy": False,
            "error": False,
            "path": "/chat/00000000-0000-0000-0000-000000000001",
        }

    monkeypatch.setattr(page, "evaluate", evaluate)
    monkeypatch.setattr(page, "wait_for", lambda *_args, **_kwargs: True)

    result = page.send_turn("qualification prompt")

    composer = next(
        expression
        for expression in evaluations
        if "HTMLTextAreaElement.prototype" in expression
    )
    assert "if(!input || !send) return false" in composer
    assert "send.disabled) return false" not in composer
    assert result["reasoning"] is True


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


def test_browser_pilot_requires_every_pair_and_reasoning_render():
    rendered = {
        "new_reasoning": 5,
        "new_tool": 0,
        "new_answer": 5,
        "followup_reasoning": 5,
        "followup_tool": 0,
        "followup_answer": 5,
    }

    assert pilot_passes(rendered=rendered, pairs=5, marked=10, session_count=5)
    rendered["followup_reasoning"] = 4
    assert not pilot_passes(rendered=rendered, pairs=5, marked=10, session_count=5)


def test_browser_selects_an_explicit_discovered_model(monkeypatch):
    page = object.__new__(ChromePage)
    page.timeout = 1
    evaluations: list[str] = []

    def evaluate(expression: str):
        evaluations.append(expression)
        return True

    monkeypatch.setattr(page, "evaluate", evaluate)
    monkeypatch.setattr(page, "wait_for", lambda *_args, **_kwargs: True)

    page.select_model("openai/gpt-5.6-luna")

    assert any('select.value="openai/gpt-5.6-luna"' in item for item in evaluations)
