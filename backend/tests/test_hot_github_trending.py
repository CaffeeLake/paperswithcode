"""Integration-style orchestration test for the 15-minute hot pipeline."""

from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock


WORKFLOWS_DIR = Path(__file__).parents[2] / ".github" / "workflows"
if str(WORKFLOWS_DIR) not in sys.path:
    sys.path.append(str(WORKFLOWS_DIR))

from scripts.hourly import update_hot_github_trending as hot  # noqa: E402


def test_hot_job_fetches_scores_and_propagates_in_one_run(monkeypatch):
    monkeypatch.setenv("PWC_GITHUB_TOKEN", "shared")
    monkeypatch.delenv("PWC_GITHUB_TOKEN_HOT", raising=False)
    monkeypatch.setattr(
        hot,
        "run_queue",
        lambda *args, **kwargs: {
            "eligible_groups": 1,
            "selected_groups": 1,
            "processed_groups": 1,
            "api_calls": 1,
            "successes": 1,
            "failures": 0,
            "retries": 0,
            "snapshots_stored": 1,
            "rate_limit_stops": 0,
            "rate_limit_limit": 5000,
            "rate_limit_remaining": 4500,
            "rate_limit_reset": 123,
            "oldest_eligible_age_days": 0,
            "touched_repository_ids": [11],
        },
    )
    session = Mock()
    monkeypatch.setattr(
        hot, "db_manager", SimpleNamespace(session_local=lambda: session)
    )
    repository_calls = []
    monkeypatch.setattr(
        hot,
        "calculate_repository_scores",
        lambda db, ids, **kwargs: repository_calls.append((db, ids, kwargs))
        or {"updated": 1, "insufficient": 0, "skipped": 0},
    )
    monkeypatch.setattr(
        hot, "get_latest_paper_ids_for_repositories", lambda db, ids: [101]
    )
    paper_calls = []
    monkeypatch.setattr(
        hot,
        "calculate_paper_scores",
        lambda db, paper_ids: paper_calls.append((db, paper_ids))
        or {"population": 2, "selected": 1, "written": 1, "cleared": 0},
    )

    job = hot.HotGitHubTrendingJob.__new__(hot.HotGitHubTrendingJob)
    job.selection_only = False
    job.logger = Mock()
    job.run()

    assert repository_calls[0][1] == [11]
    assert repository_calls[0][2]["hot_mode"] is True
    assert paper_calls == [(session, [101])]
    session.close.assert_called_once()
    summaries = [
        call
        for call in job.logger.info.call_args_list
        if "HOT_GITHUB_TRENDING_SUMMARY" in call.args[0]
    ]
    assert len(summaries) == 1
