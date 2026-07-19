from pathlib import Path
import sys
from unittest.mock import Mock

import pytest


WORKFLOWS_DIR = Path(__file__).parents[2] / ".github" / "workflows"
sys.path.insert(0, str(WORKFLOWS_DIR))

from scripts.hourly.update_github_stars import get_next_repository_group  # noqa: E402


def _session_with_row():
    session = Mock()
    session.execute.return_value.fetchall.return_value = [
        (
            "huggingface",
            "transformers",
            [1, 2],
            2,
            None,
            162_685,
            None,
            3,
        )
    ]
    return session


def test_fresh_queue_uses_recent_eligibility():
    session = _session_with_row()

    get_next_repository_group(session, "fresh")

    query = str(session.execute.call_args.args[0])
    assert "linked.newest_paper_date >= :six_months_ago" in query
    assert "repo_groups.oldest_update < :threshold_recent" in query
    assert "repo_groups.oldest_update ASC NULLS FIRST" in query
    assert "array_agg(r.id ORDER BY r.id)" in query


def test_weekly_queue_uses_regular_eligibility():
    session = _session_with_row()

    result = get_next_repository_group(session, "weekly")

    query = str(session.execute.call_args.args[0])
    assert "linked.newest_paper_date < :six_months_ago" in query
    assert "repo_groups.oldest_update < :threshold_regular" in query
    assert result["owner"] == "huggingface"
    assert result["repository_ids"] == [1, 2]


def test_unknown_queue_is_rejected():
    session = Mock()

    with pytest.raises(ValueError, match="Unknown GitHub stars queue"):
        get_next_repository_group(session, "other")

    session.execute.assert_not_called()


def test_database_errors_are_not_reported_as_an_empty_queue():
    session = Mock()
    session.execute.side_effect = RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        get_next_repository_group(session, "fresh")
