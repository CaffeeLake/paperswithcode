"""Focused tests for full-corpus normalization with targeted paper writes."""

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    REPO_ROOT
    / ".github"
    / "workflows"
    / "scripts"
    / "hourly"
    / "calculate_paper_trending_scores.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "calculate_paper_trending_scores_for_test", SCRIPT
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_targeted_compute_only_changes_selected_papers(monkeypatch):
    cron = _load_module()
    population = {
        1: {"github_raw": 10.0, "existing": False, "artifacts": []},
        2: {"github_raw": 2.0, "existing": True, "artifacts": []},
        3: {"github_raw": 0.0, "existing": True, "artifacts": []},
    }
    calls = []

    def fake_compute(github_raw, github_corpus, artifacts, artifact_corpora):
        calls.append((github_raw, list(github_corpus)))
        return github_raw, github_raw, 0.0

    monkeypatch.setattr(cron, "compute_paper_score", fake_compute)
    github_corpus, hf_corpora = cron.derive_corpora(population)
    updates, clears = cron.build_score_changes(
        population, github_corpus, hf_corpora, paper_ids=[2, 3]
    )

    assert [update["id"] for update in updates] == [2]
    assert clears == [3]
    assert len(calls) == 2
    # The selected score is still normalized against paper 1's larger signal.
    assert calls[0][1] == [2.0, 10.0]


def test_full_and_targeted_compute_agree_for_same_paper(monkeypatch):
    cron = _load_module()
    population = {
        1: {"github_raw": 10.0, "existing": False, "artifacts": []},
        2: {"github_raw": 2.0, "existing": False, "artifacts": []},
    }
    github_corpus, hf_corpora = cron.derive_corpora(population)
    full, _ = cron.build_score_changes(population, github_corpus, hf_corpora)
    targeted, _ = cron.build_score_changes(
        population, github_corpus, hf_corpora, paper_ids=[2]
    )

    assert targeted == [next(update for update in full if update["id"] == 2)]
