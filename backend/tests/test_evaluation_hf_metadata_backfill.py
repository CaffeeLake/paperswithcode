from types import SimpleNamespace

import pytest

from backend.services.evaluation_hf_metadata_backfill import (
    EvaluationMetadataBackfill,
    EvaluationRow,
    MetadataProposal,
    apply_fill_only,
    canonical_hf_model_url,
    normalized_model_variant,
    verify_sibling_consistency,
)


def _row(
    id: int,
    paper_id: int = 1,
    model_name: str = "Model-2.0_Base",
    hf_model_url: str | None = None,
    num_parameters: int | None = None,
) -> EvaluationRow:
    return EvaluationRow(id, paper_id, model_name, hf_model_url, num_parameters)


def test_canonical_urls_reject_paths_and_normalization_preserves_variants():
    assert canonical_hf_model_url("https://huggingface.co/Org/Model_2.0") == (
        "https://huggingface.co/Org/Model_2.0"
    )
    assert canonical_hf_model_url("https://huggingface.co/Org/Model/tree/main") is None
    assert canonical_hf_model_url("https://huggingface.co//Org/Model/") is None
    assert canonical_hf_model_url(" https://huggingface.co/Org/Model") is None
    assert canonical_hf_model_url("https://huggingface.co/models?search=x") is None
    assert normalized_model_variant("Model-2.0_Base") == "model\x1f2\x1f0\x1fbase"
    assert normalized_model_variant("Model-20_Base") == "model\x1f20\x1fbase"
    assert normalized_model_variant("Model-2.0_Base") != normalized_model_variant(
        "Model-2.00_Base"
    )


def test_propagates_unambiguous_siblings_and_reports_conflicts_without_lookup():
    backfill = EvaluationMetadataBackfill(
        lambda _repo: (_ for _ in ()).throw(AssertionError())
    )
    result = backfill.plan(
        [
            _row(1, hf_model_url="https://huggingface.co/org/model", num_parameters=7),
            _row(2),
            _row(3, paper_id=2, hf_model_url="https://huggingface.co/org/a"),
            _row(4, paper_id=2, hf_model_url="https://huggingface.co/org/b"),
        ],
        {1: [], 2: []},
    )
    assert result.proposals[2].hf_model_url == "https://huggingface.co/org/model"
    assert result.proposals[2].num_parameters == 7
    assert result.sibling_url_conflicts == {"2:model\x1f2\x1f0\x1fbase": [3, 4]}
    assert 3 not in result.proposals and 4 not in result.proposals


def test_count_conflicts_leave_the_entire_displayed_entry_unchanged():
    backfill = EvaluationMetadataBackfill(
        lambda _repo: (_ for _ in ()).throw(AssertionError())
    )
    result = backfill.plan(
        [
            _row(
                1,
                model_name="conflict",
                hf_model_url="https://huggingface.co/o/conflict",
                num_parameters=7,
            ),
            _row(2, model_name="conflict", num_parameters=8),
            _row(3, model_name="conflict"),
        ],
        {1: []},
    )
    assert result.sibling_count_conflicts == {"1:conflict": [1, 2, 3]}
    assert result.proposals == {}


def test_case_insensitive_sibling_urls_are_unambiguous():
    result = EvaluationMetadataBackfill(lambda _repo: None).plan(
        [
            _row(1, hf_model_url="https://huggingface.co/Org/Model"),
            _row(2, hf_model_url="https://huggingface.co/org/model"),
            _row(3),
        ],
        {1: []},
    )
    assert result.sibling_url_conflicts == {}
    assert result.proposals[3].hf_model_url == "https://huggingface.co/Org/Model"


def test_exact_paper_match_uses_cached_safetensors_total_and_never_parses_name():
    calls = []

    def lookup(repo_id):
        calls.append(repo_id)
        return SimpleNamespace(id="owner/Model_2.0-Base", safetensors={"total": 123})

    backfill = EvaluationMetadataBackfill(lookup)
    result = backfill.plan(
        [
            _row(1, model_name="Model-2.0_Base"),
            _row(2, model_name="Model_2-0.Base"),
            _row(3, paper_id=2, model_name="Model-2.0_Base"),
        ],
        {
            1: ["https://huggingface.co/owner/Model_2.0-Base"],
            2: ["https://huggingface.co/owner/Model_2.0-Base"],
        },
    )
    assert calls == ["owner/Model_2.0-Base"]
    assert (
        result.proposals[1].hf_model_url
        == "https://huggingface.co/owner/Model_2.0-Base"
    )
    assert result.proposals[1].num_parameters == 123
    assert result.proposals[2].num_parameters == 123
    assert result.proposals[3].num_parameters == 123


def test_ambiguous_and_missing_safetensors_are_reported_and_apply_is_fill_only():
    def lookup(repo_id):
        return SimpleNamespace(id=repo_id, safetensors=None)

    backfill = EvaluationMetadataBackfill(lookup)
    result = backfill.plan(
        [
            _row(1, model_name="same"),
            _row(2, paper_id=2, model_name="only", num_parameters=9),
            _row(3, paper_id=3, model_name="no-weights"),
        ],
        {
            1: [
                "https://huggingface.co/a/same",
                "https://huggingface.co/b/same",
            ],
            2: ["https://huggingface.co/o/only"],
            3: ["https://huggingface.co/o/no_weights"],
        },
    )
    assert result.ambiguous_matches == {"1:same": ["a/same", "b/same"]}
    assert result.missing_safetensors == ["o/no_weights"]
    assert result.proposals[2].hf_model_url == "https://huggingface.co/o/only"
    assert result.proposals[2].num_parameters is None


def test_existing_url_rejects_safetensors_from_a_different_repository():
    result = EvaluationMetadataBackfill(
        lambda _repo: SimpleNamespace(id="other/repository", safetensors={"total": 42})
    ).plan([_row(1, hf_model_url="https://huggingface.co/o/model")], {1: []})
    assert result.proposals == {}
    assert result.unavailable_repositories == ["o/model"]


def test_sibling_consistency_verification_rejects_a_post_apply_conflict():
    rows = {
        1: SimpleNamespace(
            id=1, hf_model_url="https://huggingface.co/o/a", num_parameters=1
        ),
        2: SimpleNamespace(
            id=2, hf_model_url="https://huggingface.co/o/b", num_parameters=1
        ),
    }
    with pytest.raises(RuntimeError, match="sibling URL conflict"):
        verify_sibling_consistency(rows, {"1:model": [1, 2]})


def test_apply_only_fills_currently_empty_values_and_is_idempotent():
    row = SimpleNamespace(id=1, hf_model_url=None, num_parameters=5)
    proposal = MetadataProposal("https://huggingface.co/o/model", 9)
    assert apply_fill_only({1: row}, {1: proposal}) == [1]
    assert row.hf_model_url == "https://huggingface.co/o/model"
    assert row.num_parameters == 5
    assert apply_fill_only({1: row}, {1: proposal}) == []
