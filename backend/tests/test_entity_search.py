"""Pure relevance-policy coverage shared by all entity search services."""

import pytest

from backend.services.entity_search import (
    EntitySearchKind,
    choose_fuzzy_winner,
    deterministic_match,
    normalize_entity_search_text,
    prepare_entity_search,
    tokenize_entity_search_text,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("SWE-Bench_Multilingual", "swe bench multilingual"),
        ("τ²-Bench", "tau2 bench"),
        ("SIR²+", "sir2+"),
        ("512×288", "512x288"),
        ("Ego→Exo", "ego to exo"),
        ("ScanNet++", "scannet++"),
    ],
)
def test_bounded_normalization(raw, expected):
    assert normalize_entity_search_text(raw) == expected


def test_meaningful_punctuation_stays_distinct_for_identity():
    assert normalize_entity_search_text("ScanNet") != normalize_entity_search_text(
        "ScanNet++"
    )
    assert normalize_entity_search_text("C#") != normalize_entity_search_text("C")
    assert normalize_entity_search_text("Model 2.1") != normalize_entity_search_text(
        "Model 21"
    )


def test_canonical_routes_are_identity_only():
    terms = prepare_entity_search(
        "https://paperswithcode.co/benchmark/swe-bench/?ignored=yes",
        EntitySearchKind.DATASET,
    )
    assert terms.identity_only
    assert terms.slug_identity == "swe-bench"
    assert deterministic_match(terms, name="SWE-Bench", slug="swe-bench") == (0, 1.0)
    assert (
        deterministic_match(terms, name="SWE-Bench Pro", slug="swe-bench-pro") is None
    )


@pytest.mark.parametrize(
    "query",
    [
        "https://example.com/benchmark/swe-bench",
        "https://paperswithcode.co/paper/swe-bench",
        "/datasets/swe-bench",
    ],
)
def test_untrusted_or_unrelated_routes_are_rejected(query):
    assert prepare_entity_search(query, EntitySearchKind.DATASET).invalid


def test_plain_numeric_query_is_not_an_id_or_slug_identity():
    terms = prepare_entity_search("427", EntitySearchKind.DATASET)
    assert terms.slug_identity is None
    assert terms.tokens == ("427",)


@pytest.mark.parametrize(
    ("query", "name"),
    [
        ("swe bench multilingual", "SWE-Bench Multilingual"),
        ("multilingual swe bench", "SWE-Bench Multilingual"),
        ("swe ben mul", "SWE-Bench Multilingual"),
        ("k3", "Kimi K3"),
        ("tau2 bench", "τ²-Bench"),
        ("sir2", "SIR²+ WildScene"),
        ("512x288", "VideoMatte (512×288)"),
        ("ego to exo", "Ego-Exo4D (Ego→Exo)"),
    ],
)
def test_all_token_prefix_matching(query, name):
    terms = prepare_entity_search(query, EntitySearchKind.DATASET)
    match = deterministic_match(terms, name=name, slug="unrelated-slug")
    assert match is not None
    assert match[0] in {1, 3}


def test_prefix_matching_does_not_use_infixes():
    terms = prepare_entity_search("imi", EntitySearchKind.DATASET)
    assert deterministic_match(terms, name="Kimi K3", slug="kimi-k3") is None


def test_full_name_is_exact_identity_only():
    exact = prepare_entity_search(
        "Convolutional Neural Network", EntitySearchKind.METHOD
    )
    partial = prepare_entity_search("Neural", EntitySearchKind.METHOD)
    assert deterministic_match(
        exact,
        name="CNN",
        slug="cnn",
        full_name="Convolutional Neural Network",
    ) == (2, 1.0)
    assert (
        deterministic_match(
            partial,
            name="CNN",
            slug="cnn",
            full_name="Convolutional Neural Network",
        )
        is None
    )


def test_blank_and_punctuation_only_queries_are_not_usable():
    assert not prepare_entity_search("   ", EntitySearchKind.TASK).usable
    assert not prepare_entity_search("---___///", EntitySearchKind.TASK).usable
    assert tokenize_entity_search_text("---___///") == ()


def test_fuzzy_winner_requires_confidence_and_margin():
    winner = choose_fuzzy_winner(
        "swe benhc",
        [
            (21, "SWE-Bench", 0.75),
            (22, "SWE-Bench Verified", 0.60),
        ],
    )
    assert winner is not None
    assert winner.entity_id == 21
    assert (
        choose_fuzzy_winner(
            "multilingal",
            [
                (1, "SWE-Bench Multilingual", 0.60),
                (2, "FLEURS Multilingual", 0.58),
            ],
        )
        is None
    )
    assert choose_fuzzy_winner("zzzzzz", [(1, "ImageNet", 0.2)]) is None
