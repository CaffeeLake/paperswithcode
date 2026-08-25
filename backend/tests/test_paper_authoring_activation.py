from __future__ import annotations

from backend.chat_sandbox_worker.agent import WorkerToolHooks
from backend.chat_sandbox_worker.config import WorkerSettings
from backend.chat_sandbox_worker.prompt import render


def test_paper_prompt_is_feature_gated_and_includes_only_bounded_metadata():
    disabled = render(paper_artifacts_enabled=False)
    enabled = render(
        paper_artifacts_enabled=True,
        paper_descriptor={"artifact_id": "paper-1", "title": "Careful draft"},
    )

    assert "## Private paper authoring" not in disabled
    assert "# private paper authoring guide" not in disabled
    assert '"paper_artifacts_enabled":false' in disabled
    assert "## Private paper authoring" in enabled
    assert "pwc-paper create" in enabled
    assert '"artifact_id":"paper-1"' in enabled
    assert '"paper_artifacts_enabled":true' in enabled


def test_paper_cli_activation_lazily_extends_worker_limits():
    settings = WorkerSettings(
        chat_max_tool_calls=12,
        chat_max_turns=8,
        chat_max_direct_search_calls=4,
        chat_latex_paper_max_tool_calls=30,
        chat_latex_paper_max_tool_rounds=12,
        chat_latex_paper_max_direct_search_calls=8,
        chat_latex_paper_timeout_seconds=600,
    )
    hooks = WorkerToolHooks(settings)

    assert hooks.budget.maximum_calls == 12
    assert hooks.budget.maximum_rounds == 6
    assert hooks.budget.maximum_direct_searches == 4
    hooks.activate_paper(settings)

    assert hooks.paper_activated
    assert hooks.budget.maximum_calls == 30
    assert hooks.budget.maximum_rounds == 12
    assert hooks.budget.maximum_direct_searches == 8
    assert hooks.bash_timeout_ms == 600_000
