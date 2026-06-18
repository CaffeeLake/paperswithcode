from backend.utils.urls import external_source_url_to_paper_url, parse_arxiv_url
from backend.services.evaluation_service import (
    evaluation_is_external,
    evaluation_public_source_url,
    evaluation_result_url,
)


def test_parse_arxiv_url_supports_html_paths():
    assert parse_arxiv_url("https://arxiv.org/html/2606.13141v1") == (
        "2606.13141",
        "v1",
    )


def test_external_source_url_to_paper_url_rewrites_arxiv_links():
    assert (
        external_source_url_to_paper_url("https://arxiv.org/html/2606.13141v1")
        == "/paper/2606.13141"
    )
    assert (
        external_source_url_to_paper_url("https://arxiv.org/abs/2512.23351")
        == "/paper/2512.23351"
    )


def test_external_source_url_to_paper_url_leaves_non_arxiv_links():
    url = "https://huggingface.co/UsefulSensors/moonshine-streaming-tiny"
    assert external_source_url_to_paper_url(url) == url


def test_evaluation_result_url_prefers_pwc_for_external_arxiv_sources():
    assert (
        evaluation_result_url(
            "https://arxiv.org/html/2606.13141v1",
            40193,
            "2411.13093",
            None,
        )
        == "/paper/2606.13141"
    )


def test_evaluation_is_external_uses_raw_source_url():
    assert evaluation_is_external(
        "https://arxiv.org/html/2606.13141v1",
        "2411.13093",
        40193,
    )
    assert (
        evaluation_public_source_url("https://arxiv.org/html/2606.13141v1")
        == "/paper/2606.13141"
    )


def test_evaluation_is_external_false_for_same_arxiv_paper():
    assert not evaluation_is_external(
        "https://arxiv.org/abs/2411.13093",
        "2411.13093",
        40193,
    )


class _FakePaper:
    def __init__(
        self,
        paper_id: int,
        *,
        source_url: str | None = None,
        hf_models: list[str] | None = None,
    ):
        self.id = paper_id
        self.source_url = source_url
        self.hf_models = hf_models or []
        self.hf_datasets = []
        self.hf_spaces = []


class _FakeQuery:
    def __init__(self, result):
        self._result = result

    def filter(self, *args, **kwargs):
        return self

    def join(self, *args, **kwargs):
        return self

    def first(self):
        return self._result

    def all(self):
        return []


class _FakeDB:
    def __init__(self, result):
        self._result = result

    def query(self, *args, **kwargs):
        return _FakeQuery(self._result)


def test_evaluation_is_external_false_for_model_card_source():
    model_url = "https://huggingface.co/UsefulSensors/moonshine-streaming-tiny"
    db = _FakeDB(_FakePaper(40193, hf_models=[model_url]))
    assert not evaluation_is_external(
        model_url,
        "2411.13093",
        40193,
        db,
    )


def test_evaluation_is_external_true_for_independent_source():
    db = _FakeDB(_FakePaper(paper_id=40193))
    assert evaluation_is_external(
        "https://example.com/a-competition-page",
        None,
        40193,
        db,
    )


def test_evaluation_is_external_false_when_source_matches_same_paper():
    source_url = "https://example.com/this-paper"
    db = _FakeDB(_FakePaper(paper_id=40193, source_url=source_url))
    assert not evaluation_is_external(
        source_url,
        None,
        40193,
        db,
    )
