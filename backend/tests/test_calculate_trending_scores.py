"""Regression tests for the repository EMA trending cron."""

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_SCRIPTS = REPO_ROOT / ".github" / "workflows"
CRON_SCRIPT = WORKFLOW_SCRIPTS / "scripts" / "hourly" / "calculate_trending_scores.py"


def _load_cron_module():
    sys.path.insert(0, str(WORKFLOW_SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "calculate_trending_scores_for_test", CRON_SCRIPT
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _Result:
    def __init__(self, row=(0, 0, 0), rows=None):
        self.row = row
        self.rows = rows or []

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class _Session:
    def __init__(self, result=None, error=None):
        self.result = result or _Result()
        self.error = error
        self.statement = None
        self.params = None
        self.committed = False
        self.rolled_back = False

    def execute(self, statement, params):
        self.statement = str(statement)
        self.params = params
        if self.error:
            raise self.error
        return self.result

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def test_process_repository_batch_sanitizes_and_clamps_scores():
    cron = _load_cron_module()
    session = _Session(result=_Result(row=(2, 0, 0)))

    result = cron.process_repository_batch(session, [101, 102])

    assert result == {"updated": 2, "insufficient": 0, "skipped": 0}
    assert session.committed is True
    assert "LIMIT 10" in session.statement
    assert "valid_pairs AS" in session.statement
    assert "trending_score::text = 'NaN'" in session.statement
    assert "WHEN trending_score < :min_prev_score THEN 0.0" in session.statement
    assert "WHEN trending_score > :max_score THEN :max_score" in session.statement
    assert "LEAST(GREATEST(new_score, 0.0), :max_score)::numeric(10, 4)" in (
        session.statement
    )
    assert session.params["min_prev_score"] == cron.MIN_PREVIOUS_SCORE
    assert session.params["max_score"] == cron.MAX_TRENDING_SCORE


def test_process_repository_batch_reraises_batch_errors():
    cron = _load_cron_module()
    session = _Session(error=RuntimeError("numeric underflow"))

    with pytest.raises(RuntimeError, match="numeric underflow"):
        cron.process_repository_batch(session, [160474])

    assert session.rolled_back is True
    assert session.committed is False


def test_repository_queue_prioritizes_recent_official_paper_repos():
    cron = _load_cron_module()
    session = _Session(result=_Result(rows=[(42,), (43,)]))

    repo_ids = cron.get_repositories_needing_trending_update(
        session, batch_size=2, update_threshold_hours=1
    )

    assert repo_ids == [42, 43]
    assert "LEFT JOIN paper_repositories pr" in session.statement
    assert "pr.is_official = TRUE" in session.statement
    assert "p.is_latest_version" in session.statement
    assert "MAX(p.date_published) >= NOW() - INTERVAL '30 days'" in session.statement
