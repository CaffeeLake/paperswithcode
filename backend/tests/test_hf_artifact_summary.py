from types import SimpleNamespace

from backend.services.paper_service import PaperService


def _paper(arxiv_id=None, models=None, datasets=None, spaces=None):
    return SimpleNamespace(
        arxiv_id=arxiv_id,
        hf_models=models or [],
        hf_datasets=datasets or [],
        hf_spaces=spaces or [],
    )


def test_no_artifacts_returns_none():
    summary = PaperService._build_hf_artifact_summary(_paper(arxiv_id="2605.20613"), {})
    assert summary is None


def test_arxiv_picks_most_populated_category_link():
    paper = _paper(arxiv_id="2605.20613")
    summary = PaperService._build_hf_artifact_summary(
        paper, {"model": 7, "dataset": 3, "space": 1}
    )
    assert summary is not None
    assert summary.best_kind == "model"
    assert summary.best_count == 7
    assert summary.model_count == 7
    assert summary.dataset_count == 3
    assert summary.space_count == 1
    assert summary.best_url == "https://huggingface.co/models?other=arxiv:2605.20613"


def test_arxiv_dataset_winner_uses_datasets_path():
    paper = _paper(arxiv_id="2605.20613")
    summary = PaperService._build_hf_artifact_summary(
        paper, {"model": 1, "dataset": 5, "space": 0}
    )
    assert summary.best_kind == "dataset"
    assert summary.best_url == "https://huggingface.co/datasets?other=arxiv:2605.20613"


def test_tie_breaks_model_then_dataset_then_space():
    paper = _paper(arxiv_id="2605.20613")
    summary = PaperService._build_hf_artifact_summary(
        paper, {"model": 4, "dataset": 4, "space": 4}
    )
    assert summary.best_kind == "model"

    summary = PaperService._build_hf_artifact_summary(paper, {"dataset": 4, "space": 4})
    assert summary.best_kind == "dataset"


def test_arxiv_space_winner_uses_papers_page():
    paper = _paper(arxiv_id="2605.20613")
    summary = PaperService._build_hf_artifact_summary(
        paper, {"model": 1, "dataset": 0, "space": 4}
    )
    assert summary.best_kind == "space"
    assert summary.best_count == 4
    assert summary.best_url == "https://huggingface.co/papers/2605.20613"


def test_external_paper_uses_explicit_url():
    paper = _paper(
        models=[
            "https://huggingface.co/org/model-a",
            "https://huggingface.co/org/model-b",
        ],
        datasets=["https://huggingface.co/datasets/org/ds"],
    )
    summary = PaperService._build_hf_artifact_summary(paper, {})
    assert summary.best_kind == "model"
    assert summary.best_count == 2
    assert summary.best_url == "https://huggingface.co/org/model-a"


def test_counts_combine_junction_and_explicit_max():
    paper = _paper(arxiv_id="2605.20613", models=["https://huggingface.co/org/m"])
    summary = PaperService._build_hf_artifact_summary(paper, {"model": 3})
    assert summary.model_count == 3
